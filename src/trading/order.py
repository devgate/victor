"""
Order execution module.
Handles trade execution with risk management integration.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from src.trading.kis_client import KISClient, OrderResult
from src.trading.risk_manager import RiskManager
from src.trading.strategy import TradeAction, TradeDecision, TradingStrategy
from src.utils.exceptions import OrderExecutionError, RiskLimitExceededError
from src.utils.logger import get_logger, trade_log

logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    """Result of order execution."""
    success: bool
    decision: TradeDecision
    order_result: Optional[OrderResult] = None
    error_message: Optional[str] = None
    executed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "decision": self.decision.to_dict(),
            "order_result": {
                "order_id": self.order_result.order_id,
                "quantity": self.order_result.quantity,
                "price": self.order_result.price,
            } if self.order_result else None,
            "error_message": self.error_message,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


class OrderExecutor:
    """
    Order execution manager.

    Handles:
    - Order validation via risk manager
    - Order execution via KIS client
    - Trade recording
    """

    def __init__(
        self,
        kis_client: KISClient,
        risk_manager: RiskManager,
        dry_run: bool = False,
    ):
        """
        Initialize order executor.

        Args:
            kis_client: KIS API client
            risk_manager: Risk manager instance
            dry_run: If True, simulate orders without actual execution
        """
        self.kis = kis_client
        self.risk = risk_manager
        self.dry_run = dry_run

    def execute(self, decision: TradeDecision) -> ExecutionResult:
        """
        Execute a trade decision.

        Args:
            decision: TradeDecision to execute

        Returns:
            ExecutionResult with success status and details
        """
        # Get current balance for validation
        try:
            balance = self.kis.get_balance()
        except Exception as e:
            return ExecutionResult(
                success=False,
                decision=decision,
                error_message=f"Failed to get balance: {e}",
            )

        # Set initial portfolio value if not set
        if self.risk._initial_portfolio_value is None:
            self.risk.set_initial_portfolio_value(balance.total_eval_amount)

        # Validate order
        valid, reason = self.risk.validate_order(decision, balance)
        if not valid:
            trade_log(f"Order rejected: {decision.stock_code} - {reason}")
            return ExecutionResult(
                success=False,
                decision=decision,
                error_message=reason,
            )

        # Execute order
        if self.dry_run:
            return self._simulate_execution(decision)

        try:
            if decision.action == TradeAction.BUY:
                order_result = self.kis.buy_market(
                    decision.stock_code,
                    decision.quantity,
                )
            else:  # SELL
                # Calculate realized P&L for sell orders
                holding = self.kis.get_holding(decision.stock_code)
                realized_pnl = None
                if holding:
                    current_price = self.kis.get_current_price(decision.stock_code)
                    cost_basis = holding.avg_buy_price * decision.quantity
                    realized_pnl = (current_price - holding.avg_buy_price) * decision.quantity

                order_result = self.kis.sell_market(
                    decision.stock_code,
                    decision.quantity,
                )

                # Record with P&L
                self.risk.record_trade(decision, order_result, realized_pnl)

                return ExecutionResult(
                    success=True,
                    decision=decision,
                    order_result=order_result,
                    executed_at=datetime.now(),
                )

            # Record buy trade
            self.risk.record_trade(decision, order_result)

            trade_log(
                f"Executed: {decision.action.value.upper()} {decision.stock_code} "
                f"x{decision.quantity} | Order ID: {order_result.order_id}"
            )

            return ExecutionResult(
                success=True,
                decision=decision,
                order_result=order_result,
                executed_at=datetime.now(),
            )

        except OrderExecutionError as e:
            trade_log(f"Order failed: {decision.stock_code} - {e}")
            return ExecutionResult(
                success=False,
                decision=decision,
                error_message=str(e),
            )
        except Exception as e:
            logger.error(f"Unexpected error executing order: {e}")
            return ExecutionResult(
                success=False,
                decision=decision,
                error_message=f"Unexpected error: {e}",
            )

    def _simulate_execution(self, decision: TradeDecision) -> ExecutionResult:
        """
        Simulate order execution for dry run mode.

        Args:
            decision: TradeDecision to simulate

        Returns:
            ExecutionResult with simulated results
        """
        trade_log(
            f"[DRY RUN] {decision.action.value.upper()} {decision.stock_code} "
            f"x{decision.quantity} | Reason: {decision.reason}"
        )

        # Create simulated order result
        order_result = OrderResult(
            success=True,
            order_id=f"DRY-{datetime.now().strftime('%H%M%S')}",
            stock_code=decision.stock_code,
            order_type=decision.action.value,
            quantity=decision.quantity,
            price=decision.target_price,
            message="Dry run simulation",
            executed_at=datetime.now(),
        )

        return ExecutionResult(
            success=True,
            decision=decision,
            order_result=order_result,
            executed_at=datetime.now(),
        )

    def execute_batch(
        self,
        decisions: List[TradeDecision],
    ) -> List[ExecutionResult]:
        """
        Execute multiple trade decisions.

        Args:
            decisions: List of TradeDecision objects

        Returns:
            List of ExecutionResult objects
        """
        results = []

        for decision in decisions:
            # Check if we can still trade
            can_trade, reason = self.risk.can_trade()
            if not can_trade:
                logger.warning(f"Cannot continue trading: {reason}")
                results.append(ExecutionResult(
                    success=False,
                    decision=decision,
                    error_message=reason,
                ))
                continue

            result = self.execute(decision)
            results.append(result)

        return results

    def get_execution_summary(
        self,
        results: List[ExecutionResult],
    ) -> dict:
        """
        Generate execution summary.

        Args:
            results: List of execution results

        Returns:
            Summary dictionary
        """
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        buy_count = sum(
            1 for r in successful
            if r.decision.action == TradeAction.BUY
        )
        sell_count = sum(
            1 for r in successful
            if r.decision.action == TradeAction.SELL
        )

        return {
            "total": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "buy_count": buy_count,
            "sell_count": sell_count,
            "daily_stats": self.risk.get_daily_stats(),
        }
