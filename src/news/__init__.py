"""
News collection module.

Provides collectors for various Korean news sources and an aggregator
to combine them with deduplication and caching.
"""
from src.news.aggregator import NewsAggregator, NewsCache
from src.news.base import NewsArticle, NewsCollector
from src.news.bigkinds import BigKindsCollector
from src.news.maekyung import MaekyungCollector
from src.news.newneek import NewneekCollector
from src.news.uppity import UppityCollector

__all__ = [
    "NewsArticle",
    "NewsCollector",
    "NewsAggregator",
    "NewsCache",
    "NewneekCollector",
    "UppityCollector",
    "MaekyungCollector",
    "BigKindsCollector",
]
