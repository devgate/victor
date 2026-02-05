"""
Slack notification module.
Sends trading alerts and reports to Slack.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

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

    def send_daily_report(self, report: dict) -> bool:
        """
        Send daily analysis report.

        Args:
            report: Report dictionary from NewsAnalyzer

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
