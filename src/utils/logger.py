import logging
import sys
from config.settings import Config


def get_logger(name: str = "eda_flow") -> logging.Logger:
    """
    Returns a configured logger instance streaming to stdout.
    Prevents duplicate handler registration across calls.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        log_level_str = getattr(Config, "LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        logger.setLevel(log_level)

        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# Default logger instance
logger = get_logger("eda_flow")
