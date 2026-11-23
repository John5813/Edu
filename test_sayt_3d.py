"""Saytdagi «🧊 3D taqdimot»: faqat to'liq mos mavzu qabul qilinadi, oldindan 8 slayd tanlangan.

Ilgari «Plural Noun» kabi mavzu («qisman» — faqat ramziy kitob modeli) jimgina qabul qilinib, bitta kitob
animatsiyali taqdimot chiqardi; shaklda esa oldindan 4 slayd tanlanib turardi.

    python test_sayt_3d.py
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


import services.kat3d as kat3d  # noqa: E402
from services import web_kinds  # noqa: E402
from services.kat3d import qidiruv  # noqa: E402
from services.med3d import auto as med3d_auto  # noqa: E402
from services.web_jobs import JobError  # noqa: E402

BUILT = []


async def fake_build(topic, count, ids, **kw):
    BUILT.append((topic, count, list(ids)))
    return "/tmp/3d.pptx", count


med3d_auto.check_topic = lambda topic, language="uz": {"ok": False, "checked": True}
kat3d.build_deck = fake_build
PARAMS = {"topic": "Plural Noun", "slide_count": 8, "language": "en", "author": "", "preferences": ""}


async def run(result):
    qidiruv.top = lambda topic, language="uz": result
    BUILT.clear()
    try:
        await web_kinds._three_d_run(dict(PARAMS), lambda *a: None)
        return None
    except JobError as exc:
        return exc


async def main():
    print("1) Mavzu tekshiruvi")
    err = await run({"level": "partial", "ok": True, "ids": ["kitob"], "choices": ["kitob", "x"], "asosiy": []})
    check("«qisman» mos (faqat ramziy model) — rad, no_3d (pul qaytadi), taqdimot yasalmaydi",
          err is not None and err.code == "no_3d" and not BUILT, (err, BUILT))
    err = await run({"level": "none", "ok": False, "ids": []})
    check("mos model yo'q — rad", err is not None and err.code == "no_3d" and not BUILT)
    err = await run({"level": "full", "ok": True, "ids": ["a", "b", "c"], "asosiy": ["a"]})
    check("to'liq mos — taqdimot yasaladi, so'ralgan slaydlar soni bilan",
          err is None and BUILT and BUILT[0][1] == 8 and BUILT[0][2] == ["a", "b", "c"], (err, BUILT))

    print("2) Shakl")
    opts = web_kinds._three_d_options()
    check("oldindan 8 slayd tanlangan (4 emas)", opts.get("default_size") == "8"
          and any(z["key"] == "8" for z in opts["sizes"]), opts.get("default_size"))
    js = open("webapp/site/static/studio.js", encoding="utf8").read()
    check("studio.js «default_size» ni hisobga oladi", "o.default_size" in js)
    check("normalize: slayd soni berilmasa — 8", web_kinds._three_d_normalize({"topic": "Yurak"})["slide_count"] == 8)

    print("\n✅ hammasi o'tdi" if not FAILS else f"\n❌ {len(FAILS)} ta xato: {FAILS}")
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
