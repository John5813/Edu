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
        data["db"] = Database
        return await handler(event, data)

class LanguageMiddleware(BaseMiddleware):
    """Middleware to add user language to handlers"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        db = data.get("db", Database)
        
        # Always try to get user from database
        try:
            user = await db.get_user(user_id)
            if user:
                data["user_lang"] = user.language
                data["user"] = user
            else:
                # If user doesn't exist, set defaults
                data["user_lang"] = "uz"
                data["user"] = None
        except Exception as e:
            # On any error, set safe defaults
            data["user_lang"] = "uz"
            data["user"] = None
        
        return await handler(event, data)
