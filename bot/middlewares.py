
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from database.database import Database

class DatabaseMiddleware(BaseMiddleware):
    """Middleware to add database access to handlers"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        data["db"] = Database()
        return await handler(event, data)

class LanguageMiddleware(BaseMiddleware):
    """Middleware to add user language to handlers and auto-create users"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        db = data.get("db")
        
        if db:
            user = await db.get_user(user_id)
            
            # If user doesn't exist, create them automatically with Uzbek language
            if not user:
                username = event.from_user.username
                first_name = event.from_user.first_name
                
                # Create user with default language 'uz'
                user = await db.create_user(
                    telegram_id=user_id,
                    username=username,
                    first_name=first_name,
                    language='uz'  # Default to Uzbek
                )
            
            data["user_lang"] = user.language
            data["user"] = user
        else:
            data["user_lang"] = "uz"  # Changed from "en" to "uz"
            data["user"] = None
        
        return await handler(event, data)
