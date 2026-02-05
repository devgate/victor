"""
Logging configuration for Victor Trading System.
Uses loguru for structured logging with rotation and formatting.
"""
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

# Remove default handler
logger.remove()


def setup_logger(
    log_level: str = "INFO",
    log_dir: Optional[str] = None,
    app_name: str = "victor",
) -> None:
    """
    Setup logging configuration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files. If None, logs only to console.
        app_name: Application name for log file naming.
    """
    # Console handler with color formatting
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File handler with rotation
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # General log file
        logger.add(
            log_path / f"{app_name}.log",
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation="10 MB",
            retention="30 days",
            compression="gz",
            encoding="utf-8",
        )

        # Error log file (separate)
        logger.add(
            log_path / f"{app_name}_error.log",
            level="ERROR",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation="10 MB",
            retention="30 days",
            compression="gz",
            encoding="utf-8",
        )

        # Trading log file (separate for audit)
        logger.add(
            log_path / f"{app_name}_trades.log",
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            rotation="1 day",
            retention="90 days",
            compression="gz",
            encoding="utf-8",
            filter=lambda record: "trade" in record["extra"],
        )


def get_logger(name: str = "victor"):
    """
    Get a logger instance with the specified name.

    Args:
        name: Logger name (module name)

    Returns:
        Logger instance bound with the name.
    """
    return logger.bind(name=name)


def trade_log(message: str, **kwargs) -> None:
    """
    Log a trade-related message to the dedicated trades log.

    Args:
        message: Log message
        **kwargs: Additional context to include in the log
    """
    logger.bind(trade=True).info(f"[TRADE] {message}", **kwargs)


def news_log(message: str, **kwargs) -> None:
    """
    Log a news collection-related message.

    Args:
        message: Log message
        **kwargs: Additional context to include in the log
    """
    logger.bind(news=True).info(f"[NEWS] {message}", **kwargs)


def analysis_log(message: str, **kwargs) -> None:
    """
    Log an analysis-related message.

    Args:
        message: Log message
        **kwargs: Additional context to include in the log
    """
    logger.bind(analysis=True).info(f"[ANALYSIS] {message}", **kwargs)


# Export logger directly for convenience
__all__ = [
    "logger",
    "setup_logger",
    "get_logger",
    "trade_log",
    "news_log",
    "analysis_log",
]
