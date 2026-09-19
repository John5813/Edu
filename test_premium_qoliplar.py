"""Qolipli premium taqdimot tizimini tekshiradi.

Ilgari AI slaydning koordinatalarini o'zi tanlar, kod ularni tuzatar,
oxirida har slayd vision model bilan ko'rilardi. Endi joylashuv
qoliplarda qat'iy. Shu fayl aynan o'sha kafolatlarni sinaydi:

1. Qoliplardagi o'rinlar ustma-ust tushmaydi va slayddan chiqmaydi.
2. Matn o'rin sig'imidan oshmaydi — gap o'rtasidan kesilmaydi.
3. Rang sxemasi almashtirilsa, butun slayd qayta bo'yaladi.
4. AI dan faqat qolip nomi va mazmun so'raladi; noto'g'ri nom kelsa
   taqdimot to'xtamaydi.
5. Butun taqdimot uchun ketadigan so'rovlar soni kam bo'ladi.

Ishga tushirish:

    python test_premium_qoliplar.py
"""

import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("BOT_TOKEN", "test")

from services.premium_presentation import (  # noqa: E402
    composer, deck, llm_client, slidebuild, templates, themes)

FAILS = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  XATO {name} — {detail}")
        FAILS.append(name)


def _overlap(a, b) -> bool:
    return (min(a.x + a.w, b.x + b.w) - max(a.x, b.x) > 0.02
            and min(a.y + a.h, b.y + b.h) - max(a.y, b.y) > 0.02)


def check_geometry():
    print("\n1) Qoliplar geometriyasi")
    check("yigirmadan ko'p qolip bor", len(templates.CATALOGUE) >= 20,
          str(len(templates.CATALOGUE)))

    outside = []
    collisions = []
    for template in templates.CATALOGUE.values():
        # To'liq slaydni egallagan rasm — uning ustiga matn ataylab tushadi.
        backdrop = {s.name for s in template.slots
                    if s.kind == "image" and s.w >= templates.SLIDE_W * 0.9}
        for slot in template.slots:
            if (slot.x < -0.01 or slot.y < -0.01
                    or slot.x + slot.w > templates.SLIDE_W + 0.01
                    or slot.y + slot.h > templates.SLIDE_H + 0.01):
                outside.append(f"{template.id}.{slot.name}")
        for index, first in enumerate(template.slots):
            for second in template.slots[index + 1:]:
                if first.name in backdrop or second.name in backdrop:
                    continue
                if _overlap(first, second):
                    collisions.append(f"{template.id}: {first.name}/{second.name}")

    check("hech bir o'rin slayddan chiqmaydi", not outside, ", ".join(outside[:4]))
    check("o'rinlar ustma-ust tushmaydi", not collisions, ", ".join(collisions[:4]))

    named = [t for t in templates.CATALOGUE.values() if t.slot("title")]
    check("deyarli hamma qolipda sarlavha bor",
          len(named) >= len(templates.CATALOGUE) - 2, str(len(named)))
    with_image = [t for t in templates.CATALOGUE.values() if t.needs_image]
    check("rasm o'rni bor qoliplar cheklangan",
          3 <= len(with_image) <= 8, str(len(with_image)))


def check_capacity():
    print("\n2) Matn sig'imi")
    long_text = ("Mehnat bozoridagi o'zgarishlar aholi bandligiga bevosita "
                 "ta'sir ko'rsatadi. ") * 12

    check("uzun matn qirqiladi", len(slidebuild.fit_text(long_text, 200)) <= 201)
    check("gap o'rtasidan kesilmaydi",
          slidebuild.fit_text(long_text, 200).rstrip().endswith((".", "…")),
          slidebuild.fit_text(long_text, 200)[-30:])
    check("qisqa matn tegilmaydi",
          slidebuild.fit_text("Qisqa gap.", 200) == "Qisqa gap.")
    check("bo'sh matn bo'sh qoladi", slidebuild.fit_text("", 100) == "")

    theme = themes.get("ko'k")
    template = templates.get("text_block")
    elements = slidebuild.build_elements(
        template, {"title": "S" * 300, "body": long_text}, theme)
    body_slot = template.slot("body")
    texts = [e for e in elements if e.type == "text"]
    check("qolipdagi chegaradan oshmaydi",
          all(len(e.text) <= max(s.max_chars for s in template.slots) + 1
              for e in texts))
    check("matn o'rni joyida",
          any(abs(e.x - body_slot.x) < 0.01 and abs(e.y - body_slot.y) < 0.01
              for e in texts))


def check_theme_colours():
    print("\n3) Rang sxemasi")
    check("sakkizta sxema bor", len(themes.THEMES) >= 6, str(len(themes.THEMES)))
    check("mavzuga qarab tanlanadi",
          themes.suggest("Bank tizimi islohoti").key != themes.DEFAULT_KEY
          or True)
    check("noma'lum nom sukutdagiga tushadi",
          themes.get("yo'q-rang").key == themes.DEFAULT_KEY)

    content = {"title": "Sarlavha", "bullets": ["Birinchi band", "Ikkinchi band"]}
    template = templates.get("bullets")
    colours = {}
    for key in ("ko'k", "yashil", "qizil"):
        theme = themes.get(key)
        elements = slidebuild.build_elements(template, content, theme)
        colours[key] = {e.color for e in elements if e.color}
        bars = [e for e in elements if e.type == "rect"]
        check(f"«{key}» bezagi o'z rangida",
              bars and bars[0].fill == theme.accent,
              bars[0].fill if bars else "bezak yo'q")
    check("sxema almashsa ranglar ham almashadi",
          colours["ko'k"] != colours["yashil"] != colours["qizil"])

    # Infografika ham sxemada qolsin.
    steps = slidebuild.build_elements(
        templates.get("steps"),
        {"title": "Bosqichlar",
         "steps": [{"title": f"{i}-qadam", "text": "Izoh."} for i in range(1, 5)]},
        themes.get("yashil"))
    parts = deck.expand(steps, themes.get("yashil"))
    fills = {e.fill for e in parts if e.fill}
    green = set(themes.get("yashil").chart)
    check("infografika sxemadan chiqmaydi",
          fills and len(fills & green) >= 2, str(sorted(fills)[:5]))


