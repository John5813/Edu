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
        
        user = await db.get_user(user_id)
        if user:
            data["user_lang"] = user.language
            data["user"] = user
        else:
            data["user_lang"] = "en"
            data["user"] = None
        
        return await handler(event, data)
