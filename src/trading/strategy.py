"""
Trading strategy module.
Implements conservative risk management focused strategies.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from src.analysis.analyzer import TradingSignal
from src.trading.kis_client import AccountBalance, StockHolding
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TradeAction(Enum):
    """Trading action types."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class TradeDecision:
    """Trading decision output."""
    action: TradeAction
    stock_code: str
    stock_name: str
    quantity: int
    reason: str
    confidence: float  # 0.0 - 1.0
    target_price: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "quantity": self.quantity,
            "reason": self.reason,
            "confidence": self.confidence,
            "target_price": self.target_price,
        }


class TradingStrategy:
    """
    Conservative trading strategy.

    Focuses on:
    - Position sizing with splits
    - Stop-loss and take-profit
    - Maximum position limits
    - Daily loss limits
    """

    def __init__(self, config: dict):
        """
        Initialize trading strategy.

        Args:
            config: Strategy configuration dictionary
        """
        strategy_config = config.get("strategy", {})

        # Position sizing
        self.max_single_trade_ratio = strategy_config.get("max_single_trade_ratio", 0.1)
        self.split_count = strategy_config.get("split_count", 3)

        # Risk management
        self.stop_loss_rate = strategy_config.get("stop_loss_rate", -0.05)
        self.take_profit_rate = strategy_config.get("take_profit_rate", 0.10)
        self.max_holding_ratio = strategy_config.get("max_holding_ratio", 0.2)
        self.daily_loss_limit = strategy_config.get("daily_loss_limit", -0.03)
        self.max_trades_per_day = strategy_config.get("max_trades_per_day", 10)

        # Signal thresholds
        self.buy_threshold = strategy_config.get("buy_threshold", 0.3)
        self.sell_threshold = strategy_config.get("sell_threshold", -0.2)
        self.min_mentions = strategy_config.get("min_mentions", 3)

        # Price getter function (injected)
        self._get_price_func = None

    def set_price_getter(self, func) -> None:
        """Set function to get current stock prices."""
        self._get_price_func = func

    def _get_current_price(self, stock_code: str) -> float:
        """Get current price for a stock."""
        if self._get_price_func:
            return self._get_price_func(stock_code)
        raise RuntimeError("Price getter not configured")

    def evaluate(
        self,
        signal: TradingSignal,
        holdings: List[StockHolding],
        balance: AccountBalance,
    ) -> Optional[TradeDecision]:
        """
        Evaluate a trading signal and make a decision.

        Args:
            signal: TradingSignal to evaluate
            holdings: Current stock holdings
            balance: Current account balance

        Returns:
            TradeDecision or None if no action needed
        """
        # Find if we already hold this stock
        holding = None
        for h in holdings:
            if h.stock_code == signal.stock_code:
                holding = h
                break

        # Calculate normalized sentiment
        avg_sentiment = signal.avg_sentiment
        confidence = min(signal.mentions / 10, 1.0)

        # =====================================
        # SELL decisions (for held positions)
        # =====================================
        if holding:
            # 1. Stop-loss check
            if holding.profit_rate <= self.stop_loss_rate:
                return TradeDecision(
                    action=TradeAction.SELL,
                    stock_code=signal.stock_code,
                    stock_name=signal.stock_name,
                    quantity=holding.quantity,  # Sell all
                    reason=f"Stop-loss triggered ({holding.profit_rate:.1%})",
                    confidence=1.0,
                )

            # 2. Take-profit check (sell half)
            if holding.profit_rate >= self.take_profit_rate:
                sell_qty = max(holding.quantity // 2, 1)
                return TradeDecision(
                    action=TradeAction.SELL,
                    stock_code=signal.stock_code,
                    stock_name=signal.stock_name,
                    quantity=sell_qty,
                    reason=f"Take-profit ({holding.profit_rate:.1%})",
                    confidence=0.8,
                )

            # 3. Negative news - partial sell
            if avg_sentiment < self.sell_threshold:
                sell_qty = max(holding.quantity // self.split_count, 1)
                return TradeDecision(
                    action=TradeAction.SELL,
                    stock_code=signal.stock_code,
                    stock_name=signal.stock_name,
                    quantity=sell_qty,
                    reason=f"Negative sentiment ({avg_sentiment:.2f})",
                    confidence=confidence,
                )

        # =====================================
        # BUY decisions
        # =====================================
        if avg_sentiment > self.buy_threshold and signal.mentions >= self.min_mentions:
            # Check position limit
            if holding:
                current_ratio = (
                    holding.quantity * holding.current_price
                ) / max(balance.total_eval_amount, 1)

                if current_ratio >= self.max_holding_ratio:
                    logger.debug(
                        f"Position limit reached for {signal.stock_code}: "
                        f"{current_ratio:.1%} >= {self.max_holding_ratio:.1%}"
                    )
                    return None

            # Calculate buy quantity
            try:
                buy_qty = self._calculate_buy_quantity(
                    signal.stock_code,
                    balance,
                )
                if buy_qty > 0:
                    return TradeDecision(
                        action=TradeAction.BUY,
                        stock_code=signal.stock_code,
                        stock_name=signal.stock_name,
                        quantity=buy_qty,
                        reason=f"Positive news ({signal.mentions} mentions, sentiment: {avg_sentiment:.2f})",
                        confidence=confidence,
                    )
            except Exception as e:
                logger.warning(f"Failed to calculate buy quantity: {e}")

        return None

    def _calculate_buy_quantity(
        self,
        stock_code: str,
        balance: AccountBalance,
    ) -> int:
        """
        Calculate buy quantity based on position sizing rules.

        Args:
            stock_code: Stock to buy
            balance: Current account balance

        Returns:
            Number of shares to buy
        """
        # Maximum investment per trade
        max_invest = balance.cash * self.max_single_trade_ratio / self.split_count

        # Get current price
        current_price = self._get_current_price(stock_code)
        if current_price <= 0:
            return 0

        # Calculate quantity
        quantity = int(max_invest / current_price)

        return max(quantity, 0)

    def evaluate_batch(
        self,
        signals: Dict[str, TradingSignal],
        holdings: List[StockHolding],
        balance: AccountBalance,
        max_decisions: int = 5,
    ) -> List[TradeDecision]:
        """
        Evaluate multiple signals and return top decisions.

        Args:
            signals: Dictionary of trading signals
            holdings: Current holdings
            balance: Current balance
            max_decisions: Maximum number of decisions to return

        Returns:
            List of TradeDecision objects
        """
        decisions = []

        # Sort signals by strength
        sorted_signals = sorted(
            signals.values(),
            key=lambda s: s.signal_strength,
            reverse=True,
        )

        for signal in sorted_signals:
            decision = self.evaluate(signal, holdings, balance)
            if decision:
                decisions.append(decision)

            if len(decisions) >= max_decisions:
                break

        return decisions

    def should_execute(self, decision: TradeDecision) -> bool:
        """
        Check if a decision should be executed based on confidence.

        Args:
            decision: TradeDecision to check

        Returns:
            True if decision should be executed
        """
        # Stop-loss always executes
        if "stop-loss" in decision.reason.lower():
            return True

        # Take-profit always executes
        if "take-profit" in decision.reason.lower():
            return True

        # News-based decisions require higher confidence
        return decision.confidence >= 0.5
