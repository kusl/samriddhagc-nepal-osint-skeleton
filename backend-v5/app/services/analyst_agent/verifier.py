"""Web search + cross-reference verification for flagged stories.

Uses duckduckgo-search for web lookup and DB keyword similarity
for cross-referencing against our own story database.
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.story import Story
from app.models.story_cluster import StoryCluster
from app.services.analyst_agent.claude_runner import call_claude_json
from app.services.analyst_agent.prompts import (
    ANALYST_PERSONA,
    VERIFICATION_PROMPT,
    VERIFICATION_VERDICT_SCHEMA,
)

logger = logging.getLogger(__name__)

# Known credible Nepali news sources (for context in verification)
CREDIBLE_NEPALI_SOURCES = {
    "The Kathmandu Post", "Republica", "Kantipur", "Nagarik", "Annapurna Post",
    "Himalayan Times", "Online Khabar", "Setopati", "Ratopati", "Naya Patrika",
    "RSS (Rastriya Samachar Samiti)", "Nepal Television", "BBC Nepali",
    "eKantipur", "Gorkhapatra",
}


class Verifier:
    """Verifies flagged stories using web search and DB cross-reference."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def verify_story(
        self,
        headline: str,
        source_name: str,
        flag_reason: str,
        story_id: Optional[str] = None,
    ) -> dict:
        """Full verification pipeline for a suspicious story.

        1. Web search with multiple query strategies
        2. Cross-reference our DB for related stories
        3. Claude evaluation of evidence

        Returns dict with verdict, confidence, reasoning, evidence.
        """
        # Fetch story details from DB if we have the ID
        summary = ""
        published_at = ""
        confidence_level = "unknown"
        unique_sources = "unknown"
        diversity_score = 0.0
        cluster_id = None

        if story_id:
            story = await self._get_story(story_id)
            if story:
                summary = self._extract_summary(story)
                published_at = story.published_at.isoformat() if story.published_at else "unknown"
                cluster_id = story.cluster_id
                if story.cluster:
                    confidence_level = story.cluster.confidence_level or "unknown"
                    unique_sources = ", ".join(story.cluster.unique_sources or [])
                    diversity_score = story.cluster.diversity_score or 0.0

        # Step 1: Web search with multiple strategies
        web_results = await self._multi_query_search(headline, source_name, summary)

        # Step 2: DB cross-reference
        db_matches = await self._cross_reference_db(headline, story_id)

        # Step 3: Claude evaluation
        prompt = VERIFICATION_PROMPT.format(
            persona=ANALYST_PERSONA,
            headline=headline,
            source_name=source_name,
            published_at=published_at,
            summary=summary or "(no summary available)",
            flag_reason=flag_reason,
            web_results_section=self._format_web_results(web_results),
            db_matches_section=self._format_db_matches(db_matches),
            confidence_level=confidence_level,
            unique_sources=unique_sources,
            diversity_score=diversity_score,
            schema=VERIFICATION_VERDICT_SCHEMA,
        )

        verdict = await call_claude_json(prompt, timeout=120, model="haiku")

        # Attach evidence to the verdict
        verdict["evidence"] = {
            "web_results": web_results,
            "db_matches": [
                {"title": m["title"], "source": m["source"], "similarity": m.get("similarity")}
                for m in db_matches
            ],
        }

        return verdict

    async def _get_story(self, story_id: str) -> Optional[Story]:
        """Fetch a story by ID string."""
        try:
            from uuid import UUID
            result = await self.db.execute(
                select(Story)
                .outerjoin(StoryCluster, Story.cluster_id == StoryCluster.id)
                .where(Story.id == UUID(story_id))
            )
            return result.scalar_one_or_none()
        except (ValueError, TypeError):
            return None

    def _extract_summary(self, story: Story) -> str:
        """Extract summary text from a story."""
        if story.ai_summary:
            return (
                story.ai_summary.get("haiku_summary")
                or story.ai_summary.get("summary")
                or story.ai_summary.get("bluf")
                or ""
            )
        return story.summary or ""

    def _extract_key_claims(self, headline: str, summary: str) -> list[str]:
        """Extract key factual claims from headline and summary for targeted search."""
        queries = []

        # Strategy 1: Use full headline (best for exact-match)
        queries.append(headline)

        # Strategy 2: Extract named entities and numbers (specific claims)
        # Look for numbers, proper nouns, quoted strings
        numbers = re.findall(r'\b\d+[\d,]*\b', headline)
        # Combine headline with "Nepal" for context if not already present
        if "nepal" not in headline.lower() and "नेपाल" not in headline:
            queries.append(f"{headline} Nepal")

        # Strategy 3: If headline contains numbers (casualty claims etc.),
        # search for the specific number + context
        if numbers:
            # Extract words around the number for a focused query
            for num in numbers[:2]:
                idx = headline.find(num)
                # Get surrounding context (30 chars each side)
                start = max(0, idx - 30)
                end = min(len(headline), idx + len(num) + 30)
                snippet = headline[start:end].strip()
                if len(snippet) > 10:
                    queries.append(snippet)

        # Strategy 4: Use summary keywords if headline is too short
        if summary and len(headline) < 30:
            # Take first sentence of summary
            first_sentence = summary.split('.')[0].strip()
            if first_sentence:
                queries.append(first_sentence[:100])

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for q in queries:
            q_lower = q.lower().strip()
            if q_lower not in seen and len(q_lower) > 5:
                seen.add(q_lower)
                unique.append(q)

        return unique[:4]  # Max 4 queries to avoid rate limits

    async def _multi_query_search(
        self, headline: str, source_name: str, summary: str
    ) -> list[dict]:
        """Run multiple search queries for better coverage.

        Uses different query strategies:
        1. Full headline (exact match)
        2. Headline + Nepal context
        3. Key claims extraction
        4. Source-specific search
        """
        queries = self._extract_key_claims(headline, summary)

        # Add source-specific search if source is known
        if source_name and source_name.lower() not in headline.lower():
            queries.append(f'"{source_name}" {headline[:50]}')

        all_results = []
        seen_urls = set()

        for query in queries:
            results = await self._web_search(query, max_results=5)
            for r in results:
                url = r.get("url", "")
                if url not in seen_urls:
                    seen_urls.add(url)
                    # Tag which query found this result
                    r["query_used"] = query[:50]
                    # Tag if from known credible source
                    r["credible_source"] = any(
                        src.lower() in r.get("title", "").lower()
                        or src.lower() in url.lower()
                        for src in CREDIBLE_NEPALI_SOURCES
                    )
                    all_results.append(r)

        # Sort: credible sources first, then by relevance (query order)
        all_results.sort(key=lambda r: (not r.get("credible_source", False)))

        logger.info(
            "Multi-query search for '%s': %d unique results from %d queries",
            headline[:50], len(all_results), len(queries),
        )
        return all_results[:15]  # Cap at 15 results

    async def _web_search(self, query: str, max_results: int = 5) -> list[dict]:
        """Search the web using duckduckgo-search.

        Returns list of {title, url, snippet}.
        """
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    })
            logger.info("Web search for '%s': %d results", query[:50], len(results))
            return results
        except ImportError:
            logger.warning("duckduckgo-search not installed. Skipping web search.")
            return []
        except Exception as e:
            logger.warning("Web search failed for '%s': %s", query[:50], e)
            return []

    async def _cross_reference_db(
        self, headline: str, exclude_story_id: Optional[str] = None,
    ) -> list[dict]:
        """Find related stories in our DB using keyword matching.

        Returns list of {title, source, published_at, summary, similarity}.
        """
        # Use simple keyword matching from headline words
        keywords = [w for w in headline.split() if len(w) > 3][:8]
        if not keywords:
            return []

        # Search for stories with similar titles in the last 7 days
        since = datetime.now(timezone.utc) - timedelta(days=7)
        query = (
            select(Story)
            .where(Story.created_at >= since)
            .order_by(desc(Story.published_at))
            .limit(100)
        )
        result = await self.db.execute(query)
        candidates = result.scalars().all()

        matches = []
        for story in candidates:
            if exclude_story_id and str(story.id) == exclude_story_id:
                continue

            # Simple keyword overlap score
            title_lower = story.title.lower()
            overlap = sum(1 for kw in keywords if kw.lower() in title_lower)
            if overlap >= 2:  # At least 2 keyword matches
                matches.append({
                    "title": story.title,
                    "source": story.source_name or story.source_id,
                    "published_at": story.published_at.isoformat() if story.published_at else None,
                    "summary": self._extract_summary(story),
                    "similarity": overlap / len(keywords),
                })

        # Sort by overlap score
        matches.sort(key=lambda m: m["similarity"], reverse=True)
        return matches[:10]

    def _format_web_results(self, results: list[dict]) -> str:
        if not results:
            return "No web search results found."
        lines = []
        for r in results:
            credible_tag = " [KNOWN CREDIBLE SOURCE]" if r.get("credible_source") else ""
            lines.append(
                f"- {r['title']}{credible_tag}\n"
                f"  URL: {r.get('url', 'N/A')}\n"
                f"  {r['snippet'][:250]}"
            )
        return "\n".join(lines)

    def _format_db_matches(self, matches: list[dict]) -> str:
        if not matches:
            return "No matching stories found in our database."
        lines = []
        for m in matches:
            lines.append(
                f"- {m['title']}\n"
                f"  Source: {m['source']} | Published: {m.get('published_at', 'unknown')}\n"
                f"  Summary: {m.get('summary', 'N/A')[:200]}"
            )
        return "\n".join(lines)
