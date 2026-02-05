"""
Analysis module for news processing.

Provides keyword extraction, sentiment analysis, stock mapping,
and integrated analysis for generating trading signals.

Now includes dynamic trend tracking for automatic keyword discovery.
"""
from src.analysis.analyzer import ArticleAnalysis, NewsAnalyzer, TradingSignal
from src.analysis.dynamic_mapper import DynamicStockMapper, DynamicStockMatch
from src.analysis.keyword_extractor import KeywordExtractor
from src.analysis.sentiment import SentimentAnalyzer, SentimentLabel, SentimentResult
from src.analysis.stock_mapper import StockMapper, StockMapping, StockSignal
from src.analysis.trend_tracker import TrendingKeyword, TrendTracker

__all__ = [
    "KeywordExtractor",
    "SentimentAnalyzer",
    "SentimentLabel",
    "SentimentResult",
    "StockMapper",
    "StockMapping",
    "StockSignal",
    "NewsAnalyzer",
    "ArticleAnalysis",
    "TradingSignal",
    "TrendTracker",
    "TrendingKeyword",
    "DynamicStockMapper",
    "DynamicStockMatch",
]
