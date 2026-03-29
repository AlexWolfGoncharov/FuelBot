"""
Logging configuration for the Fuel Tracker Bot
"""
import logging
import sys
from config.settings import settings


def setup_logging():
    """Setup logging for the entire application"""

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format='%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('bot.log', encoding='utf-8')
        ]
    )

    # Reduce noise from third-party libraries
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("Logging configured successfully")
