"""
News collection module.

Provides collectors for various Korean news sources and an aggregator
to combine them with deduplication and caching.
"""
from src.news.aggregator import NewsAggregator, NewsCache
from src.news.base import NewsArticle, NewsCollector
from src.news.edaily import EdailyCollector
from src.news.hankyung import HankyungCollector
from src.news.maekyung import MaekyungCollector
from src.news.newneek import NewneekCollector
from src.news.uppity import UppityCollector
from src.news.yonhap import YonhapCollector

__all__ = [
    "NewsArticle",
    "NewsCollector",
    "NewsAggregator",
    "NewsCache",
    "NewneekCollector",
    "UppityCollector",
    "MaekyungCollector",
    "HankyungCollector",
    "EdailyCollector",
    "YonhapCollector",
]
