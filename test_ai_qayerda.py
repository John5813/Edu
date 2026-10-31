"""AI nazorati: qaysi xizmatda qaysi model ishlagani (admin statistikasi Mini App).

    python test_ai_qayerda.py
"""
import asyncio
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:test")

import database.database as dbmod
from database.database import init_db
from services import admin_analytics, ai_usage
from services.daily_stats import today_uzt

dbmod.DATABASE_FILE = os.path.join(tempfile.mkdtemp(), "ai-qayerda.db")
admin_analytics.DATABASE_FILE = dbmod.DATABASE_FILE
FAILS = []


def check(name, condition, detail=""):
    print(("  ok   " if condition else "  XATO ") + name + ("" if condition else f" — {detail}"))
    if not condition:
        FAILS.append(name)


async def rows():
    day = today_uzt()
    return {(r["service"], r["kind"], r["name"]): r["count"] for r in await ai_usage.where_counts(day, day)}


async def main():
    await init_db()

    print("1) Yozish va xizmat nomi")
    with ai_usage.where("Kurs ishi"):
        with ai_usage.where("Jadval"):           # ichki nom tashqisini almashtirmaydi
            ai_usage.record("text", "anthropic/claude-sonnet-5")
        ai_usage.record("text", "anthropic/claude-sonnet-5")
    ai_usage.record("text", "openai/gpt-4.1")      # nomsiz — faqat umumiy hisobda
    ai_usage.record("photo", ai_usage.PHOTO_AI, service="Kurs ishi")
    got = await rows()
    check("ichma-ich chaqiruv tashqi xizmat nomi bilan yoziladi",
          got.get(("Kurs ishi", "text", "anthropic/claude-sonnet-5")) == 2, got)
    check("nomsiz yozuv xizmat jadvaliga tushmaydi", not any(k[2] == "openai/gpt-4.1" for k in got), got)
    check("rasm manbasi (photo) xizmat jadvaliga tushmaydi", not any(k[1] == "photo" for k in got), got)
    check("kontekstdan chiqqach nom tozalanadi", ai_usage.current() == "", ai_usage.current())

    print("2) Matn so'rovlari (llm_client)")
    from services.premium_presentation import llm_client

    llm_client._count_model("google/gemini-2.5-flash-lite", "receipt")
    llm_client._count_model("anthropic/claude-sonnet-5", "text")
    with ai_usage.where("3D Pro"):
        llm_client._count_model("google/gemini-3.1-flash-lite", "vision")
    got = await rows()
    check("chek o'qish o'z nomi bilan", got.get(("To'lov cheki", "text", "google/gemini-2.5-flash-lite")) == 1, got)
    check("nomsiz matn — zamonaviy taqdimot", got.get(("Zamonaviy taqdimot", "text", "anthropic/claude-sonnet-5")) == 1, got)
    check("xizmat ichidagi ko'rish so'rovi ikkalasini ham ko'rsatadi",
          got.get(("3D Pro · Slayd tekshiruvi (ko'z)", "text", "google/gemini-3.1-flash-lite")) == 1, got)

    print("3) Rasm (Together)")
    from services import together_service

    together_service._count_image("black-forest-labs/FLUX.2-pro", "med3d_visual")
    together_service._count_image("black-forest-labs/FLUX.1-schnell", "docs")
    together_service._count_image("black-forest-labs/FLUX.1-schnell", "pro3d_raw")
    got = await rows()
    check("3D Anatomiya rasmi fayl nomidan aniqlanadi",
          got.get(("3D Anatomiya", "image", "black-forest-labs/FLUX.2-pro")) == 1, got)
    check("hujjat rasmi maqsaddan aniqlanadi", got.get(("Hujjatlar", "image", "black-forest-labs/FLUX.1-schnell")) == 1, got)
    check("3D Pro rasmi", got.get(("3D Pro", "image", "black-forest-labs/FLUX.1-schnell")) == 1, got)

    print("4) AIService kirish metodlari")
    from services.ai_service import AIService

    seen = {}

    async def fake_outline(self, topic, section_count, document_type, language):
        seen[document_type] = ai_usage.current()
        raise RuntimeError("to'xtatildi")

    async def fake_course(self, *args, **kwargs):
        return ai_usage.current()

    original = AIService._generate_document_outline
    AIService._generate_document_outline = fake_outline
    try:
        service = AIService.__new__(AIService)
        for kind in ("referat", "independent_work"):
            try:
                await service.generate_document_content("Mavzu", 5, kind, "uz")
            except Exception:
                pass
    finally:
        AIService._generate_document_outline = original
    check("referat nomi", seen.get("referat") == "Referat", seen)
    check("mustaqil ish nomi", seen.get("independent_work") == "Mustaqil ish", seen)
    wrapped = AIService.__dict__["generate_course_work_content"]
    check("kurs ishi metodi o'ralgan", getattr(wrapped, "__wrapped__", None) is not None)
    tracked = sys.modules["services.ai_service"]._track_service(fake_course, "Kurs ishi")
    check("o'ralgan metod ichida xizmat nomi bor", await tracked(service) == "Kurs ishi")

    print("5) Admin statistikasi ma'lumoti")
    data = await admin_analytics.dashboard(7)
    where = data.get("ai_where") or []
    check("dashboard xizmat bo'yicha ro'yxatni beradi",
          any(r["service"] == "Kurs ishi" and r["count"] == 2 for r in where), where)
    config_rows = data.get("ai_config") or []
    services = {(r["service"], r["kind"]) for r in config_rows}
    check("sozlamada hujjatlar va zamonaviy taqdimot matn modeli",
          {("Hujjatlar va oddiy taqdimot", "text"), ("Zamonaviy taqdimot", "text")} <= services, services)
    check("sozlamada 3D Anatomiya modeli", ("3D Anatomiya", "text") in services, services)
    check("sozlamada 3D taqdimot (katalog) modeli", ("3D taqdimot (katalog)", "text") in services, services)
    check("sozlamada chek modeli Claude emas",
          all(not r["model"].startswith("anthropic/") for r in config_rows if r["service"] == "To'lov cheki"))
    # Claude sukut emas (config.DEFAULT_AI_MODEL) — faqat admin tanlasa; tanlanganda nomi o'qiladigan bo'ladi.
    from unittest import mock as _mock
    from database.database import Database as _Db

    with _mock.patch.object(_Db, "get_premium_ai_model", _mock.AsyncMock(return_value="claude_sonnet_5")):
        chosen = await admin_analytics.ai_config()
    check("o'qiladigan nom: admin tanlagan Claude Sonnet 5",
          any(r["name"] == "Claude Sonnet 5" for r in chosen if r["service"] == "Zamonaviy taqdimot"), chosen)
    check("sukut model ham o'qiladigan nom bilan (ID emas)",
          all("/" not in r["name"] for r in config_rows if r["service"] == "Zamonaviy taqdimot"), config_rows)

    print("6) Sahifa")
    html = open("webapp/site/admin_statistics.html", encoding="utf-8").read()
    js = open("webapp/site/static/admin-statistics.js", encoding="utf-8").read()
    check("sahifada panel bor", 'id="ai-where"' in html and 'id="ai-config"' in html)
    check("JS ikkala ro'yxatni chizadi", "drawAIWhere(data.ai_where)" in js and "drawAIConfig(data.ai_config)" in js)


asyncio.run(main())
print("\nHAMMASI O'TDI" if not FAILS else f"\n{len(FAILS)} ta XATO: {FAILS}")
sys.exit(1 if FAILS else 0)
