"""
Stock mapper module for mapping keywords to stock codes.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import yaml

from src.utils.exceptions import StockMappingError
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class StockMapping:
    """Represents a stock with its associated keywords."""
    stock_code: str
    stock_name: str
    industry: str
    keywords: List[str]
    weight: float = 1.0

    def matches_keyword(self, keyword: str) -> bool:
        """Check if keyword matches this stock."""
        keyword_lower = keyword.lower()
        return any(
            kw.lower() == keyword_lower or keyword_lower in kw.lower()
            for kw in self.keywords
        )


@dataclass
class StockSignal:
    """Aggregated signal for a stock."""
    stock_code: str
    stock_name: str
    industry: str
    match_count: int = 0
    matched_keywords: Set[str] = field(default_factory=set)
    sentiment_sum: float = 0.0
    mention_count: int = 0

    @property
    def avg_sentiment(self) -> float:
        """Average sentiment score."""
        if self.mention_count == 0:
            return 0.0
        return self.sentiment_sum / self.mention_count

    @property
    def relevance_score(self) -> float:
        """Overall relevance score based on matches and sentiment."""
        return self.match_count * (1 + self.avg_sentiment)


class StockMapper:
    """
    Maps keywords to related stocks.

    Uses a YAML configuration file to define keyword-stock mappings.
    Supports exact matching and fuzzy matching for keywords.
    """

    def __init__(self, mapping_file: Optional[str] = None):
        """
        Initialize stock mapper.

        Args:
            mapping_file: Path to keywords_mapping.yaml
        """
        self.mapping_file = mapping_file
        self._stocks: List[StockMapping] = []
        self._keyword_index: Dict[str, List[StockMapping]] = {}
        self._industry_keywords: Dict[str, List[str]] = {}
        self._sentiment_keywords: Dict[str, List[str]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Ensure mappings are loaded."""
        if self._loaded:
            return

        if self.mapping_file:
            self._load_from_file(self.mapping_file)
        else:
            self._load_default()

        self._build_index()
        self._loaded = True

    def _load_from_file(self, path: str) -> None:
        """Load mappings from YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            logger.warning(f"Mapping file not found: {path}")
            self._load_default()
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # Load stock mappings
            for stock_data in data.get("stocks", []):
                mapping = StockMapping(
                    stock_code=stock_data["stock_code"],
                    stock_name=stock_data["stock_name"],
                    industry=stock_data.get("industry", ""),
                    keywords=stock_data.get("keywords", []),
                    weight=stock_data.get("weight", 1.0),
                )
                self._stocks.append(mapping)

            # Load industry keywords
            self._industry_keywords = data.get("industries", {})

            # Load sentiment keywords
            self._sentiment_keywords = data.get("sentiment_keywords", {})

            logger.info(f"Loaded {len(self._stocks)} stock mappings from {path}")

        except Exception as e:
            raise StockMappingError(f"Failed to load mappings: {e}", cause=e)

    def _load_default(self) -> None:
        """Load default stock mappings."""
        # Minimal default mappings for major Korean stocks
        defaults = [
            ("005930", "Samsung Electronics", "semiconductor", [
                "Samsung", "Samsung Electronics", "Galaxy", "semiconductor"
            ]),
            ("000660", "SK Hynix", "semiconductor", [
                "SK Hynix", "Hynix", "HBM", "memory"
            ]),
            ("035420", "NAVER", "internet", [
                "NAVER", "Naver", "search", "LINE"
            ]),
            ("035720", "Kakao", "internet", [
                "Kakao", "KakaoTalk"
            ]),
        ]

        for code, name, industry, keywords in defaults:
            self._stocks.append(StockMapping(
                stock_code=code,
                stock_name=name,
                industry=industry,
                keywords=keywords,
            ))

        logger.info(f"Loaded {len(self._stocks)} default stock mappings")

    def _build_index(self) -> None:
        """Build keyword to stock index."""
        self._keyword_index.clear()

        for stock in self._stocks:
            for keyword in stock.keywords:
                keyword_lower = keyword.lower()
                if keyword_lower not in self._keyword_index:
                    self._keyword_index[keyword_lower] = []
                self._keyword_index[keyword_lower].append(stock)

        # Add industry keywords to stock mappings
        for stock in self._stocks:
            industry = stock.industry.lower()
            if industry in self._industry_keywords:
                for keyword in self._industry_keywords[industry]:
                    keyword_lower = keyword.lower()
                    if keyword_lower not in self._keyword_index:
                        self._keyword_index[keyword_lower] = []
                    if stock not in self._keyword_index[keyword_lower]:
                        self._keyword_index[keyword_lower].append(stock)

    def find_stocks(
        self,
        keywords: List[str],
    ) -> List[Tuple[StockMapping, int]]:
        """
        Find stocks related to given keywords.

        Args:
            keywords: List of keywords to match

        Returns:
            List of (StockMapping, match_count) tuples, sorted by match count
        """
        self._ensure_loaded()

        stock_matches: Dict[str, Tuple[StockMapping, int]] = {}

        for keyword in keywords:
            keyword_lower = keyword.lower()

            # Exact match
            if keyword_lower in self._keyword_index:
                for stock in self._keyword_index[keyword_lower]:
                    if stock.stock_code not in stock_matches:
                        stock_matches[stock.stock_code] = (stock, 0)
                    current = stock_matches[stock.stock_code]
                    stock_matches[stock.stock_code] = (current[0], current[1] + 1)

            # Partial match (keyword contained in indexed keyword)
            else:
                for indexed_kw, stocks in self._keyword_index.items():
                    if keyword_lower in indexed_kw or indexed_kw in keyword_lower:
                        for stock in stocks:
                            if stock.stock_code not in stock_matches:
                                stock_matches[stock.stock_code] = (stock, 0)
                            current = stock_matches[stock.stock_code]
                            stock_matches[stock.stock_code] = (current[0], current[1] + 1)

        # Sort by match count (descending)
        results = list(stock_matches.values())
        results.sort(key=lambda x: x[1], reverse=True)

        return results

    def get_stock(self, stock_code: str) -> Optional[StockMapping]:
        """
        Get stock mapping by code.

        Args:
            stock_code: Stock code to look up

        Returns:
            StockMapping or None
        """
        self._ensure_loaded()

        for stock in self._stocks:
            if stock.stock_code == stock_code:
                return stock
        return None

    def get_all_stocks(self) -> List[StockMapping]:
        """Get all stock mappings."""
        self._ensure_loaded()
        return self._stocks.copy()

    def is_positive_keyword(self, keyword: str) -> bool:
        """Check if keyword indicates positive sentiment."""
        self._ensure_loaded()
        positive = self._sentiment_keywords.get("positive", [])
        return keyword.lower() in [kw.lower() for kw in positive]

    def is_negative_keyword(self, keyword: str) -> bool:
        """Check if keyword indicates negative sentiment."""
        self._ensure_loaded()
        negative = self._sentiment_keywords.get("negative", [])
        return keyword.lower() in [kw.lower() for kw in negative]

    def aggregate_signals(
        self,
        stock_matches: List[Tuple[StockMapping, int]],
        keywords: List[str],
        sentiment_score: float = 0.0,
    ) -> Dict[str, StockSignal]:
        """
        Aggregate stock signals from matches.

        Args:
            stock_matches: List of (StockMapping, match_count)
            keywords: Original keywords
            sentiment_score: Overall sentiment score

        Returns:
            Dictionary of stock_code -> StockSignal
        """
        signals: Dict[str, StockSignal] = {}

        for stock, match_count in stock_matches:
            if stock.stock_code not in signals:
                signals[stock.stock_code] = StockSignal(
                    stock_code=stock.stock_code,
                    stock_name=stock.stock_name,
                    industry=stock.industry,
                )

            signal = signals[stock.stock_code]
            signal.match_count += match_count
            signal.sentiment_sum += sentiment_score
            signal.mention_count += 1

            # Track matched keywords
            for keyword in keywords:
                if stock.matches_keyword(keyword):
                    signal.matched_keywords.add(keyword)

        return signals
