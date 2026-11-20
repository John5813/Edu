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

bk.reset()
bk.add("EEEE5555eeee")
names = lambda: [x["mask"] for x in bk.status()]   # noqa: E731
active = lambda: next(x["mask"] for x in bk.status() if x["active"])   # noqa: E731
first = active()
check("qo'lda o'tkazib yuborish: joriy kalit tugagan deb belgilanadi, keyingisi faol", bk.skip() >= 0 and active() != first)
check("qo'lda tanlash: istalgan kalitga o'tish (tugagan bo'lsa ham qayta sinaladi)",
      bk.activate(names().index(first)) and active() == first and bk.take() == "ENVK0000envk")
bk.activate(names().index("EEEE…eeee"))
check("tanlangan kalit so'rovlarda ishlatiladi", bk.take() == "EEEE5555eeee")

os.environ.setdefault("BOT_TOKEN", "1:x")
bk.reset()
bk.add("DDDD4444dddd")
from bot.handlers import admin  # noqa: E402

text, markup = admin._brave_keys_view()
buttons = [b.text for row in markup.inline_keyboard for b in row]
check("admin panel: kalitlar niqoblangan, to'liq kalit ko'rinmaydi, qo'shish/nollash/o'chirish tugmalari",
      "DDDD…dddd" in text and "DDDD4444dddd" not in text and "➕ Kalit qo'shish" in buttons
      and any(t.startswith("🗑") for t in buttons) and "⏭ Keyingi kalitga o'tish" in buttons
      and any(t.startswith("▶️") for t in buttons), (text, buttons))
check("panel ostida «Yopish» tugmasi, o'chirish avval tasdiq so'raydi",
      buttons[-1] == "❌ Yopish" and all(b.callback_data.startswith("brave_ask:")
                                        for row in markup.inline_keyboard for b in row if b.text.startswith("🗑")),
      buttons)
check(".env dagi kalitni paneldan o'chirib bo'lmaydi (u .env da turadi)",
      not any("1-kalit" in t for t in buttons), buttons)

print("Limit tugashi haqida adminga xabar")
from services import admin_alerts  # noqa: E402
ALERTS = []
admin_alerts.alert = lambda key, text, cooldown=0: ALERTS.append((key, text))
bk.reset()
for k in [r for r in bk.status()]:
    pass
bk.report_failure("BBBB2222bbbb", 402)
check("402 (kredit tugadi) — adminga xabar: qaysi kalit, nima bo'ldi, nechta kalit qoldi",
      ALERTS and "BBBB…bbbb" in ALERTS[-1][1] and "krediti tugadi" in ALERTS[-1][1] and "ishlaydigan kalitlar" in ALERTS[-1][1], ALERTS)
n = len(ALERTS)
bk.report_failure("CCCC3333cccc", 429, {"X-RateLimit-Limit": "1, 15000", "X-RateLimit-Remaining": "0, 9000"})
check("429 faqat soniyalik chegara (oylik qoldiq bor) — kalit tugagan deb belgilanmaydi, xabar yo'q",
      len(ALERTS) == n and not next(r for r in bk.status() if r["mask"] == "CCCC…cccc")["spent"], ALERTS[n:])
bk.report_failure("CCCC3333cccc", 429, {"X-RateLimit-Limit": "1, 15000", "X-RateLimit-Remaining": "0, 0"})
check("429 oylik limit tugadi — xabar", "oylik limiti tugadi" in ALERTS[-1][1], ALERTS[-1])
for row in bk.status():                     # qolgan hamma kalit krediti ham tugadi
    pass
for key in [k["key"] for k in bk._load()["keys"]]:
    bk.report_failure(key, 402)
all_down = [t for k, t in ALERTS if k == "brave_all_down"]
check("hamma kalit tugaganda — alohida 🚨 xabar va yechim (kredit / yangi kalit)",
      all_down and "HAMMA" in all_down[-1] and "Kalit qo'shish" in all_down[-1], ALERTS[-3:])
text, _ = admin._brave_keys_view()
check("admin panel: tugagan kalit belgisi va oxirgi rad sababi ko'rinadi", "oxirgi rad: HTTP 402" in text
      and "darhol xabar keladi" in text, text)
bk.reset(); ALERTS.clear()
bk.note_response("AAAA1111aaaa", {"X-RateLimit-Limit": "1, 2000", "X-RateLimit-Remaining": "0, 150"})
check("oylik limitli kalitda 10% dan kam qoldi — ogohlantirish", ALERTS and "150 ta so'rov qoldi" in ALERTS[-1][1], ALERTS)
ALERTS.clear()
bk.note_response("AAAA1111aaaa", {"X-RateLimit-Limit": "50, 0", "X-RateLimit-Remaining": "49, 0"})
check("kredit bo'yicha tarif (oylik limit 0) — bekorga ogohlantirmaydi", not ALERTS, ALERTS)
bk.report_failure("AAAA1111aaaa", 402)
bk.note_response("AAAA1111aaaa", {"X-RateLimit-Limit": "50, 0", "X-RateLimit-Remaining": "49, 0"})
check("kredit to'ldirilib kalit yana ishlasa — rad belgisi o'chadi", not bk.status()[0]["error"], bk.status()[0])

import asyncio, threading  # noqa: E401,E402
import importlib  # noqa: E402
importlib.reload(admin_alerts)
SENT = []
class _Bot:
    async def send_message(self, chat, text, **kw): SENT.append((chat, text))
async def _thread_case():
    import config
    if not config.ADMIN_IDS:
        config.ADMIN_IDS.append(7001)
    admin_alerts.set_bot(_Bot())
    th = threading.Thread(target=admin_alerts.alert, args=("t", "oqimdan xabar"))
    th.start(); th.join()
    await asyncio.sleep(0.05)
asyncio.run(_thread_case())
check("boshqa oqimdan (Brave so'rovi thread'da) ham adminga xabar yetadi", any(t == "oqimdan xabar" for _, t in SENT), SENT)

print()
print("HAMMASI O'TDI" if not FAILS else f"XATOLAR: {len(FAILS)} — {FAILS}")
sys.exit(1 if FAILS else 0)
