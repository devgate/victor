"""
Custom exceptions for Victor Trading System.
Provides structured error handling with detailed context.
"""
from typing import Any, Dict, Optional


class VictorError(Exception):
    """Base exception class for Victor Trading System."""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        self.message = message
        self.details = details or {}
        self.cause = cause
        super().__init__(self.message)

    def __str__(self) -> str:
        result = self.message
        if self.details:
            result += f" | Details: {self.details}"
        if self.cause:
            result += f" | Caused by: {self.cause}"
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None,
        }


# ============================================================
# News Collection Exceptions
# ============================================================


class NewsError(VictorError):
    """Base exception for news-related errors."""
    pass


class NewsCollectionError(NewsError):
    """Raised when news collection fails."""
    pass


class NewsParsingError(NewsError):
    """Raised when news parsing fails."""
    pass


class NewsCacheError(NewsError):
    """Raised when news caching operations fail."""
    pass


# ============================================================
# Analysis Exceptions
# ============================================================


class AnalysisError(VictorError):
    """Base exception for analysis-related errors."""
    pass


class KeywordExtractionError(AnalysisError):
    """Raised when keyword extraction fails."""
    pass


class SentimentAnalysisError(AnalysisError):
    """Raised when sentiment analysis fails."""
    pass


class StockMappingError(AnalysisError):
    """Raised when stock mapping fails."""
    pass


# ============================================================
# Trading Exceptions
# ============================================================


class TradingError(VictorError):
    """Base exception for trading-related errors."""
    pass


class OrderExecutionError(TradingError):
    """Raised when order execution fails."""

    def __init__(
        self,
        message: str,
        stock_code: Optional[str] = None,
        order_type: Optional[str] = None,
        quantity: Optional[int] = None,
        **kwargs,
    ):
        details = {
            "stock_code": stock_code,
            "order_type": order_type,
            "quantity": quantity,
        }
        details.update(kwargs)
        super().__init__(message, details=details)


class InsufficientBalanceError(TradingError):
    """Raised when account balance is insufficient."""

    def __init__(
        self,
        message: str,
        required_amount: Optional[float] = None,
        available_amount: Optional[float] = None,
        **kwargs,
    ):
        details = {
            "required_amount": required_amount,
            "available_amount": available_amount,
        }
        details.update(kwargs)
        super().__init__(message, details=details)


class RiskLimitExceededError(TradingError):
    """Raised when a risk limit is exceeded."""

    def __init__(
        self,
        message: str,
        limit_type: Optional[str] = None,
        current_value: Optional[float] = None,
        limit_value: Optional[float] = None,
        **kwargs,
    ):
        details = {
            "limit_type": limit_type,
            "current_value": current_value,
            "limit_value": limit_value,
        }
        details.update(kwargs)
        super().__init__(message, details=details)


class PositionLimitError(TradingError):
    """Raised when position limit is exceeded."""
    pass


class MarketClosedError(TradingError):
    """Raised when attempting to trade outside market hours."""
    pass


# ============================================================
# API Exceptions
# ============================================================


class APIError(VictorError):
    """Base exception for API-related errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        **kwargs,
    ):
        details = {
            "status_code": status_code,
            "response_body": response_body,
        }
        details.update(kwargs)
        super().__init__(message, details=details)


class KISAPIError(APIError):
    """Raised when Korea Investment Securities API call fails."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        **kwargs,
    ):
        details = {
            "kis_error_code": error_code,
            "kis_error_message": error_message,
        }
        details.update(kwargs)
        super().__init__(message, **details)


class AuthenticationError(APIError):
    """Raised when API authentication fails."""
    pass


class RateLimitError(APIError):
    """Raised when API rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        **kwargs,
    ):
        details = {"retry_after_seconds": retry_after}
        details.update(kwargs)
        super().__init__(message, **details)


# ============================================================
# Configuration Exceptions
# ============================================================


class ConfigurationError(VictorError):
    """Raised when configuration is invalid or missing."""
    pass


class MissingConfigError(ConfigurationError):
    """Raised when required configuration is missing."""

    def __init__(self, config_key: str, **kwargs):
        message = f"Missing required configuration: {config_key}"
        super().__init__(message, details={"config_key": config_key, **kwargs})


# ============================================================
# Notification Exceptions
# ============================================================


class NotificationError(VictorError):
    """Base exception for notification-related errors."""
    pass


class SlackNotificationError(NotificationError):
    """Raised when Slack notification fails."""
    pass


# ============================================================
# Scheduler Exceptions
# ============================================================


class SchedulerError(VictorError):
    """Base exception for scheduler-related errors."""
    pass


class JobExecutionError(SchedulerError):
    """Raised when a scheduled job fails."""

    def __init__(
        self,
        message: str,
        job_id: Optional[str] = None,
        job_name: Optional[str] = None,
        **kwargs,
    ):
        details = {
            "job_id": job_id,
            "job_name": job_name,
        }
        details.update(kwargs)
        super().__init__(message, details=details)
