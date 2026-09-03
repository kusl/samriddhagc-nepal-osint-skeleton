"""Bluesky scraping service — orchestrates scraper → repository → classifier → WebSocket.

Mirrors RedditService so Bluesky posts land in the same `tweets` table and inherit
the existing relevance classification, dedup and realtime broadcast path. This is
the live replacement for NitterService, which has no working backend since the
Nitter network was taken down in August 2026.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.realtime_bus import publish_news
from app.ingestion.bluesky_scraper import BlueskyScraper
from app.ingestion.nitter_scraper import ScrapedTweet
from app.repositories.twitter import TwitterRepository
from app.services.relevance_service import RelevanceService
from app.services.tweet_dedup_service import TweetDedupService

logger = logging.getLogger(__name__)

_SOURCES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "sources.yaml"


def _load_bluesky_config() -> dict:
    try:
        with open(_SOURCES_PATH) as f:
            cfg = yaml.safe_load(f)
        return {
            "bluesky_config": cfg.get("bluesky_config", {}),
            "bluesky_accounts": cfg.get("bluesky_accounts", []),
            "bluesky_discovery": cfg.get("bluesky_discovery", []),
        }
    except Exception as e:
        logger.error(f"Failed to load bluesky config: {e}")
        return {"bluesky_config": {}, "bluesky_accounts": [], "bluesky_discovery": []}


class BlueskyService:
    """Orchestrates Bluesky scraping, storage, classification, and broadcasting."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TwitterRepository(db)
        self.relevance_service = RelevanceService()

        config = _load_bluesky_config()
        self._bluesky_config = config["bluesky_config"]
        self._accounts = config["bluesky_accounts"]
        self._discovery = config["bluesky_discovery"]

    def _create_scraper(self) -> BlueskyScraper:
        return BlueskyScraper(
            request_timeout=self._bluesky_config.get("request_timeout", 30),
            delay_between_requests=self._bluesky_config.get("delay_between_requests", 1.0),
        )

    async def scrape_all_accounts(self) -> dict:
        """Scrape every configured Bluesky account timeline.

        Returns:
            Stats dict with accounts_scraped, posts_fetched, new_posts, errors.
        """
        stats = {
            "accounts_scraped": 0,
            "posts_fetched": 0,
            "new_posts": 0,
            "errors": [],
        }

        if not self._accounts:
            logger.debug("No bluesky accounts configured, skipping")
            return stats

        max_pages = self._bluesky_config.get("max_pages", 2)
        page_limit = self._bluesky_config.get("page_limit", 50)

        async with self._create_scraper() as scraper:
            for account in self._accounts:
                handle = account["handle"]
                category = account.get("category", "news")

                try:
                    result = await scraper.scrape_author_feed(
                        handle, limit=page_limit, max_pages=max_pages
                    )
                    if not result.success:
                        stats["errors"].append(f"@{handle}: {result.error}")
                        continue

                    stats["accounts_scraped"] += 1
                    stats["posts_fetched"] += len(result.tweets)

                    new_count = await self._ingest_tweets(
                        result.tweets,
                        source_query=f"bluesky:{handle}",
                        category=category,
                    )
                    stats["new_posts"] += new_count

                    await asyncio.sleep(scraper.delay_between_requests)

                except Exception as e:
                    logger.exception(f"Error scraping Bluesky @{handle}: {e}")
                    stats["errors"].append(f"@{handle}: {e}")

        return stats

    async def discover_accounts(self) -> List[dict]:
        """Search Bluesky for Nepal-relevant accounts not yet in sources.yaml.

        Read-only: returns candidates for a human to promote into config rather
        than silently widening what we ingest.
        """
        if not self._discovery:
            return []

        known = {a["handle"].lower() for a in self._accounts}
        seen: set[str] = set()
        candidates: List[dict] = []

        async with self._create_scraper() as scraper:
            for term_cfg in self._discovery:
                term = term_cfg["term"] if isinstance(term_cfg, dict) else str(term_cfg)
                try:
                    actors = await scraper.search_actors(term, limit=25)
                except Exception as e:
                    logger.warning(f"Bluesky discovery failed for '{term}': {e}")
                    continue

                for actor in actors:
                    h = actor.handle.lower()
                    if h in known or h in seen:
                        continue
                    seen.add(h)
                    candidates.append(
                        {
                            "handle": actor.handle,
                            "display_name": actor.display_name,
                            "description": actor.description[:200],
                            "matched_term": term,
                        }
                    )

                await asyncio.sleep(scraper.delay_between_requests)

        logger.info(f"Bluesky discovery: {len(candidates)} new candidate accounts")
        return candidates

    async def _ingest_tweets(
        self,
        tweets: List[ScrapedTweet],
        source_query: str,
        category: str,
    ) -> int:
        """Store converted Bluesky posts and run relevance classification.

        Returns:
            Number of newly inserted posts.
        """
        new_count = 0

        for scraped in tweets:
            try:
                db_tweet, created = await self.repo.upsert_tweet(
                    tweet_id=scraped.tweet_id,
                    author_id=scraped.author_username,
                    text=scraped.text,
                    author_username=scraped.author_username,
                    author_name=scraped.author_name,
                    language=scraped.language,
                    is_retweet=scraped.is_retweet,
                    is_reply=scraped.is_reply,
                    is_quote=scraped.is_quote,
                    retweet_count=scraped.retweet_count,
                    reply_count=scraped.reply_count,
                    like_count=scraped.like_count,
                    quote_count=scraped.quote_count,
                    hashtags=scraped.hashtags,
                    mentions=scraped.mentions,
                    urls=scraped.urls,
                    media_urls=scraped.media_urls,
                    tweeted_at=scraped.tweeted_at,
                    fetched_at=datetime.now(timezone.utc),
                    source_query=source_query,
                )

                if not created:
                    continue

                new_count += 1

                try:
                    result = self.relevance_service.classify(
                        title=scraped.text[:200],
                        content=scraped.text,
                        source_id=f"bluesky_{source_query}",
                    )

                    nepal_relevance = result.level.value
                    relevance_score = result.score
                    is_relevant = result.score >= 0.3
                    classified_category = (
                        result.category.value if result.category else category
                    )

                    await self.repo.mark_processed(
                        tweet_id=db_tweet.id,
                        nepal_relevance=nepal_relevance,
                        category=classified_category,
                        is_relevant=is_relevant,
                        relevance_score=relevance_score,
                    )

                    if is_relevant:
                        await publish_news(
                            {
                                "type": "new_tweet",
                                "source": "bluesky",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "data": {
                                    "tweet_id": scraped.tweet_id,
                                    "author": scraped.author_username,
                                    "text": scraped.text[:280],
                                    "category": classified_category,
                                    "relevance": nepal_relevance,
                                },
                            }
                        )

                except Exception as e:
                    logger.warning(
                        f"Classification failed for bluesky post {scraped.tweet_id}: {e}"
                    )

                try:
                    dedup_service = TweetDedupService(self.db)
                    await dedup_service.on_ingest(db_tweet)
                except Exception as e:
                    logger.warning(
                        f"Dedup failed for bluesky post {scraped.tweet_id}: {e}"
                    )

            except Exception as e:
                logger.warning(f"Failed to store bluesky post {scraped.tweet_id}: {e}")

        return new_count
