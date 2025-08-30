import aiosqlite
import asyncio
from datetime import datetime
from typing import List, Optional, Dict
from .models import User, Payment, Channel, Promocode, UsedPromocode, DocumentOrder, BroadcastMessage
from config import DATABASE_URL

DATABASE_FILE = "bot.db"

async def init_db():
    """Initialize database with tables"""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        # Users table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'en',
                balance INTEGER DEFAULT 0,
                free_service_used BOOLEAN DEFAULT FALSE,
                promocode_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Payments table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                screenshot_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Channels table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE NOT NULL,
                channel_username TEXT,
                title TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Promocodes table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Used promocodes table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS used_promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                promocode_id INTEGER NOT NULL,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (promocode_id) REFERENCES promocodes (id)
            )
        ''')

        # Document orders table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS document_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                document_type TEXT NOT NULL,
                topic TEXT NOT NULL,
                specifications TEXT,
                file_path TEXT,
                status TEXT DEFAULT 'generating',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Broadcast messages table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS broadcast_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_text TEXT NOT NULL,
                message_type TEXT DEFAULT 'text',
                file_id TEXT,
                target_audience TEXT DEFAULT 'all',
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP
            )
        ''')

        await db.commit()

class Database:
    @staticmethod
    async def get_user(telegram_id: int) -> Optional[User]:
        """Get user by telegram ID"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return User(**dict(row))
                return None

    @staticmethod
    async def get_user_by_id(user_id: int) -> Optional[User]:
        """Get user by internal ID"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return User(**dict(row))
                return None

    @staticmethod
    async def create_user(telegram_id: int, username: str = None, first_name: str = None, language: str = 'en') -> User:
        """Create new user"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                """INSERT INTO users (telegram_id, username, first_name, language) 
                   VALUES (?, ?, ?, ?)""",
                (telegram_id, username, first_name, language)
            )
            await db.commit()
            return await Database.get_user(telegram_id)

    @staticmethod
    async def update_user_language(telegram_id: int, language: str):
        """Update user language"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE users SET language = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                (language, telegram_id)
            )
            await db.commit()

    @staticmethod
    async def update_user_balance(telegram_id: int, amount: int):
        """Update user balance"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE users SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                (amount, telegram_id)
            )
            await db.commit()

    @staticmethod
    async def mark_free_service_used(telegram_id: int):
        """Mark that user has used free service"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE users SET free_service_used = TRUE, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                (telegram_id,)
            )
            await db.commit()

    @staticmethod
    async def reset_free_service(telegram_id: int):
        """Reset free service (from promocode)"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE users SET free_service_used = FALSE, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                (telegram_id,)
            )
            await db.commit()

    @staticmethod
    async def create_payment(user_id: int, amount: int, screenshot_file_id: str) -> int:
        """Create payment record"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                "INSERT INTO payments (user_id, amount, screenshot_file_id) VALUES (?, ?, ?)",
                (user_id, amount, screenshot_file_id)
            )
            await db.commit()
            return cursor.lastrowid

    @staticmethod
    async def get_payment_by_id(payment_id: int) -> Optional[Payment]:
        """Get payment by ID"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM payments WHERE id = ?", (payment_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Payment(**dict(row))
                return None

    @staticmethod
    async def get_pending_payments() -> List[Payment]:
        """Get all pending payments"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM payments WHERE status = 'pending' ORDER BY created_at"
            ) as cursor:
                rows = await cursor.fetchall()
                return [Payment(**dict(row)) for row in rows]

    @staticmethod
    async def update_payment_status(payment_id: int, status: str):
        """Update payment status"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE payments SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, payment_id)
            )
            await db.commit()

    @staticmethod
    async def get_active_channels() -> List[Channel]:
        """Get all active channels"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM channels WHERE is_active = TRUE"
            ) as cursor:
                rows = await cursor.fetchall()
                return [Channel(**dict(row)) for row in rows]

    @staticmethod
    async def add_channel(channel_id: str, channel_username: str, title: str):
        """Add new channel"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "INSERT OR REPLACE INTO channels (channel_id, channel_username, title) VALUES (?, ?, ?)",
                (channel_id, channel_username, title)
            )
            await db.commit()

    @staticmethod
    async def remove_channel(channel_id: str):
        """Remove channel"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE channels SET is_active = FALSE WHERE channel_id = ?",
                (channel_id,)
            )
            await db.commit()

    @staticmethod
    async def get_channel_by_id(channel_id: str) -> Optional[Channel]:
        """Get channel by ID"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Channel(**dict(row))
                return None

    @staticmethod
    async def create_promocode(code: str, expires_at: datetime) -> int:
        """Create promocode"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                "INSERT INTO promocodes (code, expires_at) VALUES (?, ?)",
                (code, expires_at)
            )
            await db.commit()
            return cursor.lastrowid

    @staticmethod
    async def get_promocode(code: str) -> Optional[Promocode]:
        """Get promocode by code"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM promocodes WHERE code = ? AND is_active = TRUE",
                (code,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Promocode(**dict(row))
                return None

    @staticmethod
    async def get_promocode_by_id(promocode_id: int) -> Optional[Promocode]:
        """Get promocode by ID"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM promocodes WHERE id = ?", (promocode_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Promocode(**dict(row))
                return None

    @staticmethod
    async def is_promocode_used(user_id: int, promocode_id: int) -> bool:
        """Check if user has used this promocode"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM used_promocodes WHERE user_id = ? AND promocode_id = ?",
                (user_id, promocode_id)
            ) as cursor:
                count = await cursor.fetchone()
                return count[0] > 0

    @staticmethod
    async def mark_promocode_used(user_id: int, promocode_id: int):
        """Mark promocode as used by user"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "INSERT INTO used_promocodes (user_id, promocode_id) VALUES (?, ?)",
                (user_id, promocode_id)
            )
            await db.commit()

    @staticmethod
    async def deactivate_promocode(promocode_id: int):
        """Deactivate promocode"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE promocodes SET is_active = FALSE WHERE id = ?",
                (promocode_id,)
            )
            await db.commit()

    @staticmethod
    async def get_active_promocodes() -> List[Promocode]:
        """Get all active promocodes"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM promocodes WHERE is_active = TRUE ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [Promocode(**dict(row)) for row in rows]

    @staticmethod
    async def count_promocode_usage(promocode_id: int) -> int:
        """Count how many times a promocode has been used"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM used_promocodes WHERE promocode_id = ?",
                (promocode_id,)
            ) as cursor:
                count = await cursor.fetchone()
                return count[0] if count else 0

    @staticmethod
    async def get_all_promocodes_with_stats() -> List[Dict]:
        """Get all promocodes with usage statistics"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT 
                    p.*,
                    COALESCE(u.usage_count, 0) as usage_count
                FROM promocodes p
                LEFT JOIN (
                    SELECT promocode_id, COUNT(*) as usage_count 
                    FROM used_promocodes 
                    GROUP BY promocode_id
                ) u ON p.id = u.promocode_id
                ORDER BY p.created_at DESC
            """) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    async def create_document_order(user_id: int, document_type: str, topic: str, specifications: str) -> int:
        """Create document order"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                "INSERT INTO document_orders (user_id, document_type, topic, specifications) VALUES (?, ?, ?, ?)",
                (user_id, document_type, topic, specifications)
            )
            await db.commit()
            return cursor.lastrowid

    @staticmethod
    async def get_document_order(order_id: int) -> Optional[DocumentOrder]:
        """Get document order by ID"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM document_orders WHERE id = ?", (order_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return DocumentOrder(**dict(row))
                return None

    @staticmethod
    async def update_document_order(order_id: int, status: str, file_path: str = None):
        """Update document order"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            if file_path:
                await db.execute(
                    "UPDATE document_orders SET status = ?, file_path = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (status, file_path, order_id)
                )
            else:
                await db.execute(
                    "UPDATE document_orders SET status = ? WHERE id = ?",
                    (status, order_id)
                )
            await db.commit()

    @staticmethod
    async def get_user_orders(user_id: int, limit: int = 10) -> List[DocumentOrder]:
        """Get user's recent orders"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM document_orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [DocumentOrder(**dict(row)) for row in rows]

    @staticmethod
    async def get_all_users() -> List[User]:
        """Get all users"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
                rows = await cursor.fetchall()
                return [User(**dict(row)) for row in rows]

    @staticmethod
    async def get_active_users(days: int = 30) -> List[User]:
        """Get users active within specified days"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE updated_at >= datetime('now', '-{} days') ORDER BY updated_at DESC".format(days)
            ) as cursor:
                rows = await cursor.fetchall()
                return [User(**dict(row)) for row in rows]

    @staticmethod
    async def get_user_stats() -> dict:
        """Get user statistics"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            # Total users
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]

            # Users today
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')"
            ) as cursor:
                users_today = (await cursor.fetchone())[0]

            # Users this week
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-7 days')"
            ) as cursor:
                users_week = (await cursor.fetchone())[0]

            # Users this month
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-30 days')"
            ) as cursor:
                users_month = (await cursor.fetchone())[0]

            # Total revenue
            async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved'"
            ) as cursor:
                total_revenue = (await cursor.fetchone())[0]

            # Revenue this month
            async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved' AND created_at >= datetime('now', '-30 days')"
            ) as cursor:
                revenue_month = (await cursor.fetchone())[0]

            # Document orders
            async with db.execute("SELECT COUNT(*) FROM document_orders") as cursor:
                total_orders = (await cursor.fetchone())[0]

            # Orders this month
            async with db.execute(
                "SELECT COUNT(*) FROM document_orders WHERE created_at >= datetime('now', '-30 days')"
            ) as cursor:
                orders_month = (await cursor.fetchone())[0]

            # Orders by type
            async with db.execute(
                "SELECT document_type, COUNT(*) FROM document_orders GROUP BY document_type"
            ) as cursor:
                orders_by_type = {row[0]: row[1] for row in await cursor.fetchall()}

            return {
                'total_users': total_users,
                'users_today': users_today,
                'users_week': users_week,
                'users_month': users_month,
                'total_revenue': total_revenue,
                'revenue_month': revenue_month,
                'total_orders': total_orders,
                'orders_month': orders_month,
                'orders_by_type': orders_by_type
            }

    @staticmethod
    async def create_broadcast_message(message_text: str, message_type: str = 'text', file_id: str = None, target_audience: str = 'all') -> int:
        """Create broadcast message record"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                "INSERT INTO broadcast_messages (message_text, message_type, file_id, target_audience) VALUES (?, ?, ?, ?)",
                (message_text, message_type, file_id, target_audience)
            )
            await db.commit()
            return cursor.lastrowid

    @staticmethod
    async def update_broadcast_stats(broadcast_id: int, sent_count: int, failed_count: int):
        """Update broadcast message statistics"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE broadcast_messages SET sent_count = ?, failed_count = ?, sent_at = CURRENT_TIMESTAMP WHERE id = ?",
                (sent_count, failed_count, broadcast_id)
            )
            await db.commit()

    @staticmethod
    async def get_broadcast_history(limit: int = 10) -> List[BroadcastMessage]:
        """Get broadcast message history"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM broadcast_messages ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [BroadcastMessage(**dict(row)) for row in rows]

    @staticmethod
    async def cleanup_expired_promocodes():
        """Cleanup expired promocodes"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE promocodes SET is_active = FALSE WHERE expires_at < datetime('now') AND is_active = TRUE"
            )
            await db.commit()

    @staticmethod
    async def get_user_count_by_language() -> dict:
        """Get user count by language"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "SELECT language, COUNT(*) FROM users GROUP BY language"
            ) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}