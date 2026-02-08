"""
Slack notification module.
Sends trading alerts and reports to Slack.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.trading.kis_client import AccountBalance
from src.trading.order import ExecutionResult
from src.trading.strategy import TradeAction, TradeDecision
from src.utils.exceptions import SlackNotificationError
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SlackNotifier:
    """
    Slack notification sender.

    Uses Slack Webhook to send messages with rich formatting.
    """

    def __init__(self, webhook_url: str, enabled: bool = True):
        """
        Initialize Slack notifier.

        Args:
            webhook_url: Slack Incoming Webhook URL
            enabled: If False, notifications are logged but not sent
        """
        self.webhook_url = webhook_url
        self.enabled = enabled
        self._client = None

    @property
    def client(self):
        """Lazy load Slack webhook client."""
        if self._client is None:
            try:
                from slack_sdk.webhook import WebhookClient
                self._client = WebhookClient(self.webhook_url)
            except ImportError:
                raise SlackNotificationError(
                    "slack-sdk not installed. Run: pip install slack-sdk"
                )
        return self._client

    def send_message(
        self,
        text: str,
        blocks: Optional[List[Dict]] = None,
    ) -> bool:
        """
        Send a message to Slack.

        Args:
            text: Fallback text for notifications
            blocks: Optional Block Kit blocks for rich formatting

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.info(f"[Slack disabled] {text}")
            return True

        try:
            response = self.client.send(text=text, blocks=blocks)
            if response.status_code != 200:
                logger.error(f"Slack error: {response.status_code} - {response.body}")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack message: {e}")
            return False

    def send_trade_alert(
        self,
        result: ExecutionResult,
    ) -> bool:
        """
        Send trade execution alert.

        Args:
            result: Trade execution result

        Returns:
            True if sent successfully
        """
        decision = result.decision

        if decision.action == TradeAction.BUY:
            emoji = ":chart_with_upwards_trend:"
            action_text = "Buy"
            color = "#36a64f"  # Green
        else:
            emoji = ":chart_with_downwards_trend:"
            action_text = "Sell"
            color = "#ff6b6b"  # Red

        if result.success:
            status_emoji = ":white_check_mark:"
            status_text = "Executed"
        else:
            status_emoji = ":x:"
            status_text = "Failed"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {action_text} Order {status_text}",
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Stock:*\n{decision.stock_name}\n({decision.stock_code})"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Quantity:*\n{decision.quantity:,} shares"
                    },
                ]
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Reason:*\n{decision.reason}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Confidence:*\n{decision.confidence:.0%}"
                    },
                ]
            },
        ]

        if result.order_result and result.order_result.price:
            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Price:*\n{result.order_result.price:,.0f} KRW"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Order ID:*\n{result.order_result.order_id}"
                    },
                ]
            })

        if not result.success and result.error_message:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":warning: *Error:* {result.error_message}"
                }
            })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Victor Trading | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        })

        return self.send_message(
            text=f"{action_text} {decision.stock_name}: {status_text}",
            blocks=blocks,
        )

    def send_daily_report(
        self,
        report: dict,
        account_balance: Optional[AccountBalance] = None,
    ) -> bool:
        """
        Send daily analysis report.

        Args:
            report: Report dictionary from NewsAnalyzer
            account_balance: Optional account balance to include

        Returns:
            True if sent successfully
        """
        sentiment = report.get("sentiment_distribution", {})

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":newspaper: Daily Analysis Report",
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Articles Analyzed:* {report.get('article_count', 0)}\n"
                        f"*Sentiment:* "
                        f":green_circle: {sentiment.get('positive', 0)} "
                        f":white_circle: {sentiment.get('neutral', 0)} "
                        f":red_circle: {sentiment.get('negative', 0)}"
                    )
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Top Keywords:*\n{', '.join(report.get('top_keywords', [])[:10])}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Top Stocks:*\n{', '.join(report.get('top_stocks', [])[:5])}"
                }
            },
        ]

        # Add trading stats if available
        daily_stats = report.get("daily_stats", {})
        if daily_stats:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Today's Trades:*\n"
                        f"- Buy: {daily_stats.get('buy_count', 0)}\n"
                        f"- Sell: {daily_stats.get('sell_count', 0)}\n"
                        f"- Realized P&L: {daily_stats.get('realized_pnl', 0):+,.0f} KRW"
                    )
                }
            })

        # Add account balance section if provided
        if account_balance:
            blocks.extend(self._build_account_blocks(account_balance))

        blocks.extend([
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Victor Trading | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                ]
            }
        ])

        return self.send_message(
            text="Daily Analysis Report",
            blocks=blocks,
        )

    def send_error_alert(
        self,
        error_type: str,
        error_message: str,
        details: Optional[dict] = None,
    ) -> bool:
        """
        Send error alert.

        Args:
            error_type: Type of error
            error_message: Error message
            details: Optional additional details

        Returns:
            True if sent successfully
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":rotating_light: System Alert",
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error Type:* {error_type}\n*Message:* {error_message}"
                }
            },
        ]

        if details:
            detail_text = "\n".join(f"- {k}: {v}" for k, v in details.items())
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Details:*\n{detail_text}"
                }
            })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Victor Trading | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        })

        return self.send_message(
            text=f"Error: {error_type}",
            blocks=blocks,
        )

    def send_startup_message(self) -> bool:
        """Send system startup notification."""
        return self.send_message(
            text=":rocket: Victor Trading System Started",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ":rocket: *Victor Trading System Started*\n"
                                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                }
            ],
        )

    def send_shutdown_message(self) -> bool:
        """Send system shutdown notification."""
        return self.send_message(
            text=":stop_sign: Victor Trading System Stopped",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ":stop_sign: *Victor Trading System Stopped*\n"
                                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                }
            ],
        )

    def _build_account_blocks(self, balance: AccountBalance) -> List[Dict]:
        """
        Build Slack blocks for account status.

        Args:
            balance: AccountBalance object

        Returns:
            List of Slack block dicts
        """
        profit_sign = "+" if balance.total_profit_loss >= 0 else ""
        profit_emoji = ":chart_with_upwards_trend:" if balance.total_profit_loss >= 0 else ":chart_with_downwards_trend:"

        blocks = [
            {"type": "divider"},
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":bank: 계좌 현황",
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*예수금:*\n{balance.cash:,.0f} 원"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*주식평가:*\n{balance.stock_eval_amount:,.0f} 원"
                    },
                ]
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*총 평가금액:*\n{balance.total_eval_amount:,.0f} 원"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*총 손익:*\n{profit_emoji} {profit_sign}{balance.total_profit_loss:,.0f} 원 ({profit_sign}{balance.total_profit_rate:.2f}%)"
                    },
                ]
            },
        ]

        # Add holdings summary
        if balance.holdings:
            holdings_text = []
            for h in balance.holdings[:5]:  # Show top 5
                h_sign = "+" if h.profit_rate >= 0 else ""
                h_emoji = ":small_blue_diamond:" if h.profit_rate >= 0 else ":small_orange_diamond:"
                holdings_text.append(
                    f"{h_emoji} {h.stock_name}: {h.quantity:,}주 | {h_sign}{h.profit_rate:.1f}%"
                )

            if len(balance.holdings) > 5:
                holdings_text.append(f"_... 외 {len(balance.holdings) - 5}개 종목_")

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*보유 종목 ({len(balance.holdings)}개):*\n" + "\n".join(holdings_text)
                }
            })
        else:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*보유 종목:* 없음"
                }
            })

        return blocks

    def send_cycle_result(
        self,
        summary: dict,
        error: Optional[str] = None,
        account_balance: Optional[AccountBalance] = None,
    ) -> bool:
        """
        Send analysis cycle result notification.

        Args:
            summary: Cycle summary dictionary
            error: Optional error message if cycle failed
            account_balance: Optional account balance to include

        Returns:
            True if sent successfully
        """
        if error:
            # Failed cycle
            emoji = ":x:"
            status = "Failed"
            color = "#ff6b6b"
        elif summary.get("trades_executed", 0) > 0:
            # Successful with trades
            emoji = ":white_check_mark:"
            status = "Completed"
            color = "#36a64f"
        else:
            # Successful but no trades
            emoji = ":information_source:"
            status = "Completed (No trades)"
            color = "#4a90d9"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Analysis Cycle {status}",
                }
            },
        ]

        if error:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":warning: *Error:*\n```{error}```"
                }
            })
        else:
            # Add summary stats
            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Articles Collected:*\n{summary.get('articles_collected', 0)}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Signals Generated:*\n{summary.get('signals_generated', 0)}"
                    },
                ]
            })
            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Decisions Made:*\n{summary.get('decisions_made', 0)}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Trades:*\n:white_check_mark: {summary.get('trades_executed', 0)} | :x: {summary.get('trades_failed', 0)}"
                    },
                ]
            })

        # Add account balance section if provided
        if account_balance:
            blocks.extend(self._build_account_blocks(account_balance))

        blocks.extend([
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Victor Trading | {summary.get('timestamp', datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))}"
                    }
                ]
            }
        ])

        return self.send_message(
            text=f"Analysis Cycle {status}",
            blocks=blocks,
        )
