"""
Base classes and data models for news collection.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class NewsArticle:
    """Represents a news article."""
    source: str                           # News source (newneek, uppity, etc.)
    title: str                            # Article title
    content: str                          # Article content/body
    url: str                              # Original URL
    published_at: datetime                # Publication date
    summary: Optional[str] = None         # Summary if available
    keywords: List[str] = field(default_factory=list)  # Extracted keywords
    sentiment_score: float = 0.0          # Sentiment score (-1 to 1)

    def __hash__(self) -> int:
        """Hash based on URL for deduplication."""
        return hash(self.url)

    def __eq__(self, other) -> bool:
        """Equality based on URL."""
        if not isinstance(other, NewsArticle):
            return False
        return self.url == other.url

    @property
    def text(self) -> str:
        """Combined title and content for analysis."""
        return f"{self.title}\n\n{self.content}"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "source": self.source,
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "summary": self.summary,
            "keywords": self.keywords,
            "sentiment_score": self.sentiment_score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NewsArticle":
        """Create from dictionary."""
        data = data.copy()
        if isinstance(data.get("published_at"), str):
            data["published_at"] = datetime.fromisoformat(data["published_at"])
        return cls(**data)


class NewsCollector(ABC):
    """
    Abstract base class for news collectors.

    All news source-specific collectors should inherit from this class
    and implement the required methods.
    """

    source_name: str = "unknown"

    @abstractmethod
    async def fetch_latest(self, limit: int = 10) -> List[NewsArticle]:
        """
        Fetch the latest news articles.

        Args:
            limit: Maximum number of articles to fetch

        Returns:
            List of NewsArticle objects
        """
        pass

    async def fetch_by_keyword(self, keyword: str, limit: int = 10) -> List[NewsArticle]:
        """
        Fetch news articles by keyword search.

        Args:
            keyword: Search keyword
            limit: Maximum number of articles to fetch

        Returns:
            List of NewsArticle objects

        Note:
            Not all collectors may support keyword search.
            Default implementation returns empty list.
        """
        return []

    def is_valid_article(self, article: NewsArticle) -> bool:
        """
        Validate an article.

        Args:
            article: Article to validate

        Returns:
            True if article is valid
        """
        if not article.title or not article.title.strip():
            return False
        if not article.url:
            return False
        return True

    def _create_article(
        self,
        title: str,
        content: str,
        url: str,
        published_at: datetime,
        summary: Optional[str] = None,
    ) -> NewsArticle:
        """
        Helper to create a NewsArticle with this collector's source.

        Args:
            title: Article title
            content: Article content
            url: Article URL
            published_at: Publication date
            summary: Optional summary

        Returns:
            NewsArticle instance
        """
        return NewsArticle(
            source=self.source_name,
            title=title.strip(),
            content=content.strip(),
            url=url,
            published_at=published_at,
            summary=summary.strip() if summary else None,
        )
