"""
Main entry point for the Fuel Tracker Bot
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import settings
from config.logging_config import setup_logging
from models.database import init_db
from bot.handlers import start, refuel, stats, manage_refuels, ai_assistant, batch_refuel, smart_photo, manual_refuel

logger = logging.getLogger(__name__)


async def main():
    """Main function to start the bot"""

    # Setup logging
    setup_logging()
    logger.info("Starting Fuel Tracker Bot...")

    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        return

    # Create bot and dispatcher
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Register routers (ORDER MATTERS!)
    dp.include_router(start.router)
    dp.include_router(refuel.router)  # Handles photos in specific states
    dp.include_router(manual_refuel.router)  # Manual refuel entry
    dp.include_router(batch_refuel.router)  # Handles photos in batch state
    dp.include_router(smart_photo.router)  # Handles photos WITHOUT state (must be before stats/manage)
    dp.include_router(stats.router)
    dp.include_router(manage_refuels.router)
    dp.include_router(ai_assistant.router)  # AI chat must be last to catch unhandled text

    logger.info("All handlers registered")

    # Start polling
    try:
        logger.info("Bot started successfully! Polling for updates...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"Error during polling: {e}", exc_info=True)
    finally:
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