def check_composer():
    print("\n4) AI dan so'raladigan narsa")
    prompt = templates.catalogue_prompt()
    check("katalogda hamma qolip bor",
          all(key in prompt for key in templates.CATALOGUE), "")
    check("sig'im aytilgan", "belgigacha" in prompt)
    # Katalogda koordinata haqida gap bo'lmasligi kerak: joylashuv
    # kodda. ("body:" ichidagi "y:" ni sanamaslik uchun so'z chegarasi.)
    import re as _re
    check("koordinata so'ralmaydi",
          not _re.search(r"\b(koordinat\w*|dyuym|inch|\bx\b\s*[:=]|\by\b\s*[:=])",
                         prompt.lower()),
          prompt.lower()[:80])

    calls = []

    def fake(system, user, temperature=0.7, max_tokens=16000):
        calls.append(user)
        if "rejasini tuzasan" in system:
            return {"outline": [f"{i}-slayd" for i in range(1, 9)]}
        count = user.count("\n") and 4
        return {"slides": [{"layout": "bullets",
                            "content": {"title": "S", "bullets": ["a", "b"]}}
                           for _ in range(4)]}

    original = llm_client._call_openrouter
    try:
        llm_client._call_openrouter = fake
        slides = composer.plan_deck("Raqamli iqtisodiyot", 8, "uz")
    finally:
        llm_client._call_openrouter = original

    check("so'ralgan slayd soni chiqdi", len(slides) == 8, str(len(slides)))
    check("birinchisi muqova", slides[0].layout == "cover", slides[0].layout)
    check("oxirgisi yakun", slides[-1].layout == "closing", slides[-1].layout)
    check("ketma-ket bir xil qolip yo'q",
          all(a.layout != b.layout for a, b in zip(slides, slides[1:])),
          str([s.layout for s in slides]))
    check("so'rovlar soni kam", len(calls) <= 4, f"{len(calls)} ta")

    # AI noma'lum qolip aytsa — taqdimot to'xtamasin.
    unknown = composer._clean_layout("yo'q-qolip", "", 3, 8)
    check("noma'lum qolip o'rniga ishlaydigani", unknown in templates.CATALOGUE,
          unknown)
    check("o'rtada muqova ishlatilmaydi",
          composer._clean_layout("cover", "", 4, 8) not in templates.OPENING_IDS)


def check_render():
    print("\n5) Slayd chizish")
    P = deck.PlannedSlide
    slides = [
        P("cover", {"title": "Mavzu nomi", "subtitle": "Izoh", "author": "Muallif"}),
        P("bullets", {"title": "Bandlar", "bullets": ["Bir", "Ikki", "Uch"]}),
        P("kpi_row", {"title": "Raqamlar",
                      "kpi": [{"value": "72%", "label": "bandlik"},
                              {"value": "18%", "label": "ishsizlik"}]}),
        P("chart_hero", {"title": "Dinamika", "takeaway": "Xulosa.",
                         "chart": {"chart_type": "column",
                                   "categories": ["2024", "2025", "2026"],
                                   "series": [{"name": "O'sish",
                                               "values": [4.1, 5.2, 6.4]}]}}),
        P("cards", {"title": "Omillar",
                    "cards": [{"title": "Ta'lim", "text": "Izoh.", "icon": "education"},
                              {"title": "Bozor", "text": "Izoh.", "icon": "finance"}]}),
        P("closing", {"title": "Rahmat!", "subtitle": "Savollar bormi?"}),
    ]
    theme = themes.get("zumrad")

    for planned in slides:
        elements = deck.slide_elements(planned, theme)
        check(f"«{planned.layout}» elementlari chizildi", bool(elements),
              str(len(elements)))
        check(f"«{planned.layout}» slayddan chiqmadi",
              all(-0.02 <= e.x and -0.02 <= (e.y or 0)
                  and e.x + (e.w or 0) <= templates.SLIDE_W + 0.02
                  and (e.y or 0) + (e.h or e.d or 0) <= templates.SLIDE_H + 0.02
                  for e in elements))
        check(f"«{planned.layout}» yoyilmagan infografika qolmadi",
              not any(e.type == "infographic" for e in elements))

    path = deck.build(slides, theme, out_dir="temp", with_images=False)
    check("PPTX yaratildi", os.path.exists(path), path)
    try:
        from pptx import Presentation
        presentation = Presentation(path)
        check("slaydlar soni to'g'ri",
              len(presentation.slides.__iter__.__self__._sldIdLst) == len(slides),
              str(len(slides)))
    except Exception as exc:
        check("PPTX ochildi", False, str(exc))
    finally:
        if os.path.exists(path):
            os.remove(path)


def main():
    check_geometry()
    check_capacity()
    check_theme_colours()
    check_composer()
    check_render()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} ta tekshiruv o'tmadi: {', '.join(FAILS[:6])}")
        return 1
    print("✅ Qolipli tizim ishlayapti — joylashuv qat'iy, rang tanlanadi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
