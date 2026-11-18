"""Admin xabarlarida to'lov qayerdan qilingani: sayt yoki bot (Click, Payme, Uzum)."""
import time

import aiosqlite

UZUM_WINDOW = 24 * 3600      # Uzum havolasi berilgandan keyin shuncha vaqt ichidagi to'lov — o'sha manbadan


def note(source: str) -> str:
    """Admin xabari oxiriga: « · 🌐 sayt orqali» yoki « · 🤖 bot orqali» (noma'lum — bo'sh)."""
    source = (source or "").lower()
    if source == "web":
        return " · 🌐 sayt orqali"
    if source == "bot":
        return " · 🤖 bot orqali"
    return ""


async def _conn():
    from database.database import DATABASE_FILE
    conn = await aiosqlite.connect(DATABASE_FILE)
    await conn.execute("""CREATE TABLE IF NOT EXISTS uzum_link_source (
        telegram_id INTEGER NOT NULL, source TEXT NOT NULL, created_at REAL NOT NULL)""")
    return conn


async def remember_uzum(telegram_id: int, source: str) -> None:
    """Uzum to'lovi deeplink orqali (Uzum serveri manbani qaytarmaydi): havola qayerdan berilgani eslab qolinadi."""
    conn = await _conn()
    try:
        await conn.execute("DELETE FROM uzum_link_source WHERE created_at < ?", (time.time() - UZUM_WINDOW,))
        await conn.execute("INSERT INTO uzum_link_source (telegram_id, source, created_at) VALUES (?, ?, ?)",
                           (int(telegram_id), str(source or ""), time.time()))
        await conn.commit()
    finally:
        await conn.close()


async def uzum_source(telegram_id: int) -> str:
    conn = await _conn()
    try:
        async with conn.execute("SELECT source FROM uzum_link_source WHERE telegram_id = ? AND created_at >= ? "
                                "ORDER BY created_at DESC LIMIT 1", (int(telegram_id), time.time() - UZUM_WINDOW)) as cur:
            row = await cur.fetchone()
        return row[0] if row else ""
    finally:
        await conn.close()
