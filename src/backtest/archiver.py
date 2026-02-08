"""
Article archiver for backtesting.
Saves collected articles to date-based JSON files for later replay.
"""
import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional

from src.news.base import NewsArticle
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ArticleArchiver:
    """Saves and loads news articles for backtesting."""

    def __init__(self, archive_dir: str = "./data/article_archive"):
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, dt: date) -> Path:
        return self.archive_dir / f"articles_{dt.isoformat()}.json"

    def save_articles(self, articles: List[NewsArticle]) -> int:
        """
        Save articles grouped by publication date.

        Returns:
            Number of new articles saved
        """
        if not articles:
            return 0

        # Group by date
        by_date: dict[date, List[NewsArticle]] = {}
        for article in articles:
            d = article.published_at.date()
            by_date.setdefault(d, []).append(article)

        saved_count = 0
        for d, day_articles in by_date.items():
            file_path = self._get_file_path(d)

            # Load existing articles for this date
            existing_urls = set()
            existing = []
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    existing_urls = {a["url"] for a in existing}
                except Exception:
                    existing = []

            # Append only new articles
            for article in day_articles:
                if article.url not in existing_urls:
                    existing.append(article.to_dict())
                    saved_count += 1

            # Write back
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

        if saved_count > 0:
            logger.info(f"Archived {saved_count} new articles")
        return saved_count

    def load_articles(
        self,
        start_date: date,
        end_date: date,
    ) -> List[NewsArticle]:
        """
        Load archived articles for a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of NewsArticle objects sorted by published_at
        """
        articles = []
        current = start_date

        while current <= end_date:
            file_path = self._get_file_path(current)
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for item in data:
                        articles.append(NewsArticle.from_dict(item))
                except Exception as e:
                    logger.warning(f"Failed to load {file_path}: {e}")

            # Next day
            from datetime import timedelta
            current += timedelta(days=1)

        # Normalize timezone for sorting (strip tzinfo to avoid naive vs aware comparison)
        articles.sort(key=lambda a: a.published_at.replace(tzinfo=None))
        logger.info(
            f"Loaded {len(articles)} archived articles "
            f"({start_date} ~ {end_date})"
        )
        return articles

    def get_available_dates(self) -> List[date]:
        """Get list of dates with archived articles."""
        dates = []
        for f in sorted(self.archive_dir.glob("articles_*.json")):
            try:
                date_str = f.stem.replace("articles_", "")
                dates.append(date.fromisoformat(date_str))
            except ValueError:
                continue
        return dates
