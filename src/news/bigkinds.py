"""
BigKinds API client.
Collects news from BigKinds news big data platform.
"""
from datetime import datetime, timedelta
from typing import List, Optional

import aiohttp

from src.news.base import NewsArticle, NewsCollector
from src.utils.exceptions import APIError, NewsCollectionError
from src.utils.logger import get_logger, news_log

logger = get_logger(__name__)


class BigKindsCollector(NewsCollector):
    """
    BigKinds API collector.

    BigKinds is a news big data analysis service provided by
    Korea Press Foundation. It provides access to news articles
    from major Korean news outlets.

    Note: Requires API key from BigKinds.
    """

    source_name = "bigkinds"
    API_BASE = "https://www.bigkinds.or.kr/api"
    # Alternative API endpoint for keyword extraction
    KEYWORD_API = "http://api.bigkindslab.or.kr:5002"

    def __init__(
        self,
        api_key: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        """
        Initialize BigKinds collector.

        Args:
            api_key: BigKinds API key
            session: Optional aiohttp session
        """
        self.api_key = api_key
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None:
            headers = {
                "Content-Type": "application/json",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self) -> None:
        """Close the session if we own it."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def fetch_latest(self, limit: int = 20) -> List[NewsArticle]:
        """
        Fetch latest news from BigKinds.

        Args:
            limit: Maximum number of articles to fetch

        Returns:
            List of NewsArticle objects
        """
        if not self.api_key:
            logger.warning("BigKinds API key not configured, skipping")
            return []

        # Search for recent news in economy/finance categories
        end_date = datetime.now()
        start_date = end_date - timedelta(days=2)

        return await self.search_news(
            query="",  # Empty query for latest news
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            categories=["경제", "산업"],
            limit=limit,
        )

    async def search_news(
        self,
        query: str,
        start_date: str,
        end_date: str,
        categories: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[NewsArticle]:
        """
        Search news articles via BigKinds API.

        Args:
            query: Search query
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            categories: News categories to filter
            limit: Maximum number of results

        Returns:
            List of NewsArticle objects
        """
        session = await self._get_session()
        articles = []

        try:
            # Build search request
            search_params = {
                "query": query,
                "published_at": {
                    "from": start_date,
                    "until": end_date,
                },
                "provider": [],  # All providers
                "category": categories or [],
                "sort": {"date": "desc"},
                "return_from": 0,
                "return_size": limit,
                "fields": [
                    "title",
                    "content",
                    "published_at",
                    "provider",
                    "category",
                    "byline",
                    "news_id",
                ],
            }

            async with session.post(
                f"{self.API_BASE}/news/search",
                json=search_params,
                timeout=30,
            ) as response:
                if response.status != 200:
                    raise APIError(
                        f"BigKinds API error: HTTP {response.status}",
                        status_code=response.status,
                    )

                data = await response.json()

            # Parse results
            documents = data.get("documents", [])

            for doc in documents:
                try:
                    article = self._parse_document(doc)
                    if article and self.is_valid_article(article):
                        articles.append(article)
                        news_log(f"Collected: {article.title[:50]}...")
                except Exception as e:
                    logger.debug(f"Error parsing BigKinds document: {e}")
                    continue

            logger.info(f"BigKinds: Collected {len(articles)} articles")
            return articles

        except aiohttp.ClientError as e:
            raise NewsCollectionError(
                f"Network error fetching BigKinds: {e}",
                cause=e,
            )
        except Exception as e:
            if isinstance(e, (APIError, NewsCollectionError)):
                raise
            raise NewsCollectionError(
                f"Error fetching BigKinds news: {e}",
                cause=e,
            )

    def _parse_document(self, doc: dict) -> Optional[NewsArticle]:
        """
        Parse a BigKinds document into NewsArticle.

        Args:
            doc: Document dictionary from API

        Returns:
            NewsArticle or None
        """
        title = doc.get("title", "")
        content = doc.get("content", "")
        news_id = doc.get("news_id", "")

        if not title:
            return None

        # Parse date
        published_str = doc.get("published_at", "")
        try:
            published_at = datetime.strptime(published_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            published_at = datetime.now()

        # Build URL (BigKinds doesn't provide direct URL, construct one)
        url = f"https://www.bigkinds.or.kr/v2/news/newsDetailView.do?newsId={news_id}"

        return self._create_article(
            title=title,
            content=content,
            url=url,
            published_at=published_at,
        )

    async def fetch_by_keyword(self, keyword: str, limit: int = 10) -> List[NewsArticle]:
        """
        Fetch news by keyword search.

        Args:
            keyword: Search keyword
            limit: Maximum number of articles

        Returns:
            List of NewsArticle objects
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        return await self.search_news(
            query=keyword,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            limit=limit,
        )

    async def extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """
        Extract keywords using BigKinds keyword extraction API.

        Args:
            text: Text to extract keywords from
            top_n: Number of keywords to return

        Returns:
            List of keywords
        """
        session = await self._get_session()

        try:
            async with session.post(
                f"{self.KEYWORD_API}/get_keyword",
                json={"text": text, "top_n": top_n},
                timeout=30,
            ) as response:
                if response.status != 200:
                    logger.warning(f"Keyword extraction failed: HTTP {response.status}")
                    return []

                data = await response.json()
                return data.get("keywords", [])

        except Exception as e:
            logger.warning(f"Keyword extraction error: {e}")
            return []
