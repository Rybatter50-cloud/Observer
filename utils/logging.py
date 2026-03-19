"""
Observer Intelligence Platform - Logging Configuration
Provides structured logging with proper handlers and formatters
"""

import logging
import threading
import sys
from datetime import datetime
from typing import List
from colorama import Fore, Style, init

init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for console output.

    Does NOT mutate the shared record.levelname -- instead formats
    the colored version locally so other handlers see the original.
    """

    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        # Save and restore levelname so ANSI codes don't leak to other handlers
        original_levelname = record.levelname
        if original_levelname in self.COLORS:
            record.levelname = f"{self.COLORS[original_levelname]}{original_levelname}{Style.RESET_ALL}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


class SystemLogHandler(logging.Handler):
    """Custom handler that stores logs for dashboard display.

    Thread-safe: uses a lock around list mutation.
    Uses the formatted message (not raw) for consistency.
    """

    def __init__(self, max_logs: int = 100):
        super().__init__()
        self.logs: List[str] = []
        self.max_logs = max_logs
        self._lock = threading.Lock()

    def emit(self, record):
        try:
            msg = self.format(record)
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {msg}"

            with self._lock:
                self.logs.insert(0, log_entry)
                if len(self.logs) > self.max_logs:
                    self.logs.pop()
        except Exception:
            self.handleError(record)

    def get_logs(self) -> List[str]:
        """Return current logs for dashboard"""
        with self._lock:
            return self.logs.copy()


def setup_logging(debug: bool = False) -> SystemLogHandler:
    """
    Configure application logging
    
    Args:
        debug: Enable debug level logging
        
    Returns:
        SystemLogHandler instance for retrieving logs
    """
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_formatter = ColoredFormatter(
        '%(levelname)s | %(name)s | %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # System log handler for dashboard
    system_handler = SystemLogHandler()
    system_handler.setLevel(logging.INFO)
    system_formatter = logging.Formatter('%(message)s')
    system_handler.setFormatter(system_formatter)
    logger.addHandler(system_handler)
    
    return system_handler


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module"""
    return logging.getLogger(name)
