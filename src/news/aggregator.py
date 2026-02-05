"""
News aggregator that combines multiple news sources.
"""
import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

import aiohttp

from src.news.base import NewsArticle, NewsCollector
from src.news.bigkinds import BigKindsCollector
from src.news.maekyung import MaekyungCollector
from src.news.newneek import NewneekCollector
from src.news.uppity import UppityCollector
from src.utils.exceptions import NewsCollectionError
from src.utils.logger import get_logger, news_log

logger = get_logger(__name__)


class NewsCache:
    """
    Simple file-based cache for news articles.
    Prevents re-processing of already seen articles.
    """

    def __init__(self, cache_dir: str, ttl_hours: int = 24):
        """
        Initialize news cache.

        Args:
            cache_dir: Directory to store cache files
            ttl_hours: Cache TTL in hours
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)
        self._seen_urls: Set[str] = set()
        self._load_cache()

    def _get_cache_file(self) -> Path:
        """Get cache file path for today."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self.cache_dir / f"seen_urls_{date_str}.json"

    def _load_cache(self) -> None:
        """Load cached URLs from file."""
        cache_file = self._get_cache_file()
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    self._seen_urls = set(json.load(f))
                logger.debug(f"Loaded {len(self._seen_urls)} cached URLs")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
                self._seen_urls = set()

        # Clean old cache files
        self._cleanup_old_cache()

    def _save_cache(self) -> None:
        """Save cached URLs to file."""
        cache_file = self._get_cache_file()
        try:
            with open(cache_file, "w") as f:
                json.dump(list(self._seen_urls), f)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _cleanup_old_cache(self) -> None:
        """Remove cache files older than TTL."""
        cutoff = datetime.now() - self.ttl
        for cache_file in self.cache_dir.glob("seen_urls_*.json"):
            try:
                date_str = cache_file.stem.replace("seen_urls_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    cache_file.unlink()
                    logger.debug(f"Removed old cache file: {cache_file}")
            except Exception:
                pass

    def is_seen(self, article: NewsArticle) -> bool:
        """
        Check if an article has been seen before.

        Args:
            article: Article to check

        Returns:
            True if already seen
        """
        return article.url in self._seen_urls

    def mark_seen(self, article: NewsArticle) -> None:
        """
        Mark an article as seen.

        Args:
            article: Article to mark
        """
        self._seen_urls.add(article.url)

    def save(self) -> None:
        """Save cache to disk."""
        self._save_cache()


class NewsAggregator:
    """
    Aggregates news from multiple sources.

    Handles parallel fetching, deduplication, and caching.
    """

    def __init__(
        self,
        config: dict,
        cache_dir: Optional[str] = None,
    ):
        """
        Initialize news aggregator.

        Args:
            config: News configuration dictionary
            cache_dir: Optional cache directory path
        """
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._collectors: List[NewsCollector] = []

        # Setup cache
        cache_config = config.get("cache", {})
        if cache_dir or cache_config.get("enabled", True):
            cache_path = cache_dir or cache_config.get("directory", "./data/news_cache")
            ttl_hours = cache_config.get("ttl_hours", 24)
            self.cache = NewsCache(cache_path, ttl_hours)
        else:
            self.cache = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create shared aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Safari/537.36"
                }
            )
        return self._session

    async def _setup_collectors(self) -> None:
        """Setup news collectors based on configuration."""
        session = await self._get_session()
        sources_config = self.config.get("sources", [])

        for source in sources_config:
            name = source.get("name", "")
            enabled = source.get("enabled", True)

            if not enabled:
                continue

            try:
                if name == "newneek":
                    self._collectors.append(NewneekCollector(session))
                elif name == "uppity":
                    self._collectors.append(UppityCollector(session))
                elif name == "maekyung":
                    self._collectors.append(MaekyungCollector(session))
                elif name == "bigkinds":
                    api_key = source.get("api_key")
                    if api_key:
                        self._collectors.append(BigKindsCollector(api_key, session))
                    else:
                        logger.warning("BigKinds API key not configured, skipping")
                else:
                    logger.warning(f"Unknown news source: {name}")
            except Exception as e:
                logger.error(f"Failed to setup collector {name}: {e}")

        logger.info(f"Initialized {len(self._collectors)} news collectors")

    async def collect_all(self) -> List[NewsArticle]:
        """
        Collect news from all enabled sources.

        Returns:
            List of deduplicated NewsArticle objects
        """
        if not self._collectors:
            await self._setup_collectors()

        all_articles: List[NewsArticle] = []
        sources_config = {
            s.get("name"): s for s in self.config.get("sources", [])
        }

        # Collect from all sources in parallel
        tasks = []
        for collector in self._collectors:
            source_config = sources_config.get(collector.source_name, {})
            limit = source_config.get("fetch_limit", 10)
            tasks.append(self._collect_from_source(collector, limit))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Collection error: {result}")
                continue
            all_articles.extend(result)

        # Deduplicate
        unique_articles = self._deduplicate(all_articles)

        # Filter by cache
        if self.cache:
            new_articles = []
            for article in unique_articles:
                if not self.cache.is_seen(article):
                    self.cache.mark_seen(article)
                    new_articles.append(article)
            self.cache.save()
            logger.info(
                f"After cache filter: {len(new_articles)} new articles "
                f"(filtered {len(unique_articles) - len(new_articles)} seen)"
            )
            return new_articles

        return unique_articles

    async def _collect_from_source(
        self,
        collector: NewsCollector,
        limit: int,
    ) -> List[NewsArticle]:
        """
        Collect news from a single source with error handling.

        Args:
            collector: News collector instance
            limit: Maximum articles to fetch

        Returns:
            List of NewsArticle objects
        """
        try:
            articles = await collector.fetch_latest(limit)
            news_log(f"Source {collector.source_name}: {len(articles)} articles")
            return articles
        except NewsCollectionError as e:
            logger.warning(f"Failed to collect from {collector.source_name}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error from {collector.source_name}: {e}")
            return []

    def _deduplicate(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """
        Remove duplicate articles.

        Args:
            articles: List of articles to deduplicate

        Returns:
            Deduplicated list
        """
        seen_urls: Set[str] = set()
        seen_titles: Set[str] = set()
        unique: List[NewsArticle] = []

        for article in articles:
            # Check URL
            if article.url in seen_urls:
                continue

            # Check similar titles (simple fuzzy matching)
            title_key = self._normalize_title(article.title)
            if title_key in seen_titles:
                continue

            seen_urls.add(article.url)
            seen_titles.add(title_key)
            unique.append(article)

        logger.debug(
            f"Deduplicated: {len(articles)} -> {len(unique)} articles"
        )
        return unique

    def _normalize_title(self, title: str) -> str:
        """
        Normalize title for deduplication.

        Args:
            title: Article title

        Returns:
            Normalized title hash
        """
        # Remove whitespace and common suffixes
        normalized = title.strip().lower()
        normalized = normalized.replace(" ", "")

        # Use first 30 chars for fuzzy matching
        return normalized[:30]

    async def close(self) -> None:
        """Close all collectors and session."""
        for collector in self._collectors:
            if hasattr(collector, "close"):
                try:
                    await collector.close()
                except Exception:
                    pass

        if self._session:
            await self._session.close()
            self._session = None

        self._collectors = []
