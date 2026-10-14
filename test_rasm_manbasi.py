"""Rasm manbasi — mijoz tanlovi: internetdan / AI chizadi / aralash.

- "web": faqat internet qidiruvi, AI chizmaydi (topilmagan joyda matn qoladi);
- "ai": internetga qaralmaydi, hammasini AI chizadi;
- "mix" (sukut): avval internet, topilmaganini AI chizadi;
- xulosa ekranida uchta tugma, tanlangani ✓; 3D Pro'da tanlov yo'q.

    python test_rasm_manbasi.py
"""
import asyncio, os, sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import html_images

PAGE = '<section class="slide"><div class="body"><div class="rasm" data-prompt="{p}"></div></div></section>'
COVER = '<section class="slide dark"><div class="body"><h1 class="title big">Mavzu</h1></div></section>'


def run(source, found):
    """found — internet natijasi har slot uchun (None — topilmadi). (qo'yilgan, qidirildimi, chizilganlar)"""
    calls = {"find": 0, "drawn": []}

    async def find(topic, slots, **kw):
        calls["find"] += 1
        return list(found)[:len(slots)]

    async def generate(prompt):
        calls["drawn"].append(prompt)
        return "/ai.png"

    pages = [PAGE.format(p="bir"), PAGE.format(p="ikki")]
    with patch.object(html_images, "_take_uri", lambda path: "data:image/png;base64,AA" if path else None), \
            patch.object(html_images, "_together_generate", lambda aspect="4:3": generate):
        _, placed = asyncio.run(html_images.fill_photos(pages, topic="Mavzu", source=source,
                                                        find=find if source != "ai" else None))
    return placed, calls


print("1) Slayd rasmlari")
placed, calls = run("web", ["/web1.jpg", None])
check("internetdan: qidiriladi, AI chizmaydi, topilmagani bo'sh", calls["find"] == 1 and not calls["drawn"]
      and placed == 1, (placed, calls))
placed, calls = run("ai", ["/web1.jpg", "/web2.jpg"])
check("AI: internetga qaralmaydi, ikkalasini chizadi", calls["find"] == 0 and len(calls["drawn"]) == 2
      and placed == 2, (placed, calls))
placed, calls = run("mix", ["/web1.jpg", None])
check("aralash: internetdan topilgani, qolganini AI", calls["find"] == 1 and len(calls["drawn"]) == 1
      and placed == 2, (placed, calls))
placed, calls = run("noma'lum", ["/web1.jpg", None])
check("noma'lum qiymat — aralash", placed == 2 and len(calls["drawn"]) == 1, (placed, calls))

print("\n2) Muqova rasmi")
async def cover(source, found):
    calls = {"find": 0}
    async def find(topic, slots, **kw):
        calls["find"] += 1
        return [found]
    async def generate(subject):
        calls["drawn"] = True
        return "/ai.png"
    with patch.object(html_images, "_take_uri", lambda path: "data:image/png;base64,AA" if path else None):
        _, done = await html_images.fill_cover([COVER], "Mavzu", generate=generate, find=find, source=source)
    return done, calls
done, calls = asyncio.run(cover("web", None))
check("internetdan: muqova topilmasa AI chizmaydi", not done and calls["find"] == 1 and "drawn" not in calls, calls)
done, calls = asyncio.run(cover("ai", "/web.jpg"))
check("AI: muqova internetdan qidirilmaydi, chiziladi", done and calls["find"] == 0 and calls.get("drawn"), calls)
done, calls = asyncio.run(cover("mix", None))
check("aralash: muqova topilmasa AI chizadi", done and calls["find"] == 1 and calls.get("drawn"), calls)

print("\n3) Bot: xulosa ekrani")
from bot.handlers import premium_presentation as h
data = {"topic": "Plombalar", "slide_count": 10, "presentation_language": "ru"}
text, markup = h._summary(data, "uz")
buttons = [b for row in markup.inline_keyboard for b in row if b.callback_data.startswith("prem_ppt_img:")]
check("uchta tugma, sukut — aralash ✓", [b.callback_data for b in buttons] == ["prem_ppt_img:web", "prem_ppt_img:ai",
      "prem_ppt_img:mix"] and buttons[2].text.startswith("✓") and not buttons[0].text.startswith("✓"), buttons)
check("xulosada rasm manbasi yozilgan", "🖼 Rasmlar" in text and "avval internetdan" in text, text)
text, markup = h._summary({**data, "photo_source": "web"}, "uz")
buttons = [b for row in markup.inline_keyboard for b in row if b.callback_data.startswith("prem_ppt_img:")]
check("internet tanlangan ✓", buttons[0].text.startswith("✓") and "haqiqiy fotosuratlar" in text)
pro = {**data, "kind": h.KIND_PRO3D}
text, markup = h._summary(pro, "uz")
check("3D Pro'da tanlov yo'q", h._photo_source(pro) is None and "prem_ppt_img:" not in str(markup)
      and "🖼 Rasmlar" not in text)

stored = {}
async def tap(value):
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=5, user_id=5))
    await state.update_data(**data)
    edit = AsyncMock()
    cb = SimpleNamespace(data=f"prem_ppt_img:{value}", answer=AsyncMock(), from_user=SimpleNamespace(id=5),
                         message=SimpleNamespace(edit_text=edit))
    with patch.object(h, "_lang_of", AsyncMock(return_value="uz")):
        await h.premium_ppt_photo_source(cb, state, None)
    stored.update(await state.get_data())
    return edit
edit = asyncio.run(tap("ai"))
check("tugma bosilsa tanlov saqlanadi va xulosa yangilanadi", stored.get("photo_source") == "ai" and edit.await_count == 1)
edit = asyncio.run(tap("xyz"))
check("noto'g'ri qiymat e'tiborsiz", edit.await_count == 0)

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
