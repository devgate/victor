"""
Historical price data provider for backtesting.
Uses FinanceDataReader for Korean stock OHLCV data with file caching.
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PriceDataProvider:
    """Provides historical stock price data with file caching."""

    def __init__(self, cache_dir: str = "./data/price_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._fdr = None

    def _get_fdr(self):
        """Lazy-load FinanceDataReader."""
        if self._fdr is None:
            try:
                import FinanceDataReader as fdr
                self._fdr = fdr
            except ImportError:
                raise ImportError(
                    "FinanceDataReader is required for backtesting. "
                    "Install it with: pip install finance-datareader"
                )
        return self._fdr

    def _cache_path(self, stock_code: str) -> Path:
        return self.cache_dir / f"{stock_code}.json"

    def _load_cache(self, stock_code: str) -> Dict[str, dict]:
        """Load cached price data for a stock."""
        path = self._cache_path(stock_code)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self, stock_code: str, data: Dict[str, dict]) -> None:
        """Save price data to cache."""
        path = self._cache_path(stock_code)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def get_prices(
        self,
        stock_code: str,
        start_date: date,
        end_date: date,
    ) -> Dict[str, dict]:
        """
        Get OHLCV price data for a stock in a date range.

        Returns:
            Dict of date_str -> {"open", "high", "low", "close", "volume"}
        """
        cache = self._load_cache(stock_code)

        # Check which dates are missing
        missing_start = None
        missing_end = None
        current = start_date
        while current <= end_date:
            date_str = current.isoformat()
            if date_str not in cache:
                if missing_start is None:
                    missing_start = current
                missing_end = current
            current += timedelta(days=1)

        # Fetch missing data
        if missing_start is not None:
            self._fetch_and_cache(
                stock_code,
                missing_start - timedelta(days=5),  # buffer for holidays
                missing_end + timedelta(days=1),
                cache,
            )

        # Filter to requested range
        result = {}
        current = start_date
        while current <= end_date:
            date_str = current.isoformat()
            if date_str in cache:
                result[date_str] = cache[date_str]
            current += timedelta(days=1)

        return result

    def _fetch_and_cache(
        self,
        stock_code: str,
        start: date,
        end: date,
        cache: Dict[str, dict],
    ) -> None:
        """Fetch price data from FinanceDataReader and update cache."""
        fdr = self._get_fdr()
        try:
            df = fdr.DataReader(
                stock_code,
                start.isoformat(),
                end.isoformat(),
            )

            if df is None or df.empty:
                logger.warning(f"No price data for {stock_code} ({start} ~ {end})")
                return

            for idx, row in df.iterrows():
                date_str = idx.strftime("%Y-%m-%d")
                cache[date_str] = {
                    "open": float(row.get("Open", 0)),
                    "high": float(row.get("High", 0)),
                    "low": float(row.get("Low", 0)),
                    "close": float(row.get("Close", 0)),
                    "volume": int(row.get("Volume", 0)),
                }

            self._save_cache(stock_code, cache)
            logger.info(
                f"Fetched {len(df)} price records for {stock_code} "
                f"({start} ~ {end})"
            )

        except Exception as e:
            logger.warning(f"Failed to fetch price data for {stock_code}: {e}")

    def get_price_on_date(
        self,
        stock_code: str,
        target_date: date,
    ) -> Optional[float]:
        """
        Get closing price on a specific date.
        Falls back to previous trading day if target_date is a holiday.

        Returns:
            Closing price or None
        """
        # Try up to 7 days back for holidays/weekends
        for i in range(7):
            d = target_date - timedelta(days=i)
            prices = self.get_prices(stock_code, d, d)
            date_str = d.isoformat()
            if date_str in prices:
                return prices[date_str]["close"]

        logger.warning(f"No price found for {stock_code} near {target_date}")
        return None
