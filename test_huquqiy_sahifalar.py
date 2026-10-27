"""Huquqiy sahifalar (/oferta, /tolov-va-qaytarish, /xavfsizlik): Uzum Bank talabi bo'yicha saytda turishi kerak.

- uchala sahifa ochiladi, sarlavha, bo'limlar va rekvizitlar bor; bo'sh rekvizit ko'rsatilmaydi;
- summa chegaralari va aloqa matnga qo'yiladi, {..} qolib ketmaydi, HTML qochiriladi;
- bosh sahifa, xizmat sahifalari, do'kon va hamyonda havolalar; sitemap'da bor.

    python test_huquqiy_sahifalar.py
"""
import asyncio
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {str(detail)[:300]}"))
    if not cond:
        FAILS.append(name)


import config
import database.database as dbmod

dbmod.DATABASE_FILE = os.path.join(tempfile.mkdtemp(), "test.db")
config.LEGAL_NAME, config.LEGAL_STIR, config.LEGAL_ADDRESS = "YTT «Sinov <b>»", "123456789", ""
config.LEGAL_PHONE, config.LEGAL_EMAIL, config.LEGAL_BANK = "+998 90 000 00 00", "", ""
config.ADMIN_CONTACT = "@yordam"

from webapp import legal


async def main():
    from aiohttp.test_utils import TestClient, TestServer
    from database.database import init_db
    from webapp.server import create_web_app

    await init_db()
    async with TestClient(TestServer(create_web_app())) as client:
        print("1) Sahifalar")
        for slug, page in legal.PAGES.items():
            resp = await client.get(f"/{slug}")
            text = await resp.text()
            check(f"/{slug} → 200, sarlavha", resp.status == 200 and f"<h1>{legal._esc(page['h1'])}</h1>" in text, resp.status)
            check(f"/{slug}: barcha bo'limlar", all(legal._esc(h) in text for h, _ in page["sections"]))
            check(f"/{slug}: {{..}} qolmagan", not re.search(r"\{(min|max|contact|site|date)\}", text))
            check(f"/{slug}: rekvizitlar, bo'shlari yo'q", "123456789" in text and "+998 90 000 00 00" in text
                  and "Manzil" not in text and "E-pochta" not in text)
            check(f"/{slug}: HTML qochirilgan", "Sinov &lt;b&gt;" in text and "Sinov <b>" not in text)
            check(f"/{slug}: uchala sahifaga havola", all(f'href="/{s}"' in text for s in legal.PAGES))

        text = await (await client.get("/tolov-va-qaytarish")).text()
        check("to'lov: usullar, chegaralar, aloqa", all(w in text for w in ("Uzum Bank", "Click", "Payme",
                                                                           "1 000", "5 000 000", "@yordam")), text)
        check("to'lov: qaytarish qoidalari", "10 ish kuni" in text and "3 kun" in text and "Ishlatilmagan" in text)
        text = await (await client.get("/xavfsizlik")).text()
        check("xavfsizlik: karta saqlanmaydi, SMS-kod so'ralmaydi", "saqlanmaydi" in text and "SMS-kod" in text)
        text = await (await client.get("/oferta")).text()
        check("oferta: aksept, narx, qaytarish, sana", all(w in text for w in ("aksept", "Xizmat narxi", "Qaytarish",
                                                                              config.LEGAL_DATE)))

        print("\n2) Ruscha")
        for slug, page in legal.PAGES_RU.items():
            resp = await client.get(f"/ru/{slug}")
            text = await resp.text()
            check(f"/ru/{slug} → 200, ruscha sarlavha, lang=ru", resp.status == 200 and '<html lang="ru">' in text
                  and f"<h1>{legal._esc(page['h1'])}</h1>" in text, resp.status)
            check(f"/ru/{slug}: bo'limlar soni o'zbekcha bilan bir xil",
                  len(page["sections"]) == len(legal.PAGES[slug]["sections"])
                  and all(legal._esc(h) in text for h, _ in page["sections"]))
            check(f"/ru/{slug}: {{..}} qolmagan, rekvizitlar ruscha",
                  not re.search(r"\{(min|max|contact|site|date)\}", text) and "ИНН" in text and "123456789" in text)
            check(f"/ru/{slug}: tabs /ru/, o'zbekchaga qaytish", all(f'href="/ru/{s}"' in text for s in legal.PAGES)
                  and f'href="/{slug}" hreflang="uz"' in text)
            uz = await (await client.get(f"/{slug}")).text()
            check(f"/{slug}: ruschaga havola va hreflang", f'href="/ru/{slug}" hreflang="ru"' in uz
                  and 'hreflang="ru"' in uz)
        text = await (await client.get("/ru/tolov-va-qaytarish")).text()
        check("ru to'lov: 10 рабочих дней, 3 дней, суммы", "10 рабочих дней" in text and "3 дней" in text
              and "1 000" in text and "5 000 000" in text)

        print("\n3) Havolalar")
        for path in ("/", "/taqdimot", "/shop"):
            resp = await client.get(path)
            text = await resp.text()
            check(f"{path}: oferta havolasi", resp.status == 200 and 'href="/oferta"' in text
                  and 'href="/tolov-va-qaytarish"' in text, resp.status)
        app_js = open("webapp/site/static/app.js", encoding="utf-8").read()
        check("hamyonda havolalar", 'href="/tolov-va-qaytarish"' in app_js and 'href="/oferta"' in app_js)
        text = await (await client.get("/sitemap.xml")).text()
        check("sitemap'da (uz va ru)", all(f"/{s}</loc>" in text and f"/ru/{s}</loc>" in text for s in legal.PAGES),
              text[:500])


asyncio.run(main())
print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
