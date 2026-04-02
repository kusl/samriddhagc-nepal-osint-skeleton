"""LLM-based cluster validation using OpenAI or a safe fallback."""
import json
import logging
from dataclasses import dataclass
from typing import List, Optional

from app.services.openai_runtime import get_openai_runtime

logger = logging.getLogger(__name__)

CLUSTER_VALIDATION_SYSTEM = """You are a news clustering assistant. Your job is to determine if news headlines are about the SAME specific event or topic.

Rules:
1. Headlines must be about the SAME specific event, not just related topics
2. "Election news" is NOT a valid cluster - each specific political event should be separate
3. "Sports news" is NOT a valid cluster - each match/tournament should be separate
4. Weather in different locations should NOT cluster together
5. Different political statements from different people should NOT cluster
6. Stories from different countries should NEVER cluster together

Output ONLY valid JSON, no other text."""


@dataclass
class ClusterValidation:
    """Result of cluster validation."""
    is_valid: bool
    confidence: float  # 0.0 to 1.0
    reason: str
    suggested_groups: Optional[List[List[int]]] = None  # Indices of stories that should be together


class LLMClusterValidator:
    """
    Validates story clusters using OpenAI structured output.
    """

    def __init__(self) -> None:
        self.openai_runtime = get_openai_runtime()

    def _get_headers(self) -> dict:
        """Get HTTP headers for API requests."""
        return {}

    async def validate_cluster(
        self,
        titles: List[str],
        category: Optional[str] = None,
    ) -> ClusterValidation:
        """
        Validate if a set of headlines should be clustered together.

        Args:
            titles: List of news headlines
            category: Optional category hint

        Returns:
            ClusterValidation result
        """
        if not self.openai_runtime.clustering_enabled:
            # Fallback: assume valid if we can't validate
            return ClusterValidation(
                is_valid=True,
                confidence=0.0,
                reason="LLM validation disabled (OpenAI unavailable)",
            )

        if len(titles) < 2:
            return ClusterValidation(
                is_valid=False,
                confidence=1.0,
                reason="Need at least 2 stories for a cluster",
            )

        # Limit titles to avoid token limits
        titles_to_check = titles[:10]

        # Build prompt
        titles_text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles_to_check))

        user_prompt = f"""Are these {len(titles_to_check)} headlines about the SAME specific event?

Headlines:
{titles_text}

Return strict JSON with:
- is_same_event: boolean
- confidence: number from 0 to 1
- reason: short explanation
- groups: arrays of 1-based headline numbers that belong together

If they are not all about the same event, split them into the most precise groups possible.
Different death counts, different places, different speakers, and different incidents should be split."""

        try:
            result = await self.openai_runtime.json_completion(
                system_prompt=CLUSTER_VALIDATION_SYSTEM,
                user_prompt=user_prompt,
                schema_name="cluster_validation",
                schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "is_same_event": {"type": "boolean"},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                        "groups": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                        },
                    },
                    "required": ["is_same_event", "confidence", "reason", "groups"],
                },
                model=self.openai_runtime.settings.openai_clustering_model,
                max_completion_tokens=220,
                cache_scope="cluster-validation",
                usage_bucket="structured",
            )

            suggested_groups = None
            if not result.get("is_same_event") and "groups" in result:
                groups = result["groups"]
                if groups and isinstance(groups[0], list):
                    suggested_groups = [[i - 1 for i in g if 1 <= i <= len(titles_to_check)] for g in groups]

            return ClusterValidation(
                is_valid=result.get("is_same_event", True),
                confidence=float(result.get("confidence", 0.5)),
                reason=result.get("reason", ""),
                suggested_groups=suggested_groups,
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse LLM validation response")
            return ClusterValidation(
                is_valid=True,
                confidence=0.0,
                reason=f"Parse error: {str(e)}",
            )
        except Exception as e:
            logger.error(f"LLM validation exception: {e}")
            return ClusterValidation(
                is_valid=True,
                confidence=0.0,
                reason=f"Exception: {str(e)}",
            )

    async def split_cluster(
        self,
        titles: List[str],
        story_ids: List[str],
    ) -> List[List[str]]:
        """
        Use LLM to split a mixed cluster into valid sub-clusters.

        Args:
            titles: List of headlines
            story_ids: List of story IDs (parallel to titles)

        Returns:
            List of ID groups that should be clustered together
        """
        if len(titles) < 2:
            return [story_ids]

        validation = await self.validate_cluster(titles)

        if validation.is_valid:
            return [story_ids]

        if validation.suggested_groups:
            # Convert indices to story IDs
            result_groups = []
            for group in validation.suggested_groups:
                if len(group) >= 2:  # Only keep groups with 2+ stories
                    result_groups.append([story_ids[i] for i in group if i < len(story_ids)])
            return result_groups if result_groups else []

        # No suggested groups - return empty (don't cluster)
        return []


# Singleton instance
_validator_instance: Optional[LLMClusterValidator] = None


def get_llm_validator() -> LLMClusterValidator:
    """Get the global LLMClusterValidator singleton."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = LLMClusterValidator()
    return _validator_instance
