"""
Newneek (뉴닉) news crawler.
Collects news from Newneek newsletter archive.
"""
import asyncio
import random
from datetime import datetime
from typing import List, Optional

import aiohttp
from bs4 import BeautifulSoup

from src.news.base import NewsArticle, NewsCollector
from src.utils.exceptions import NewsCollectionError, NewsParsingError
from src.utils.logger import get_logger, news_log

logger = get_logger(__name__)

# Retry settings for rate limiting
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # seconds


class NewneekCollector(NewsCollector):
    """
    Newneek newsletter collector.

    Newneek provides daily newsletters covering social and economic issues
    in an easy-to-understand format.
    """

    source_name = "newneek"
    BASE_URL = "https://newneek.co"
    ARCHIVE_URL = f"{BASE_URL}/post"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """
        Initialize Newneek collector.

        Args:
            session: Optional aiohttp session. If not provided, creates a new one.
        """
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Safari/537.36"
                }
            )
        return self._session

    async def close(self) -> None:
        """Close the session if we own it."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def _fetch_with_retry(
        self, session: aiohttp.ClientSession, url: str
    ) -> Optional[str]:
        """
        Fetch URL with retry logic for rate limiting.

        Args:
            session: aiohttp session
            url: URL to fetch

        Returns:
            HTML content or None
        """
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status == 429:
                        # Rate limited - wait and retry
                        delay = RETRY_DELAY_BASE * (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(f"Newneek rate limited, waiting {delay:.1f}s (attempt {attempt + 1})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.warning(f"Newneek HTTP {response.status} for {url}")
                        return None
            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching {url} (attempt {attempt + 1})")
                await asyncio.sleep(RETRY_DELAY_BASE)
                continue
            except Exception as e:
                logger.warning(f"Error fetching {url}: {e}")
                return None

        logger.warning(f"Failed to fetch {url} after {MAX_RETRIES} retries")
        return None

    async def fetch_latest(self, limit: int = 10) -> List[NewsArticle]:
        """
        Fetch latest Newneek newsletters.

        Args:
            limit: Maximum number of articles to fetch

        Returns:
            List of NewsArticle objects
        """
        articles = []
        session = await self._get_session()

        try:
            # Fetch archive page with retry
            html = await self._fetch_with_retry(session, self.ARCHIVE_URL)
            if not html:
                logger.warning("Newneek: Could not fetch archive page (possibly rate limited)")
                return articles

            # Parse article links
            soup = BeautifulSoup(html, "lxml")
            article_links = self._parse_article_links(soup, limit)

            # Fetch individual articles with delay to avoid rate limiting
            for i, url in enumerate(article_links):
                try:
                    # Add small delay between requests
                    if i > 0:
                        await asyncio.sleep(0.5 + random.uniform(0, 0.5))

                    article = await self._fetch_article(session, url)
                    if article and self.is_valid_article(article):
                        articles.append(article)
                        news_log(f"Collected: {article.title[:50]}...")
                except Exception as e:
                    logger.warning(f"Failed to fetch article {url}: {e}")
                    continue

            logger.info(f"Newneek: Collected {len(articles)} articles")
            return articles

        except aiohttp.ClientError as e:
            raise NewsCollectionError(
                f"Network error while fetching Newneek: {e}",
                cause=e,
            )
        except Exception as e:
            raise NewsCollectionError(
                f"Error fetching Newneek news: {e}",
                cause=e,
            )

    def _parse_article_links(self, soup: BeautifulSoup, limit: int) -> List[str]:
        """
        Parse article links from archive page.

        Args:
            soup: BeautifulSoup object of archive page
            limit: Maximum number of links to return

        Returns:
            List of article URLs
        """
        links = []

        # Find article cards/links (adjust selectors based on actual site structure)
        # Newneek uses various article card formats
        article_elements = soup.select("a[href*='/post/']")

        seen_urls = set()
        for element in article_elements:
            href = element.get("href", "")
            if not href:
                continue

            # Build full URL
            if href.startswith("/"):
                url = f"{self.BASE_URL}{href}"
            elif href.startswith("http"):
                url = href
            else:
                continue

            # Skip duplicates and non-article URLs
            if url in seen_urls or "/post/" not in url:
                continue

            seen_urls.add(url)
            links.append(url)

            if len(links) >= limit:
                break

        return links

    async def _fetch_article(
        self,
        session: aiohttp.ClientSession,
        url: str,
    ) -> Optional[NewsArticle]:
        """
        Fetch and parse a single article.

        Args:
            session: aiohttp session
            url: Article URL

        Returns:
            NewsArticle or None if parsing fails
        """
        try:
            async with session.get(url, timeout=30) as response:
                if response.status != 200:
                    return None
                html = await response.text()

            soup = BeautifulSoup(html, "lxml")

            # Extract title
            title_elem = soup.select_one("h1") or soup.select_one(".post-title")
            if not title_elem:
                return None
            title = title_elem.get_text(strip=True)

            # Extract content
            content_elem = soup.select_one("article") or soup.select_one(".post-content")
            if content_elem:
                # Remove script and style elements
                for elem in content_elem.select("script, style"):
                    elem.decompose()
                content = content_elem.get_text(separator="\n", strip=True)
            else:
                content = ""

            # Extract date (try multiple formats)
            published_at = self._parse_date(soup)

            return self._create_article(
                title=title,
                content=content,
                url=url,
                published_at=published_at,
            )

        except Exception as e:
            logger.debug(f"Error parsing article {url}: {e}")
            return None

    def _parse_date(self, soup: BeautifulSoup) -> datetime:
        """
        Parse publication date from article page.

        Args:
            soup: BeautifulSoup object

        Returns:
            datetime object (defaults to now if parsing fails)
        """
        # Try various date selectors
        date_selectors = [
            "time[datetime]",
            ".post-date",
            ".date",
            "meta[property='article:published_time']",
        ]

        for selector in date_selectors:
            elem = soup.select_one(selector)
            if not elem:
                continue

            date_str = elem.get("datetime") or elem.get("content") or elem.get_text()
            if date_str:
                try:
                    # Try ISO format
                    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

                try:
                    # Try common Korean date format
                    return datetime.strptime(date_str.strip(), "%Y.%m.%d")
                except ValueError:
                    pass

        # Default to current time
        return datetime.now()
