"""
Risk management module.
Enforces trading limits and tracks daily P&L.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from src.trading.kis_client import AccountBalance, OrderResult
from src.trading.strategy import TradeDecision
from src.utils.exceptions import RiskLimitExceededError
from src.utils.logger import get_logger, trade_log

logger = get_logger(__name__)


@dataclass
class TradeRecord:
    """Record of a single trade."""
    timestamp: datetime
    stock_code: str
    action: str  # "buy" or "sell"
    quantity: int
    price: float
    total_amount: float
    realized_pnl: Optional[float] = None


@dataclass
class DailyStats:
    """Daily trading statistics."""
    date: datetime
    trade_count: int = 0
    buy_count: int = 0
    sell_count: int = 0
    total_bought: float = 0.0
    total_sold: float = 0.0
    realized_pnl: float = 0.0
    trades: List[TradeRecord] = field(default_factory=list)


class RiskManager:
    """
    Risk management for trading operations.

    Enforces:
    - Daily loss limits
    - Maximum trade count per day
    - Position size limits
    - Order validation
    """

    def __init__(self, config: dict):
        """
        Initialize risk manager.

        Args:
            config: Risk configuration dictionary
        """
        strategy_config = config.get("strategy", {})

        self.daily_loss_limit = strategy_config.get("daily_loss_limit", -0.03)
        self.max_trades_per_day = strategy_config.get("max_trades_per_day", 10)
        self.max_single_trade_ratio = strategy_config.get("max_single_trade_ratio", 0.1)
        self.max_holding_ratio = strategy_config.get("max_holding_ratio", 0.2)

        # Daily tracking
        self._daily_stats = DailyStats(date=datetime.now())
        self._initial_portfolio_value: Optional[float] = None

    def set_initial_portfolio_value(self, value: float) -> None:
        """Set initial portfolio value for P&L calculation."""
        self._initial_portfolio_value = value
        logger.info(f"Initial portfolio value set: {value:,.0f}")

    def _ensure_today(self) -> None:
        """Ensure daily stats are for today."""
        today = datetime.now().date()
        if self._daily_stats.date.date() != today:
            self.reset_daily()

    def reset_daily(self) -> None:
        """Reset daily statistics."""
        self._daily_stats = DailyStats(date=datetime.now())
        self._initial_portfolio_value = None
        trade_log("Daily risk limits reset")

    def can_trade(self) -> Tuple[bool, str]:
        """
        Check if trading is allowed.

        Returns:
            Tuple of (can_trade, reason)
        """
        self._ensure_today()

        # Check trade count
        if self._daily_stats.trade_count >= self.max_trades_per_day:
            return False, f"Daily trade limit reached ({self.max_trades_per_day})"

        # Check daily loss limit
        if self._initial_portfolio_value:
            loss_rate = self._daily_stats.realized_pnl / self._initial_portfolio_value
            if loss_rate <= self.daily_loss_limit:
                return False, f"Daily loss limit reached ({loss_rate:.1%})"

        return True, "OK"

    def validate_order(
        self,
        decision: TradeDecision,
        balance: AccountBalance,
    ) -> Tuple[bool, str]:
        """
        Validate an order before execution.

        Args:
            decision: Trade decision to validate
            balance: Current account balance

        Returns:
            Tuple of (is_valid, reason)
        """
        self._ensure_today()

        # Check if trading is allowed
        can_trade, reason = self.can_trade()
        if not can_trade:
            return False, reason

        # Validate buy orders
        if decision.action.value == "buy":
            if decision.target_price:
                required_amount = decision.quantity * decision.target_price
            else:
                # Estimate with current holdings
                required_amount = decision.quantity * 100000  # Placeholder

            if required_amount > balance.cash:
                return False, f"Insufficient cash: need {required_amount:,.0f}, have {balance.cash:,.0f}"

            # Check single trade limit
            trade_ratio = required_amount / max(balance.total_eval_amount, 1)
            if trade_ratio > self.max_single_trade_ratio:
                return False, f"Trade exceeds single trade limit ({trade_ratio:.1%} > {self.max_single_trade_ratio:.1%})"

        # Validate sell orders
        elif decision.action.value == "sell":
            holding = None
            for h in balance.holdings:
                if h.stock_code == decision.stock_code:
                    holding = h
                    break

            if not holding:
                return False, f"No position in {decision.stock_code}"

            if decision.quantity > holding.quantity:
                return False, f"Insufficient shares: have {holding.quantity}, trying to sell {decision.quantity}"

        return True, "OK"

    def record_trade(
        self,
        decision: TradeDecision,
        result: OrderResult,
        realized_pnl: Optional[float] = None,
    ) -> None:
        """
        Record a completed trade.

        Args:
            decision: Trade decision that was executed
            result: Order execution result
            realized_pnl: Realized P&L for sell orders
        """
        self._ensure_today()

        price = result.price or 0
        total_amount = decision.quantity * price

        record = TradeRecord(
            timestamp=result.executed_at or datetime.now(),
            stock_code=decision.stock_code,
            action=decision.action.value,
            quantity=decision.quantity,
            price=price,
            total_amount=total_amount,
            realized_pnl=realized_pnl,
        )

        self._daily_stats.trades.append(record)
        self._daily_stats.trade_count += 1

        if decision.action.value == "buy":
            self._daily_stats.buy_count += 1
            self._daily_stats.total_bought += total_amount
        else:
            self._daily_stats.sell_count += 1
            self._daily_stats.total_sold += total_amount
            if realized_pnl:
                self._daily_stats.realized_pnl += realized_pnl

        trade_log(
            f"Recorded: {decision.action.value.upper()} {decision.stock_code} "
            f"x{decision.quantity} @ {price:,.0f}"
        )

    def get_daily_stats(self) -> dict:
        """Get current daily statistics."""
        self._ensure_today()

        return {
            "date": self._daily_stats.date.strftime("%Y-%m-%d"),
            "trade_count": self._daily_stats.trade_count,
            "buy_count": self._daily_stats.buy_count,
            "sell_count": self._daily_stats.sell_count,
            "total_bought": self._daily_stats.total_bought,
            "total_sold": self._daily_stats.total_sold,
            "realized_pnl": self._daily_stats.realized_pnl,
            "remaining_trades": self.max_trades_per_day - self._daily_stats.trade_count,
        }

    def get_trade_history(self) -> List[dict]:
        """Get today's trade history."""
        self._ensure_today()

        return [
            {
                "timestamp": t.timestamp.isoformat(),
                "stock_code": t.stock_code,
                "action": t.action,
                "quantity": t.quantity,
                "price": t.price,
                "total_amount": t.total_amount,
                "realized_pnl": t.realized_pnl,
            }
            for t in self._daily_stats.trades
        ]
