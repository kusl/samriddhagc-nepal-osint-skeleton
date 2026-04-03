"""Efficient OpenAI embedding-based story category classifier."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from app.config import get_settings
from app.services.openai_runtime import get_openai_runtime


@dataclass
class OpenAIStoryClassificationResult:
    category: str
    confidence: float
    scores: dict[str, float]
    embedding: list[float]


class OpenAIStoryClassifier:
    """Classify Nepal-relevant stories with a single embedding call."""

    CATEGORY_PROTOTYPES: dict[str, list[str]] = {
        "political": [
            "Nepal politics, parliament, cabinet, ministers, elections, parties, constitutional decisions, diplomacy.",
            "Government reshuffle, parliament session, political coalition, ministry decision, federal governance in Nepal.",
            "Prime minister, party leadership, parliamentary bill, cabinet meeting, mayor and minister political dispute.",
        ],
        "economic": [
            "Nepal economy, market prices, trade, remittance, tourism, banking, fiscal policy, NEPSE, hydropower investment.",
            "Budget, tax, inflation, jobs, exports, imports, central bank, rupee, agriculture market, business regulation.",
            "Economic growth, fuel prices, electricity, industry, company, investment, foreign exchange, employment in Nepal.",
        ],
        "security": [
            "Nepal police, army, border security, arrests, crime, smuggling, corruption raids, violence, cybercrime, intelligence.",
            "Law enforcement, detention, trafficking, murder, attack, armed group, customs seizure, investigation, security operation.",
            "Public order, police action, border incident, criminal network, security threat, defense or intelligence issue in Nepal.",
        ],
        "disaster": [
            "Flood, landslide, earthquake, forest fire, heavy rain, rescue, casualties, emergency response, disaster warning in Nepal.",
            "Natural disaster, river warning, fire outbreak, road accident, storm damage, relief operation, evacuation, hazard alert.",
            "Disaster incident, emergency management, weather hazard, fatalities, injuries, damage assessment, rescue teams in Nepal.",
        ],
        "social": [
            "Nepal society, protest, strike, education, health, hospital, student issue, culture, religion, rights, pollution, community issue.",
            "Public services, school, university, social movement, civic unrest, festival, welfare, environment, local society problem.",
            "Demonstration, healthcare, social justice, community conflict, municipal service issue, human rights, local public grievance.",
        ],
    }

    def __init__(self):
        self.settings = get_settings()
        self.openai = get_openai_runtime()
        self._prototype_vectors: Optional[dict[str, np.ndarray]] = None

    @property
    def enabled(self) -> bool:
        return (
            self.openai.embeddings_enabled
            and bool(self.settings.openai_story_classification_enabled)
        )

    @staticmethod
    def _normalize(vector: list[float] | np.ndarray) -> np.ndarray:
        arr = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(arr))
        if norm <= 1e-12:
            return arr
        return arr / norm

    async def _get_prototype_vectors(self) -> dict[str, np.ndarray]:
        if self._prototype_vectors is not None:
            return self._prototype_vectors

        ordered: list[tuple[str, str]] = []
        for category, texts in self.CATEGORY_PROTOTYPES.items():
            for text in texts:
                ordered.append((category, text))

        vectors = await self.openai.embed_texts(
            [text for _, text in ordered],
            model=self.settings.openai_embedding_model,
            dimensions=self.settings.openai_embedding_dimensions,
            user_scope="story-category-prototypes",
        )

        grouped: dict[str, list[np.ndarray]] = {category: [] for category in self.CATEGORY_PROTOTYPES}
        for idx, (category, _) in enumerate(ordered):
            grouped[category].append(self._normalize(vectors[idx]))

        self._prototype_vectors = {
            category: self._normalize(np.mean(category_vectors, axis=0))
            for category, category_vectors in grouped.items()
            if category_vectors
        }
        return self._prototype_vectors

    async def classify(
        self,
        *,
        title: str,
        summary: Optional[str] = None,
    ) -> Optional[OpenAIStoryClassificationResult]:
        if not self.enabled:
            return None

        text = " ".join(part.strip() for part in [title or "", summary or ""] if part and part.strip())
        if not text:
            return None

        vectors = await self.openai.embed_texts(
            [text],
            model=self.settings.openai_embedding_model,
            dimensions=self.settings.openai_embedding_dimensions,
            user_scope="story-category-classifier",
        )
        embedding = vectors[0] if vectors else []
        if not embedding:
            return None

        story_vector = self._normalize(embedding)
        prototypes = await self._get_prototype_vectors()
        if not prototypes:
            return None

        scores = {
            category: float(np.dot(story_vector, prototype))
            for category, prototype in prototypes.items()
        }
        ordered_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_category, top_score = ordered_scores[0]
        second_score = ordered_scores[1][1] if len(ordered_scores) > 1 else -1.0
        margin = max(0.0, top_score - second_score)

        # Confidence balances absolute match quality and separation from the next-best category.
        absolute_component = max(0.0, min(1.0, (top_score + 1.0) / 2.0))
        margin_component = max(0.0, min(1.0, margin / 0.12))
        confidence = max(0.0, min(1.0, (absolute_component * 0.65) + (margin_component * 0.35)))

        return OpenAIStoryClassificationResult(
            category=top_category,
            confidence=confidence,
            scores=scores,
            embedding=embedding,
        )
