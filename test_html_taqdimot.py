"""HTML slaydli premium taqdimot tizimini tekshiradi.

Eski ikki tizimda joylashuv koddan kelardi: avval AI koordinata aytar,
keyin 24 ta qat'iy qolip bo'lardi. Endi AI butun slaydni HTML/CSS/SVG
qilib chizadi, biz uni brauzerda 1920×1080 da suratga olamiz. Kod
faqat qobiq shartlarini va joylashuv kategoriyalarini beradi.

Shu fayl aynan o'sha kafolatlarni sinaydi:

1. Promptda qobiq shartlari bor, qat'iy varaqma-varaq shablon yo'q.
2. Chala kelgan HTML hujjat tashlab yuboriladi.
3. Reja kelmasa ham slaydlar xilma-xil kategoriyalarda bo'ladi.
4. Brauzer HTML ni haqiqatan 1920×1080 PNG qiladi.
5. PPTX slaydlari to'liq varaqni egallaydi.

    python test_html_taqdimot.py
"""

import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("BOT_TOKEN", "test")

from services.premium_presentation import (  # noqa: E402
    html_render, html_slides, llm_client, themes)

FAILS = []


def check(name, condition, detail=""):
    print(f"  ok   {name}" if condition else f"  XATO {name} — {detail}")
    if not condition:
        FAILS.append(name)


