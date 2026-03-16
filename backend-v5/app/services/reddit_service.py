"""Reddit scraping service — orchestrates scraper → repository → classifier → WebSocket."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.reddit_scraper import RedditScraper, ScrapedRedditPost
from app.ingestion.nitter_scraper import ScrapedTweet
from app.repositories.twitter import TwitterRepository
from app.services.relevance_service import RelevanceService
from app.services.tweet_dedup_service import TweetDedupService
from app.core.realtime_bus import publish_news

logger = logging.getLogger(__name__)

_SOURCES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "sources.yaml"


def _load_reddit_config() -> dict:
    try:
        with open(_SOURCES_PATH) as f:
            cfg = yaml.safe_load(f)
        return {
            "reddit_config": cfg.get("reddit_config", {}),
            "reddit_subreddits": cfg.get("reddit_subreddits", []),
            "reddit_searches": cfg.get("reddit_searches", []),
        }
    except Exception as e:
        logger.error(f"Failed to load reddit config: {e}")
        return {"reddit_config": {}, "reddit_subreddits": [], "reddit_searches": []}


class RedditService:
    """Orchestrates Reddit scraping, storage, classification, and broadcasting."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TwitterRepository(db)
        self.relevance_service = RelevanceService()

        config = _load_reddit_config()
        self._reddit_config = config["reddit_config"]
        self._subreddits = config["reddit_subreddits"]
        self._searches = config["reddit_searches"]

    def _create_scraper(self) -> RedditScraper:
        return RedditScraper(
            request_timeout=self._reddit_config.get("request_timeout", 30),
            delay_between_requests=self._reddit_config.get("delay_between_requests", 2.0),
        )

    async def scrape_all(self) -> dict:
        """Scrape all configured subreddits and search queries.

        Returns:
            Stats dict with subreddits_scraped, searches_scraped, posts_fetched, new_posts, errors.
        """
        stats = {
            "subreddits_scraped": 0,
            "searches_scraped": 0,
            "posts_fetched": 0,
            "new_posts": 0,
            "errors": [],
        }

        if not self._subreddits and not self._searches:
            logger.debug("No reddit sources configured, skipping")
            return stats

        scraper = self._create_scraper()
        seen_post_ids: set = set()

        async with scraper:
            # Scrape subreddits
            for sub_cfg in self._subreddits:
                subreddit = sub_cfg["subreddit"]
                sort = sub_cfg.get("sort", "new")
                limit = sub_cfg.get("limit", 25)
                category = sub_cfg.get("category", "general")
                source_query = f"reddit:r/{subreddit}"

                try:
                    result = await scraper.scrape_subreddit(
                        subreddit=subreddit,
                        sort=sort,
                        limit=limit,
                    )
                    if not result.success:
                        stats["errors"].append(f"r/{subreddit}: {result.error}")
                        continue

                    stats["subreddits_scraped"] += 1

                    # Dedup across subreddits
                    new_posts = [p for p in result.posts if p.post_id not in seen_post_ids]
                    for p in new_posts:
                        seen_post_ids.add(p.post_id)

                    stats["posts_fetched"] += len(new_posts)

                    if new_posts:
                        tweets = [RedditScraper.post_to_scraped_tweet(p, source_query) for p in new_posts]
                        new_count = await self._ingest_tweets(tweets, source_query, category)
                        stats["new_posts"] += new_count

                    await asyncio.sleep(scraper.delay_between_requests)

                except Exception as e:
                    logger.exception(f"Error scraping r/{subreddit}: {e}")
                    stats["errors"].append(f"r/{subreddit}: {e}")

            # Scrape search queries
            for search_cfg in self._searches:
                query = search_cfg["query"]
                category = search_cfg.get("category", "general")
                source_query = f"reddit:search:{query}"

                try:
                    result = await scraper.scrape_search(
                        query=query,
                        sort="new",
                        limit=25,
                        time_filter="day",
                    )
                    if not result.success:
                        stats["errors"].append(f"search '{query}': {result.error}")
                        continue

                    stats["searches_scraped"] += 1

                    new_posts = [p for p in result.posts if p.post_id not in seen_post_ids]
                    for p in new_posts:
                        seen_post_ids.add(p.post_id)

                    stats["posts_fetched"] += len(new_posts)

                    if new_posts:
                        tweets = [RedditScraper.post_to_scraped_tweet(p, source_query) for p in new_posts]
                        new_count = await self._ingest_tweets(tweets, source_query, category)
                        stats["new_posts"] += new_count

                    await asyncio.sleep(scraper.delay_between_requests)

                except Exception as e:
                    logger.exception(f"Error searching Reddit '{query}': {e}")
                    stats["errors"].append(f"search '{query}': {e}")

        return stats

    async def _ingest_tweets(
        self,
        tweets: List[ScrapedTweet],
        source_query: str,
        category: str,
    ) -> int:
        """Store converted Reddit posts and run relevance classification.

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

                # Classify relevance
                try:
                    result = self.relevance_service.classify(
                        title=scraped.text[:200],
                        content=scraped.text,
                        source_id=f"reddit_{source_query}",
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
                                "source": "reddit",
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
                    logger.warning(f"Classification failed for reddit post {scraped.tweet_id}: {e}")

                # Run dedup
                try:
                    dedup_service = TweetDedupService(self.db)
                    await dedup_service.on_ingest(db_tweet)
                except Exception as e:
                    logger.warning(f"Dedup failed for reddit post {scraped.tweet_id}: {e}")

            except Exception as e:
                logger.warning(f"Failed to store reddit post {scraped.tweet_id}: {e}")

        return new_count
