import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import start, documents, payments, admin, settings
from bot.middlewares import LanguageMiddleware, DatabaseMiddleware
from database.database import init_db
from config import BOT_TOKEN, ADMIN_IDS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main function to start the bot"""
    # Initialize database
    await init_db()
    
    # Initialize bot and dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher(storage=MemoryStorage())
    
    # Register middlewares
    dp.message.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())
    dp.message.middleware(LanguageMiddleware())
    dp.callback_query.middleware(LanguageMiddleware())
    
    # Register handlers
    dp.include_router(start.router)
    dp.include_router(documents.router)
    dp.include_router(payments.router)
    dp.include_router(admin.router)
    dp.include_router(settings.router)
    
    # Start polling
    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
