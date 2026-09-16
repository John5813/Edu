import aiosqlite
import asyncio
import secrets
import string
from datetime import datetime
from typing import List, Optional, Dict
from .models import User, Payment, Channel, Promocode, UsedPromocode, DocumentOrder, BroadcastMessage, Referral
from config import DATABASE_URL
import logging

logger = logging.getLogger(__name__)

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
                promocode_used TEXT,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                referral_earnings INTEGER DEFAULT 0,
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
                source TEXT DEFAULT '',
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

        # Document orders table — TRANSIENT tracker only.
        # Rows are inserted when generation starts and DELETED when generation
        # completes or fails. No personal data is kept long-term.
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

        # Anonymous document statistics — append-only, no user identifiers.
        # One row inserted per successfully completed document, with only the
        # type and the completion timestamp.
        await db.execute('''
            CREATE TABLE IF NOT EXISTS document_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_type TEXT NOT NULL,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        # Referrals table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                signup_bonus_given BOOLEAN DEFAULT 0,
                payment_bonus_given BOOLEAN DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users (telegram_id),
                FOREIGN KEY (referred_id) REFERENCES users (telegram_id)
            )
        ''')

        # Feature toggles table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS feature_toggles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_name TEXT UNIQUE NOT NULL,
                is_enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Sample files table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sample_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Blocked users table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS blocked_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                blocked_by INTEGER NOT NULL,
                reason TEXT,
                blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Bot settings table (for AI model selection, etc.)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT UNIQUE NOT NULL,
                setting_value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Do'kon katalogi: mijoz ma'lumotidan tozalangan, qayta sotuvga
        # qo'yilgan ishlar. Fayllarning o'zi Telegram omborida (yopiq kanal)
        # yotadi, bu yerda faqat file_id va ko'rgazma ma'lumoti saqlanadi.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS store_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT '',
                language TEXT DEFAULT 'uz',
                keywords TEXT DEFAULT '',
                -- Sarlavha + tavsif + kalit so'zlar, apostrofsiz va kichik
                -- harfda. Qidiruv shu ustunga tushadi, aks holda "o'zbek"
                -- va "ozbek" boshqa so'z bo'lib qolardi.
                search_text TEXT DEFAULT '',
                slide_count INTEGER DEFAULT 0,
                price INTEGER NOT NULL DEFAULT 0,
                file_id TEXT NOT NULL,
                file_type TEXT DEFAULT 'pptx',
                preview_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                view_count INTEGER DEFAULT 0,
                sale_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_store_items_active "
            "ON store_items (is_active, created_at DESC)"
        )

        # Saytdan boshlangan sotuvlar. To'lov botda amalga oshadi, shuning
        # uchun bu yerda faqat buyurtma holati kuzatiladi.
        await db.execute("""
            CREATE TABLE IF NOT EXISTS store_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                telegram_id INTEGER,
                price INTEGER NOT NULL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES store_items (id)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_store_orders_buyer "
            "ON store_orders (telegram_id, item_id)"
        )

        try:
            await db.execute("ALTER TABLE payments ADD COLUMN source TEXT DEFAULT ''")
            await db.commit()
            logger.info("Migration: added 'source' column to payments table")
        except Exception:
            pass  # Column already exists

        # Do'kon qidiruv ustuni — jadval ilgari usiz yaratilgan bo'lishi mumkin.
        try:
            await db.execute("ALTER TABLE store_items ADD COLUMN search_text TEXT DEFAULT ''")
            await db.commit()
            logger.info("Migration: added 'search_text' column to store_items")
        except Exception:
            pass  # Column already exists

        try:
            from services.store_taxonomy import normalize
            async with db.execute(
                "SELECT id, title, description, keywords FROM store_items "
                "WHERE search_text IS NULL OR search_text = ''"
            ) as cursor:
                stale = await cursor.fetchall()
            if stale:
                await db.executemany(
                    "UPDATE store_items SET search_text = ? WHERE id = ?",
                    [(normalize(" ".join(filter(None, row[1:]))), row[0]) for row in stale],
                )
                await db.commit()
                logger.info("Migration: filled search_text for %s store item(s)", len(stale))
        except Exception as store_mig_err:
            logger.warning("store_items search_text backfill skipped: %s", store_mig_err)

        # Privacy migration: copy any existing completed document_orders rows
        # into the anonymous document_stats table, then purge ALL legacy rows
        # from document_orders so no personal data (user_id, topic,
        # specifications, file_path) is retained at rest.
        #
        # 'generating' rows are also purged: after a process restart the
        # in-flight asyncio task is gone, so these rows are zombies and
        # cannot be resumed — keeping them would leak PII indefinitely.
        try:
            async with db.execute(
                "SELECT document_type, completed_at FROM document_orders WHERE status = 'completed'"
            ) as cursor:
                old_rows = await cursor.fetchall()
            if old_rows:
                await db.executemany(
                    "INSERT INTO document_stats (document_type, completed_at) VALUES (?, ?)",
                    [(r[0], r[1] or None) for r in old_rows],
                )
                logger.info(
                    f"Migration: moved {len(old_rows)} completed orders into document_stats"
                )
            cursor = await db.execute("DELETE FROM document_orders")
            if cursor.rowcount:
                logger.info(
                    f"Migration: purged {cursor.rowcount} legacy document_orders rows "
                    f"(completed + failed + stale generating)"
                )
            await db.commit()
        except Exception as mig_err:
            logger.warning(f"Migration document_orders -> document_stats skipped: {mig_err}")

        await db.commit()
        logger.info("Database initialized successfully")

class Database:
    @staticmethod
    async def get_user(telegram_id: int) -> Optional[User]:
        """Get user by telegram ID with lazy referral code backfill"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    user_dict = dict(row)
                    # Remove free_service_used field if it exists (old database schema)
                    user_dict.pop('free_service_used', None)
                    # Lazy backfill: if user doesn't have referral_code, generate one with retry logic
                    if not user_dict.get('referral_code'):
                        max_retries = 5
                        for attempt in range(max_retries):
                            try:
                                referral_code = await Database.generate_referral_code()
                                await db.execute(
                                    "UPDATE users SET referral_code = ? WHERE telegram_id = ?",
                                    (referral_code, telegram_id)
                                )
                                await db.commit()
                                user_dict['referral_code'] = referral_code
                                break
                            except aiosqlite.IntegrityError:
                                # UNIQUE constraint failed - code already exists, retry with new code
                                if attempt == max_retries - 1:
                                    raise  # Re-raise if all retries exhausted
                                continue
                    return User(**user_dict)
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
                    user_dict = dict(row)
                    # Remove free_service_used field if it exists (old database schema)
                    user_dict.pop('free_service_used', None)
                    return User(**user_dict)
                return None

    @staticmethod
    async def generate_referral_code() -> str:
        """Generate unique referral code"""
        while True:
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
            async with aiosqlite.connect(DATABASE_FILE) as db:
                async with db.execute(
                    "SELECT COUNT(*) FROM users WHERE referral_code = ?", (code,)
                ) as cursor:
                    count = (await cursor.fetchone())[0]
                    if count == 0:
                        return code

    @staticmethod
    async def create_user(telegram_id: int, username: Optional[str] = None, first_name: Optional[str] = None, language: str = 'en', referred_by: Optional[int] = None) -> User:
        """Create new user with referral code"""
        referral_code = await Database.generate_referral_code()
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                """INSERT INTO users (telegram_id, username, first_name, language, referral_code, referred_by) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (telegram_id, username, first_name, language, referral_code, referred_by)
            )
            await db.commit()
            user = await Database.get_user(telegram_id)
            if not user:
                raise ValueError(f"Failed to create user with telegram_id {telegram_id}")
            return user

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
    async def create_payment(user_id: int, amount: int, screenshot_file_id: str, source: str = "") -> int:
        """Create payment record"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                "INSERT INTO payments (user_id, amount, screenshot_file_id, source) VALUES (?, ?, ?, ?)",
                (user_id, amount, screenshot_file_id, source)
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
    async def update_payment_amount(payment_id: int, new_amount: int):
        """Update payment amount"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE payments SET amount = ?, updated_at = ? WHERE id = ?",
                (new_amount, datetime.now(), payment_id)
            )
            await db.commit()

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
    async def deactivate_promocode_by_code(code: str) -> bool:
        """Deactivate promocode by code, returns True if found and deactivated"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "UPDATE promocodes SET is_active = FALSE WHERE code = ? AND is_active = TRUE",
                (code.upper(),)
            ) as cursor:
                await db.commit()
                return cursor.rowcount > 0

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
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def get_feature_status(self, feature_name: str) -> bool:
        """Get feature toggle status"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "SELECT is_enabled FROM feature_toggles WHERE feature_name = ?",
                (feature_name,)
            ) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else True  # Default to enabled

    async def set_feature_status(self, feature_name: str, is_enabled: bool):
        """Set feature toggle status"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "INSERT OR REPLACE INTO feature_toggles (feature_name, is_enabled) VALUES (?, ?)",
                (feature_name, is_enabled)
            )
            await db.commit()

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
        """Finalize a document order.

        On "completed": insert an anonymous row into document_stats
        (document_type + completed_at only), then DELETE the original row.
        On any other status (e.g. "failed"): DELETE the original row.

        Net effect: document_orders is purely transient — no personal data
        (user_id, topic, specifications, file_path) is retained after
        generation ends.
        """
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "SELECT document_type FROM document_orders WHERE id = ?",
                (order_id,),
            ) as cursor:
                row = await cursor.fetchone()
            if row is None:
                logger.warning(
                    f"update_document_order: order_id={order_id} not found "
                    f"(status={status}); idempotent no-op."
                )
                return
            doc_type = row[0]
            if status == "completed":
                await db.execute(
                    "INSERT INTO document_stats (document_type, completed_at) VALUES (?, CURRENT_TIMESTAMP)",
                    (doc_type,),
                )
            await db.execute(
                "DELETE FROM document_orders WHERE id = ?",
                (order_id,),
            )
            await db.commit()

    @staticmethod
    async def get_all_sample_files() -> List[Dict]:
        """Get all sample files"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sample_files ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    async def get_active_sample_files() -> List[Dict]:
        """Get only active sample files"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sample_files WHERE is_active = 1 ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    async def add_sample_file(title: str, description: str, file_id: str, file_type: str) -> int:
        """Add new sample file"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                "INSERT INTO sample_files (title, description, file_id, file_type) VALUES (?, ?, ?, ?)",
                (title, description, file_id, file_type)
            )
            await db.commit()
            return cursor.lastrowid

    @staticmethod
    async def delete_sample_file(sample_id: int) -> bool:
        """Delete sample file"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "DELETE FROM sample_files WHERE id = ?", (sample_id,)
            ) as cursor:
                await db.commit()
                return cursor.rowcount > 0

    @staticmethod
    async def get_sample_file(sample_id: int) -> Optional[Dict]:
        """Get sample file by ID"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sample_files WHERE id = ?", (sample_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    @staticmethod
    async def get_all_users() -> List[User]:
        """Get all users"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users ORDER BY created_at DESC") as cursor:
                rows = await cursor.fetchall()
                users = []
                for row in rows:
                    user_dict = dict(row)
                    # Remove free_service_used field if it exists (old database schema)
                    user_dict.pop('free_service_used', None)
                    users.append(User(**user_dict))
                return users

    @staticmethod
    async def get_active_users(days: int = 30) -> List[User]:
        """Get users active within specified days"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE updated_at >= datetime('now', '-{} days') ORDER BY updated_at DESC".format(days)
            ) as cursor:
                rows = await cursor.fetchall()
                users = []
                for row in rows:
                    user_dict = dict(row)
                    # Remove free_service_used field if it exists (old database schema)
                    user_dict.pop('free_service_used', None)
                    users.append(User(**user_dict))
                return users

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

            # Revenue today
            async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved' AND date(created_at) = date('now')"
            ) as cursor:
                revenue_today = (await cursor.fetchone())[0]

            # Revenue this month
            async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved' AND created_at >= datetime('now', '-30 days')"
            ) as cursor:
                revenue_month = (await cursor.fetchone())[0]

            # Document orders (anonymous stats — completed only)
            async with db.execute("SELECT COUNT(*) FROM document_stats") as cursor:
                total_orders = (await cursor.fetchone())[0]

            # Orders this month
            async with db.execute(
                "SELECT COUNT(*) FROM document_stats WHERE completed_at >= datetime('now', '-30 days')"
            ) as cursor:
                orders_month = (await cursor.fetchone())[0]

            # Orders by type
            async with db.execute(
                "SELECT document_type, COUNT(*) FROM document_stats GROUP BY document_type"
            ) as cursor:
                orders_by_type = {row[0]: row[1] for row in await cursor.fetchall()}

            return {
                'total_users': total_users,
                'users_today': users_today,
                'users_week': users_week,
                'users_month': users_month,
                'revenue_today': revenue_today,
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

    # Referral system methods
    @staticmethod
    async def get_user_by_username(username: str) -> Optional[User]:
        """Get user by Telegram username (without @)"""
        clean = username.lstrip("@").strip()
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (clean,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return User(**dict(row))
                return None

    @staticmethod
    async def get_user_by_referral_code(referral_code: str) -> Optional[User]:
        """Get user by referral code"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE referral_code = ?", (referral_code,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return User(**dict(row))
                return None

    @staticmethod
    async def create_referral(referrer_id: int, referred_id: int) -> int:
        """Create referral record"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                (referrer_id, referred_id)
            )
            await db.commit()
            return cursor.lastrowid

    @staticmethod
    async def get_referral(referrer_id: int, referred_id: int) -> Optional[Referral]:
        """Get referral record"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM referrals WHERE referrer_id = ? AND referred_id = ?",
                (referrer_id, referred_id)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return Referral(**dict(row))
                return None

    @staticmethod
    async def update_referral_earnings(referrer_id: int, referred_id: int, amount: int):
        """Update referral earnings"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE referrals SET total_earned = total_earned + ? WHERE referrer_id = ? AND referred_id = ?",
                (amount, referrer_id, referred_id)
            )
            await db.execute(
                "UPDATE users SET referral_earnings = referral_earnings + ? WHERE telegram_id = ?",
                (amount, referrer_id)
            )
            await db.commit()

    @staticmethod
    async def update_signup_bonus(referrer_id: int, referred_id: int, given: bool = True):
        """Mark signup bonus as given"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE referrals SET signup_bonus_given = ? WHERE referrer_id = ? AND referred_id = ?",
                (given, referrer_id, referred_id)
            )
            await db.commit()

    @staticmethod
    async def update_payment_bonus(referrer_id: int, referred_id: int, given: bool = True):
        """Mark payment bonus as given"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE referrals SET payment_bonus_given = ? WHERE referrer_id = ? AND referred_id = ?",
                (given, referrer_id, referred_id)
            )
            await db.commit()

    @staticmethod
    async def get_referral_stats(telegram_id: int) -> dict:
        """Get referral statistics for user"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            # Count total referrals
            async with db.execute(
                "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (telegram_id,)
            ) as cursor:
                total_referrals = (await cursor.fetchone())[0]

            # Count referrals who made payments
            async with db.execute(
                "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND payment_bonus_given = TRUE",
                (telegram_id,)
            ) as cursor:
                paid_referrals = (await cursor.fetchone())[0]

            # Get total earnings from referrals
            async with db.execute(
                "SELECT COALESCE(SUM(total_earned), 0) FROM referrals WHERE referrer_id = ?",
                (telegram_id,)
            ) as cursor:
                total_earned = (await cursor.fetchone())[0]

            return {
                'total_referrals': total_referrals,
                'paid_referrals': paid_referrals,
                'total_earned': total_earned
            }

    @staticmethod
    async def has_made_payment(telegram_id: int) -> bool:
        """Check if user has made any approved payment"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            user = await Database.get_user(telegram_id)
            if not user:
                return False

            async with db.execute(
                "SELECT COUNT(*) FROM payments WHERE user_id = ? AND status = 'approved'",
                (user.id,)
            ) as cursor:
                count = (await cursor.fetchone())[0]
                return count > 0

    @staticmethod
    async def add_sample_file(title: str, description: str, file_id: str, file_type: str) -> bool:
        """Add a new sample file"""
        try:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute(
                    "INSERT INTO sample_files (title, description, file_id, file_type) VALUES (?, ?, ?, ?)",
                    (title, description, file_id, file_type)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding sample file: {e}")
            return False

    @staticmethod
    async def get_all_sample_files() -> List[Dict]:
        """Get all active sample files"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sample_files WHERE is_active = 1 ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    async def delete_sample_file(sample_id: int) -> bool:
        """Delete a sample file (soft delete)"""
        try:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute(
                    "UPDATE sample_files SET is_active = 0 WHERE id = ?",
                    (sample_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error deleting sample file: {e}")
            return False

    @staticmethod
    async def get_sample_file(sample_id: int) -> Optional[Dict]:
        """Get a specific sample file by ID"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sample_files WHERE id = ? AND is_active = 1",
                (sample_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    @staticmethod
    async def is_user_blocked(telegram_id: int) -> bool:
        """Check if user is blocked"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM blocked_users WHERE telegram_id = ?",
                (telegram_id,)
            ) as cursor:
                count = (await cursor.fetchone())[0]
                return count > 0

    @staticmethod
    async def block_user(telegram_id: int, username: str, blocked_by: int, reason: str = None) -> bool:
        """Block a user"""
        try:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO blocked_users (telegram_id, username, blocked_by, reason) VALUES (?, ?, ?, ?)",
                    (telegram_id, username, blocked_by, reason)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error blocking user: {e}")
            return False

    @staticmethod
    async def unblock_user(telegram_id: int) -> bool:
        """Unblock a user"""
        try:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute(
                    "DELETE FROM blocked_users WHERE telegram_id = ?",
                    (telegram_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error unblocking user: {e}")
            return False

    @staticmethod
    async def get_blocked_users() -> List[Dict]:
        """Get all blocked users"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM blocked_users ORDER BY blocked_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    @staticmethod
    async def get_bot_setting(setting_key: str) -> Optional[str]:
        """Get a bot setting value"""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "SELECT setting_value FROM bot_settings WHERE setting_key = ?",
                (setting_key,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    @staticmethod
    async def set_bot_setting(setting_key: str, setting_value: str) -> bool:
        """Set a bot setting value"""
        try:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO bot_settings (setting_key, setting_value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (setting_key, setting_value)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error setting bot setting: {e}")
            return False

    @staticmethod
    async def get_current_ai_model() -> str:
        """Get current AI model key"""
        from config import DEFAULT_AI_MODEL
        model = await Database.get_bot_setting("current_ai_model")
        return model if model else DEFAULT_AI_MODEL

    @staticmethod
    async def set_current_ai_model(model_key: str) -> bool:
        """Set current AI model"""
        return await Database.set_bot_setting("current_ai_model", model_key)

    @staticmethod
    async def get_premium_ai_model() -> str:
        """Premium taqdimot uchun tanlangan model kaliti.

        U alohida saqlanadi: premium taqdimot eng qimmat xizmat va unda
        matn sifati boshqa hujjatlardagidan ko'ra ko'proq ko'rinadi,
        shuning uchun unga kuchliroq (va qimmatroq) model qo'yish, qolgan
        xizmatlarni esa arzonroq modelda qoldirish mumkin.
        """
        from config import PREMIUM_DEFAULT_AI_MODEL

        model = await Database.get_bot_setting("premium_ai_model")
        return model if model else PREMIUM_DEFAULT_AI_MODEL

    @staticmethod
    async def set_premium_ai_model(model_key: str) -> bool:
        return await Database.set_bot_setting("premium_ai_model", model_key)

    # ── Do'kon katalogi ────────────────────────────────────────────────────

    @staticmethod
    async def generate_store_code() -> str:
        """Saytdagi havolada ko'rinadigan qisqa, takrorlanmas kod."""
        alphabet = string.ascii_uppercase + string.digits
        async with aiosqlite.connect(DATABASE_FILE) as db:
            for _ in range(20):
                code = "".join(secrets.choice(alphabet) for _ in range(8))
                async with db.execute(
                    "SELECT 1 FROM store_items WHERE public_code = ?", (code,)
                ) as cursor:
                    if await cursor.fetchone() is None:
                        return code
        raise RuntimeError("store uchun bo'sh kod topilmadi")

    @staticmethod
    async def create_store_item(
        public_code: str,
        title: str,
        file_id: str,
        price: int,
        description: str = "",
        category: str = "",
        language: str = "uz",
        keywords: str = "",
        slide_count: int = 0,
        file_type: str = "pptx",
        preview_count: int = 0,
    ) -> int:
        from services.store_taxonomy import normalize

        search_text = normalize(" ".join(filter(None, (title, description, keywords))))
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                """INSERT INTO store_items
                   (public_code, title, description, category, language, keywords,
                    search_text, slide_count, price, file_id, file_type, preview_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (public_code, title, description, category, language, keywords,
                 search_text, slide_count, price, file_id, file_type, preview_count),
            )
            await db.commit()
            return cursor.lastrowid

    @staticmethod
    async def list_store_items(
        query: str = "",
        category: str = "",
        language: str = "",
        sort: str = "new",
        limit: int = 24,
        offset: int = 0,
    ) -> Dict:
        """Katalogni filtrlab qaytaradi: {'items': [...], 'total': N, 'fuzzy': bool}.

        Qidiruv so'zma-so'z ishlaydi: mavzu aynan topilmasa ham, so'zlaridan
        biri mos kelgan ishlar chiqadi va ko'p so'zi moslari yuqori turadi.
        Umuman moslik bo'lmasa — eng yaqin sarlavhalar qaytariladi.
        """
        from services.store_taxonomy import normalize

        # Tartib faqat ma'lum qiymatlardan tanlanadi — bu ustun nomi SQL ga
        # to'g'ridan-to'g'ri qo'shilgani uchun majburiy.
        order_by = {
            "new": "created_at DESC, id DESC",
            "popular": "sale_count DESC, view_count DESC, id DESC",
            "cheap": "price ASC, id DESC",
            "expensive": "price DESC, id DESC",
        }.get(sort, "created_at DESC, id DESC")

        FIELDS = ("public_code, title, description, category, language, "
                  "slide_count, price, preview_count, sale_count, created_at")

        base_where = ["is_active = 1"]
        base_params: list = []
        if category:
            base_where.append("category = ?")
            base_params.append(category)
        if language:
            base_where.append("language = ?")
            base_params.append(language)

        words = [w for w in normalize(query).split() if len(w) >= 2][:6]
        likes = [
            "%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            for w in words
        ]

        where = list(base_where)
        rank = ""
        match_params: list = []
        if likes:
            where.append("(" + " OR ".join(
                ["search_text LIKE ? ESCAPE '\\'"] * len(likes)) + ")")
            # Ko'proq so'zi mos kelgan ish yuqorida tursin.
            rank = " + ".join(
                ["(CASE WHEN search_text LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END)"] * len(likes)
            ) + " DESC, "
            match_params = likes

        clause = " AND ".join(where)
        where_params = base_params + match_params

        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT COUNT(*) FROM store_items WHERE {clause}", where_params
            ) as cursor:
                total = (await cursor.fetchone())[0]

            if total:
                async with db.execute(
                    f"""SELECT {FIELDS} FROM store_items WHERE {clause}
                        ORDER BY {rank}{order_by} LIMIT ? OFFSET ?""",
                    where_params + match_params + [limit, offset],
                ) as cursor:
                    rows = await cursor.fetchall()
                return {"items": [dict(r) for r in rows], "total": total, "fuzzy": False}

            if not words:
                return {"items": [], "total": 0, "fuzzy": False}

            # Hech narsa mos kelmadi — mijozni bo'sh sahifada qoldirmaslik
            # uchun sarlavhasi eng yaqin ishlar ko'rsatiladi.
            base_clause = " AND ".join(base_where)
            async with db.execute(
                f"SELECT public_code, search_text FROM store_items WHERE {base_clause}",
                base_params,
            ) as cursor:
                candidates = await cursor.fetchall()

            codes = Database._closest_codes(normalize(query), candidates, limit + offset)
            if not codes:
                return {"items": [], "total": 0, "fuzzy": False}

            page = codes[offset:offset + limit]
            if not page:
                return {"items": [], "total": len(codes), "fuzzy": True}
            holes = ",".join("?" * len(page))
            async with db.execute(
                f"SELECT {FIELDS} FROM store_items WHERE public_code IN ({holes})", page
            ) as cursor:
                found = {r["public_code"]: dict(r) for r in await cursor.fetchall()}

        return {
            "items": [found[c] for c in page if c in found],
            "total": len(codes),
            "fuzzy": True,
        }

    @staticmethod
    def _closest_codes(query: str, candidates, limit: int) -> List[str]:
        """Sarlavhasi so'ralganga eng o'xshash ishlarni tartiblab qaytaradi."""
        from difflib import SequenceMatcher

        query_words = [w for w in query.split() if len(w) >= 3]
        scored = []
        for row in candidates:
            text = row["search_text"] or ""
            if not text:
                continue
            best = SequenceMatcher(None, query, text[:120]).ratio()
            # Bitta so'z ham yetarlicha o'xshash bo'lsa — mavzu yaqin demak.
            for qw in query_words:
                for tw in text.split():
                    if abs(len(tw) - len(qw)) <= 4:
                        best = max(best, SequenceMatcher(None, qw, tw).ratio())
            if best >= 0.62:
                scored.append((best, row["public_code"]))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [code for _, code in scored[:limit]]

    @staticmethod
    async def get_store_item(public_code: str) -> Optional[Dict]:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM store_items WHERE public_code = ? AND is_active = 1",
                (public_code,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    @staticmethod
    async def all_store_codes() -> List[Dict]:
        """Sayt xaritasi uchun — barcha ochiq ishlarning kodi va sanasi."""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "SELECT public_code, created_at FROM store_items "
                "WHERE is_active = 1 ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
        return [{"code": r[0], "created_at": r[1]} for r in rows]

    @staticmethod
    async def get_store_categories() -> List[Dict]:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "SELECT category, COUNT(*) FROM store_items "
                "WHERE is_active = 1 AND category != '' "
                "GROUP BY category ORDER BY COUNT(*) DESC"
            ) as cursor:
                rows = await cursor.fetchall()
        return [{"name": r[0], "count": r[1]} for r in rows]

    @staticmethod
    async def bump_store_view(public_code: str) -> None:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE store_items SET view_count = view_count + 1 "
                "WHERE public_code = ?",
                (public_code,),
            )
            await db.commit()

    @staticmethod
    async def set_store_item_active(public_code: str, is_active: bool) -> bool:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                "UPDATE store_items SET is_active = ? WHERE public_code = ?",
                (1 if is_active else 0, public_code),
            )
            await db.commit()
            return cursor.rowcount > 0

    @staticmethod
    async def record_store_sale(item_id: int, telegram_id: int, price: int) -> int:
        """Sotuvni yozadi va katalogdagi sotuv hisobini oshiradi."""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                """INSERT INTO store_orders (item_id, telegram_id, price, status, paid_at)
                   VALUES (?, ?, ?, 'paid', CURRENT_TIMESTAMP)""",
                (item_id, telegram_id, price),
            )
            await db.execute(
                "UPDATE store_items SET sale_count = sale_count + 1 WHERE id = ?",
                (item_id,),
            )
            await db.commit()
            return cursor.lastrowid

    @staticmethod
    async def has_bought_store_item(telegram_id: int, item_id: int) -> bool:
        """Sotib olingan ish qayta to'lovsiz yuklab olinishi uchun."""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute(
                "SELECT 1 FROM store_orders WHERE telegram_id = ? AND item_id = ? "
                "AND status = 'paid' LIMIT 1",
                (telegram_id, item_id),
            ) as cursor:
                return await cursor.fetchone() is not None
