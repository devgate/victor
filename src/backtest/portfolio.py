"""
Simulated portfolio for backtesting.
Tracks buy/sell operations and daily valuations without real API calls.
Compatible with TradingStrategy's AccountBalance/StockHolding interface.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from src.trading.kis_client import AccountBalance, StockHolding
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TradeRecord:
    """Record of a simulated trade."""
    date: date
    stock_code: str
    stock_name: str
    action: str  # "buy" or "sell"
    quantity: int
    price: float
    total_amount: float


class SimulatedPortfolio:
    """
    Simulated portfolio that mirrors KIS AccountBalance/StockHolding interface.

    Tracks cash, holdings, and trade history for backtesting.
    """

    def __init__(self, initial_cash: float = 500_000):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self._holdings: Dict[str, dict] = {}  # code -> {name, qty, avg_price}
        self.trade_history: List[TradeRecord] = []
        self.daily_values: List[dict] = []  # [{date, total_value, cash, stock_value}]

    def buy(
        self,
        stock_code: str,
        stock_name: str,
        quantity: int,
        price: float,
        trade_date: date,
    ) -> bool:
        """
        Execute a simulated buy order.

        Returns:
            True if order was executed
        """
        total_cost = quantity * price
        if total_cost > self.cash or quantity <= 0:
            return False

        self.cash -= total_cost

        if stock_code in self._holdings:
            h = self._holdings[stock_code]
            old_total = h["qty"] * h["avg_price"]
            h["qty"] += quantity
            h["avg_price"] = (old_total + total_cost) / h["qty"]
        else:
            self._holdings[stock_code] = {
                "name": stock_name,
                "qty": quantity,
                "avg_price": price,
            }

        self.trade_history.append(TradeRecord(
            date=trade_date,
            stock_code=stock_code,
            stock_name=stock_name,
            action="buy",
            quantity=quantity,
            price=price,
            total_amount=total_cost,
        ))
        return True

    def sell(
        self,
        stock_code: str,
        quantity: int,
        price: float,
        trade_date: date,
    ) -> bool:
        """
        Execute a simulated sell order.

        Returns:
            True if order was executed
        """
        if stock_code not in self._holdings:
            return False

        h = self._holdings[stock_code]
        if quantity > h["qty"]:
            return False

        total_proceeds = quantity * price
        self.cash += total_proceeds

        h["qty"] -= quantity
        if h["qty"] == 0:
            stock_name = h["name"]
            del self._holdings[stock_code]
        else:
            stock_name = h["name"]

        self.trade_history.append(TradeRecord(
            date=trade_date,
            stock_code=stock_code,
            stock_name=stock_name,
            action="sell",
            quantity=quantity,
            price=price,
            total_amount=total_proceeds,
        ))
        return True

    def record_daily_value(
        self,
        current_date: date,
        price_getter,
    ) -> dict:
        """
        Record daily portfolio valuation.

        Args:
            current_date: Current simulation date
            price_getter: Function(stock_code, date) -> Optional[float]

        Returns:
            Daily snapshot dict
        """
        stock_value = 0.0
        for code, h in self._holdings.items():
            price = price_getter(code, current_date)
            if price:
                stock_value += h["qty"] * price

        total_value = self.cash + stock_value
        snapshot = {
            "date": current_date.isoformat(),
            "total_value": total_value,
            "cash": self.cash,
            "stock_value": stock_value,
            "return_pct": (total_value / self.initial_cash - 1) * 100,
        }
        self.daily_values.append(snapshot)
        return snapshot

    def to_account_balance(self, price_getter) -> AccountBalance:
        """
        Convert to AccountBalance for compatibility with TradingStrategy.

        Args:
            price_getter: Function(stock_code) -> Optional[float]
        """
        holdings = []
        total_stock_eval = 0.0
        total_pnl = 0.0

        for code, h in self._holdings.items():
            current_price = price_getter(code)
            if current_price is None:
                current_price = h["avg_price"]

            eval_amount = h["qty"] * current_price
            pnl = (current_price - h["avg_price"]) * h["qty"]
            pnl_rate = ((current_price / h["avg_price"]) - 1) * 100 if h["avg_price"] > 0 else 0

            holdings.append(StockHolding(
                stock_code=code,
                stock_name=h["name"],
                quantity=h["qty"],
                avg_buy_price=h["avg_price"],
                current_price=current_price,
                eval_amount=eval_amount,
                profit_loss=pnl,
                profit_rate=pnl_rate,
            ))

            total_stock_eval += eval_amount
            total_pnl += pnl

        total_eval = self.cash + total_stock_eval
        total_rate = ((total_eval / self.initial_cash) - 1) * 100

        return AccountBalance(
            cash=self.cash,
            total_eval_amount=total_eval,
            total_profit_loss=total_pnl,
            total_profit_rate=total_rate,
            holdings=holdings,
        )

    def get_holding_codes(self) -> List[str]:
        """Get list of held stock codes."""
        return list(self._holdings.keys())
