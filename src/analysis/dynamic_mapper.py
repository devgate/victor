"""
Dynamic stock mapper that discovers stocks based on trending keywords.
Uses web search and stock databases to find relevant stocks automatically.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from src.analysis.stock_mapper import StockMapper, StockMapping
from src.analysis.trend_tracker import TrendTracker, TrendingKeyword
from src.utils.logger import analysis_log, get_logger

logger = get_logger(__name__)


@dataclass
class DynamicStockMatch:
    """Represents a dynamically discovered stock match."""
    stock_code: str
    stock_name: str
    industry: str
    matched_keywords: Set[str] = field(default_factory=set)
    trend_score: float = 0.0
    sentiment_avg: float = 0.0
    confidence: float = 0.0  # How confident we are in this match
    source: str = "dynamic"  # "static" or "dynamic"

    def to_dict(self) -> dict:
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "industry": self.industry,
            "matched_keywords": list(self.matched_keywords),
            "trend_score": self.trend_score,
            "sentiment_avg": self.sentiment_avg,
            "confidence": self.confidence,
            "source": self.source,
        }


# Korean stock name patterns for extraction from news
STOCK_PATTERNS = [
    # Company suffixes
    r"([가-힣A-Za-z0-9]+)(전자|반도체|바이오|제약|화학|건설|증권|은행|보험|카드)",
    r"([가-힣A-Za-z0-9]+)(그룹|홀딩스|인터내셔널)",
    # Common company names
    r"(삼성|SK|LG|현대|기아|네이버|카카오|셀트리온|삼바|포스코|한화|롯데|CJ|KT|두산)",
]


class DynamicStockMapper:
    """
    Dynamic stock mapper that discovers stocks from trending keywords.

    Features:
    - Extracts stock names from news text
    - Maps trending keywords to relevant stocks
    - Combines static mappings with dynamic discovery
    - Learns new keyword-stock associations over time
    """

    def __init__(
        self,
        static_mapper: Optional[StockMapper] = None,
        cache_dir: str = "./data/stock_cache",
        discovery_enabled: bool = True,
    ):
        """
        Initialize dynamic stock mapper.

        Args:
            static_mapper: Optional static StockMapper for base mappings
            cache_dir: Directory to cache discovered mappings
            discovery_enabled: Enable dynamic stock discovery
        """
        self.static_mapper = static_mapper or StockMapper()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.discovery_enabled = discovery_enabled

        # Dynamic mappings learned from news
        self._dynamic_mappings: Dict[str, DynamicStockMatch] = {}
        self._keyword_to_stocks: Dict[str, Set[str]] = {}  # keyword -> stock_codes

        # Stock name to code mapping (for extraction)
        self._name_to_code: Dict[str, str] = {}

        # Load cached data
        self._load_cache()
        self._build_name_index()

    def _get_cache_file(self) -> Path:
        """Get cache file path."""
        return self.cache_dir / "dynamic_mappings.json"

    def _load_cache(self) -> None:
        """Load cached dynamic mappings."""
        cache_file = self._get_cache_file()
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for stock_code, match_data in data.get("mappings", {}).items():
                    self._dynamic_mappings[stock_code] = DynamicStockMatch(
                        stock_code=match_data["stock_code"],
                        stock_name=match_data["stock_name"],
                        industry=match_data.get("industry", ""),
                        matched_keywords=set(match_data.get("matched_keywords", [])),
                        trend_score=match_data.get("trend_score", 0),
                        sentiment_avg=match_data.get("sentiment_avg", 0),
                        confidence=match_data.get("confidence", 0.5),
                        source=match_data.get("source", "dynamic"),
                    )

                self._keyword_to_stocks = {
                    k: set(v) for k, v in data.get("keyword_to_stocks", {}).items()
                }

                logger.debug(f"Loaded {len(self._dynamic_mappings)} cached mappings")

                # Apply confidence decay on load
                self._decay_confidence()
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

    def _save_cache(self) -> None:
        """Save dynamic mappings to cache."""
        cache_file = self._get_cache_file()
        try:
            data = {
                "mappings": {
                    code: match.to_dict()
                    for code, match in self._dynamic_mappings.items()
                },
                "keyword_to_stocks": {
                    k: list(v) for k, v in self._keyword_to_stocks.items()
                },
                "updated_at": datetime.now().isoformat(),
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _decay_confidence(self) -> None:
        """Lower confidence of associations not reinforced recently."""
        stale_codes = []
        for stock_code, match in self._dynamic_mappings.items():
            # Decay confidence by 10%
            match.confidence *= 0.9
            # Mark for removal if too low
            if match.confidence < 0.1:
                stale_codes.append(stock_code)

        for code in stale_codes:
            removed = self._dynamic_mappings.pop(code, None)
            if removed:
                for kw in removed.matched_keywords:
                    kw_lower = kw.lower()
                    if kw_lower in self._keyword_to_stocks:
                        self._keyword_to_stocks[kw_lower].discard(code)
                        if not self._keyword_to_stocks[kw_lower]:
                            del self._keyword_to_stocks[kw_lower]

        if stale_codes:
            logger.info(f"Removed {len(stale_codes)} stale dynamic mappings")
            self._save_cache()

    def _build_name_index(self) -> None:
        """Build stock name to code index from static mapper."""
        for stock in self.static_mapper.get_all_stocks():
            # Index by name
            name_lower = stock.stock_name.lower()
            self._name_to_code[name_lower] = stock.stock_code

            # Index by keywords
            for keyword in stock.keywords:
                keyword_lower = keyword.lower()
                self._name_to_code[keyword_lower] = stock.stock_code

    def extract_stock_mentions(self, text: str) -> List[Tuple[str, str]]:
        """
        Extract stock mentions from text.

        Args:
            text: News article text

        Returns:
            List of (stock_name, stock_code) tuples
        """
        mentions = []
        text_lower = text.lower()

        # Check against known stock names
        for name, code in self._name_to_code.items():
            if name in text_lower:
                mentions.append((name, code))

        # Check against patterns
        for pattern in STOCK_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    company_name = "".join(match)
                else:
                    company_name = match

                # Try to find in name index
                name_lower = company_name.lower()
                if name_lower in self._name_to_code:
                    mentions.append((company_name, self._name_to_code[name_lower]))

        # Remove duplicates
        seen = set()
        unique_mentions = []
        for name, code in mentions:
            if code not in seen:
                seen.add(code)
                unique_mentions.append((name, code))

        return unique_mentions

    def map_trending_keywords(
        self,
        trending: List[TrendingKeyword],
    ) -> List[DynamicStockMatch]:
        """
        Map trending keywords to stocks.

        Args:
            trending: List of trending keywords

        Returns:
            List of DynamicStockMatch objects
        """
        stock_scores: Dict[str, DynamicStockMatch] = {}

        for trend in trending:
            keyword = trend.keyword
            keyword_lower = keyword.lower()

            # 1. Check static mappings first
            static_matches = self.static_mapper.find_stocks([keyword])
            for stock, match_count in static_matches:
                if stock.stock_code not in stock_scores:
                    stock_scores[stock.stock_code] = DynamicStockMatch(
                        stock_code=stock.stock_code,
                        stock_name=stock.stock_name,
                        industry=stock.industry,
                        source="static",
                    )

                match = stock_scores[stock.stock_code]
                match.matched_keywords.add(keyword)
                match.trend_score = max(match.trend_score, trend.trend_score)
                match.sentiment_avg = (match.sentiment_avg + trend.sentiment_avg) / 2
                match.confidence = min(match.confidence + 0.1, 1.0)

            # 2. Check dynamic keyword mappings
            if keyword_lower in self._keyword_to_stocks:
                for stock_code in self._keyword_to_stocks[keyword_lower]:
                    if stock_code in self._dynamic_mappings:
                        dyn_match = self._dynamic_mappings[stock_code]
                        if stock_code not in stock_scores:
                            stock_scores[stock_code] = DynamicStockMatch(
                                stock_code=dyn_match.stock_code,
                                stock_name=dyn_match.stock_name,
                                industry=dyn_match.industry,
                                source="dynamic",
                            )

                        match = stock_scores[stock_code]
                        match.matched_keywords.add(keyword)
                        match.trend_score = max(match.trend_score, trend.trend_score)
                        match.sentiment_avg = (match.sentiment_avg + trend.sentiment_avg) / 2

            # 3. Check if keyword is a stock name
            if keyword_lower in self._name_to_code:
                stock_code = self._name_to_code[keyword_lower]
                stock = self.static_mapper.get_stock(stock_code)
                if stock and stock_code not in stock_scores:
                    stock_scores[stock_code] = DynamicStockMatch(
                        stock_code=stock_code,
                        stock_name=stock.stock_name,
                        industry=stock.industry,
                        matched_keywords={keyword},
                        trend_score=trend.trend_score,
                        sentiment_avg=trend.sentiment_avg,
                        confidence=0.9,
                        source="static",
                    )

        # Sort by trend_score * confidence
        results = list(stock_scores.values())
        results.sort(key=lambda x: x.trend_score * (1 + len(x.matched_keywords)) * x.confidence, reverse=True)

        return results

    def learn_association(
        self,
        keyword: str,
        stock_code: str,
        stock_name: str,
        industry: str = "",
        confidence: float = 0.5,
    ) -> None:
        """
        Learn a new keyword-stock association.

        Args:
            keyword: Keyword to associate
            stock_code: Stock code
            stock_name: Stock name
            industry: Stock industry
            confidence: Confidence in this association
        """
        keyword_lower = keyword.lower()

        # Reinforce existing association instead of re-adding
        if stock_code in self._dynamic_mappings:
            existing = self._dynamic_mappings[stock_code]
            if keyword in existing.matched_keywords:
                existing.confidence = min(existing.confidence + 0.05, 0.9)
                return

        # Cap keywords per stock to prevent pollution
        if stock_code in self._dynamic_mappings:
            if len(self._dynamic_mappings[stock_code].matched_keywords) >= 30:
                return

        # Update dynamic mappings
        if stock_code not in self._dynamic_mappings:
            self._dynamic_mappings[stock_code] = DynamicStockMatch(
                stock_code=stock_code,
                stock_name=stock_name,
                industry=industry,
                confidence=confidence,
                source="dynamic",
            )

        self._dynamic_mappings[stock_code].matched_keywords.add(keyword)

        # Update keyword index
        if keyword_lower not in self._keyword_to_stocks:
            self._keyword_to_stocks[keyword_lower] = set()
        self._keyword_to_stocks[keyword_lower].add(stock_code)

        # Only update name index for actual stock names, not keywords
        self._name_to_code[stock_name.lower()] = stock_code

        analysis_log(f"Learned association: '{keyword}' -> {stock_name} ({stock_code})")

        # Save cache
        self._save_cache()

    def _is_proximate(self, text: str, keyword: str, stock_name: str) -> bool:
        """
        Check if keyword appears near stock name in text.

        Args:
            text: Full article text
            keyword: Keyword to check
            stock_name: Stock name to check proximity with

        Returns:
            True if keyword and stock name appear in the same sentence
        """
        sentences = re.split(r'[.。!?\n]', text)
        for sentence in sentences:
            if stock_name.lower() in sentence.lower() and keyword in sentence:
                return True
        return False

    def update_from_articles(
        self,
        articles_text: List[str],
        keywords_per_article: List[List[str]],
    ) -> None:
        """
        Update dynamic mappings by analyzing articles.

        Only learns associations where the keyword appears in the same
        sentence as the stock name and passes financial domain filtering.

        Args:
            articles_text: List of article texts
            keywords_per_article: Keywords extracted from each article
        """
        if not self.discovery_enabled:
            return

        from src.analysis.keyword_extractor import KOREAN_STOP_WORDS, FINANCIAL_DOMAIN_TERMS

        for text, keywords in zip(articles_text, keywords_per_article):
            # Extract stock mentions from text
            mentions = self.extract_stock_mentions(text)
            if not mentions:
                continue

            # Associate keywords with mentioned stocks (with quality gates)
            for stock_name, stock_code in mentions:
                stock = self.static_mapper.get_stock(stock_code)
                if not stock:
                    continue

                for keyword in keywords:
                    # Gate 1: Minimum length
                    if len(keyword) < 2:
                        continue

                    # Gate 2: Not a stop word
                    if keyword in KOREAN_STOP_WORDS:
                        continue

                    # Gate 3: Proximity check - keyword must be in same sentence
                    if not self._is_proximate(text, keyword, stock_name):
                        continue

                    # Gate 4: Financial relevance check
                    is_financial = keyword in FINANCIAL_DOMAIN_TERMS
                    if not is_financial:
                        # Also check partial match with financial terms
                        keyword_lower = keyword.lower()
                        is_financial = any(
                            term in keyword_lower or keyword_lower in term
                            for term in FINANCIAL_DOMAIN_TERMS
                            if len(term) >= 2 and len(keyword_lower) >= 2
                        )
                    # Allow 4+ char compound nouns even if not in financial terms
                    if not is_financial and len(keyword) < 4:
                        continue

                    self.learn_association(
                        keyword=keyword,
                        stock_code=stock_code,
                        stock_name=stock.stock_name,
                        industry=stock.industry,
                        confidence=0.4,
                    )

    def get_stocks_for_keywords(
        self,
        keywords: List[str],
    ) -> List[DynamicStockMatch]:
        """
        Get stocks related to given keywords.

        Args:
            keywords: List of keywords

        Returns:
            List of DynamicStockMatch objects
        """
        stock_matches: Dict[str, DynamicStockMatch] = {}

        for keyword in keywords:
            keyword_lower = keyword.lower()

            # Check static mapper
            static_matches = self.static_mapper.find_stocks([keyword])
            for stock, match_count in static_matches:
                if stock.stock_code not in stock_matches:
                    stock_matches[stock.stock_code] = DynamicStockMatch(
                        stock_code=stock.stock_code,
                        stock_name=stock.stock_name,
                        industry=stock.industry,
                        confidence=0.8,
                        source="static",
                    )
                stock_matches[stock.stock_code].matched_keywords.add(keyword)

            # Check dynamic mappings
            if keyword_lower in self._keyword_to_stocks:
                for stock_code in self._keyword_to_stocks[keyword_lower]:
                    if stock_code in self._dynamic_mappings:
                        dyn = self._dynamic_mappings[stock_code]
                        if stock_code not in stock_matches:
                            stock_matches[stock_code] = DynamicStockMatch(
                                stock_code=dyn.stock_code,
                                stock_name=dyn.stock_name,
                                industry=dyn.industry,
                                confidence=dyn.confidence,
                                source="dynamic",
                            )
                        stock_matches[stock_code].matched_keywords.add(keyword)

        results = list(stock_matches.values())
        results.sort(key=lambda x: len(x.matched_keywords) * x.confidence, reverse=True)
        return results

    def get_summary(self) -> dict:
        """Get summary of dynamic mappings."""
        return {
            "static_stocks": len(self.static_mapper.get_all_stocks()),
            "dynamic_stocks": len(self._dynamic_mappings),
            "learned_keywords": len(self._keyword_to_stocks),
            "discovery_enabled": self.discovery_enabled,
        }
