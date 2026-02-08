"""Logging configuration for the application."""

import logging
import sys
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_logging_configured = False

def setup_logging(
    level: LogLevel = "INFO",
    format_string: str | None = None,
    enable_otel: bool = True,
) -> logging.Logger:
    """Configure and return the application logger.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        format_string: Custom format string. Uses default if None.
        enable_otel: If True, attach an OpenTelemetry LoggingHandler so logs
            are exported via OTLP alongside stdout.

    Returns:
        Configured logger instance.
    """
    if format_string is None:
        format_string = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if enable_otel:
        try:
            from utils.telemetry import setup_telemetry

            otel_handler = setup_telemetry()
            handlers.append(otel_handler)
        except Exception:
            # OTel setup is best-effort; don't break the application.
            pass

    logging.basicConfig(
        level=getattr(logging, level),
        format=format_string,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )

    global _logging_configured
    _logging_configured = True

    logger = logging.getLogger("dl_obs")
    logger.setLevel(getattr(logging, level))

    return logger

def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module.

    Auto-configures logging if setup_logging() hasn't been called.

    Args:
        name: Module name (typically __name__).

    Returns:
        Logger instance for the module.
    """
    global _logging_configured
    if not _logging_configured:
        setup_logging()
        _logging_configured = True

    return logging.getLogger(f"dl_obs.{name}")
