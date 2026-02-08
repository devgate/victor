"""
Backtest report generator.
Calculates performance metrics and formats results for display.
"""
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from src.backtest.portfolio import SimulatedPortfolio


@dataclass
class BacktestReport:
    """Backtest result with performance metrics."""
    start_date: date
    end_date: date
    initial_cash: float
    portfolio: SimulatedPortfolio

    @property
    def final_value(self) -> float:
        if self.portfolio.daily_values:
            return self.portfolio.daily_values[-1]["total_value"]
        return self.initial_cash

    @property
    def total_return_pct(self) -> float:
        return (self.final_value / self.initial_cash - 1) * 100

    @property
    def total_trades(self) -> int:
        return len(self.portfolio.trade_history)

    @property
    def buy_count(self) -> int:
        return sum(1 for t in self.portfolio.trade_history if t.action == "buy")

    @property
    def sell_count(self) -> int:
        return sum(1 for t in self.portfolio.trade_history if t.action == "sell")

    @property
    def max_drawdown_pct(self) -> float:
        """Maximum drawdown percentage."""
        if not self.portfolio.daily_values:
            return 0.0

        peak = self.initial_cash
        max_dd = 0.0
        for snapshot in self.portfolio.daily_values:
            value = snapshot["total_value"]
            if value > peak:
                peak = value
            dd = (value - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd
        return max_dd

    @property
    def win_rate(self) -> float:
        """Win rate based on completed round-trip trades."""
        sells = [t for t in self.portfolio.trade_history if t.action == "sell"]
        if not sells:
            return 0.0

        # Match sells with their corresponding buys
        wins = 0
        buy_prices = {}  # stock_code -> list of (price, qty)
        for trade in self.portfolio.trade_history:
            if trade.action == "buy":
                buy_prices.setdefault(trade.stock_code, []).append(
                    (trade.price, trade.quantity)
                )
            elif trade.action == "sell":
                buys = buy_prices.get(trade.stock_code, [])
                if buys:
                    avg_buy = sum(p * q for p, q in buys) / sum(q for _, q in buys)
                    if trade.price > avg_buy:
                        wins += 1

        return (wins / len(sells)) * 100 if sells else 0.0

    @property
    def sharpe_ratio(self) -> float:
        """Simplified Sharpe ratio (annualized, risk-free rate = 3%)."""
        if len(self.portfolio.daily_values) < 2:
            return 0.0

        daily_returns = []
        for i in range(1, len(self.portfolio.daily_values)):
            prev = self.portfolio.daily_values[i - 1]["total_value"]
            curr = self.portfolio.daily_values[i]["total_value"]
            if prev > 0:
                daily_returns.append(curr / prev - 1)

        if not daily_returns:
            return 0.0

        import statistics
        avg = statistics.mean(daily_returns)
        std = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0.001

        if std == 0:
            return 0.0

        # Annualize (252 trading days)
        annual_return = avg * 252
        annual_std = std * (252 ** 0.5)
        risk_free = 0.03

        return (annual_return - risk_free) / annual_std

    def print_report(self) -> None:
        """Print formatted backtest report to terminal."""
        print()
        print("=" * 60)
        print("  BACKTEST REPORT")
        print("=" * 60)
        print(f"  Period:       {self.start_date} ~ {self.end_date}")
        print(f"  Initial Cash: {self.initial_cash:>15,.0f} KRW")
        print(f"  Final Value:  {self.final_value:>15,.0f} KRW")
        print()

        # Return
        sign = "+" if self.total_return_pct >= 0 else ""
        print(f"  Total Return: {sign}{self.total_return_pct:>14.2f} %")
        print(f"  Max Drawdown: {self.max_drawdown_pct:>14.2f} %")
        print(f"  Sharpe Ratio: {self.sharpe_ratio:>14.2f}")
        print(f"  Win Rate:     {self.win_rate:>14.1f} %")
        print()

        # Trades
        print(f"  Total Trades: {self.total_trades:>14}")
        print(f"    - Buy:      {self.buy_count:>14}")
        print(f"    - Sell:     {self.sell_count:>14}")
        print()

        # Trade history
        if self.portfolio.trade_history:
            print("-" * 60)
            print(f"  {'Date':<12} {'Action':<6} {'Stock':<14} {'Qty':>6} {'Price':>10}")
            print("-" * 60)
            for t in self.portfolio.trade_history:
                print(
                    f"  {t.date.isoformat():<12} "
                    f"{t.action.upper():<6} "
                    f"{t.stock_name:<14} "
                    f"{t.quantity:>6,} "
                    f"{t.price:>10,.0f}"
                )
            print("-" * 60)

        # Daily values
        if self.portfolio.daily_values:
            print()
            print("  Daily Portfolio Value:")
            print("-" * 60)
            for snap in self.portfolio.daily_values:
                ret = snap["return_pct"]
                sign = "+" if ret >= 0 else ""
                bar_len = int(abs(ret) * 2)
                bar = ("+" if ret >= 0 else "-") * min(bar_len, 20)
                print(
                    f"  {snap['date']}  "
                    f"{snap['total_value']:>12,.0f} KRW  "
                    f"{sign}{ret:>6.2f}%  "
                    f"{bar}"
                )
            print("-" * 60)

        # Remaining holdings
        held = self.portfolio.get_holding_codes()
        if held:
            print(f"\n  Remaining Holdings: {', '.join(held)}")

        print("=" * 60)
        print()

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_cash": self.initial_cash,
            "final_value": self.final_value,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "buy_count": self.buy_count,
            "sell_count": self.sell_count,
            "trade_history": [
                {
                    "date": t.date.isoformat(),
                    "action": t.action,
                    "stock_code": t.stock_code,
                    "stock_name": t.stock_name,
                    "quantity": t.quantity,
                    "price": t.price,
                }
                for t in self.portfolio.trade_history
            ],
        }
