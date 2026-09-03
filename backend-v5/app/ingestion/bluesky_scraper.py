"""Bluesky (AT Protocol) scraper — a keyless replacement for the retired Nitter network.

Nitter went dark in late August 2026 after X Corp. served cease-and-desist notices
on the instances and the upstream project, so `nitter_scraper` has no working
backend left. Bluesky's public AppView answers `app.bsky.feed.getAuthorFeed` and
`app.bsky.actor.searchActors` with no API key and no account, which gives us back a
post-shaped social feed we can ingest through the existing tweet pipeline.

Note: `app.bsky.feed.searchPosts` is NOT usable here — the public AppView returns
403 for it — so discovery goes through `searchActors` and collection through
per-account timelines.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import quote

import aiohttp

from app.ingestion.nitter_scraper import ScrapedTweet

logger = logging.getLogger(__name__)

PUBLIC_APPVIEW = "https://public.api.bsky.app/xrpc"


@dataclass
class BlueskyActor:
    """A Bluesky account surfaced by actor search."""

    handle: str
    did: str
    display_name: str = ""
    description: str = ""


@dataclass
class BlueskyScrapeResult:
    """Result of a Bluesky scrape operation."""

    success: bool
    tweets: List[ScrapedTweet] = field(default_factory=list)
    error: Optional[str] = None
    scrape_duration_ms: int = 0


class BlueskyScraper:
    """Async Bluesky public-AppView client, keyless and unauthenticated."""

    DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")

    # at://did:plc:xxx/app.bsky.feed.post/<rkey>
    RKEY_RE = re.compile(r"/app\.bsky\.feed\.post/([A-Za-z0-9]+)$")

    def __init__(
        self,
        request_timeout: int = 30,
        delay_between_requests: float = 1.0,
        base_url: str = PUBLIC_APPVIEW,
    ):
        self.request_timeout = request_timeout
        self.delay_between_requests = delay_between_requests
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.request_timeout),
            headers={
                # The public AppView 403s requests with no browser-ish UA.
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            self._session = None

    async def _get_json(self, path: str) -> Optional[dict]:
        """GET an XRPC endpoint, returning parsed JSON or None on any failure."""
        url = f"{self.base_url}/{path}"
        try:
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                if resp.status == 429:
                    logger.warning("Bluesky rate limited (429), backing off 30s")
                    await asyncio.sleep(30)
                    return None
                body = (await resp.text())[:200]
                logger.warning(f"Bluesky {resp.status} for {path}: {body}")
                return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching Bluesky {path}")
            return None
        except aiohttp.ClientError as e:
            logger.warning(f"HTTP error fetching Bluesky {path}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to parse Bluesky response for {path}: {e}")
            return None

    def _detect_language(self, text: str) -> str:
        """Detect language from script, not the post's self-declared `langs`.

        Nepali outlets on Bluesky routinely tag Devanagari posts as `en`, so the
        record's own language field cannot be trusted.
        """
        return "ne" if len(self.DEVANAGARI_RE.findall(text)) >= 3 else "en"

    @staticmethod
    def _facet_values(record: dict) -> tuple[List[str], List[str], List[str]]:
        """Pull hashtags, mentions and links out of a post's richtext facets."""
        hashtags: List[str] = []
        mentions: List[str] = []
        urls: List[str] = []
        for facet in record.get("facets") or []:
            for feature in facet.get("features") or []:
                ftype = feature.get("$type", "")
                if ftype.endswith("#tag") and feature.get("tag"):
                    hashtags.append(feature["tag"].lstrip("#"))
                elif ftype.endswith("#mention") and feature.get("did"):
                    mentions.append(feature["did"])
                elif ftype.endswith("#link") and feature.get("uri"):
                    urls.append(feature["uri"])
        return hashtags, mentions, urls

    @staticmethod
    def _embed_media(post: dict) -> tuple[List[str], List[str]]:
        """Extract media URLs and any external link from a post's hydrated embed."""
        media: List[str] = []
        links: List[str] = []
        embed = post.get("embed") or {}

        def _harvest(node: dict, depth: int = 0) -> None:
            if not node or not isinstance(node, dict) or depth > 3:
                return
            for img in node.get("images") or []:
                src = img.get("fullsize") or img.get("thumb")
                if src:
                    media.append(src)
            external = node.get("external") or {}
            if external.get("uri"):
                links.append(external["uri"])
            if external.get("thumb"):
                media.append(external["thumb"])
            playlist = (node.get("video") or {}).get("playlist") if node.get("video") else None
            if playlist:
                media.append(playlist)
            if node.get("playlist"):
                media.append(node["playlist"])
            # Quoted posts nest their own media under `media`
            nested = node.get("media")
            if isinstance(nested, dict) and nested is not node:
                _harvest(nested, depth + 1)

        _harvest(embed)
        return media, links

    def post_to_scraped_tweet(
        self, item: dict, source_query: str = ""
    ) -> Optional[ScrapedTweet]:
        """Convert one `getAuthorFeed` item into the shared ScrapedTweet shape.

        Field mapping mirrors `RedditScraper.post_to_scraped_tweet` so Bluesky
        posts flow through the same repository, classifier and dedup path:
          - tweet_id:        "bsky_{rkey}"       (namespaced, no ID collisions)
          - author_username: "bsky:{handle}"     (distinguishes from X handles)
          - like_count:      likeCount
          - retweet_count:   repostCount
        """
        post = item.get("post") or {}
        record = post.get("record") or {}
        author = post.get("author") or {}

        text = (record.get("text") or "").strip()
        if not text:
            return None

        uri = post.get("uri") or ""
        rkey_match = self.RKEY_RE.search(uri)
        if not rkey_match:
            return None
        tweet_id = f"bsky_{rkey_match.group(1)}"

        handle = author.get("handle") or "unknown"
        display_name = author.get("displayName") or handle

        tweeted_at = None
        raw_created = record.get("createdAt") or post.get("indexedAt")
        if raw_created:
            try:
                tweeted_at = datetime.fromisoformat(
                    raw_created.replace("Z", "+00:00")
                ).astimezone(timezone.utc)
            except (ValueError, TypeError):
                tweeted_at = None

        hashtags, mentions, urls = self._facet_values(record)
        media_urls, embed_links = self._embed_media(post)
        for link in embed_links:
            if link not in urls:
                urls.append(link)

        # A repost carries a `reason` on the feed item, not on the post itself.
        reason_type = (item.get("reason") or {}).get("$type", "")
        is_repost = reason_type.endswith("#reasonRepost")
        embed_type = (record.get("embed") or {}).get("$type", "")
        is_quote = "app.bsky.embed.record" in embed_type

        return ScrapedTweet(
            tweet_id=tweet_id,
            author_username=f"bsky:{handle}",
            author_name=display_name,
            text=text[:500],
            tweeted_at=tweeted_at,
            is_retweet=is_repost,
            is_reply=bool(record.get("reply")),
            is_quote=is_quote,
            retweet_count=int(post.get("repostCount") or 0),
            reply_count=int(post.get("replyCount") or 0),
            like_count=int(post.get("likeCount") or 0),
            quote_count=int(post.get("quoteCount") or 0),
            hashtags=hashtags,
            mentions=mentions,
            urls=urls,
            media_urls=media_urls,
            language=self._detect_language(text),
        )

    async def scrape_author_feed(
        self, handle: str, limit: int = 50, max_pages: int = 2
    ) -> BlueskyScrapeResult:
        """Fetch a Bluesky account's recent posts, paginating by cursor."""
        t0 = time.monotonic()
        collected: List[ScrapedTweet] = []
        seen: set[str] = set()
        cursor: Optional[str] = None
        source_query = f"bluesky:{handle}"

        for page in range(max_pages):
            path = (
                f"app.bsky.feed.getAuthorFeed?actor={quote(handle)}"
                f"&limit={limit}&filter=posts_no_replies"
            )
            if cursor:
                path += f"&cursor={quote(cursor)}"

            data = await self._get_json(path)
            if data is None:
                if page == 0:
                    return BlueskyScrapeResult(
                        success=False,
                        error=f"Bluesky feed fetch failed for @{handle}",
                        scrape_duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                break  # partial success — keep what we already have

            feed = data.get("feed") or []
            new_on_page = 0
            convert_errors = 0
            for item in feed:
                try:
                    tweet = self.post_to_scraped_tweet(item, source_query)
                except Exception as e:
                    convert_errors += 1
                    logger.warning(f"Failed to convert Bluesky post from @{handle}: {e}")
                    continue
                if tweet and tweet.tweet_id not in seen:
                    seen.add(tweet.tweet_id)
                    collected.append(tweet)
                    new_on_page += 1

            # Every post on a non-empty page failing to convert is a code fault,
            # not an empty feed — do not report it as a clean scrape.
            if feed and convert_errors == len(feed):
                return BlueskyScrapeResult(
                    success=False,
                    tweets=collected,
                    error=(
                        f"All {convert_errors} posts from @{handle} failed to convert"
                    ),
                    scrape_duration_ms=int((time.monotonic() - t0) * 1000),
                )

            cursor = data.get("cursor")
            if not cursor or new_on_page == 0:
                break

            await asyncio.sleep(self.delay_between_requests)

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info(
            f"Bluesky: {len(collected)} posts from @{handle} ({elapsed}ms)"
        )
        return BlueskyScrapeResult(
            success=True, tweets=collected, scrape_duration_ms=elapsed
        )

    async def search_actors(self, query: str, limit: int = 25) -> List[BlueskyActor]:
        """Discover accounts matching a term (used to widen the Nepal account list)."""
        data = await self._get_json(
            f"app.bsky.actor.searchActors?q={quote(query)}&limit={limit}"
        )
        if not data:
            return []
        return [
            BlueskyActor(
                handle=a.get("handle", ""),
                did=a.get("did", ""),
                display_name=a.get("displayName") or "",
                description=a.get("description") or "",
            )
            for a in data.get("actors") or []
            if a.get("handle")
        ]

    async def probe(self) -> bool:
        """Cheap liveness check for the public AppView."""
        data = await self._get_json("app.bsky.actor.getProfile?actor=bsky.app")
        return bool(data and data.get("did"))
