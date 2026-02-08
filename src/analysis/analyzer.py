"""
Integrated news analysis module.
Combines keyword extraction, sentiment analysis, and stock mapping.
Now with dynamic trend tracking for real-time keyword discovery.
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from src.analysis.dynamic_mapper import DynamicStockMapper, DynamicStockMatch
from src.analysis.keyword_extractor import KeywordExtractor
from src.analysis.sentiment import SentimentAnalyzer, SentimentResult
from src.analysis.stock_mapper import StockMapper, StockMapping, StockSignal
from src.analysis.trend_tracker import TrendTracker, TrendingKeyword
from src.news.base import NewsArticle
from src.utils.logger import analysis_log, get_logger

logger = get_logger(__name__)


@dataclass
class ArticleAnalysis:
    """Analysis result for a single news article."""
    article: NewsArticle
    keywords: List[str]
    sentiment: SentimentResult
    related_stocks: List[tuple]  # List of (StockMapping, match_count)

    def to_dict(self) -> dict:
        return {
            "article": self.article.to_dict(),
            "keywords": self.keywords,
            "sentiment": self.sentiment.to_dict(),
            "related_stocks": [
                {"code": stock.stock_code, "name": stock.stock_name, "matches": count}
                for stock, count in self.related_stocks
            ],
        }


@dataclass
class TradingSignal:
    """Aggregated trading signal for a stock."""
    stock_code: str
    stock_name: str
    industry: str
    mentions: int = 0
    sentiment_sum: float = 0.0
    keywords: Set[str] = field(default_factory=set)
    articles: List[NewsArticle] = field(default_factory=list)

    @property
    def avg_sentiment(self) -> float:
        """Average sentiment score."""
        if self.mentions == 0:
            return 0.0
        return self.sentiment_sum / self.mentions

    @property
    def signal_strength(self) -> float:
        """Overall signal strength (0-1)."""
        # Combine mentions and sentiment
        mention_score = min(self.mentions / 10, 1.0)
        sentiment_score = (self.avg_sentiment + 1) / 2  # Normalize to 0-1
        return mention_score * 0.5 + sentiment_score * 0.5

    def to_dict(self) -> dict:
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "industry": self.industry,
            "mentions": self.mentions,
            "avg_sentiment": self.avg_sentiment,
            "signal_strength": self.signal_strength,
            "keywords": list(self.keywords),
        }


class NewsAnalyzer:
    """
    Integrated news analyzer.

    Combines keyword extraction, sentiment analysis, and stock mapping
    to generate trading signals from news articles.

    Now with dynamic trend tracking for automatic keyword discovery.
    """

    def __init__(
        self,
        keyword_extractor: Optional[KeywordExtractor] = None,
        sentiment_analyzer: Optional[SentimentAnalyzer] = None,
        stock_mapper: Optional[StockMapper] = None,
        config: Optional[dict] = None,
        enable_trends: bool = True,
    ):
        """
        Initialize news analyzer.

        Args:
            keyword_extractor: Optional custom keyword extractor
            sentiment_analyzer: Optional custom sentiment analyzer
            stock_mapper: Optional custom stock mapper
            config: Optional configuration dictionary
            enable_trends: Enable dynamic trend tracking
        """
        config = config or {}
        keyword_config = config.get("keyword_extraction", {})
        sentiment_config = config.get("sentiment", {})
        trend_config = config.get("trends", {})

        # Initialize components
        self.keyword_extractor = keyword_extractor or KeywordExtractor(
            method=keyword_config.get("method", "combined"),
            min_keyword_length=keyword_config.get("min_keyword_length", 2),
            top_n=keyword_config.get("top_n", 10),
            keybert_threshold=keyword_config.get("keybert_threshold", 0.5),
            use_financial_filter=keyword_config.get("use_financial_filter", True),
        )

        self.sentiment_analyzer = sentiment_analyzer or SentimentAnalyzer(
            model_name=sentiment_config.get("model"),
            use_model=True,
        )

        self.stock_mapper = stock_mapper or StockMapper(
            mapping_file=config.get("mapping_file", "config/keywords_mapping.yaml"),
        )

        # Initialize trend tracking
        self.enable_trends = enable_trends
        if enable_trends:
            self.trend_tracker = TrendTracker(
                data_dir=trend_config.get("data_dir", "./data/trends"),
                window_hours=trend_config.get("window_hours", 24),
                min_count=trend_config.get("min_count", 3),
                trend_threshold=trend_config.get("trend_threshold", 2.0),
            )
            self.dynamic_mapper = DynamicStockMapper(
                static_mapper=self.stock_mapper,
                cache_dir=trend_config.get("cache_dir", "./data/stock_cache"),
                discovery_enabled=True,
            )
        else:
            self.trend_tracker = None
            self.dynamic_mapper = None

    def analyze_article(self, article: NewsArticle) -> ArticleAnalysis:
        """
        Analyze a single news article.

        Args:
            article: NewsArticle to analyze

        Returns:
            ArticleAnalysis with keywords, sentiment, and related stocks
        """
        text = article.text

        # Extract keywords
        keywords = self.keyword_extractor.extract(text)

        # Analyze sentiment
        sentiment = self.sentiment_analyzer.analyze(text)

        # Find related stocks
        related_stocks = self.stock_mapper.find_stocks(keywords)

        # Update article with analysis results
        article.keywords = keywords
        article.sentiment_score = sentiment.score

        analysis_log(
            f"Analyzed: {article.title[:50]}... "
            f"| Keywords: {len(keywords)} | Sentiment: {sentiment.label.value} "
            f"| Related stocks: {len(related_stocks)}"
        )

        return ArticleAnalysis(
            article=article,
            keywords=keywords,
            sentiment=sentiment,
            related_stocks=related_stocks,
        )

    def analyze_batch(self, articles: List[NewsArticle]) -> List[ArticleAnalysis]:
        """
        Analyze multiple news articles.

        Args:
            articles: List of NewsArticle objects

        Returns:
            List of ArticleAnalysis objects
        """
        results = []
        extracted_keywords: Dict[str, List[str]] = {}

        for article in articles:
            try:
                analysis = self.analyze_article(article)
                results.append(analysis)
                extracted_keywords[article.url] = analysis.keywords
            except Exception as e:
                logger.warning(f"Failed to analyze article: {e}")
                continue

        # Update trend tracking
        if self.enable_trends and self.trend_tracker and results:
            self.trend_tracker.update(articles, extracted_keywords)

            # Update dynamic mapper with learned associations
            if self.dynamic_mapper:
                texts = [a.text for a in articles]
                keywords_list = [extracted_keywords.get(a.url, []) for a in articles]
                self.dynamic_mapper.update_from_articles(texts, keywords_list)

        logger.info(f"Analyzed {len(results)}/{len(articles)} articles")
        return results

    def aggregate_signals(
        self,
        analyses: List[ArticleAnalysis],
    ) -> Dict[str, TradingSignal]:
        """
        Aggregate article analyses into trading signals per stock.

        Args:
            analyses: List of ArticleAnalysis objects

        Returns:
            Dictionary of stock_code -> TradingSignal
        """
        signals: Dict[str, TradingSignal] = {}

        for analysis in analyses:
            sentiment_score = analysis.sentiment.score

            for stock, match_count in analysis.related_stocks:
                code = stock.stock_code

                if code not in signals:
                    signals[code] = TradingSignal(
                        stock_code=code,
                        stock_name=stock.stock_name,
                        industry=stock.industry,
                    )

                signal = signals[code]
                signal.mentions += match_count
                signal.sentiment_sum += sentiment_score * match_count
                signal.keywords.update(analysis.keywords[:5])
                signal.articles.append(analysis.article)

        # Sort by signal strength
        sorted_signals = dict(
            sorted(
                signals.items(),
                key=lambda x: x[1].signal_strength,
                reverse=True,
            )
        )

        logger.info(f"Generated signals for {len(sorted_signals)} stocks")
        return sorted_signals

    def get_top_signals(
        self,
        signals: Dict[str, TradingSignal],
        min_mentions: int = 2,
        min_sentiment: Optional[float] = None,
        limit: int = 10,
    ) -> List[TradingSignal]:
        """
        Get top trading signals filtered by criteria.

        Args:
            signals: Dictionary of signals
            min_mentions: Minimum mention count
            min_sentiment: Minimum average sentiment (optional)
            limit: Maximum signals to return

        Returns:
            List of top TradingSignal objects
        """
        filtered = []

        for signal in signals.values():
            if signal.mentions < min_mentions:
                continue
            if min_sentiment is not None and signal.avg_sentiment < min_sentiment:
                continue
            filtered.append(signal)

        # Sort by signal strength
        filtered.sort(key=lambda x: x.signal_strength, reverse=True)

        return filtered[:limit]

    def generate_report(
        self,
        analyses: List[ArticleAnalysis],
        signals: Dict[str, TradingSignal],
    ) -> dict:
        """
        Generate an analysis report.

        Args:
            analyses: List of article analyses
            signals: Dictionary of trading signals

        Returns:
            Report dictionary
        """
        # Collect all keywords
        all_keywords = []
        for analysis in analyses:
            all_keywords.extend(analysis.keywords)

        # Count keyword frequencies
        keyword_counts = Counter(all_keywords)
        top_keywords = [kw for kw, _ in keyword_counts.most_common(20)]

        # Top stocks by mentions
        top_stocks = sorted(
            signals.values(),
            key=lambda x: x.mentions,
            reverse=True,
        )[:10]

        # Sentiment distribution
        positive_count = sum(
            1 for a in analyses
            if a.sentiment.score > 0.2
        )
        negative_count = sum(
            1 for a in analyses
            if a.sentiment.score < -0.2
        )
        neutral_count = len(analyses) - positive_count - negative_count

        report = {
            "article_count": len(analyses),
            "top_keywords": top_keywords,
            "top_stocks": [s.stock_name for s in top_stocks],
            "sentiment_distribution": {
                "positive": positive_count,
                "negative": negative_count,
                "neutral": neutral_count,
            },
            "signals": [s.to_dict() for s in top_stocks],
        }

        # Add trend information if available
        if self.enable_trends and self.trend_tracker:
            trending = self.get_trending_keywords(limit=10)
            emerging = self.get_emerging_issues(limit=5)

            report["trending_keywords"] = [
                {"keyword": t.keyword, "count": t.count, "trend_score": t.trend_score}
                for t in trending
            ]
            report["emerging_issues"] = [
                {"keyword": e.keyword, "count": e.count, "sentiment": e.sentiment_avg}
                for e in emerging
            ]

        return report

    # ========================================
    # Trend-based methods
    # ========================================

    def get_trending_keywords(
        self,
        limit: int = 20,
        min_trend_score: Optional[float] = None,
    ) -> List[TrendingKeyword]:
        """
        Get currently trending keywords.

        Args:
            limit: Maximum keywords to return
            min_trend_score: Minimum trend score

        Returns:
            List of TrendingKeyword objects
        """
        if not self.enable_trends or not self.trend_tracker:
            return []
        return self.trend_tracker.get_trending_keywords(limit, min_trend_score)

    def get_emerging_issues(self, limit: int = 10) -> List[TrendingKeyword]:
        """
        Get newly emerging issues.

        Args:
            limit: Maximum issues to return

        Returns:
            List of TrendingKeyword objects representing emerging issues
        """
        if not self.enable_trends or not self.trend_tracker:
            return []
        return self.trend_tracker.get_emerging_issues(limit)

    def get_trend_based_signals(
        self,
        limit: int = 10,
    ) -> List[DynamicStockMatch]:
        """
        Get trading signals based on trending keywords.

        This method finds stocks that are associated with currently
        trending keywords, providing dynamic signal generation.

        Args:
            limit: Maximum signals to return

        Returns:
            List of DynamicStockMatch objects
        """
        if not self.enable_trends or not self.dynamic_mapper:
            return []

        # Get trending keywords
        trending = self.get_trending_keywords(limit=30)
        if not trending:
            return []

        # Map to stocks
        matches = self.dynamic_mapper.map_trending_keywords(trending)

        analysis_log(
            f"Trend-based signals: {len(trending)} trending keywords -> "
            f"{len(matches)} stock matches"
        )

        return matches[:limit]

    def aggregate_signals_with_trends(
        self,
        analyses: List[ArticleAnalysis],
    ) -> Dict[str, TradingSignal]:
        """
        Aggregate signals combining static and trend-based analysis.

        Args:
            analyses: List of ArticleAnalysis objects

        Returns:
            Dictionary of stock_code -> TradingSignal
        """
        # Get base signals from static analysis
        signals = self.aggregate_signals(analyses)

        # Enhance with trend-based signals if enabled
        if self.enable_trends and self.dynamic_mapper:
            trend_matches = self.get_trend_based_signals(limit=20)

            for match in trend_matches:
                code = match.stock_code

                if code not in signals:
                    signals[code] = TradingSignal(
                        stock_code=code,
                        stock_name=match.stock_name,
                        industry=match.industry,
                    )

                signal = signals[code]
                # Boost signal with trend data
                signal.mentions += int(match.trend_score)
                signal.sentiment_sum += match.sentiment_avg * match.trend_score
                signal.keywords.update(match.matched_keywords)

            # Re-sort by signal strength
            signals = dict(
                sorted(
                    signals.items(),
                    key=lambda x: x[1].signal_strength,
                    reverse=True,
                )
            )

        return signals

    def get_trend_summary(self) -> dict:
        """Get summary of current trends."""
        if not self.enable_trends or not self.trend_tracker:
            return {"enabled": False}

        summary = self.trend_tracker.get_summary()
        summary["enabled"] = True

        if self.dynamic_mapper:
            summary["dynamic_mapper"] = self.dynamic_mapper.get_summary()

        return summary
