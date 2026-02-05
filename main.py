#!/usr/bin/env python3
"""
Victor Trading System - Main Entry Point

An intelligent trading system that:
1. Collects and analyzes news from multiple sources
2. Extracts keywords and performs sentiment analysis
3. Maps keywords to stocks and generates trading signals
4. Executes trades via Korea Investment Securities API
5. Reports results via Slack
"""
import argparse
import asyncio
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional

from config.settings import Settings, load_keywords_mapping
from src.analysis.analyzer import NewsAnalyzer, TradingSignal
from src.news.aggregator import NewsAggregator
from src.news.base import NewsArticle
from src.notification.slack import SlackNotifier
from src.scheduler.scheduler import TradingScheduler
from src.trading.kis_client import KISClient
from src.trading.order import OrderExecutor
from src.trading.risk_manager import RiskManager
from src.trading.strategy import TradingStrategy
from src.utils.logger import get_logger, setup_logger

logger = get_logger(__name__)


class VictorTrading:
    """
    Main trading system orchestrator.

    Coordinates all components for news-based automated trading.
    """

    def __init__(self, dry_run: bool = True):
        """
        Initialize Victor Trading System.

        Args:
            dry_run: If True, simulate trades without execution
        """
        self.settings = Settings()
        self.dry_run = dry_run
        self._running = False

        # Initialize components
        self._init_components()

    def _init_components(self) -> None:
        """Initialize all system components."""
        config = self.settings.config

        # News aggregator
        self.news_aggregator = NewsAggregator(
            config=config.get("news", {}),
            cache_dir=config.get("data", {}).get("news_cache"),
        )

        # News analyzer
        self.analyzer = NewsAnalyzer(config=config.get("analysis", {}))

        # KIS API client
        kis_config = config.get("kis", {})
        self.kis_client = KISClient(
            app_key=kis_config.get("app_key", ""),
            app_secret=kis_config.get("app_secret", ""),
            account_number=kis_config.get("account_number", ""),
            hts_id=kis_config.get("hts_id", ""),
            virtual=kis_config.get("virtual", True),
        )

        # Trading components
        trading_config = config.get("trading", {})
        self.risk_manager = RiskManager(trading_config)
        self.strategy = TradingStrategy(trading_config)
        self.strategy.set_price_getter(self.kis_client.get_current_price)

        self.order_executor = OrderExecutor(
            kis_client=self.kis_client,
            risk_manager=self.risk_manager,
            dry_run=self.dry_run,
        )

        # Slack notifier
        slack_config = config.get("slack", {})
        self.slack = SlackNotifier(
            webhook_url=slack_config.get("webhook_url", ""),
            enabled=slack_config.get("enabled", True),
        )

        # Scheduler
        scheduler_config = config.get("scheduler", {})
        self.scheduler = TradingScheduler(
            config=scheduler_config,
            timezone=scheduler_config.get("timezone", "Asia/Seoul"),
        )

        # Register job handlers
        self._register_handlers()

        logger.info(f"Victor Trading initialized (dry_run={self.dry_run})")

    def _register_handlers(self) -> None:
        """Register scheduler job handlers."""
        self.scheduler.register_handler("morning_analysis", self.run_analysis_cycle)
        self.scheduler.register_handler("intraday_analysis", self.run_analysis_cycle)
        self.scheduler.register_handler("daily_report", self.send_daily_report)
        self.scheduler.register_handler("risk_reset", self.reset_risk_limits)

    async def collect_news(self) -> List[NewsArticle]:
        """
        Collect news from all configured sources.

        Returns:
            List of NewsArticle objects
        """
        logger.info("Collecting news from all sources...")
        try:
            articles = await self.news_aggregator.collect_all()
            logger.info(f"Collected {len(articles)} new articles")
            return articles
        except Exception as e:
            logger.error(f"News collection failed: {e}")
            self.slack.send_error_alert(
                error_type="News Collection",
                error_message=str(e),
            )
            return []

    def analyze_news(self, articles: List[NewsArticle]) -> Dict[str, TradingSignal]:
        """
        Analyze news articles and generate trading signals.

        Uses dynamic trend tracking to discover emerging keywords and issues.

        Args:
            articles: List of news articles

        Returns:
            Dictionary of stock_code -> TradingSignal
        """
        if not articles:
            logger.info("No articles to analyze")
            return {}

        logger.info(f"Analyzing {len(articles)} articles...")

        # Analyze articles (this also updates trend tracker)
        analyses = self.analyzer.analyze_batch(articles)

        # Generate signals with trend-based enhancement
        signals = self.analyzer.aggregate_signals_with_trends(analyses)

        # Log trending keywords
        trending = self.analyzer.get_trending_keywords(limit=5)
        if trending:
            trend_keywords = ", ".join([t.keyword for t in trending])
            logger.info(f"Trending keywords: {trend_keywords}")

        # Log emerging issues
        emerging = self.analyzer.get_emerging_issues(limit=3)
        if emerging:
            emerging_keywords = ", ".join([e.keyword for e in emerging])
            logger.info(f"Emerging issues: {emerging_keywords}")

        logger.info(f"Generated {len(signals)} trading signals")
        return signals

    def make_trading_decisions(
        self,
        signals: Dict[str, TradingSignal],
    ) -> List:
        """
        Make trading decisions based on signals.

        Args:
            signals: Dictionary of trading signals

        Returns:
            List of TradeDecision objects
        """
        try:
            # Get current holdings and balance
            balance = self.kis_client.get_balance()
            holdings = balance.holdings

            # Generate decisions
            decisions = self.strategy.evaluate_batch(
                signals=signals,
                holdings=holdings,
                balance=balance,
            )

            # Filter by confidence
            executable = [d for d in decisions if self.strategy.should_execute(d)]

            logger.info(
                f"Made {len(decisions)} decisions, "
                f"{len(executable)} executable"
            )
            return executable

        except Exception as e:
            logger.error(f"Decision making failed: {e}")
            return []

    def execute_trades(self, decisions: List) -> List:
        """
        Execute trading decisions.

        Args:
            decisions: List of TradeDecision objects

        Returns:
            List of ExecutionResult objects
        """
        if not decisions:
            logger.info("No trades to execute")
            return []

        logger.info(f"Executing {len(decisions)} trades...")
        results = self.order_executor.execute_batch(decisions)

        # Send Slack alerts for each execution
        for result in results:
            try:
                self.slack.send_trade_alert(result)
            except Exception as e:
                logger.warning(f"Failed to send trade alert: {e}")

        # Log summary
        summary = self.order_executor.get_execution_summary(results)
        logger.info(
            f"Execution complete: {summary['successful']}/{summary['total']} successful"
        )

        return results

    async def run_analysis_cycle(self) -> dict:
        """
        Run a complete analysis and trading cycle.

        Returns:
            Summary dictionary
        """
        logger.info("=" * 50)
        logger.info("Starting analysis cycle")
        logger.info("=" * 50)

        # 1. Collect news
        articles = await self.collect_news()

        # 2. Analyze news
        signals = self.analyze_news(articles)

        # 3. Make trading decisions
        decisions = self.make_trading_decisions(signals)

        # 4. Execute trades
        results = self.execute_trades(decisions)

        # 5. Generate summary
        summary = {
            "timestamp": datetime.now().isoformat(),
            "articles_collected": len(articles),
            "signals_generated": len(signals),
            "decisions_made": len(decisions),
            "trades_executed": len([r for r in results if r.success]),
            "trades_failed": len([r for r in results if not r.success]),
        }

        logger.info(f"Cycle complete: {summary}")
        return summary

    async def send_daily_report(self) -> None:
        """Generate and send daily report."""
        logger.info("Generating daily report...")

        try:
            # Get recent articles for report
            articles = await self.collect_news()
            analyses = self.analyzer.analyze_batch(articles) if articles else []
            signals = self.analyzer.aggregate_signals(analyses) if analyses else {}

            # Generate report
            report = self.analyzer.generate_report(analyses, signals)

            # Add trading stats
            report["daily_stats"] = self.risk_manager.get_daily_stats()

            # Send to Slack
            self.slack.send_daily_report(report)
            logger.info("Daily report sent")

        except Exception as e:
            logger.error(f"Daily report failed: {e}")
            self.slack.send_error_alert(
                error_type="Daily Report",
                error_message=str(e),
            )

    def reset_risk_limits(self) -> None:
        """Reset daily risk limits."""
        self.risk_manager.reset_daily()
        logger.info("Risk limits reset for new trading day")

    async def start(self) -> None:
        """Start the trading system with scheduler."""
        self._running = True

        # Send startup notification
        self.slack.send_startup_message()

        # Setup and start scheduler
        self.scheduler.setup_jobs()
        self.scheduler.start()

        logger.info("Victor Trading System started")
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE TRADING'}")
        logger.info(f"Scheduled jobs: {self.scheduler.get_status()['jobs']}")

        # Keep running until stopped
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the trading system."""
        self._running = False

        # Stop scheduler
        self.scheduler.stop()

        # Close news aggregator
        await self.news_aggregator.close()

        # Send shutdown notification
        self.slack.send_shutdown_message()

        logger.info("Victor Trading System stopped")

    async def run_once(self) -> dict:
        """
        Run a single analysis cycle (for manual/testing).

        Returns:
            Summary dictionary
        """
        try:
            return await self.run_analysis_cycle()
        finally:
            await self.news_aggregator.close()


def setup_signal_handlers(victor: VictorTrading, loop: asyncio.AbstractEventLoop):
    """Setup signal handlers for graceful shutdown."""

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        victor._running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Victor Trading System - News-based Automated Trading"
    )
    parser.add_argument(
        "--mode",
        choices=["daemon", "once", "status"],
        default="daemon",
        help="Run mode: daemon (continuous), once (single cycle), status (show status)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable live trading (default: dry run)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logger(log_level=args.log_level, log_dir="./data/logs")

    # Determine dry run mode
    dry_run = not args.live
    if not dry_run:
        logger.warning("=" * 50)
        logger.warning("LIVE TRADING MODE - Real money will be used!")
        logger.warning("=" * 50)

    # Initialize system
    victor = VictorTrading(dry_run=dry_run)

    # Run based on mode
    if args.mode == "daemon":
        logger.info("Starting in daemon mode...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        setup_signal_handlers(victor, loop)

        try:
            loop.run_until_complete(victor.start())
        finally:
            loop.close()

    elif args.mode == "once":
        logger.info("Running single analysis cycle...")
        result = asyncio.run(victor.run_once())
        print("\nAnalysis Result:")
        for key, value in result.items():
            print(f"  {key}: {value}")

    elif args.mode == "status":
        print("\nVictor Trading System Status")
        print("=" * 40)
        print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
        print(f"Environment: {victor.settings.env}")

        # Check KIS connection
        try:
            balance = victor.kis_client.get_balance()
            print(f"\nAccount Balance:")
            print(f"  Cash: {balance.cash:,.0f} KRW")
            print(f"  Total: {balance.total_eval_amount:,.0f} KRW")
            print(f"  Holdings: {len(balance.holdings)} stocks")
        except Exception as e:
            print(f"\nKIS API: Connection failed - {e}")

        # Scheduler status
        print(f"\nScheduler Jobs:")
        scheduler_config = victor.settings.scheduler_config.get("jobs", {})
        for job, time in scheduler_config.items():
            print(f"  {job}: {time}")


if __name__ == "__main__":
    main()
