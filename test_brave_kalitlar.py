"""Brave kalitlari navbati: har kalit LIMIT so'rovdan keyin almashadi, rad etilgani o'tkazib yuboriladi.

    python test_brave_kalitlar.py
"""
import os
import sys
import tempfile

os.environ["BRAVE_KEYS_FILE"] = os.path.join(tempfile.mkdtemp(), "brave_keys.json")
os.environ["BRAVE_KEY_LIMIT"] = "3"
os.environ.pop("BRAVE_API_KEY", None)
os.environ.pop("BRAVE_SEARCH_API_KEY", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import brave_keys as bk  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


check("kalit yo'q — bo'sh", bk.take() == "" and bk.current() == "")
check("kalit qo'shiladi", bk.add("AAAA1111aaaa") and bk.add("BBBB2222bbbb") and bk.add("CCCC3333cccc"))
check("bir xil kalit ikki marta qo'shilmaydi", not bk.add("AAAA1111aaaa"))
seq = [bk.take() for _ in range(7)]
check("har kalit 3 so'rov (LIMIT), keyin navbatdagisi",
      seq == ["AAAA1111aaaa"] * 3 + ["BBBB2222bbbb"] * 3 + ["CCCC3333cccc"], seq)
bk.report_failure("CCCC3333cccc", 429)
check("429 — limit tugagan kalit o'tkazib yuboriladi, hammasi tugasa hisob boshidan", bk.take() == "AAAA1111aaaa")
bk.report_failure("AAAA1111aaaa", 401)
check("401 — yaroqsiz kalit endi ishlatilmaydi", bk.take() in ("BBBB2222bbbb", "CCCC3333cccc"))
st = bk.status()
check("holat: niqoblangan kalit, hisob, faol belgi",
      len(st) == 3 and st[0]["mask"] == "AAAA…aaaa" and st[0]["failed"] and sum(s["active"] for s in st) == 1, st)
bk.reset()
check("nollash: hammasi qayta ishlaydi, birinchidan boshlanadi", bk.take() == "AAAA1111aaaa" and not bk.status()[0]["failed"])
check("o'chirish", bk.remove(0) and [s["mask"] for s in bk.status()] == ["BBBB…bbbb", "CCCC…cccc"])
os.environ["BRAVE_API_KEY"] = "ENVK0000envk"
check(".env dagi kalit ham ro'yxatga birinchi bo'lib kiradi", bk.status()[0]["mask"] == "ENVK…envk")
bk.report_failure("BBBB2222bbbb", 403)
bk.report_failure("CCCC3333cccc", 403)
bk.report_failure("ENVK0000envk", 403)
check("hamma kalit yaroqsiz — bo'sh (qidiruv rasmni AI ga topshiradi)", bk.take() == "")

os.environ.setdefault("BOT_TOKEN", "1:x")
bk.reset()
bk.add("DDDD4444dddd")
from bot.handlers import admin  # noqa: E402

text, markup = admin._brave_keys_view()
buttons = [b.text for row in markup.inline_keyboard for b in row]
check("admin panel: kalitlar niqoblangan, to'liq kalit ko'rinmaydi, qo'shish/nollash/o'chirish tugmalari",
      "DDDD…dddd" in text and "DDDD4444dddd" not in text and "➕ Kalit qo'shish" in buttons
      and any(t.startswith("🗑") for t in buttons), (text, buttons))
check(".env dagi kalitni paneldan o'chirib bo'lmaydi (u .env da turadi)",
      not any("1-kalit" in t for t in buttons), buttons)

print()
print("HAMMASI O'TDI" if not FAILS else f"XATOLAR: {len(FAILS)} — {FAILS}")
sys.exit(1 if FAILS else 0)
