"""Reddit scraper for Nepal-related subreddits.

Uses Reddit's public JSON API (no authentication required).
Converts Reddit posts to ScrapedTweet format for unified ingestion
through the existing /twitter/ingest pipeline.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp

from app.ingestion.nitter_scraper import ScrapedTweet

logger = logging.getLogger(__name__)


@dataclass
class ScrapedRedditPost:
    """A post scraped from Reddit's public JSON API."""

    post_id: str
    author_username: str
    author_name: str  # same as username for Reddit
    text: str  # title + selftext combined
    subreddit: str
    score: int
    num_comments: int
    created_utc: datetime
    url: str
    is_self: bool  # selftext post vs link post
    flair: Optional[str] = None
    language: str = "en"


@dataclass
class RedditScrapeResult:
    """Result of a Reddit scrape operation."""

    success: bool
    posts: List[ScrapedRedditPost] = field(default_factory=list)
    subreddit: str = ""
    error: Optional[str] = None
    scrape_duration_ms: int = 0


class RedditScraper:
    """Scrapes Reddit's public JSON API for Nepal-related content.

    Reddit returns JSON natively when .json is appended to any URL.
    Rate limit: ~60 requests/minute for unauthenticated access.
    We add a configurable delay between requests to stay well under the limit.
    """

    BASE_URL = "https://www.reddit.com"
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Devanagari Unicode range for language detection
    DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

    def __init__(
        self,
        request_timeout: int = 30,
        delay_between_requests: float = 2.0,
    ):
        self.request_timeout = request_timeout
        self.delay_between_requests = delay_between_requests
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.request_timeout),
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            self._session = None

    def _detect_language(self, text: str) -> str:
        """Detect language: Devanagari chars -> 'ne', else 'en'."""
        devanagari_count = len(self.DEVANAGARI_RE.findall(text))
        if devanagari_count >= 3:
            return "ne"
        return "en"

    def _parse_post(self, post_data: dict) -> Optional[ScrapedRedditPost]:
        """Parse a Reddit JSON post object into ScrapedRedditPost.

        Args:
            post_data: A child object from Reddit's listing JSON.
                       The actual data is in post_data["data"].

        Returns:
            ScrapedRedditPost or None if parsing fails.
        """
        try:
            data = post_data.get("data", post_data)

            post_id = data.get("id", "")
            if not post_id:
                return None

            author = data.get("author", "[deleted]")
            if author in ("[deleted]", "[removed]", "AutoModerator"):
                return None

            title = data.get("title", "").strip()
            selftext = data.get("selftext", "").strip()
            is_self = data.get("is_self", False)

            # Combine title + selftext for self posts, just title for link posts
            if is_self and selftext:
                # Truncate selftext to keep combined text manageable
                max_selftext = 500 - len(title) - 3  # 3 for " | "
                if max_selftext > 0 and len(selftext) > max_selftext:
                    selftext = selftext[:max_selftext] + "..."
                text = f"{title} | {selftext}" if selftext else title
            else:
                text = title

            if not text:
                return None

            subreddit = data.get("subreddit", "")
            score = data.get("score", 0)
            num_comments = data.get("num_comments", 0)

            # created_utc is a Unix timestamp (float)
            created_utc_ts = data.get("created_utc", 0)
            if created_utc_ts:
                created_utc = datetime.fromtimestamp(created_utc_ts, tz=timezone.utc)
            else:
                created_utc = datetime.now(timezone.utc)

            url = data.get("url", "")
            # For self posts, use the permalink as URL
            if is_self:
                permalink = data.get("permalink", "")
                if permalink:
                    url = f"https://www.reddit.com{permalink}"

            flair = data.get("link_flair_text")

            language = self._detect_language(text)

            return ScrapedRedditPost(
                post_id=post_id,
                author_username=author,
                author_name=author,
                text=text,
                subreddit=subreddit,
                score=score,
                num_comments=num_comments,
                created_utc=created_utc,
                url=url,
                is_self=is_self,
                flair=flair,
                language=language,
            )

        except Exception as e:
            logger.debug("Failed to parse Reddit post: %s", e)
            return None

    async def _fetch_json(self, url: str) -> Optional[dict]:
        """Fetch JSON from a Reddit URL with error handling.

        Returns:
            Parsed JSON dict on success, None on failure.
        """
        if not self._session:
            raise RuntimeError("RedditScraper must be used as async context manager")

        try:
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()

                if resp.status == 429:
                    # Rate limited -- back off significantly
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    logger.warning(
                        "Reddit rate limited (429), waiting %ds...", retry_after
                    )
                    await asyncio.sleep(retry_after)
                    return None

                if resp.status == 403:
                    logger.warning(
                        "Reddit returned 403 Forbidden for %s (possibly blocked)", url
                    )
                    return None

                if resp.status == 404:
                    logger.warning("Reddit returned 404 for %s", url)
                    return None

                logger.warning(
                    "Unexpected status %d from Reddit: %s", resp.status, url
                )
                return None

        except asyncio.TimeoutError:
            logger.warning("Timeout fetching %s", url)
            return None
        except aiohttp.ClientError as e:
            logger.warning("HTTP error fetching %s: %s", url, e)
            return None
        except Exception as e:
            logger.warning("Unexpected error fetching %s: %s", url, e)
            return None

    async def scrape_subreddit(
        self,
        subreddit: str,
        sort: str = "new",
        limit: int = 25,
        time_filter: str = "day",
    ) -> RedditScrapeResult:
        """Scrape posts from a subreddit.

        Uses: https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&t={time_filter}

        Args:
            subreddit: Subreddit name (without r/ prefix).
            sort: Sort order -- "new", "hot", "top", "rising".
            limit: Number of posts to fetch (max 100).
            time_filter: Time filter for "top" sort -- "hour", "day", "week", "month", "year", "all".

        Returns:
            RedditScrapeResult with scraped posts.
        """
        t0 = time.monotonic()

        url = f"{self.BASE_URL}/r/{subreddit}/{sort}.json?limit={limit}&raw_json=1"
        if sort == "top":
            url += f"&t={time_filter}"

        logger.debug("Fetching r/%s (%s): %s", subreddit, sort, url)
        data = await self._fetch_json(url)

        if data is None:
            elapsed = int((time.monotonic() - t0) * 1000)
            return RedditScrapeResult(
                success=False,
                subreddit=subreddit,
                error=f"Failed to fetch r/{subreddit}",
                scrape_duration_ms=elapsed,
            )

        posts = []
        seen_ids: set = set()

        children = data.get("data", {}).get("children", [])
        for child in children:
            post = self._parse_post(child)
            if post and post.post_id not in seen_ids:
                seen_ids.add(post.post_id)
                posts.append(post)

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info(
            "Scraped %d posts from r/%s (%s) in %dms",
            len(posts), subreddit, sort, elapsed,
        )

        return RedditScrapeResult(
            success=True,
            posts=posts,
            subreddit=subreddit,
            scrape_duration_ms=elapsed,
        )

    async def scrape_search(
        self,
        query: str,
        subreddit: Optional[str] = None,
        sort: str = "relevance",
        limit: int = 25,
        time_filter: str = "day",
    ) -> RedditScrapeResult:
        """Search Reddit for a query, optionally within a specific subreddit.

        Uses:
            Global: https://www.reddit.com/search.json?q={query}&sort={sort}&limit={limit}&t={time_filter}
            Subreddit: https://www.reddit.com/r/{subreddit}/search.json?q={query}&restrict_sr=on&sort={sort}&limit={limit}&t={time_filter}

        Args:
            query: Search query string.
            subreddit: Optional subreddit to restrict search to.
            sort: Sort order -- "relevance", "new", "hot", "top", "comments".
            limit: Number of results (max 100).
            time_filter: Time filter -- "hour", "day", "week", "month", "year", "all".

        Returns:
            RedditScrapeResult with search results.
        """
        t0 = time.monotonic()

        # URL-encode query
        from urllib.parse import quote

        encoded_query = quote(query)

        if subreddit:
            url = (
                f"{self.BASE_URL}/r/{subreddit}/search.json"
                f"?q={encoded_query}&restrict_sr=on&sort={sort}"
                f"&limit={limit}&t={time_filter}&raw_json=1"
            )
            label = f"r/{subreddit} search '{query}'"
        else:
            url = (
                f"{self.BASE_URL}/search.json"
                f"?q={encoded_query}&sort={sort}"
                f"&limit={limit}&t={time_filter}&raw_json=1"
            )
            label = f"search '{query}'"

        logger.debug("Searching Reddit: %s", label)
        data = await self._fetch_json(url)

        if data is None:
            elapsed = int((time.monotonic() - t0) * 1000)
            return RedditScrapeResult(
                success=False,
                subreddit=subreddit or "",
                error=f"Failed to search: {label}",
                scrape_duration_ms=elapsed,
            )

        posts = []
        seen_ids: set = set()

        children = data.get("data", {}).get("children", [])
        for child in children:
            post = self._parse_post(child)
            if post and post.post_id not in seen_ids:
                seen_ids.add(post.post_id)
                posts.append(post)

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info(
            "Search '%s': %d posts in %dms", label, len(posts), elapsed
        )

        return RedditScrapeResult(
            success=True,
            posts=posts,
            subreddit=subreddit or "",
            scrape_duration_ms=elapsed,
        )

    @staticmethod
    def post_to_scraped_tweet(
        post: ScrapedRedditPost,
        source_query: str = "",
    ) -> ScrapedTweet:
        """Convert a ScrapedRedditPost to ScrapedTweet format for unified ingestion.

        Maps Reddit fields to tweet fields:
          - tweet_id: "reddit_{post_id}" to avoid collision with Twitter IDs
          - author_username: "reddit:{username}" to distinguish from Twitter users
          - text: "[r/{subreddit}] {text}" (truncated to 500 chars)
          - like_count: Reddit score
          - reply_count: num_comments
          - hashtags: extracted from subreddit name and flair

        Args:
            post: ScrapedRedditPost to convert.
            source_query: Source tag like "reddit:r/NepalStock".

        Returns:
            ScrapedTweet instance ready for ingestion.
        """
        # Build display text with subreddit context
        display_text = f"[r/{post.subreddit}] {post.text}"
        if len(display_text) > 500:
            display_text = display_text[:497] + "..."

        # Extract hashtag-like tags from subreddit and flair
        hashtags = [post.subreddit]
        if post.flair:
            # Clean flair text into a tag
            flair_tag = post.flair.strip().replace(" ", "_")
            if flair_tag:
                hashtags.append(flair_tag)

        # Extract any URLs from the post (for link posts, the URL is the content)
        urls = []
        if not post.is_self and post.url and not post.url.startswith("https://www.reddit.com"):
            urls.append(post.url)

        return ScrapedTweet(
            tweet_id=f"reddit_{post.post_id}",
            author_username=f"reddit:{post.author_username}",
            author_name=post.author_name,
            text=display_text,
            tweeted_at=post.created_utc,
            is_retweet=False,
            is_reply=False,
            is_quote=False,
            retweet_count=0,
            reply_count=post.num_comments,
            like_count=post.score,
            quote_count=0,
            hashtags=hashtags,
            mentions=[],
            urls=urls,
            media_urls=[],
            language=post.language,
        )
