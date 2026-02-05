"""
Korea Investment Securities API Client.
Wraps the python-kis library for account management and trading operations.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from src.utils.exceptions import (
    AuthenticationError,
    InsufficientBalanceError,
    KISAPIError,
    OrderExecutionError,
)
from src.utils.logger import get_logger, trade_log

logger = get_logger(__name__)


@dataclass
class StockHolding:
    """Represents a stock holding in the portfolio."""
    stock_code: str
    stock_name: str
    quantity: int
    avg_buy_price: float
    current_price: float
    eval_amount: float
    profit_loss: float
    profit_rate: float

    @property
    def total_cost(self) -> float:
        return self.quantity * self.avg_buy_price


@dataclass
class AccountBalance:
    """Represents account balance information."""
    cash: float                    # Available cash
    total_eval_amount: float       # Total evaluation amount
    total_profit_loss: float       # Total profit/loss
    total_profit_rate: float       # Total profit rate
    holdings: List[StockHolding]   # Stock holdings

    @property
    def stock_eval_amount(self) -> float:
        """Total stock evaluation amount."""
        return sum(h.eval_amount for h in self.holdings)


@dataclass
class StockQuote:
    """Represents current stock price information."""
    stock_code: str
    stock_name: str
    current_price: float
    change: float
    change_rate: float
    volume: int
    open_price: float
    high_price: float
    low_price: float
    prev_close: float


@dataclass
class OrderResult:
    """Represents order execution result."""
    success: bool
    order_id: Optional[str] = None
    stock_code: Optional[str] = None
    order_type: Optional[str] = None  # "buy" or "sell"
    quantity: Optional[int] = None
    price: Optional[float] = None
    message: Optional[str] = None
    executed_at: Optional[datetime] = None


class KISClient:
    """
    Korea Investment Securities API Client.

    Provides methods for:
    - Account balance and holdings inquiry
    - Stock price inquiry
    - Buy/Sell orders (market and limit)
    - Order cancellation
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_number: str,
        hts_id: str,
        virtual: bool = False,
    ):
        """
        Initialize KIS API client.

        Args:
            app_key: KIS API app key
            app_secret: KIS API app secret
            account_number: Account number (format: XXXXXXXX-XX)
            hts_id: HTS ID for authentication
            virtual: If True, use paper trading (mock) environment
        """
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_number = account_number
        self.hts_id = hts_id
        self.virtual = virtual
        self._kis = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Ensure the KIS client is initialized."""
        if self._initialized:
            return

        try:
            from pykis import PyKis

            self._kis = PyKis(
                id=self.hts_id,
                account=self.account_number,
                appkey=self.app_key,
                secretkey=self.app_secret,
                virtual=self.virtual,
            )
            self._initialized = True
            logger.info(
                f"KIS API client initialized (virtual={self.virtual})"
            )
        except ImportError:
            raise KISAPIError(
                "python-kis library not installed. Run: pip install python-kis"
            )
        except Exception as e:
            raise AuthenticationError(
                f"Failed to initialize KIS API client: {e}",
                cause=e,
            )

    @property
    def kis(self):
        """Get the underlying PyKis instance."""
        self._ensure_initialized()
        return self._kis

    # ============================================================
    # Account Information
    # ============================================================

    def get_balance(self) -> AccountBalance:
        """
        Get account balance and holdings.

        Returns:
            AccountBalance object with cash, evaluation, and holdings.
        """
        try:
            account = self.kis.account()
            balance = account.balance()

            holdings = []
            for stock in balance.stocks:
                holding = StockHolding(
                    stock_code=stock.code,
                    stock_name=stock.name,
                    quantity=stock.quantity,
                    avg_buy_price=float(stock.avg_buy_price),
                    current_price=float(stock.current_price),
                    eval_amount=float(stock.eval_amount),
                    profit_loss=float(stock.profit_loss),
                    profit_rate=float(stock.profit_rate),
                )
                holdings.append(holding)

            return AccountBalance(
                cash=float(balance.withdrawable_cash),
                total_eval_amount=float(balance.total_eval_amount),
                total_profit_loss=float(balance.total_profit_loss),
                total_profit_rate=float(balance.total_profit_rate),
                holdings=holdings,
            )
        except Exception as e:
            raise KISAPIError(f"Failed to get account balance: {e}", cause=e)

    def get_holdings(self) -> List[StockHolding]:
        """
        Get current stock holdings.

        Returns:
            List of StockHolding objects.
        """
        balance = self.get_balance()
        return balance.holdings

    def get_holding(self, stock_code: str) -> Optional[StockHolding]:
        """
        Get holding for a specific stock.

        Args:
            stock_code: Stock code to look up

        Returns:
            StockHolding if found, None otherwise.
        """
        holdings = self.get_holdings()
        for holding in holdings:
            if holding.stock_code == stock_code:
                return holding
        return None

    # ============================================================
    # Stock Price Information
    # ============================================================

    def get_quote(self, stock_code: str) -> StockQuote:
        """
        Get current stock quote.

        Args:
            stock_code: Stock code to look up

        Returns:
            StockQuote with current price information.
        """
        try:
            stock = self.kis.stock(stock_code)
            quote = stock.quote()

            return StockQuote(
                stock_code=stock_code,
                stock_name=quote.name,
                current_price=float(quote.price),
                change=float(quote.change),
                change_rate=float(quote.change_rate),
                volume=int(quote.volume),
                open_price=float(quote.open),
                high_price=float(quote.high),
                low_price=float(quote.low),
                prev_close=float(quote.prev_close),
            )
        except Exception as e:
            raise KISAPIError(
                f"Failed to get quote for {stock_code}: {e}",
                cause=e,
            )

    def get_current_price(self, stock_code: str) -> float:
        """
        Get current price for a stock.

        Args:
            stock_code: Stock code to look up

        Returns:
            Current price as float.
        """
        quote = self.get_quote(stock_code)
        return quote.current_price

    # ============================================================
    # Order Execution
    # ============================================================

    def buy_market(self, stock_code: str, quantity: int) -> OrderResult:
        """
        Place a market buy order.

        Args:
            stock_code: Stock code to buy
            quantity: Number of shares to buy

        Returns:
            OrderResult with execution details.
        """
        try:
            stock = self.kis.stock(stock_code)
            order = stock.buy(qty=quantity)

            result = OrderResult(
                success=True,
                order_id=str(order.order_id),
                stock_code=stock_code,
                order_type="buy",
                quantity=quantity,
                price=float(order.price) if order.price else None,
                message="Market buy order placed",
                executed_at=datetime.now(),
            )

            trade_log(
                f"BUY MARKET: {stock_code} x {quantity} @ market price",
                order_id=result.order_id,
            )
            return result

        except Exception as e:
            error_msg = str(e)
            if "insufficient" in error_msg.lower():
                raise InsufficientBalanceError(
                    f"Insufficient balance to buy {stock_code}",
                    cause=e,
                )
            raise OrderExecutionError(
                f"Failed to place market buy order: {e}",
                stock_code=stock_code,
                order_type="buy_market",
                quantity=quantity,
                cause=e,
            )

    def buy_limit(
        self,
        stock_code: str,
        quantity: int,
        price: float,
    ) -> OrderResult:
        """
        Place a limit buy order.

        Args:
            stock_code: Stock code to buy
            quantity: Number of shares to buy
            price: Limit price

        Returns:
            OrderResult with execution details.
        """
        try:
            stock = self.kis.stock(stock_code)
            order = stock.buy(qty=quantity, price=int(price))

            result = OrderResult(
                success=True,
                order_id=str(order.order_id),
                stock_code=stock_code,
                order_type="buy",
                quantity=quantity,
                price=price,
                message=f"Limit buy order placed at {price:,.0f}",
                executed_at=datetime.now(),
            )

            trade_log(
                f"BUY LIMIT: {stock_code} x {quantity} @ {price:,.0f}",
                order_id=result.order_id,
            )
            return result

        except Exception as e:
            raise OrderExecutionError(
                f"Failed to place limit buy order: {e}",
                stock_code=stock_code,
                order_type="buy_limit",
                quantity=quantity,
                cause=e,
            )

    def sell_market(self, stock_code: str, quantity: int) -> OrderResult:
        """
        Place a market sell order.

        Args:
            stock_code: Stock code to sell
            quantity: Number of shares to sell

        Returns:
            OrderResult with execution details.
        """
        try:
            stock = self.kis.stock(stock_code)
            order = stock.sell(qty=quantity)

            result = OrderResult(
                success=True,
                order_id=str(order.order_id),
                stock_code=stock_code,
                order_type="sell",
                quantity=quantity,
                price=float(order.price) if order.price else None,
                message="Market sell order placed",
                executed_at=datetime.now(),
            )

            trade_log(
                f"SELL MARKET: {stock_code} x {quantity} @ market price",
                order_id=result.order_id,
            )
            return result

        except Exception as e:
            raise OrderExecutionError(
                f"Failed to place market sell order: {e}",
                stock_code=stock_code,
                order_type="sell_market",
                quantity=quantity,
                cause=e,
            )

    def sell_limit(
        self,
        stock_code: str,
        quantity: int,
        price: float,
    ) -> OrderResult:
        """
        Place a limit sell order.

        Args:
            stock_code: Stock code to sell
            quantity: Number of shares to sell
            price: Limit price

        Returns:
            OrderResult with execution details.
        """
        try:
            stock = self.kis.stock(stock_code)
            order = stock.sell(qty=quantity, price=int(price))

            result = OrderResult(
                success=True,
                order_id=str(order.order_id),
                stock_code=stock_code,
                order_type="sell",
                quantity=quantity,
                price=price,
                message=f"Limit sell order placed at {price:,.0f}",
                executed_at=datetime.now(),
            )

            trade_log(
                f"SELL LIMIT: {stock_code} x {quantity} @ {price:,.0f}",
                order_id=result.order_id,
            )
            return result

        except Exception as e:
            raise OrderExecutionError(
                f"Failed to place limit sell order: {e}",
                stock_code=stock_code,
                order_type="sell_limit",
                quantity=quantity,
                cause=e,
            )

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancellation was successful.
        """
        try:
            order = self.kis.order(order_id)
            result = order.cancel()

            trade_log(f"ORDER CANCELLED: {order_id}")
            return result

        except Exception as e:
            raise OrderExecutionError(
                f"Failed to cancel order {order_id}: {e}",
                cause=e,
            )

    # ============================================================
    # Utility Methods
    # ============================================================

    def is_market_open(self) -> bool:
        """
        Check if the market is currently open.

        Returns:
            True if market is open.
        """
        now = datetime.now()

        # Check if it's a weekday (Monday=0, Sunday=6)
        if now.weekday() >= 5:
            return False

        # Market hours: 9:00 - 15:30 KST
        market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

        return market_open <= now <= market_close

    def validate_order(
        self,
        stock_code: str,
        order_type: str,
        quantity: int,
        price: Optional[float] = None,
    ) -> tuple[bool, str]:
        """
        Validate an order before execution.

        Args:
            stock_code: Stock code
            order_type: "buy" or "sell"
            quantity: Number of shares
            price: Price for limit orders

        Returns:
            Tuple of (is_valid, message)
        """
        if quantity <= 0:
            return False, "Quantity must be positive"

        if order_type == "buy":
            balance = self.get_balance()
            current_price = self.get_current_price(stock_code)
            required_amount = quantity * current_price

            if required_amount > balance.cash:
                return False, f"Insufficient balance: need {required_amount:,.0f}, have {balance.cash:,.0f}"

        elif order_type == "sell":
            holding = self.get_holding(stock_code)
            if not holding:
                return False, f"No holding for {stock_code}"
            if holding.quantity < quantity:
                return False, f"Insufficient shares: have {holding.quantity}, trying to sell {quantity}"

        return True, "OK"
