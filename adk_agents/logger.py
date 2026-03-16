import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

class CustomLogger:
    """
    Centralized logging system for DB Intelligence Agent.
    Supports console coloring and rotating file logs.
    """
    
    def __init__(self, name="db_agent", log_dir="logs", level=logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.logger.propagate = False
        
        # Avoid duplicate handlers if already initialized
        if not self.logger.handlers:
            os.makedirs(log_dir, exist_ok=True)
            
            # 1. Console Handler (with icons/formatting)
            console_handler = logging.StreamHandler(sys.stdout)
            console_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
            
            # 2. File Handler (Rotating)
            log_file = os.path.join(log_dir, "db_agent.log")
            file_handler = RotatingFileHandler(
                log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
            )
            file_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | [%(name)s] | %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

    def info(self, msg, icon="ℹ️"):
        self.logger.info(f"{icon} {msg}")

    def warning(self, msg, icon="⚠️"):
        self.logger.warning(f"{icon} {msg}")

    def error(self, msg, icon="❌"):
        self.logger.error(f"{icon} {msg}")

    def debug(self, msg, icon="🔍"):
        self.logger.debug(f"{icon} {msg}")

    def success(self, msg, icon="✅"):
        self.logger.info(f"{icon} {msg}")

class CustomLoggerAdapter(logging.LoggerAdapter):
    """
    Adapter that preserves custom convenience methods (success, info, etc.)
    and injects session_id into messages.
    """
    def info(self, msg, icon="ℹ️", *args, **kwargs):
        self.logger.info(f"{icon} {msg}", *args, **kwargs)

    def warning(self, msg, icon="⚠️", *args, **kwargs):
        self.logger.warning(f"{icon} {msg}", *args, **kwargs)

    def error(self, msg, icon="❌", *args, **kwargs):
        self.logger.error(f"{icon} {msg}", *args, **kwargs)

    def debug(self, msg, icon="🔍", *args, **kwargs):
        self.logger.debug(f"{icon} {msg}", *args, **kwargs)

    def success(self, msg, icon="✅", *args, **kwargs):
        self.logger.info(f"{icon} {msg}", *args, **kwargs)

# Global singleton instance
_logger_instance = None

def get_logger(session_id=None):
    """Get the global logger, optionally with session context."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = CustomLogger()
    
    if session_id:
        # Return our custom adapter so convenience methods work
        return CustomLoggerAdapter(_logger_instance.logger, {"session_id": session_id})
    return _logger_instance
