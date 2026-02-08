"""
Backtesting engine.
Replays archived articles through the analysis pipeline and simulates trading.
"""
from datetime import date, timedelta
from typing import Dict, List, Optional

from src.analysis.analyzer import NewsAnalyzer, TradingSignal
from src.backtest.archiver import ArticleArchiver
from src.backtest.portfolio import SimulatedPortfolio
from src.backtest.price_data import PriceDataProvider
from src.backtest.report import BacktestReport
from src.news.base import NewsArticle
from src.trading.strategy import TradeAction, TradingStrategy
from src.utils.logger import get_logger

logger = get_logger(__name__)


class BacktestEngine:
    """
    Backtesting engine that replays historical articles.

    Reuses existing NewsAnalyzer and TradingStrategy components
    but replaces KIS API with simulated portfolio and historical prices.
    """

    def __init__(
        self,
        config: dict,
        initial_cash: float = 500_000,
    ):
        """
        Initialize backtesting engine.

        Args:
            config: Full application config dict
            initial_cash: Starting cash amount
        """
        analysis_config = config.get("analysis", {})
        trading_config = config.get("trading", {})

        # Reuse existing analysis pipeline (trends disabled to prevent data leakage)
        self.analyzer = NewsAnalyzer(
            config=analysis_config,
            enable_trends=False,
        )

        # Reuse existing trading strategy
        self.strategy = TradingStrategy(trading_config)

        # Backtest-specific components
        self.archiver = ArticleArchiver()
        self.price_provider = PriceDataProvider()
        self.portfolio = SimulatedPortfolio(initial_cash=initial_cash)

        # Wire price getter for strategy
        self._current_sim_date: Optional[date] = None
        self.strategy.set_price_getter(self._get_price_for_strategy)

    def _get_price_for_strategy(self, stock_code: str) -> float:
        """Price getter compatible with TradingStrategy interface."""
        if self._current_sim_date is None:
            return 0.0
        price = self.price_provider.get_price_on_date(stock_code, self._current_sim_date)
        return price or 0.0

    def run(
        self,
        start_date: date,
        end_date: date,
    ) -> BacktestReport:
        """
        Run backtest over a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            BacktestReport with results
        """
        logger.info(f"Starting backtest: {start_date} ~ {end_date}")
        logger.info(f"Initial cash: {self.portfolio.initial_cash:,.0f} KRW")

        # Load all archived articles
        all_articles = self.archiver.load_articles(start_date, end_date)
        if not all_articles:
            logger.warning("No archived articles found for the date range")
            return BacktestReport(
                start_date=start_date,
                end_date=end_date,
                initial_cash=self.portfolio.initial_cash,
                portfolio=self.portfolio,
            )

        # Group articles by trading day (weekend articles carry over to Monday)
        articles_by_date: Dict[date, List[NewsArticle]] = {}
        for article in all_articles:
            d = article.published_at.date()
            # Move weekend articles to next Monday
            while d.weekday() >= 5:
                d += timedelta(days=1)
            articles_by_date.setdefault(d, []).append(article)

        # Determine actual date range (extend end to include carried-over articles)
        effective_end = end_date
        while effective_end.weekday() >= 5:
            effective_end += timedelta(days=1)

        # Process each trading day
        current = start_date
        days_processed = 0

        while current <= effective_end:
            self._current_sim_date = current

            # Skip weekends (no market)
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            day_articles = articles_by_date.get(current, [])

            if day_articles:
                self._process_day(current, day_articles)
                days_processed += 1

            # Record daily portfolio value
            self.portfolio.record_daily_value(
                current,
                lambda code, d=current: self.price_provider.get_price_on_date(code, d),
            )

            current += timedelta(days=1)

        logger.info(f"Backtest complete: {days_processed} trading days processed")

        return BacktestReport(
            start_date=start_date,
            end_date=end_date,
            initial_cash=self.portfolio.initial_cash,
            portfolio=self.portfolio,
        )

    def _process_day(self, sim_date: date, articles: List[NewsArticle]) -> None:
        """Process a single trading day."""
        logger.debug(f"[{sim_date}] Processing {len(articles)} articles")

        # 1. Analyze articles
        analyses = self.analyzer.analyze_batch(articles)
        if not analyses:
            return

        # 2. Aggregate signals (static only, no trends)
        signals = self.analyzer.aggregate_signals(analyses)
        if not signals:
            return

        # 3. Get current balance for strategy
        def price_getter(code):
            return self.price_provider.get_price_on_date(code, sim_date)

        balance = self.portfolio.to_account_balance(price_getter)

        # 4. Evaluate signals through strategy
        decisions = self.strategy.evaluate_batch(
            signals=signals,
            holdings=balance.holdings,
            balance=balance,
        )

        # 5. Filter and execute
        executable = [d for d in decisions if self.strategy.should_execute(d)]

        for decision in executable:
            price = self.price_provider.get_price_on_date(
                decision.stock_code, sim_date
            )
            if price is None or price <= 0:
                continue

            if decision.action == TradeAction.BUY:
                success = self.portfolio.buy(
                    stock_code=decision.stock_code,
                    stock_name=decision.stock_name,
                    quantity=decision.quantity,
                    price=price,
                    trade_date=sim_date,
                )
                if success:
                    logger.info(
                        f"[{sim_date}] BUY {decision.stock_name} "
                        f"x{decision.quantity} @ {price:,.0f}"
                    )

            elif decision.action == TradeAction.SELL:
                success = self.portfolio.sell(
                    stock_code=decision.stock_code,
                    quantity=decision.quantity,
                    price=price,
                    trade_date=sim_date,
                )
                if success:
                    logger.info(
                        f"[{sim_date}] SELL {decision.stock_name} "
                        f"x{decision.quantity} @ {price:,.0f}"
                    )
