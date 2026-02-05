"""
Uppity (어피티) news crawler.
Collects news from Uppity money letter.
"""
from datetime import datetime
from typing import List, Optional

import aiohttp
from bs4 import BeautifulSoup

from src.news.base import NewsArticle, NewsCollector
from src.utils.exceptions import NewsCollectionError
from src.utils.logger import get_logger, news_log

logger = get_logger(__name__)


class UppityCollector(NewsCollector):
    """
    Uppity money letter collector.

    Uppity provides financial and economic news in newsletter format,
    covering personal finance, investment, and economic trends.
    """

    source_name = "uppity"
    BASE_URL = "https://uppity.co.kr"
    # Updated URLs based on current site structure
    NEWSLETTER_URL = f"{BASE_URL}/newsletter/money-letter/"
    ECONOMY_NEWS_URL = f"{BASE_URL}/economy-news/"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """
        Initialize Uppity collector.

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
        Fetch latest Uppity newsletters and economy news.

        Args:
            limit: Maximum number of articles to fetch

        Returns:
            List of NewsArticle objects
        """
        articles = []
        session = await self._get_session()

        # Fetch from multiple sources
        urls_to_fetch = [
            self.NEWSLETTER_URL,
            self.ECONOMY_NEWS_URL,
        ]

        try:
            for page_url in urls_to_fetch:
                try:
                    async with session.get(page_url, timeout=30) as response:
                        if response.status != 200:
                            logger.warning(f"Uppity {page_url}: HTTP {response.status}")
                            continue
                        html = await response.text()

                    soup = BeautifulSoup(html, "lxml")
                    article_links = self._parse_newsletter_links(soup, limit // 2 + 1)

                    for url in article_links:
                        if len(articles) >= limit:
                            break
                        try:
                            article = await self._fetch_newsletter(session, url)
                            if article and self.is_valid_article(article):
                                articles.append(article)
                                news_log(f"Collected: {article.title[:50]}...")
                        except Exception as e:
                            logger.warning(f"Failed to fetch article {url}: {e}")
                            continue

                except Exception as e:
                    logger.warning(f"Failed to fetch {page_url}: {e}")
                    continue

            logger.info(f"Uppity: Collected {len(articles)} articles")
            return articles[:limit]

        except aiohttp.ClientError as e:
            raise NewsCollectionError(
                f"Network error while fetching Uppity: {e}",
                cause=e,
            )
        except Exception as e:
            raise NewsCollectionError(
                f"Error fetching Uppity news: {e}",
                cause=e,
            )

    def _parse_newsletter_links(self, soup: BeautifulSoup, limit: int) -> List[str]:
        """
        Parse newsletter and article links from list page.

        Args:
            soup: BeautifulSoup object
            limit: Maximum number of links

        Returns:
            List of article URLs
        """
        import re

        links = []

        # Try multiple selectors for WordPress-based site
        selectors = [
            "a[href*='/economy-news/']",
            "a[href*='/newsletter/']",
            "article a",
            ".post a",
            ".entry-title a",
            "h2 a",
            "h3 a",
        ]

        # Pattern for article URLs (3+ digit IDs, not pagination like /2/ or /3/)
        article_id_pattern = re.compile(r'/(\d{3,})/?$')
        # Pattern for pagination (1-2 digit numbers at end)
        pagination_pattern = re.compile(r'/\d{1,2}/?$')

        seen_urls = set()
        for selector in selectors:
            elements = soup.select(selector)
            for element in elements:
                href = element.get("href", "")
                if not href:
                    continue

                # Skip category/tag pages and non-article links
                skip_patterns = ["/category/", "/tag/", "/page/", "#", "javascript:", "-letter/", "-letter"]
                if any(skip in href for skip in skip_patterns):
                    continue

                # Build full URL
                if href.startswith("/"):
                    url = f"{self.BASE_URL}{href}"
                elif href.startswith("http"):
                    url = href
                else:
                    continue

                # Skip section URLs (like /economy-news/ without article ID)
                if url.rstrip('/') in [
                    f"{self.BASE_URL}/economy-news",
                    f"{self.BASE_URL}/newsletter",
                    f"{self.BASE_URL}/newsletter/money-letter",
                ]:
                    continue

                # Skip pagination URLs (like /economy-news/2/)
                if pagination_pattern.search(url):
                    continue

                # Skip if already seen
                if url in seen_urls:
                    continue

                # Prefer URLs with article IDs (3+ digits)
                if article_id_pattern.search(url):
                    seen_urls.add(url)
                    links.append(url)

                if len(links) >= limit:
                    break

            if len(links) >= limit:
                break

        return links

    async def _fetch_newsletter(
        self,
        session: aiohttp.ClientSession,
        url: str,
    ) -> Optional[NewsArticle]:
        """
        Fetch and parse a single newsletter.

        Args:
            session: aiohttp session
            url: Newsletter URL

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
            title_elem = soup.select_one("h1") or soup.select_one(".newsletter-title")
            if not title_elem:
                return None
            title = title_elem.get_text(strip=True)

            # Extract content
            content_elem = (
                soup.select_one(".newsletter-content")
                or soup.select_one("article")
                or soup.select_one(".content")
            )
            if content_elem:
                for elem in content_elem.select("script, style, nav"):
                    elem.decompose()
                content = content_elem.get_text(separator="\n", strip=True)
            else:
                content = ""

            # Extract date
            published_at = self._parse_date(soup)

            # Extract summary if available
            summary_elem = soup.select_one(".newsletter-summary") or soup.select_one("meta[name='description']")
            summary = None
            if summary_elem:
                summary = summary_elem.get("content") or summary_elem.get_text(strip=True)

            return self._create_article(
                title=title,
                content=content,
                url=url,
                published_at=published_at,
                summary=summary,
            )

        except Exception as e:
            logger.debug(f"Error parsing newsletter {url}: {e}")
            return None

    def _parse_date(self, soup: BeautifulSoup) -> datetime:
        """
        Parse publication date from newsletter page.

        Args:
            soup: BeautifulSoup object

        Returns:
            datetime object
        """
        date_selectors = [
            "time[datetime]",
            ".newsletter-date",
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
                    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

                try:
                    return datetime.strptime(date_str.strip(), "%Y.%m.%d")
                except ValueError:
                    pass

                try:
                    return datetime.strptime(date_str.strip(), "%Y-%m-%d")
                except ValueError:
                    pass

        return datetime.now()
