"""
Maekyung Ssok (매경쏙) news crawler.
Collects news from Maekyung Economy newspaper.
"""
from datetime import datetime
from typing import List, Optional

import aiohttp
from bs4 import BeautifulSoup

from src.news.base import NewsArticle, NewsCollector
from src.utils.exceptions import NewsCollectionError
from src.utils.logger import get_logger, news_log

logger = get_logger(__name__)


class MaekyungCollector(NewsCollector):
    """
    Maekyung (매일경제) news collector.

    Collects economic and financial news from Maekyung newspaper.
    """

    source_name = "maekyung"
    BASE_URL = "https://www.mk.co.kr"
    # Economy section
    ECONOMY_URL = f"{BASE_URL}/news/economy/"
    # Stock/Finance section
    STOCK_URL = f"{BASE_URL}/news/stock/"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """
        Initialize Maekyung collector.

        Args:
            session: Optional aiohttp session.
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

    async def fetch_latest(self, limit: int = 10) -> List[NewsArticle]:
        """
        Fetch latest Maekyung news from economy and stock sections.

        Args:
            limit: Maximum number of articles to fetch (split between sections)

        Returns:
            List of NewsArticle objects
        """
        articles = []
        session = await self._get_session()

        # Fetch from both sections
        section_limit = max(limit // 2, 1)

        for section_url in [self.ECONOMY_URL, self.STOCK_URL]:
            try:
                section_articles = await self._fetch_section(
                    session, section_url, section_limit
                )
                articles.extend(section_articles)
            except Exception as e:
                logger.warning(f"Failed to fetch section {section_url}: {e}")

        logger.info(f"Maekyung: Collected {len(articles)} articles")
        return articles[:limit]

    async def _fetch_section(
        self,
        session: aiohttp.ClientSession,
        section_url: str,
        limit: int,
    ) -> List[NewsArticle]:
        """
        Fetch articles from a specific section.

        Args:
            session: aiohttp session
            section_url: Section URL
            limit: Maximum articles to fetch

        Returns:
            List of NewsArticle objects
        """
        articles = []

        try:
            async with session.get(section_url, timeout=30) as response:
                if response.status != 200:
                    raise NewsCollectionError(
                        f"Failed to fetch section: HTTP {response.status}"
                    )
                html = await response.text()

            soup = BeautifulSoup(html, "lxml")
            article_links = self._parse_article_links(soup, limit)
            logger.debug(f"Maekyung: Found {len(article_links)} article links in {section_url}")

            for url in article_links:
                try:
                    article = await self._fetch_article(session, url)
                    if article:
                        if self.is_valid_article(article):
                            articles.append(article)
                            news_log(f"Collected: {article.title[:50]}...")
                        else:
                            logger.warning(f"Article validation failed: {url}")
                    else:
                        logger.warning(f"Article fetch returned None: {url}")
                except Exception as e:
                    logger.warning(f"Failed to fetch article {url}: {e}")
                    continue

            return articles

        except aiohttp.ClientError as e:
            raise NewsCollectionError(
                f"Network error fetching Maekyung: {e}",
                cause=e,
            )

    def _parse_article_links(self, soup: BeautifulSoup, limit: int) -> List[str]:
        """
        Parse article links from section page.

        Args:
            soup: BeautifulSoup object
            limit: Maximum number of links

        Returns:
            List of article URLs
        """
        links = []

        # Maekyung article link patterns
        article_elements = soup.select("a[href*='/news/']")

        seen_urls = set()
        for element in article_elements:
            href = element.get("href", "")
            if not href:
                continue

            # Filter for article URLs (typically contain article ID)
            if not any(char.isdigit() for char in href):
                continue

            # Build full URL
            if href.startswith("/"):
                url = f"{self.BASE_URL}{href}"
            elif href.startswith("http"):
                url = href
            else:
                continue

            if url in seen_urls:
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
            NewsArticle or None
        """
        try:
            async with session.get(url, timeout=30) as response:
                if response.status != 200:
                    return None
                html = await response.text()

            soup = BeautifulSoup(html, "lxml")

            # Extract title (using current site structure)
            title_elem = (
                soup.select_one("h2.view_head_title")
                or soup.select_one("h1.top_title")
                or soup.select_one("h2.news_ttl")
                or soup.select_one("h1")
            )
            if not title_elem:
                return None
            title = title_elem.get_text(strip=True)

            # Extract content
            content_elem = (
                soup.select_one("#article_body")
                or soup.select_one(".news_cnt_detail_wrap")
                or soup.select_one("article")
            )
            if content_elem:
                # Remove ads and related elements
                for elem in content_elem.select("script, style, .ad, .related"):
                    elem.decompose()
                content = content_elem.get_text(separator="\n", strip=True)
            else:
                content = ""

            # Extract date
            published_at = self._parse_date(soup)

            return self._create_article(
                title=title,
                content=content,
                url=url,
                published_at=published_at,
            )

        except Exception as e:
            logger.warning(f"Error parsing Maekyung article {url}: {e}")
            return None

    def _parse_date(self, soup: BeautifulSoup) -> datetime:
        """
        Parse publication date from article.

        Args:
            soup: BeautifulSoup object

        Returns:
            datetime object
        """
        date_selectors = [
            ".time_area",
            ".news_info_wrap time",
            "meta[property='article:published_time']",
        ]

        for selector in date_selectors:
            elem = soup.select_one(selector)
            if not elem:
                continue

            date_str = elem.get("datetime") or elem.get("content") or elem.get_text()
            if date_str:
                # Clean up the date string
                date_str = date_str.strip()

                try:
                    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

                # Try Korean format: 2024.01.15 10:30
                try:
                    return datetime.strptime(date_str[:16], "%Y.%m.%d %H:%M")
                except ValueError:
                    pass

                try:
                    return datetime.strptime(date_str[:10], "%Y.%m.%d")
                except ValueError:
                    pass

        return datetime.now()