def _page(title="Sinov", extra=""):
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;padding:90px;background:#FFFFFF;
    font-family:'DejaVu Sans','Liberation Sans',Arial,sans-serif}}
    h1{{font-size:64px;color:#10241C}}</style></head>
    <body><h1>{title}</h1>{extra}</body></html>"""


def check_prompt():
    print("\n1) Qobiq qoidalari")
    theme = themes.get("zumrad")
    rules = html_slides.shell_rules(theme, "uz")

    check("o'lcham aytilgan", "1920px × 1080px" in rules, rules[:80])
    check("tashqi fayl taqiqlangan",
          "Google Fonts" in rules and "YO'Q" in rules)
    check("shrift qat'iy", html_slides.FONT_STACK in rules)
    check("tanlangan rang promptda", theme.accent in rules, theme.accent)
    check("matn kesilishi taqiqlangan", "ellipsis" in rules)
    check("ajratuvchi aytilgan", html_slides.MARKER in rules)
    check("bo'sh joy egasi taqiqlangan", "Lorem ipsum" in rules)

    # Qat'iy shablon bo'lmasligi kerak: kategoriya — yo'nalish, o'rin
    # koordinatasi emas.
    catalogue = html_slides.catalogue_text()
    check("kategoriyalar ro'yxati bor", len(html_slides.CATEGORY_KEYS) >= 12,
          str(len(html_slides.CATEGORY_KEYS)))
    check("kategoriyada koordinata yo'q",
          not any(word in catalogue.lower()
                  for word in ("px", "x:", "y:", "dyuym")), catalogue[:80])
    check("diagramma kategoriyasi bor", "diagramma" in html_slides.CATEGORY_KEYS)
    check("jadval kategoriyasi bor", "jadval" in html_slides.CATEGORY_KEYS)


def check_split():
    print("\n2) Javobni slaydlarga ajratish")
    good = _page("Bir") + f"\n{html_slides.MARKER}\n" + _page("Ikki")
    check("ikkita slayd ajratildi", len(html_slides.split_slides(good)) == 2)

    truncated = _page("Bir") + f"\n{html_slides.MARKER}\n" + "<html><body><h1>Chala"
    parts = html_slides.split_slides(truncated)
    check("chala slayd tashlandi", len(parts) == 1, str(len(parts)))

    fenced = "```html\n" + _page("Bir") + "\n```"
    check("markdown ramkasi olib tashlandi",
          len(html_slides.split_slides(fenced)) == 1)

    thinking = "<think>o'ylayapman</think>" + _page("Bir")
    parts = html_slides.split_slides(thinking)
    check("o'ylash bloki olib tashlandi",
          len(parts) == 1 and "o'ylayapman" not in parts[0])
    check("bo'sh javobdan slayd chiqmaydi", html_slides.split_slides("") == [])


def check_outline():
    print("\n3) Reja va kategoriyalar")

    def fake(system, user, temperature=0.7, max_tokens=16000):
        return {"slides": [{"brief": f"{i}-slayd", "category": "kartalar"}
                           for i in range(1, 9)]}

    original = llm_client._call_openrouter
    try:
        llm_client._call_openrouter = fake
        outline = html_slides.plan_outline("Raqamli iqtisodiyot", 8, "uz")
    finally:
        llm_client._call_openrouter = original

    check("reja to'liq", len(outline) == 8, str(len(outline)))
    check("birinchisi muqova", outline[0]["category"] == "muqova")
    check("oxirgisi yakun", outline[-1]["category"] == "yakun")
    check("ketma-ket takror yo'q",
          all(a["category"] != b["category"]
              for a, b in zip(outline, outline[1:])),
          str([o["category"] for o in outline]))

    # AI javob bermasa ham reja tuzilishi kerak.
    def broken(*a, **k):
        raise RuntimeError("model javob bermadi")

    try:
        llm_client._call_openrouter = broken
        fallback = html_slides.plan_outline("Mavzu", 6, "uz")
    finally:
        llm_client._call_openrouter = original

    check("reja kelmasa ham slaydlar bor", len(fallback) == 6)
    check("zaxira rejada ham xilma-xillik",
          len({o["category"] for o in fallback}) >= 4,
          str([o["category"] for o in fallback]))


def check_writer():
    print("\n4) Slaydlarni bo'laklab yozish")
    calls = []

    def fake(system, user, temperature=0.7, max_tokens=1800):
        calls.append(user)
        pages = [_page(f"Slayd {len(calls)}.{i}") for i in range(3)]
        return f"\n{html_slides.MARKER}\n".join(pages)

    def fake_plan(system, user, temperature=0.7, max_tokens=16000):
        return {"slides": [{"brief": f"{i}", "category": "kartalar"}
                           for i in range(1, 7)]}

    orig_text, orig_json = llm_client._call_openrouter_text, llm_client._call_openrouter
    try:
        llm_client._call_openrouter_text = fake
        llm_client._call_openrouter = fake_plan
        pages = html_slides.write_slides("Mavzu", 6, themes.get("ko'k"), "uz")
    finally:
        llm_client._call_openrouter_text = orig_text
        llm_client._call_openrouter = orig_json

    check("so'ralgan slayd soni chiqdi", len(pages) == 6, str(len(pages)))
    check("bo'laklab so'raldi", len(calls) == 2, f"{len(calls)} ta so'rov")
    check("rejadagi o'rin ko'rsatilgan", "→" in calls[0], calls[0][:60])
    check("ikkinchi bo'lak avvalgisini biladi",
          "takrorlama" in calls[1].lower(), calls[1][:80])


def check_render():
    print("\n5) Brauzerda suratga olish")
    if not html_render.available():
        check("playwright o'rnatilgan", False, "playwright yo'q")
        return

    pages = [
        _page("Birinchi slayd", '<svg width="600" height="300">'
              '<circle cx="150" cy="150" r="120" fill="#1F8A70"/></svg>'),
        _page("Ikkinchi slayd",
              '<table><tr><td>A</td><td>B</td></tr></table>'),
    ]
    images = html_render.shoot(pages, out_dir="temp")
    check("har slayd suratga olindi", len(images) == 2, str(len(images)))

    try:
        from PIL import Image
        with Image.open(images[0]) as picture:
            size = picture.size
        check("surat 1920×1080", size == (1920, 1080), str(size))
        with Image.open(images[0]) as picture:
            colours = picture.convert("RGB").getcolors(maxcolors=200000) or []
        check("slayd bo'sh emas", len(colours) > 3, str(len(colours)))

        path = html_render.build_pptx(images, "temp", "sinov")
        from pptx import Presentation
        presentation = Presentation(path)
        check("PPTX slaydlari to'g'ri",
              len(presentation.slides._sldIdLst) == 2)
        check("slayd 16:9 varaq",
              abs(presentation.slide_width / 914400 - 13.333) < 0.01
              and abs(presentation.slide_height / 914400 - 7.5) < 0.01)
        picture_shape = list(presentation.slides)[0].shapes[0]
        check("rasm butun varaqni egallaydi",
              picture_shape.width == presentation.slide_width
              and picture_shape.height == presentation.slide_height)
        os.remove(path)
    finally:
        for image in images:
            if os.path.exists(image):
                os.remove(image)


def main():
    check_prompt()
    check_split()
    check_outline()
    check_writer()
    check_render()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} ta tekshiruv o'tmadi: {', '.join(FAILS[:5])}")
        return 1
    print("✅ HTML slaydlar chiziladi, suratga olinadi va PPTX ga tushadi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
