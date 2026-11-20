"""Admin «🔄 Botni yangilash»: «⏳ GitHub tekshirilmoqda...» da qotib qolmaydi.

- commit nomida «<», «>», «&» bo'lsa ham xabar chiqadi (HTML tozalanadi; avval Telegram rad etib, xabar qotardi);
- HTML baribir rad etilsa — oddiy matn bilan yangilanadi;
- osilib qolgan git (bola jarayonlari quvurni ushlab tursa ham) vaqt tugaganda o'ldiriladi;
- git parol/token so'rab kutib qolmaydi; tekshiruv alohida oqimda va umumiy vaqt chegarasi bilan.

    python test_bot_yangilash.py
"""
import asyncio
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


from bot.handlers import admin  # noqa: E402
from services import self_update  # noqa: E402


def telegram_html_ok(text: str) -> bool:
    """Telegram kabi: ruxsat etilgan teglardan tashqari «<» yoki noto'g'ri «&» bo'lsa — rad."""
    rest = re.sub(r"</?(?:b|i|u|s|code|pre|a(?: [^>]*)?)>", "", text)
    return "<" not in rest and ">" not in rest and not re.search(r"&(?!(?:amp|lt|gt|quot|#\d+);)", rest)


print("1) Commit nomida <, >, & — xabar chiqadi")
state = {"ok": True, "branch": "main", "current": "abc123 Tuzatish & <test>",
         "incoming": ["677351f Saytdagi tayyor fayl Telegramga: nomida <, >, & bo'lsa ham yetadi",
                      "b7f43d5 Personaj qo'shish"], "local_only": [], "dirty": []}
text, has = admin._format_update_status(state)
check("yangilanishlar ro'yxati HTML sifatida to'g'ri (Telegram qabul qiladi)", telegram_html_ok(text) and has, text)
check("commit nomi o'qiladigan holda", "nomida &lt;, &gt;, &amp; bo'lsa ham" in text, text)
text, _ = admin._format_update_status({"ok": False, "error": "fatal: <xato> & boshqa"})
check("git xatosi ham tozalanadi", telegram_html_ok(text), text)
text, _ = admin._format_update_status(dict(state, incoming=[], dirty=["a<b>.py"]))
check("o'zgargan fayl nomi ham tozalanadi", telegram_html_ok(text), text)


class Msg:
    def __init__(self, reject_html=False):
        self.reject_html, self.edits = reject_html, []
    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        if parse_mode == "HTML" and (self.reject_html or not telegram_html_ok(text)):
            raise RuntimeError("Bad Request: can't parse entities")
        self.edits.append((text, parse_mode))


print("2) HTML baribir rad etilsa — oddiy matn")
m = Msg(reject_html=True)
asyncio.run(admin._safe_edit(m, "🔄 <b>Botni yangilash</b>\n• 1 &amp; 2", None))
check("xabar baribir yangilanadi (teglarsiz)", m.edits and m.edits[-1] == ("🔄 Botni yangilash\n• 1 & 2", None), m.edits)

print("3) Osilib qolgan git — vaqt tugaganda to'xtaydi")
t0 = time.monotonic()
ok, out = self_update._run(["sh", "-c", "sleep 30 & sleep 30"], timeout=2)
took = time.monotonic() - t0
check("bola jarayoni quvurni ushlab tursa ham 2 soniyada qaytadi (avval cheksiz kutardi)", not ok and took < 8 and "tugamadi" in out,
      (ok, out, took))
ok, out = self_update._run(["sh", "-c", "echo $GIT_TERMINAL_PROMPT; read x; echo javob:$x"], timeout=5)
check("git parol so'rab kutmaydi (terminal so'rovi o'chiq, kirish yopiq)", ok and out.startswith("0") and "javob:" in out, out)
check("fetch: sekin ulanish uziladi, avtomatik gc o'chiq", "http.lowSpeedTime=30" in self_update._FETCH_OPTS
      and "gc.auto=0" in self_update._FETCH_OPTS)


async def slow_case():
    real, real_timeout = self_update.status, self_update.STATUS_TIMEOUT
    self_update.status = lambda: time.sleep(3) or {"ok": True}
    self_update.STATUS_TIMEOUT = 1
    try:
        return await admin._update_status()
    finally:
        self_update.status, self_update.STATUS_TIMEOUT = real, real_timeout
st = asyncio.run(slow_case())
check("GitHub javob bermasa — vaqt tugagach tushunarli xabar (qotib qolmaydi)", not st["ok"] and "javob bermadi" in st["error"], st)

import inspect  # noqa: E402
src = inspect.getsource(admin.handle_self_update) + inspect.getsource(admin._do_self_update)
check("tekshiruv va yangilash alohida oqimda (umumiy oqimlar band bo'lsa ham boshlanadi)",
      "asyncio.to_thread(self_update" not in src and "in_background" in inspect.getsource(admin._do_self_update))

print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
