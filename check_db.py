import aiosqlite
import asyncio

async def check():
    db = await aiosqlite.connect('bot.db')
    
    # Total users
    cursor = await db.execute('SELECT COUNT(*) FROM users')
    count = await cursor.fetchone()
    print(f'📊 Total users: {count[0]}')
    
    # Recent users
    cursor = await db.execute('SELECT telegram_id, username, first_name, language, created_at FROM users ORDER BY created_at DESC LIMIT 10')
    users = await cursor.fetchall()
    print(f'\n📝 Recent 10 users:')
    for u in users:
        print(f'  - ID: {u[0]}, Username: {u[1]}, Name: {u[2]}, Lang: {u[3]}, Created: {u[4]}')
    
    await db.close()

asyncio.run(check())
