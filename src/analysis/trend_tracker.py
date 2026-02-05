"""
Dynamic trend tracking module.
Automatically extracts and tracks trending keywords from news.
"""
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from src.news.base import NewsArticle
from src.utils.logger import analysis_log, get_logger

logger = get_logger(__name__)


@dataclass
class TrendingKeyword:
    """Represents a trending keyword with its metrics."""
    keyword: str
    count: int
    trend_score: float  # How much it's trending (velocity)
    first_seen: datetime
    last_seen: datetime
    related_articles: List[str] = field(default_factory=list)  # Article URLs
    sentiment_avg: float = 0.0

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "count": self.count,
            "trend_score": self.trend_score,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "article_count": len(self.related_articles),
            "sentiment_avg": self.sentiment_avg,
        }


@dataclass
class TrendSnapshot:
    """Snapshot of keyword trends at a point in time."""
    timestamp: datetime
    keyword_counts: Dict[str, int]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "keyword_counts": self.keyword_counts,
        }


class TrendTracker:
    """
    Tracks trending keywords over time.

    Features:
    - Extracts keywords from news articles
    - Tracks keyword frequency over time
    - Detects trending (rapidly increasing) keywords
    - Identifies emerging issues and events
    """

    def __init__(
        self,
        data_dir: str = "./data/trends",
        window_hours: int = 24,
        min_count: int = 3,
        trend_threshold: float = 2.0,
    ):
        """
        Initialize trend tracker.

        Args:
            data_dir: Directory to store trend data
            window_hours: Time window for trend calculation
            min_count: Minimum mentions to consider a keyword
            trend_threshold: Minimum trend score to be "trending"
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.window_hours = window_hours
        self.min_count = min_count
        self.trend_threshold = trend_threshold

        # Current session tracking
        self._current_keywords: Counter = Counter()
        self._keyword_articles: Dict[str, List[str]] = defaultdict(list)
        self._keyword_sentiments: Dict[str, List[float]] = defaultdict(list)
        self._keyword_first_seen: Dict[str, datetime] = {}
        self._keyword_last_seen: Dict[str, datetime] = {}

        # Historical snapshots for trend calculation
        self._snapshots: List[TrendSnapshot] = []

        # Load existing data
        self._load_data()

    def _get_data_file(self) -> Path:
        """Get data file path for today."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self.data_dir / f"trends_{date_str}.json"

    def _load_data(self) -> None:
        """Load existing trend data."""
        data_file = self._get_data_file()
        if data_file.exists():
            try:
                with open(data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self._current_keywords = Counter(data.get("keywords", {}))
                self._keyword_articles = defaultdict(
                    list, data.get("keyword_articles", {})
                )

                # Load snapshots
                for snap_data in data.get("snapshots", []):
                    self._snapshots.append(TrendSnapshot(
                        timestamp=datetime.fromisoformat(snap_data["timestamp"]),
                        keyword_counts=snap_data["keyword_counts"],
                    ))

                logger.debug(f"Loaded {len(self._current_keywords)} keywords from cache")
            except Exception as e:
                logger.warning(f"Failed to load trend data: {e}")

    def _save_data(self) -> None:
        """Save trend data to file."""
        data_file = self._get_data_file()
        try:
            data = {
                "keywords": dict(self._current_keywords),
                "keyword_articles": dict(self._keyword_articles),
                "snapshots": [s.to_dict() for s in self._snapshots[-48:]],  # Keep 48 snapshots
                "updated_at": datetime.now().isoformat(),
            }
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save trend data: {e}")

    def update(
        self,
        articles: List[NewsArticle],
        extracted_keywords: Dict[str, List[str]],
    ) -> None:
        """
        Update trend tracking with new articles and keywords.

        Args:
            articles: List of news articles
            extracted_keywords: Dict of article_url -> keywords list
        """
        now = datetime.now()

        for article in articles:
            keywords = extracted_keywords.get(article.url, [])
            sentiment = article.sentiment_score or 0.0

            for keyword in keywords:
                # Skip very short keywords
                if len(keyword) < 2:
                    continue

                self._current_keywords[keyword] += 1
                self._keyword_articles[keyword].append(article.url)
                self._keyword_sentiments[keyword].append(sentiment)

                if keyword not in self._keyword_first_seen:
                    self._keyword_first_seen[keyword] = now
                self._keyword_last_seen[keyword] = now

        # Take a snapshot
        self._snapshots.append(TrendSnapshot(
            timestamp=now,
            keyword_counts=dict(self._current_keywords),
        ))

        # Clean old snapshots
        cutoff = now - timedelta(hours=self.window_hours * 2)
        self._snapshots = [
            s for s in self._snapshots
            if s.timestamp > cutoff
        ]

        # Save data
        self._save_data()

        analysis_log(
            f"Trend update: {len(articles)} articles, "
            f"{len(self._current_keywords)} unique keywords tracked"
        )

    def get_trending_keywords(
        self,
        limit: int = 20,
        min_trend_score: Optional[float] = None,
    ) -> List[TrendingKeyword]:
        """
        Get currently trending keywords.

        Args:
            limit: Maximum keywords to return
            min_trend_score: Minimum trend score (default: self.trend_threshold)

        Returns:
            List of TrendingKeyword objects sorted by trend score
        """
        min_score = min_trend_score or self.trend_threshold
        trending = []

        for keyword, count in self._current_keywords.items():
            if count < self.min_count:
                continue

            trend_score = self._calculate_trend_score(keyword)

            # Calculate average sentiment
            sentiments = self._keyword_sentiments.get(keyword, [])
            sentiment_avg = sum(sentiments) / len(sentiments) if sentiments else 0.0

            trending.append(TrendingKeyword(
                keyword=keyword,
                count=count,
                trend_score=trend_score,
                first_seen=self._keyword_first_seen.get(keyword, datetime.now()),
                last_seen=self._keyword_last_seen.get(keyword, datetime.now()),
                related_articles=self._keyword_articles.get(keyword, [])[:10],
                sentiment_avg=sentiment_avg,
            ))

        # Sort by trend score
        trending.sort(key=lambda x: x.trend_score, reverse=True)

        # Filter by minimum trend score and limit
        result = [t for t in trending if t.trend_score >= min_score][:limit]

        return result

    def _calculate_trend_score(self, keyword: str) -> float:
        """
        Calculate trend score for a keyword.

        Trend score measures how quickly a keyword is gaining mentions.
        Higher score = faster growth = more "trending".

        Returns:
            Trend score (1.0 = stable, >2.0 = trending, >5.0 = viral)
        """
        if len(self._snapshots) < 2:
            return 1.0

        now = datetime.now()
        recent_window = now - timedelta(hours=self.window_hours / 4)
        older_window = now - timedelta(hours=self.window_hours)

        # Count in recent vs older window
        recent_count = 0
        older_count = 0

        for snapshot in self._snapshots:
            count = snapshot.keyword_counts.get(keyword, 0)
            if snapshot.timestamp > recent_window:
                recent_count = max(recent_count, count)
            elif snapshot.timestamp > older_window:
                older_count = max(older_count, count)

        # Calculate growth rate
        if older_count == 0:
            # New keyword - high trend if recent count is significant
            return min(recent_count / self.min_count, 10.0) if recent_count >= self.min_count else 1.0

        growth_rate = recent_count / older_count
        return growth_rate

    def get_top_keywords(self, limit: int = 30) -> List[Tuple[str, int]]:
        """
        Get top keywords by total count.

        Args:
            limit: Maximum keywords to return

        Returns:
            List of (keyword, count) tuples
        """
        return self._current_keywords.most_common(limit)

    def get_emerging_issues(self, limit: int = 10) -> List[TrendingKeyword]:
        """
        Get newly emerging issues (keywords that appeared recently and growing fast).

        Args:
            limit: Maximum issues to return

        Returns:
            List of TrendingKeyword objects
        """
        now = datetime.now()
        recent_cutoff = now - timedelta(hours=6)  # Appeared in last 6 hours

        emerging = []
        for keyword, count in self._current_keywords.items():
            first_seen = self._keyword_first_seen.get(keyword)
            if not first_seen or first_seen < recent_cutoff:
                continue

            if count < 2:  # At least 2 mentions
                continue

            trend_score = self._calculate_trend_score(keyword)
            sentiments = self._keyword_sentiments.get(keyword, [])
            sentiment_avg = sum(sentiments) / len(sentiments) if sentiments else 0.0

            emerging.append(TrendingKeyword(
                keyword=keyword,
                count=count,
                trend_score=trend_score,
                first_seen=first_seen,
                last_seen=self._keyword_last_seen.get(keyword, now),
                related_articles=self._keyword_articles.get(keyword, [])[:5],
                sentiment_avg=sentiment_avg,
            ))

        # Sort by count * trend_score
        emerging.sort(key=lambda x: x.count * x.trend_score, reverse=True)
        return emerging[:limit]

    def get_keyword_sentiment(self, keyword: str) -> Optional[float]:
        """Get average sentiment for a keyword."""
        sentiments = self._keyword_sentiments.get(keyword, [])
        if not sentiments:
            return None
        return sum(sentiments) / len(sentiments)

    def get_related_keywords(
        self,
        keyword: str,
        limit: int = 10,
    ) -> List[Tuple[str, float]]:
        """
        Get keywords that frequently appear with the given keyword.

        Args:
            keyword: Target keyword
            limit: Maximum related keywords to return

        Returns:
            List of (keyword, co-occurrence_score) tuples
        """
        target_articles = set(self._keyword_articles.get(keyword, []))
        if not target_articles:
            return []

        # Count co-occurrences
        co_occurrence: Counter = Counter()
        for other_keyword, articles in self._keyword_articles.items():
            if other_keyword == keyword:
                continue

            overlap = len(target_articles & set(articles))
            if overlap > 0:
                # Jaccard similarity
                union = len(target_articles | set(articles))
                score = overlap / union if union > 0 else 0
                co_occurrence[other_keyword] = score

        return co_occurrence.most_common(limit)

    def get_summary(self) -> dict:
        """Get summary of current trends."""
        trending = self.get_trending_keywords(10)
        emerging = self.get_emerging_issues(5)
        top = self.get_top_keywords(10)

        return {
            "total_keywords": len(self._current_keywords),
            "total_articles": sum(len(urls) for urls in self._keyword_articles.values()),
            "trending_keywords": [t.to_dict() for t in trending],
            "emerging_issues": [e.to_dict() for e in emerging],
            "top_keywords": [{"keyword": k, "count": c} for k, c in top],
            "snapshot_count": len(self._snapshots),
            "updated_at": datetime.now().isoformat(),
        }

    def reset(self) -> None:
        """Reset all tracking data."""
        self._current_keywords = Counter()
        self._keyword_articles = defaultdict(list)
        self._keyword_sentiments = defaultdict(list)
        self._keyword_first_seen = {}
        self._keyword_last_seen = {}
        self._snapshots = []
        logger.info("Trend tracker reset")