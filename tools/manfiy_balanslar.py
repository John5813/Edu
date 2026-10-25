"""Bazadagi manfiy (minus) balansli foydalanuvchilarni topadi.

Ishlatish (loyiha ildizidan):
    python tools/manfiy_balanslar.py                 # faqat ro'yxatni chiqaradi
    python tools/manfiy_balanslar.py --csv out.csv   # ro'yxatni CSV faylga ham yozadi
    python tools/manfiy_balanslar.py --tuzat         # manfiy balanslarni 0 ga tenglaydi (tasdiq so'raydi)
    python tools/manfiy_balanslar.py --baza boshqa.db

Skript faqat o'qiydi; --tuzat berilmasa bazada hech narsa o'zgarmaydi.
"""
import argparse
import csv
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def manfiylarni_ol(conn: sqlite3.Connection) -> list:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        "SELECT telegram_id, username, first_name, balance, created_at, updated_at "
        "FROM users WHERE balance < 0 ORDER BY balance ASC, created_at ASC"
    ).fetchall()


def main() -> int:
    parser = argparse.ArgumentParser(description="Manfiy balansli foydalanuvchilarni topish")
    parser.add_argument("--baza", default=str(ROOT / "bot.db"), help="SQLite baza fayli (standart: bot.db)")
    parser.add_argument("--csv", help="Natijani shu CSV faylga yozish")
    parser.add_argument("--tuzat", action="store_true", help="Manfiy balanslarni 0 ga tenglash (oldin zaxira nusxa olinadi)")
    args = parser.parse_args()

    baza = Path(args.baza)
    if not baza.exists():
        print(f"❌ Baza topilmadi: {baza}")
        return 1

    conn = sqlite3.connect(baza)
    rows = manfiylarni_ol(conn)

    if not rows:
        print("✅ Manfiy balansli foydalanuvchi yo'q.")
        return 0

    print(f"{'telegram_id':>12}  {'balans':>10}  {'username':<20}  {'ism':<20}  ro'yxatdan o'tgan")
    print("-" * 90)
    for r in rows:
        print(f"{r['telegram_id']:>12}  {r['balance']:>10,}  {(r['username'] or '-'):<20.20}  "
              f"{(r['first_name'] or '-'):<20.20}  {r['created_at']}")
    print("-" * 90)
    jami = sum(r["balance"] for r in rows)
    print(f"Jami: {len(rows)} ta foydalanuvchi, umumiy minus: {jami:,} so'm")

    # Qaysi summalar ko'p uchrayotganini ko'rsatadi (masalan, hammasi -5000 bo'lsa, bitta sababdan)
    guruhlar = conn.execute(
        "SELECT balance, COUNT(*) AS soni FROM users WHERE balance < 0 GROUP BY balance ORDER BY soni DESC"
    ).fetchall()
    print("\nSummalar bo'yicha:")
    for g in guruhlar:
        print(f"  {g['balance']:>10,} so'm  →  {g['soni']} ta")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["telegram_id", "username", "first_name", "balance", "created_at", "updated_at"])
            w.writerows([tuple(r) for r in rows])
        print(f"\n📄 CSV yozildi: {args.csv}")

    if args.tuzat:
        javob = input(f"\n⚠️ {len(rows)} ta foydalanuvchi balansi 0 ga tenglanadi. Davom etilsinmi? (ha/yo'q): ")
        if javob.strip().lower() not in ("ha", "h", "yes", "y"):
            print("Bekor qilindi.")
            return 0
        zaxira = baza.with_name(f"{baza.stem}_zaxira_{datetime.now():%Y%m%d_%H%M%S}{baza.suffix}")
        conn.close()
        shutil.copy2(baza, zaxira)
        print(f"💾 Zaxira nusxa: {zaxira}")
        conn = sqlite3.connect(baza)
        cur = conn.execute(
            "UPDATE users SET balance = 0, updated_at = CURRENT_TIMESTAMP WHERE balance < 0"
        )
        conn.commit()
        print(f"✅ {cur.rowcount} ta foydalanuvchi balansi 0 ga tenglandi.")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
