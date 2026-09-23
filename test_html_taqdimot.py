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
5. PPTX slaydi TAHRIRLANADI: matn — matn qutisi, jadval — jadval,
   blok — shakl. Faqat diagramma rasm bo'lib qoladi.

    python test_html_taqdimot.py
"""

import asyncio
import os
import subprocess
import sys

sys.path.insert(0, ".")
os.environ.setdefault("BOT_TOKEN", "test")

from services.premium_presentation import (  # noqa: E402
    deck_charts, deck_math, deck_shape, deck_style, html_extract, html_images, html_render,
    html_slides, llm_client, themes)

FAILS = []


def check(name, condition, detail=""):
    print(f"  ok   {name}" if condition else f"  XATO {name} — {detail}")
    if not condition:
        FAILS.append(name)


def _page(title="Sinov", extra=""):
    """Model qaytaradigan slayd mazmuni (to'liq hujjat emas)."""
    inner = extra or '<p class="note">Matn.</p>'
    return ('<section class="slide"><div class="head">'
            f'<h2 class="title">{title}</h2><div class="rule"></div></div>'
            f'<div class="body">{inner}</div></section>')


def check_handler_names():
    """Taqdimot oqimida aniqlanmagan o'zgaruvchi qolmaganini tekshiradi.

    Tizim qayta yozilganda eski o'zgaruvchiga qilingan bitta havola
    qolib ketgan edi: slaydlar yaratilib, fayl tayyor bo'lgandan keyin
    "yuborilmoqda" xabarida `NameError` chiqar va mijoz to'lagan puli
    qaytarilar edi. Sintaksis tekshiruvi bunday xatoni ko'rmaydi.
    """
    print("\n0) Oqimda aniqlanmagan nom yo'qligi")
    try:
        from pyflakes import api, reporter
    except ImportError:
        print("  o'tkazildi   pyflakes o'rnatilmagan")
        return

    import io

    files = [
        "bot/handlers/premium_presentation.py",
        "services/premium_presentation/html_render.py",
        "services/premium_presentation/html_slides.py",
        "services/premium_presentation/html_extract.py",
        "services/premium_presentation/pptx_build.py",
    ]
    for path in files:
        out, err = io.StringIO(), io.StringIO()
        api.checkPath(path, reporter.Reporter(out, err))
        undefined = [line for line in out.getvalue().splitlines()
                     if "undefined name" in line]
        check(f"{os.path.basename(path)} da aniqlanmagan nom yo'q",
              not undefined, "; ".join(undefined[:2]))


def check_prompt():
    """Model bilan MAZMUN haqida gaplashiladi, dizayn haqida emas.

    Ilgari promptda "shriftni shunday ber, rangni bunday qil" degan
    o'nlab qoida turardi va model ularning yarmini unutardi — har
    slayd boshqacha chiqardi. Endi dizayn CSS da qat'iy turibdi,
    model esa faqat qaysi blok va ichida qanday matn bo'lishini
    aytadi.
    """
    print("\n1) Mazmun qoidalari")
    theme = themes.get("zumrad")
    rules = html_slides.shell_rules(theme, "uz")

    check("ajratuvchi aytilgan", html_slides.MARKER in rules)
    check("varaq tuzilishi berilgan",
          '<section class="slide">' in rules and '<div class="body">' in rules)
    check("bo'sh joy egasi taqiqlangan", "o'rin egallovchi" in rules)
    check("bo'sh blok taqiqlangan", "BO'SH BLOK QOLDIRMA" in rules)
    check("ikonka ro'yxati bor", "data-icon" in rules)

    # Dizayn haqida so'ralmaydi: rang, piksel va CSS promptda YO'Q.
    check("CSS yozish taqiqlangan",
          "`<style>`" in rules and 'style="..."' in rules)
    check("rang tanlash so'ralmagan", theme.accent not in rules, theme.accent)
    check("SVG chizish taqiqlangan", "`<svg>` yozma" in rules)
    check("diagramma ma'lumot bilan beriladi",
          'data-kind="bar"' in rules and "data-series" in rules)

    for name in ("cols-3", "kpi", "timeline", "steps", "quote",
                 "table", "card", "list"):
        check(f"{name} bloki bor", name in deck_style.BLOCKS)


def check_design_system():
    """Dizayn CSS da qat'iy va bir xil bo'lsin."""
    print("\n1b) Dizayn tizimi")
    theme = themes.get("binafsha")
    css = deck_style.stylesheet(theme)

    check("almashtirilmagan kalit qolmadi",
          not any(word in css for word in
                  ("BACKGROUND", "HEADING", "ACCENT", "BANDCARD", "SANS")),
          css[:80])
    check("tanlangan sxema ishlatilgan", "#" + theme.accent in css)
    check("varaq o'lchami qat'iy", "width:1920px" in css and "1080px" in css)
    check("soya yo'q", "shadow" not in css.lower())

    # Qutiga qat'iy balandlik berilmasa, matn undan chiqib keta
    # olmaydi. Slaydning o'zi va bezaklargina o'lchamli bo'ladi.
    lines = [line for line in css.split("\n")
             if "height:" in line and "line-height" not in line
             and "min-height" not in line and "max-height" not in line]
    loose = [line for line in lines if "auto" not in line
             and "100%" not in line and "1080px" not in line
             and "0" not in line
             and not any(f"height:{n}px" in line for n in
                         (4, 5, 6, 14, 22, 56, 96))]
    check("kartochkaga qat'iy balandlik yo'q", not loose, str(loose[:2]))

    other = deck_style.stylesheet(themes.get("qizil"))
    check("sxema butun uslubni almashtiradi", other != css)
    check("tuzilish o'zgarmaydi", css.count("{") == other.count("{"))

    page = deck_style.page(theme, '<section class="slide">x</section>')
    check("to'liq hujjat yig'iladi",
          page.startswith("<!DOCTYPE html>") and page.endswith("</html>"))
    check("CSS hujjat ichida", "<style>" in page)


def check_charts():
    """Diagrammani kod chizadi — hisob har safar to'g'ri bo'ladi."""
    print("\n1c) Diagrammalar")
    import re as _re

    theme = themes.get("ko'k")
    body = ('<div class="chart" data-kind="bar" data-labels="2016,2018,2020" '
            'data-series="Patent: 12,18,24|Nashr: 20,28,35" '
            'data-unit="ming"></div>')
    out = deck_charts.draw(body, theme)
    check("SVG chizildi", "<svg" in out and "</svg>" in out)
    check("ustunlar soni to'g'ri", out.count("<rect") >= 6,
          str(out.count("<rect")))
    check("qiymatlar yozildi", ">12<" in out and ">35<" in out)
    check("o'q yozuvlari bor", ">2016<" in out and ">2020<" in out)
    check("qatorlar imzolandi", ">Patent<" in out and ">Nashr<" in out)
    check("birlik ko'rsatildi", ">ming<" in out)
    check("sxema rangi ishlatildi", "#" + theme.chart[0] in out)

    # Oxirgi ikki to'rtburchak — izoh belgisi, ustun emas.
    tall = [float(m) for m in _re.findall(r'<rect[^>]*height="(\d+)"', out)][:6]
    check("ustun balandligi nolga teng emas", all(v > 0 for v in tall),
          str(tall[:4]))
    check("eng katta qiymat eng baland", tall and max(tall) == tall[-1],
          str(tall))

    line = deck_charts.draw(
        '<div class="chart" data-kind="line" data-labels="a,b,c" '
        'data-series="X: 3,6,9"></div>', theme)
    check("chiziqli diagramma chizildi", "<path" in line and "<circle" in line)

    donut = deck_charts.draw(
        '<div class="chart" data-kind="donut" data-labels="Bir,Ikki" '
        'data-series="Ulush: 75,25"></div>', theme)
    check("halqa chizildi", "<path" in donut)
    check("ulush foizga o'girildi", "75%" in donut and "25%" in donut)

    empty = deck_charts.draw('<div class="chart" data-kind="bar"></div>', theme)
    check("bo'sh diagramma olib tashlandi", "chart" not in empty, empty[:60])


def check_split():
    """Javob slayd mazmunlariga ajratilsin, uslub esa o'tkazilmasin."""
    print("\n2) Javobni slaydlarga ajratish")
    one = '<section class="slide"><div class="body">Bir</div></section>'
    two = '<section class="slide dark"><div class="body">Ikki</div></section>'

    parts = html_slides.split_slides(one + f"\n{html_slides.MARKER}\n" + two)
    check("ikkita slayd ajratildi", len(parts) == 2, str(len(parts)))
    check("sinf nomi saqlandi", len(parts) == 2 and "slide dark" in parts[1])

    half = one + f"\n{html_slides.MARKER}\n" + '<section class="slide">chala'
    check("chala slayd tashlandi",
          len(html_slides.split_slides(half)) == 1)

    fenced = "```html\n" + one + "\n```"
    check("markdown ramkasi olib tashlandi",
          len(html_slides.split_slides(fenced)) == 1)

    thinking = "<think>o'ylayapman</think>" + one
    parts = html_slides.split_slides(thinking)
    check("o'ylash bloki olib tashlandi",
          len(parts) == 1 and "o'ylayapman" not in parts[0])
    check("bo'sh javobdan slayd chiqmaydi", html_slides.split_slides("") == [])

    # Model uslub yozib yuborsa ham dizayn tizimi buzilmasin.
    dirty = ('<style>.card{color:red}</style>'
             '<section class="slide"><div class="body" style="padding:200px">'
             '<div class="card" style="background:red">Matn</div>'
             '</div></section>')
    parts = html_slides.split_slides(dirty)
    check("tashqi uslub olib tashlandi",
          len(parts) == 1 and "color:red" not in parts[0], str(parts)[:120])
    check("style atributi olib tashlandi",
          parts and "style=" not in parts[0])
    check("mazmun o'z joyida", parts and "Matn" in parts[0])

    theme = themes.get("ko'k")
    page = html_slides.build_pages(
        ['<section class="slide"><div class="body">'
         '<div class="chart" data-kind="bar" data-labels="a,b" '
         'data-series="X: 1,2"></div></div></section>'], theme)[0]
    check("sahifa to'liq hujjat", page.startswith("<!DOCTYPE html>"))
    check("CSS qo'shildi", "<style>" in page and "#" + theme.accent in page)
    check("diagramma chizildi", "<svg" in page)


def check_math():
    """Formula slaydda o'qiladigan bo'lsin.

    Matematika, fizika va iqtisod mavzularida model formulani deyarli
    har doim LaTeX bilan yozadi — u shunday o'rgatilgan. Brauzerda
    LaTeX ni hech kim o'qib bermaydi, shuning uchun slaydga dollar
    belgilari va teskari chiziqlar bilan "$nx^{n-1}$" bo'lib
    tushardi.
    """
    print("\n1d) Formula va misol")

    pairs = (
        ("Masalan, $1/n$ ketma-ketligi", "1/n"),
        ("$x \\to \\infty$ da", "x \u2192 \u221e"),
        ("$x^n$ uchun $nx^{n-1}$", "nx\u207f\u207b\u00b9"),
        ("$a_1$ va $a_2$", "a\u2081"),
        ("$\\sqrt{x^2 + y^2}$", "\u221a(x\u00b2 + y\u00b2)"),
        ("$\\alpha + \\beta \\leq \\pi$", "\u03b1 + \u03b2 \u2264 \u03c0"),
        ("$\\lim_{h \\to 0} x$", "lim (h \u2192 0) x"),
    )
    for source, want in pairs:
        got = deck_math.render(source)
        check(f"{source[:26]} \u2192 {want[:18]}", want in got, got)

    check("dollar belgisi qolmadi",
          "$" not in deck_math.render("$x^2$ va $y_1$"))
    check("teskari chiziq qolmadi",
          "\\" not in deck_math.render("$\\alpha \\to \\beta$"))
    check("formulasiz matn tegilmaydi",
          deck_math.render("Oddiy jumla.") == "Oddiy jumla.")

    # Kasr ustma-ust yoziladi.
    frac = deck_math.render("$\\frac{a+b}{2}$")
    check("kasr ustma-ust", 'class="frac"' in frac and "a+b" in frac, frac)

    # Teg ichidagi matnga tegilmaydi.
    tagged = deck_math.render('<div class="a_b" data-x="$1$">$x^2$</div>')
    check("atributga tegilmadi", 'class="a_b"' in tagged and
          'data-x="$1$"' in tagged, tagged)
    check("matn o'girildi", ">x\u00b2<" in tagged, tagged)

    # Dizayn tizimida blok va qoidalar bor.
    theme = themes.get("ko'k")
    css = deck_style.stylesheet(theme)
    check("formula uslubi bor", ".formula-body{" in css)
    check("kasr uslubi bor", ".frac{" in css and ".frac .dn{" in css)
    check("misol uslubi bor", ".misol{" in css and ".misol-answer{" in css)

    rules = html_slides.shell_rules(theme, "uz")
    check("formula bloki tushuntirilgan", "formula-body" in rules)
    check("misol bloki tushuntirilgan", "misol-answer" in rules)
    check("va'da qoidasi bor", "VA'DA QILINGAN NARSA" in rules)

    guide = deck_shape.guidance("aniq")
    check("aniq fanlarda misol bloki aytilgan", "`misol` bloki" in guide)
    check("aniq fanlarda formula bloki aytilgan",
          "`formula`" in guide)
    check("iqtisodda ham formula aytilgan",
          "`formula` blokida" in deck_shape.guidance("ijtimoiy"))


def check_fraction_boxes():
    """Kasr PowerPointda ham ustma-ust tursin.

    Kasr ota matnga qo'shib olinsa, surat va maxraj yonma-yon bitta
    qatorga tushib, formula ma'nosini yo'qotardi.
    """
    print("\n1e) Kasrning joylashuvi")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    theme = themes.get("ko'k")
    page = html_slides.build_pages(
        ['<section class="slide"><div class="body"><div class="formula">'
         '<div class="formula-body">y = $\\frac{a+b}{2}$ qiymat</div>'
         "</div></div></section>"], theme)[0]

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = html_render._launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080})
            handle = context.new_page()
            handle.set_content(page, wait_until="load")
            blocks = [b for b in html_extract.read_layout(handle)["blocks"]
                      if b["kind"] == "text"]
            context.close()
        finally:
            browser.close()

    by_text = {b["text"]: b for b in blocks}
    up = by_text.get("a+b")
    down = by_text.get("2")
    check("surat alohida quti", up is not None, str(list(by_text)))
    check("maxraj alohida quti", down is not None, str(list(by_text)))
    if up and down:
        check("maxraj suratning ostida", down["y"] > up["y"] + up["h"] - 6,
              f"{up['y']:.0f}+{up['h']:.0f} vs {down['y']:.0f}")
        check("ikkisi bir ustunda",
              abs((up["x"] + up["w"] / 2) - (down["x"] + down["w"] / 2)) < 30,
              f"{up['x']:.0f} vs {down['x']:.0f}")
    check("qolgan matn butun qoldi",
          any(t.startswith("y =") for t in by_text), str(list(by_text)))


def check_no_quotas():
    """Promptda majburlovchi kvota qolmasin.

    Bu xato ikki marta takrorlandi, shuning uchun qorovul sinov
    yozildi. Biz yozgan qoidalarning o'zi modelga prompt bo'lib
    ketadi: "har uch slaydning birida diagramma bo'lsin" desak,
    adabiyotda ham statistika o'ylab topiladi; "kamida bitta misol
    bo'lsin" desak, misol kerak bo'lmagan joyga ham tiqiladi.

    Qoida MAZMUNNI emas, KO'RINISHNI boshqarishi kerak. Shuning
    uchun promptning hamma bo'lagi — umumiy qoidalar, oila
    yo'riqnomalari, reja va slayd so'rovlari — miqdor talabiga
    tekshiriladi.
    """
    print("\n2b) Majburlovchi kvota yo'qligi")
    theme = themes.get("ko'k")

    pieces = {"qoidalar": html_slides.shell_rules(theme, "uz")}
    for key in deck_shape.FAMILY_KEYS:
        pieces[f"oila:{key}"] = deck_shape.guidance(key)
    pieces["slayd so'rovi"] = html_slides._user_prompt(
        "Mavzu", 1, 3, 9, [{"brief": "b", "category": "kartalar"}],
        [], 2, "", "", "", "aniq")

    seen = {}

    def catch(system, user, temperature=0.7, max_tokens=16000):
        seen["reja"] = user
        return {"fan": "aniq", "slides": []}

    original = llm_client._call_openrouter
    try:
        llm_client._call_openrouter = catch
        html_slides.plan_outline("Mavzu", 6, "uz")
    finally:
        llm_client._call_openrouter = original
    pieces["reja so'rovi"] = seen.get("reja", "")

    # Miqdor talab qiladigan iboralar. "Yuqori chegara" qoladi —
    # u varaqqa sig'ish uchun, tuzilishni buyurish uchun emas.
    banned = ("kamida", "majburiy", "har uch slayd", "bo'lishi shart",
              "har slaydda bo'lsin", "tagacha")
    for name, text in pieces.items():
        low = text.lower()
        hits = [word for word in banned if word in low]
        check(f"{name}da kvota yo'q", not hits, str(hits))

    # Aksincha — shaklni mazmun tanlashi AYTILGAN bo'lsin.
    rules = pieces["qoidalar"]
    check("blokni mazmun tanlashi aytilgan",
          "BLOKNI MAZMUN TANLAYDI" in rules)
    check("ketma-ket takror ruxsat etilgan",
          "bir xil shaklda bo'lishi MUMKIN" in rules)
    check("raqam o'ylab topish taqiqlangan",
          "RAQAMNI O'YLAB TOPMANG" in rules)
    check("diagrammasiz taqdimot ham to'g'ri",
          "birorta diagramma" in rules and "TO'G'RI" in rules)
    check("so'rovda shakl mazmundan kelishi aytilgan",
          "SHAKL MAZMUNDAN KELIB CHIQSIN" in pieces["slayd so'rovi"])

    # Formula va misol — imkoniyat, talab emas.
    exact = pieces["oila:aniq"]
    check("formula shartli aytilgan", "Formula BO'LSA" in exact, exact)
    check("misol shartli aytilgan", "mumkin bo'lsa" in exact, exact)
    check("iqtisodda formula shartli",
          "uchrasa" in pieces["oila:ijtimoiy"])

    # Miqdor chegarasi faqat YUQORI chegara bo'lsin.
    check("chegara yuqoridan berilgan",
          "oshmasin" in rules and "kerak emas" in rules)


def check_outline():
    """Reja mavzudan kelib chiqsin, kvotadan emas.

    Ilgari reja "kamida oltita turli kategoriya" va "ketma-ket ikki
    slayd bir xil bo'lmasin" degan kvotalarga bo'ysunardi, hatto kod
    darajasida takrorlangan kategoriya majburan almashtirilardi.
    Natijada mantiqan ketma-ket kelishi kerak bo'lgan ikki ro'yxat
    sun'iy ravishda ajratilib, taqdimotning fikri uzilardi.
    """
    print("\n3) Reja va mavzu oilasi")
    seen = {}

    def fake(system, user, temperature=0.7, max_tokens=16000):
        seen["prompt"] = user
        return {"fan": "gumanitar",
                "slides": [{"brief": f"{i}-slayd", "category": "kartalar"}
                           for i in range(1, 9)]}

    original = llm_client._call_openrouter
    try:
        llm_client._call_openrouter = fake
        plan = html_slides.plan_outline("Navoiy ijodi", 8, "uz")
    finally:
        llm_client._call_openrouter = original

    outline = plan["slides"]
    check("reja to'liq", len(outline) == 8, str(len(outline)))
    check("birinchisi muqova", outline[0]["category"] == "muqova")
    check("oxirgisi yakun", outline[-1]["category"] == "yakun")
    check("mavzu oilasi olindi", plan["family"] == "gumanitar",
          plan["family"])

    # Kvota yo'q: model bir xil kategoriya bersa, u saqlanadi.
    middle = [o["category"] for o in outline[1:-1]]
    check("ketma-ket takror majburan almashtirilmadi",
          middle == ["kartalar"] * len(middle), str(middle))
    check("rejada xilma-xillik kvotasi yo'q",
          "kamida oltita" not in seen["prompt"], "")
    check("rejada mazmunga qarab tanlash aytilgan",
          "MAZMUNGA QARAB" in seen["prompt"])
    check("raqamsiz mavzu eslatilgan",
          "raqam talab qilmasa" in seen["prompt"])

    # AI javob bermasa ham reja tuzilishi kerak.
    def broken(*a, **k):
        raise RuntimeError("model javob bermadi")

    try:
        llm_client._call_openrouter = broken
        fallback = html_slides.plan_outline("Alisher Navoiy she'riyati",
                                            6, "uz")
    finally:
        llm_client._call_openrouter = original

    check("reja kelmasa ham slaydlar bor", len(fallback["slides"]) == 6)
    check("oila kalit so'zdan topildi", fallback["family"] == "gumanitar",
          fallback["family"])
    # Zaxira rejada raqamga tayanadigan kategoriya bo'lmasin: mavzuni
    # bilmay turib diagramma so'rash — statistika o'ylab toptirishdir.
    kinds = {o["category"] for o in fallback["slides"]}
    check("zaxirada statistika kategoriyasi yo'q",
          not (kinds & {"diagramma", "korsatkichlar", "jadval", "vaqt_oqi"}),
          str(kinds))


def check_family_shape():
    """Har mavzu oilasiga o'z yo'riqnomasi berilsin."""
    print("\n3b) Mavzuga moslashish")

    pairs = (("Amir Temur saltanati", "tarix"),
             ("Alisher Navoiy ijodi", "gumanitar"),
             ("Fotosintez jarayoni", "tabiiy"),
             ("Yashirin iqtisodiyot", "ijtimoiy"),
             ("Pedagogik mahorat", "amaliy"))
    for topic, want in pairs:
        got = deck_shape.of(topic)
        check(f"{topic} → {want}", got == want, got)

    check("model taxmini ustun", deck_shape.of("Mavzu", "aniq") == "aniq")
    check("notanish taxmin yiqitmaydi",
          deck_shape.of("Mavzu", "allaqanday") == "umumiy")

    # Gumanitar mavzuda statistika TAQIQLANADI, ijtimoiyda ruxsat.
    human = deck_shape.guidance("gumanitar")
    social = deck_shape.guidance("ijtimoiy")
    exact = deck_shape.guidance("aniq")
    check("adabiyotda diagramma taqiqlangan",
          "DIAGRAMMA VA STATISTIKA YOZMANG" in human)
    check("adabiyotda iqtibos tavsiya qilingan", "Iqtibos bloki" in human)
    check("matematikada statistika kerak emas",
          "STATISTIKA BU YERDA KERAK EMAS" in exact)
    check("matematikada isbot aytilgan", "isbot" in exact)
    check("iqtisodda ko'rsatkich o'rinli", "o'rinli" in social)
    check("hamma oilada prognoz cheklangan",
          all("prognoz" in deck_shape.guidance(k).lower()
              or "o'ylab topmang" in deck_shape.guidance(k)
              or "o'ylab topilgan" in deck_shape.guidance(k)
              for k in deck_shape.FAMILY_KEYS),
          str(deck_shape.FAMILY_KEYS))


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
          "qayta aytmang" in calls[1].lower(), calls[1][:80])


def check_browser_setup():
    print("\n5) Brauzer tayyorligi")
    original_globs = html_render._BROWSER_GLOBS
    original_system = html_render._SYSTEM_BROWSERS
    original_run = subprocess.run
    calls = []

    def fake_run(command, **kwargs):
        calls.append(list(command))

        class Result:
            # Brauzerni yuklab olish tushadi, kutubxonalar esa o'rnatiladi.
            returncode = 0 if "install-deps" in command else 1
            stdout = ""
            stderr = "tarmoq yo'q"

        return Result()

    try:
        # Brauzersiz server holatini yasaymiz.
        html_render._BROWSER_GLOBS = ("yo-q-*/chrome",)
        html_render._SYSTEM_BROWSERS = ()
        html_render._install_done = False
        subprocess.run = fake_run

        check("brauzersiz serverda topilmaydi", not html_render._executable())
        check("available() yolg'on aytmaydi", not html_render.available())

        failure = html_render.install_browser()
        check("o'zi o'rnatishga urinadi", bool(calls), str(calls))
        check("to'g'ri buyruq chaqiriladi",
              calls and calls[0][-3:] == ["install", "chromium"] or
              calls and "install" in calls[0], str(calls[:1]))
        check("xato matni qaytariladi", "tarmoq" in failure, failure)

        # Ikkinchi marta qayta yuklab olishga urinmasin.
        count = len(calls)
        html_render.install_browser()
        check("ikki marta yuklab olmaydi", len(calls) == count, str(len(calls)))

        # Brauzer bor, lekin GTK kutubxonalari yo'q — eng ko'p uchraydigan
        # holat. Kod kutubxonalarni o'rnatib, qayta sinashi kerak.
        calls.clear()
        html_render._deps_done = False
        failure = html_render.install_dependencies()
        check("kutubxonalar o'rnatiladi", bool(calls), str(calls))
        check("avval install-deps sinaladi",
              calls and "install-deps" in calls[0], str(calls[:1]))
        check("kutubxona xatosi qaytmadi", failure == "", failure)
    finally:
        subprocess.run = original_run
        html_render._BROWSER_GLOBS = original_globs
        html_render._SYSTEM_BROWSERS = original_system
        html_render._install_done = False
        html_render._deps_done = False

    check("brauzer topilganda o'rnatish so'ralmaydi",
          html_render.prepare(install=False) == "" if html_render._executable()
          else True)


def check_shot():
    print("\n6) Brauzerda suratga olish")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return False

    images = html_render.shoot([_page("Birinchi slayd")], out_dir="temp")
    check("slayd suratga olindi", len(images) == 1, str(len(images)))
    if not images:
        return True
    try:
        from PIL import Image
        with Image.open(images[0]) as picture:
            size = picture.size
            colours = picture.convert("RGB").getcolors(maxcolors=200000) or []
        check("surat 1920×1080", size == (1920, 1080), str(size))
        check("slayd bo'sh emas", len(colours) > 2, str(len(colours)))
    finally:
        for image in images:
            if os.path.exists(image):
                os.remove(image)
    return True


def check_editable():
    print("\n7) Tahrirlanadigan PPTX")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    theme = themes.get("zumrad")
    font = html_slides.FONT_STACK
    slide = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;padding:84px;background:#FFFFFF;
    font-family:{font};overflow:hidden}}
    h2{{font-size:52px;color:#{theme.heading};font-weight:700}}
    .bar{{width:180px;height:9px;background:#{theme.accent};margin:26px 0 40px}}
    .card{{background:#{theme.accent_soft};border-radius:20px;padding:30px;
    width:520px}}
    .v{{font-size:56px;font-weight:700;color:#{theme.accent}}}
    table{{border-collapse:collapse;width:700px;margin-top:40px}}
    th{{background:#{theme.accent};color:#FFFFFF;font-size:22px;padding:14px}}
    td{{font-size:21px;color:#{theme.body};padding:13px}}
    </style></head><body>
    <h2>Bandlik ko'rsatkichlari<br>ikkinchi qator</h2>
    <div class="bar"></div>
    <div class="card"><div class="v">14,4 mln</div></div>
    <table><tr><th>Hudud</th><th>2026</th></tr>
    <tr><td>Toshkent shahri</td><td>1 260</td></tr></table>
    <svg width="400" height="200"><circle cx="100" cy="100" r="80"
    fill="#{theme.accent}"/></svg></body></html>"""

    path = html_render.render([slide], out_dir="temp", name="sinov")
    try:
        from pptx import Presentation
        from pptx.util import Pt

        presentation = Presentation(path)
        check("slayd yaratildi", len(presentation.slides._sldIdLst) == 1)
        check("slayd 16:9 varaq",
              abs(presentation.slide_width / 914400 - 13.333) < 0.01
              and abs(presentation.slide_height / 914400 - 7.5) < 0.01)

        shapes = list(list(presentation.slides)[0].shapes)
        texts = [s.text_frame.text for s in shapes
                 if s.has_text_frame and s.text_frame.text.strip()]
        check("sarlavha matn bo'lib turibdi",
              any("Bandlik ko'rsatkichlari" in t for t in texts), str(texts[:4]))
        check("qator ko'chishi saqlandi",
              any("\n" in t for t in texts), str(texts[:4]))
        check("ko'rsatkich matni bor", any("14,4 mln" in t for t in texts))

        check("jadval haqiqiy jadval", any(s.has_table for s in shapes))
        table = next(s.table for s in shapes if s.has_table)
        check("jadval kataklari o'qiladi",
              table.cell(0, 0).text == "Hudud"
              and table.cell(1, 0).text == "Toshkent shahri",
              table.cell(0, 0).text)

        pictures = [s for s in shapes if s.shape_type == 13]
        check("diagramma rasm bo'lib qo'yildi", len(pictures) == 1,
              str(len(pictures)))
        check("rasm butun varaqni egallamaydi",
              all(p.width < presentation.slide_width * 0.9 for p in pictures),
              str([p.width for p in pictures]))

        # Bezak bloklari — shakl; matnsiz.
        filled = [s for s in shapes
                  if s.shape_type == 1 and not s.text_frame.text.strip()]
        check("bezak bloklari shakl bo'ldi", len(filled) >= 2, str(len(filled)))

        title = next(s for s in shapes if s.has_text_frame
                     and "Bandlik" in s.text_frame.text)
        run = title.text_frame.paragraphs[0].runs[0]
        check("sarlavha o'lchami saqlandi",
              abs(run.font.size.pt - 26) < 1.5, str(run.font.size.pt))
        check("shrift PowerPointnikiga o'girildi",
              run.font.name == "Arial", str(run.font.name))
        check("rang saqlandi",
              str(run.font.color.rgb) == theme.heading.upper(),
              str(run.font.color.rgb))
        check("slayd foni oq",
              str(list(presentation.slides)[0].background.fill.fore_color.rgb)
              == "FFFFFF")
    finally:
        if os.path.exists(path):
            os.remove(path)


def check_layout_guard():
    """Joylashuv tekshiruvi va tuzatish bosqichi.

    AI HTML ni brauzersiz yozadi, shuning uchun ba'zan matn ustiga
    matn tushadi yoki mazmun yuqoriga to'planib qoladi. Buni faqat
    brauzer ko'radi — shuning uchun slayd chizilishidan oldin
    tekshiriladi va bir marta qayta so'raladi.
    """
    print("\n8) Joylashuv qorovuli")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    theme = themes.get("ko'k")
    font = html_slides.FONT_STACK

    broken = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;padding:84px;background:#FFFFFF;
    font-family:{font};overflow:hidden}}
    h2{{font-size:48px;color:#{theme.heading}}}
    .line{{position:relative;height:6px;background:#{theme.accent};margin-top:30px}}
    .card{{position:absolute;bottom:100%;margin-bottom:40px;width:320px;
    background:#{theme.accent_soft};padding:24px}}
    .c1{{left:0}} .c2{{left:460px}}
    </style></head><body><h2>Vaqt o'qi</h2><div class="line">
    <div class="card c1"><b>2022</b><div>Birinchi.</div></div>
    <div class="card c2"><b>2023</b><div>Ikkinchi.</div></div></div></body></html>"""

    whole = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;padding:84px;background:#FFFFFF;
    font-family:{font};overflow:hidden;display:flex;flex-direction:column;
    justify-content:space-between}}
    h2{{font-size:48px;color:#{theme.heading}}}
    .row{{display:flex;gap:40px}}
    .card{{flex:1;background:#{theme.accent_soft};padding:30px}}
    .foot{{font-size:20px;color:#{theme.muted}}}
    </style></head><body><h2>To'g'ri joylashgan slayd</h2>
    <div class="row"><div class="card"><b>2022</b><div>Birinchi voqea.</div></div>
    <div class="card"><b>2023</b><div>Ikkinchi voqea.</div></div></div>
    <div class="foot">Manba: statistika qo'mitasi</div></body></html>"""

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = html_render._launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            page.set_content(broken, wait_until="load")
            problems = html_extract.check_layout(page)
            check("buzuq joylashuv topiladi", bool(problems), str(problems))
            check("matn ustiga matn ko'riladi",
                  any("matn ustiga matn" in item for item in problems),
                  str(problems))
            check("bo'sh pastki qism ko'riladi",
                  any("bo'sh qolgan" in item for item in problems),
                  str(problems))

            page.set_content(whole, wait_until="load")
            check("to'g'ri slaydda shikoyat yo'q",
                  html_extract.check_layout(page) == [],
                  str(html_extract.check_layout(page)))
            context.close()
        finally:
            browser.close()

    # Tuzatish bosqichi chaqiriladimi va natijasi ishlatiladimi.
    asked = []

    def repair(html, problems):
        asked.append(problems)
        return whole

    path = html_render.render([broken], out_dir="temp", name="sinov",
                              repair=repair)
    try:
        check("buzuq slayd tuzatishga yuboriladi", bool(asked), str(asked))
        from pptx import Presentation
        texts = [shape.text_frame.text
                 for shape in list(Presentation(path).slides)[0].shapes
                 if shape.has_text_frame]
        check("tuzatilgan slayd ishlatildi",
              any("To'g'ri joylashgan" in t for t in texts), str(texts[:3]))
    finally:
        if os.path.exists(path):
            os.remove(path)


def check_decoration():
    """Shaffof bezak va doira to'g'ri o'girilishi."""
    print("\n9) Bezak ranglari va shakllari")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    theme = themes.get("ko'k")
    page_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;background:#FFFFFF;overflow:hidden;
    position:relative;font-family:{html_slides.FONT_STACK}}}
    .dot{{position:absolute;border-radius:50%;background:#{theme.accent};
    opacity:.08;width:200px;height:200px;top:120px;left:160px}}
    .hidden{{position:absolute;top:-400px;left:40px;width:300px;height:300px;
    background:#{theme.accent}}}
    h1{{font-size:56px;color:#{theme.heading};padding:400px 90px}}
    </style></head><body><div class="dot"></div><div class="hidden"></div>
    <h1>Bezak sinovi</h1></body></html>"""

    path = html_render.render([page_html], out_dir="temp", name="sinov")
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE

        shapes = list(list(Presentation(path).slides)[0].shapes)
        ovals = [s for s in shapes
                 if s.shape_type == 1 and s.auto_shape_type == MSO_SHAPE.OVAL]
        check("border-radius 50% doira bo'ldi", len(ovals) == 1, str(len(ovals)))
        if ovals:
            colour = str(ovals[0].fill.fore_color.rgb)
            check("shaffof bezak och rangga o'girildi",
                  colour != theme.accent.upper() and colour != "FFFFFF", colour)
        filled = [s for s in shapes if s.shape_type == 1]
        check("slayddan chiqqan blok qo'yilmadi", len(filled) == 1,
              str(len(filled)))
    finally:
        if os.path.exists(path):
            os.remove(path)


def check_icons():
    """Tayyor ikonkalar — eski tizimdagi 142 ta siluet."""
    print("\n11) Ikonkalar")
    from services.premium_presentation import icon_render

    names = icon_render.icon_names()
    check("ikonkalar joyida", len(names) > 100, str(len(names)))
    check("tanish nomlar bor",
          all(name in names for name in ("education", "finance", "research")),
          str(names[:5]))

    rules = html_slides.shell_rules(themes.get("zumrad"), "uz")
    check("promptda ikonka aytilgan", "data-icon" in rules)
    check("promptda ro'yxat berilgan", "education" in rules)

    theme = themes.get("zumrad")
    page = ('<html><body>'
            '<img data-icon="education" class="ikon">'
            '<img data-icon="finance" class="ikon" data-icon-color="FFFFFF">'
            '<img data-icon="yo-q-bunday-ikonka" class="ikon" style="width:60px">'
            '</body></html>')
    filled, count = html_images.apply_icons([page], theme)

    check("ikonkalar qo'yildi", count >= 2, str(count))
    check("HTML ichiga joylashdi",
          filled[0].count('src="data:image/png;base64,') >= 2, str(count))
    check("noma'lum nom slaydni buzmaydi", "<img" not in filled[0]
          or filled[0].count("<img") <= count, filled[0][:80])

    # Rang: aksent va oq — ikki xil fayl bo'lishi kerak.
    education = icon_render.resolve("education")
    check("ikonka fayli topiladi", bool(education), str(education))
    if education:
        painted = icon_render.tinted(education, theme.accent)
        white = icon_render.tinted(education, "FFFFFF")
        check("ikonka bo'yaladi", bool(painted) and painted != white,
              f"{painted} / {white}")
        from PIL import Image

        with Image.open(painted) as image:
            pixels = list(image.convert("RGBA").getdata())
        ink = {p[:3] for p in pixels if p[3] > 200}
        wanted = tuple(int(theme.accent[i:i + 2], 16) for i in (0, 2, 4))
        check("bo'yog'i sxema rangida", ink == {wanted} if ink else False,
              str(list(ink)[:3]))


def check_accent_strip():
    """Bir tomonlama chegara butun ramka bo'lib qolmasin."""
    print("\n12) Aksent chizig'i")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    theme = themes.get("zumrad")
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;padding:90px;background:#FFFFFF;
    font-family:{html_slides.FONT_STACK};overflow:hidden}}
    .card{{width:600px;height:300px;background:#{theme.accent_soft};
    border-radius:20px;border-top:8px solid #{theme.accent};padding:40px}}
    .boxed{{width:600px;height:200px;margin-top:60px;
    border:4px solid #{theme.accent};padding:30px}}
    </style></head><body>
    <div class="card"><p>Tepasida aksent chizig'i</p></div>
    <div class="boxed"><p>To'liq ramka</p></div></body></html>"""

    path = html_render.render([page], out_dir="temp", name="sinov")
    try:
        from pptx import Presentation

        shapes = [s for s in list(Presentation(path).slides)[0].shapes
                  if s.shape_type == 1]
        # Kartochka + uning tepasidagi tasma + to'liq ramkali blok.
        strips = [s for s in shapes if s.height / 914400 < 0.12]
        check("aksent chizig'i alohida tasma bo'ldi", len(strips) == 1,
              str([round(s.height / 914400, 3) for s in shapes]))
        outlined = [s for s in shapes if s.line.fill.type == 1]
        check("to'liq ramka ramka bo'lib qoldi", len(outlined) == 1,
              str(len(outlined)))
    finally:
        if os.path.exists(path):
            os.remove(path)


def check_inline_text():
    """Abzats ichidagi <b>/<span> matni ajralib ketmasligi.

    Ekstraktor faqat elementning O'Z matn tugunlarini olardi. Abzats
    ichida <b> bo'lsa, uning matni otasidan tushib qolar va alohida
    quti bo'lib o'sha abzatsning USTIGA chiqardi: varaqda matn ham
    uzilgan, ham ustma-ust bo'lib ko'rinardi.
    """
    print("\n13) Abzats ichidagi ajratilgan matn")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    theme = themes.get("ko'k")
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;padding:90px;background:#FFFFFF;
    font-family:{html_slides.FONT_STACK};overflow:hidden}}
    h2{{font-size:52px;color:#{theme.heading}}}
    p{{font-size:28px;color:#{theme.body};max-width:1200px;line-height:1.5;
    margin-top:40px}}
    b{{color:#{theme.accent}}}
    .uzun{{max-width:700px}}
    </style></head><body>
    <h2>Sarlavha <b>ajratilgan</b> so'z bilan</h2>
    <p>Yalpi ichki mahsulot <b>2026-yilda</b> pasaydi.</p>
    <p class="uzun">Bu ko'rsatkich <b>uch yil</b> davomida pasayishda davom
    etishi va ishlab chiqarish hajmiga hamda bandlik darajasiga sezilarli
    ta'sir ko'rsatishi kutilmoqda.</p>
    </body></html>"""

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = html_render._launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080})
            page_handle = context.new_page()
            page_handle.set_content(page, wait_until="load")
            blocks = [b for b in html_extract.read_layout(page_handle)["blocks"]
                      if b["kind"] == "text"]
            problems = html_extract.check_layout(page_handle)
            context.close()
        finally:
            browser.close()

    texts = [b["text"] for b in blocks]
    check("har abzats bitta quti", len(blocks) == 3, str(len(blocks)))
    check("ajratilgan so'z o'z joyida qoldi",
          any("2026-yilda pasaydi" in t for t in texts), str(texts))
    check("sarlavha ham butun",
          any(t.startswith("Sarlavha ajratilgan so'z") for t in texts),
          str(texts[:1]))
    check("matn ikki marta olinmadi",
          sum(t.count("2026-yilda") for t in texts) == 1, str(texts))
    check("soxta to'qnashuv yo'q",
          not any("matn ustiga matn" in item for item in problems),
          str(problems))

    single = [b for b in blocks if b.get("lines") == 1]
    multi = [b for b in blocks if b.get("lines", 1) > 1]
    check("qator soni o'lchanadi", bool(single) and bool(multi),
          str([b.get("lines") for b in blocks]))


def check_text_box_width():
    """Matn qutisi brauzerdagi o'lchamda qolsin.

    Ilgari har quti o'n piksel kengaytirilardi. Ko'p qatorli matnda bu
    o'rashni o'zgartirar, matn qayta o'ralib qo'shnisining ustiga
    chiqardi.
    """
    print("\n14) Matn qutisining kengligi")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    theme = themes.get("ko'k")
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;padding:90px;background:#FFFFFF;
    font-family:{html_slides.FONT_STACK};overflow:hidden}}
    .box{{width:800px;font-size:26px;color:#{theme.body};line-height:1.5}}
    </style></head><body>
    <div class="box">Bu matn sakkiz yuz piksel kenglikdagi blokda turadi va
    bir necha qatorga joylashadi, shuning uchun uning kengligi aynan
    saqlanishi kerak.</div></body></html>"""

    path = html_render.render([page], out_dir="temp", name="sinov")
    try:
        from pptx import Presentation

        shape = next(s for s in list(Presentation(path).slides)[0].shapes
                     if s.has_text_frame and s.text_frame.text.strip())
        # 800 px = 5.56 dyuym. Zaxira ikki pikseldan oshmasin.
        width = shape.width / 914400
        check("ko'p qatorli quti o'z kengligida",
              abs(width - 800 * 13.333 / 1920) < 0.03, f"{width:.3f} dyuym")
        check("matn to'liq ko'chdi",
              "saqlanishi kerak" in shape.text_frame.text,
              shape.text_frame.text[-40:])
        check("o'rash yoqilgan", shape.text_frame.word_wrap is True)
    finally:
        if os.path.exists(path):
            os.remove(path)


def check_double_text():
    """Bir matn slaydda ikki marta yozilmasin.

    Dizayn qilayotgan model sarlavhaga soya yoki nur berish uchun
    uning ikkinchi nusxasini qo'yadi: `<span>` ichida, ustma-ust
    `position:absolute` bilan yoki `filter: blur` qo'yilgan qatlamda.
    Brauzerda ikkalasi ustma-ust tushib bittadek ko'rinadi, PowerPoint
    esa ikkita alohida matn qutisi chizadi — mijoz muqovada sarlavha
    ikki marta yozilganini ko'radi.

    Chizuvchi nusxani olib tashlashi va tekshiruv HTML ning o'zi
    tuzatilishini so'rashi kerak. Ayni paytda turli joydagi bir xil
    matn (masalan ikki kartada bir sarlavha) o'chib ketmasligi kerak.
    """
    print("\n15) Matn ikki marta yozilishi")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    theme = themes.get("ko'k")
    head = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;padding:90px;background:#FFFFFF;
    font-family:{html_slides.FONT_STACK};overflow:hidden}}
    h1{{font-size:88px;color:#{theme.heading};position:relative}}
    .soya{{position:absolute;left:6px;top:6px;color:rgba(0,0,0,.35)}}
    .nur{{position:absolute;left:90px;top:90px;filter:blur(6px);
    color:#{theme.accent}}}
    .izoh{{margin-top:48px;font-size:28px;color:#{theme.body};
    line-height:1.6;max-width:1400px}}
    .karta{{display:inline-block;width:520px;padding:32px;
    background:#{theme.accent_soft};margin-right:24px}}
    .karta h3{{font-size:32px;color:#{theme.heading}}}
    </style></head><body>"""
    tail = "</body></html>"

    pages = {
        # Soya uchun ustma-ust qo'yilgan nusxa.
        "soya": head + """
        <h1><span class="soya">Muqova sarlavhasi</span>Muqova sarlavhasi</h1>
        <p class="izoh">Sarlavha ostidagi izoh matni.</p>""" + tail,
        # Xiralashtirilgan "nur" qatlami.
        "nur": head + """
        <h1 class="nur">Muqova sarlavhasi</h1>
        <h1>Muqova sarlavhasi</h1>
        <p class="izoh">Sarlavha ostidagi izoh matni.</p>""" + tail,
        # Matn oqimi ichidagi nusxa: innerText ikki marta qaytaradi.
        "oqim": head + """
        <h1><span style="color:rgba(0,0,0,.2)">Muqova sarlavhasi</span>Muqova sarlavhasi</h1>
        <p class="izoh">Sarlavha ostidagi izoh matni.</p>""" + tail,
        # Turli joydagi bir xil matn — nusxa emas, ikkalasi qolsin.
        "alohida": head + """
        <h1>Ikki karta</h1>
        <div class="karta"><h3>Yalpi ichki mahsulot</h3></div>
        <div class="karta"><h3>Yalpi ichki mahsulot</h3></div>
        <p class="izoh">Bir xil sarlavha ikki kartada, lekin ustma-ust emas.</p>"""
        + tail,
    }

    from playwright.sync_api import sync_playwright

    found = {}
    warned = {}
    with sync_playwright() as playwright:
        browser = html_render._launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080})
            for name, html in pages.items():
                handle = context.new_page()
                handle.set_content(html, wait_until="load")
                found[name] = [
                    block["text"]
                    for block in html_extract.read_layout(handle)["blocks"]
                    if block["kind"] == "text"]
                warned[name] = any("ikki marta yozilgan" in item
                                   for item in html_extract.check_layout(handle))
                handle.close()
            context.close()
        finally:
            browser.close()

    for name in ("soya", "nur", "oqim"):
        titles = [t for t in found[name] if "Muqova sarlavhasi" in t]
        check(f"{name}: sarlavha bir marta tushdi",
              len(titles) == 1 and titles[0] == "Muqova sarlavhasi",
              str(titles))

    check("soya: HTML tuzatilishi so'raladi", warned["soya"])
    check("nur: HTML tuzatilishi so'raladi", warned["nur"])

    apart = [t for t in found["alohida"] if t == "Yalpi ichki mahsulot"]
    check("turli joydagi bir xil matn saqlandi", len(apart) == 2, str(apart))
    check("alohida matn nusxa deb sanalmadi", not warned["alohida"])


def check_no_shadow():
    """Slaydda soya umuman qolmasin.

    Soya PowerPointga o'tmaydi: shakl soyasini biz o'chiramiz, matn
    soyasini esa model ko'pincha matnning ikkinchi nusxasi bilan
    chizadi — shunda sarlavha ikki marta yozilgan bo'lib chiqadi.
    Shuning uchun soya HTML ning o'zidan kesib tashlanadi: model
    qoidani unutsa ham slaydda soya qolmaydi.
    """
    print("\n16) Soya butunlay olib tashlanadi")
    theme = themes.get("ko'k")

    page = ("<!DOCTYPE html><html><head><style>"
            ".karta{box-shadow:0 4px 12px rgba(0,0,0,.2);width:400px}"
            "h1{text-shadow:2px 2px 6px #000;font-size:80px}"
            ".nur{filter:drop-shadow(0 2px 4px rgba(0,0,0,.3))}"
            ".xira{filter:blur(4px) drop-shadow(0 2px 4px #000)}"
            "</style></head><body>"
            '<div class="karta" style="box-shadow:0 2px 4px #0002;color:red">'
            "<h1>Sarlavha</h1></div></body></html>")

    out = html_slides.strip_shadows(page)
    check("slayd o'qildi", bool(out))

    check("box-shadow qolmadi", "box-shadow" not in out.lower())
    check("text-shadow qolmadi", "text-shadow" not in out.lower())
    check("drop-shadow qolmadi", "drop-shadow" not in out.lower())
    check("blur o'z joyida qoldi", "blur(4px)" in out, out[-160:])
    check("boshqa uslub tegilmadi",
          "width:400px" in out and "color:red" in out and "80px" in out, out)

    check("dizayn tizimida soya yo'q",
          "shadow" not in deck_style.stylesheet(theme).lower())


def check_repair_keeps_images():
    """Slayd qayta chizilganda rasm va ikonka yo'qolmasin.

    Tuzatish so'rovi slaydning butun HTML ini modelga yuborardi —
    ichidagi `src="data:image/png;base64,..."` bilan birga. Bitta
    fotosurat yuz minglab belgi bo'ladi: so'rov kontekstga sig'maydi,
    sig'sa ham model uzun satrni qayta yoza olmay rasmni tushirib
    qoldiradi. Natijada slaydda buzuq rasm belgisi alt matni bilan
    qolardi — mijoz uni "ortiqcha snoska" deb ko'rardi.
    """
    print("\n17) Tuzatishda rasm saqlanadi")
    theme = themes.get("ko'k")

    photo = "data:image/png;base64," + "A" * 4000
    page = ("<!DOCTYPE html><html><head><style>"
            ".foto{width:600px}</style></head><body>"
            f'<img class="foto" src="{photo}" alt="Sanoat">'
            '<img class="ikon" src="data:image/png;base64,BBBB" alt="">'
            "<h1>Sarlavha</h1></body></html>")

    parked, store = html_slides._park_images(page)
    check("rasm so'rovdan chiqarildi", "base64,AAAA" not in parked)
    check("belgi qo'yildi", 'src="#rasm1"' in parked, parked[:200])
    check("so'rov qisqardi", len(parked) < len(page) - 3900,
          f"{len(page)} → {len(parked)}")
    check("ikkala rasm ham saqlandi", len(store) == 2, str(len(store)))
    check("belgilar qaytariladi",
          html_slides._unpark_images(parked, store) == page)

    # Model belgini tushirib qoldirsa — buzuq rasm qolmasin.
    lost = parked.replace('src="#rasm1"', "")
    restored = html_slides._restore(lost, theme)
    check("egasiz rasm blokka aylandi",
          "<img" not in restored.replace('<img class="ikon"', ""),
          restored[:300])
    check("sarlavha joyida", "Sarlavha" in restored)


def check_photo_has_no_text():
    """Rasm suratiga uning ustidagi matn tushmasin.

    Brauzerning element surati ELEMENTNI emas, sahifaning o'sha
    joyini oladi. Muqovada fotosurat butun slaydni egallaydi,
    shuning uchun sarlavha, ost sarlavha va pastki qator rasmning
    ichiga ham kirib qolardi. Keyin biz o'sha matnlarni yana haqiqiy
    matn qutisi qilib ustiga qo'yardik — mijoz har bir qatorni ikki
    marta, bir-biridan sal siljigan holda ko'rardi.

    Bezak qatlami (to'q parda) esa rasmda QOLISHI kerak: u
    PowerPointda alohida shakl bo'lib chiqmaydi.
    """
    print("\n18) Rasm ichida matn qolmasin")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    # Bir rangli "fotosurat": ustidagi matn bo'lsa darhol bilinadi.
    photo = ("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5v"
             "cmcvMjAwMC9zdmciIHdpZHRoPSI4MDAiIGhlaWdodD0iNDUwIj48cmVjdCB3"
             "aWR0aD0iODAwIiBoZWlnaHQ9IjQ1MCIgZmlsbD0iI0ZGRkZGRiIvPjwvc3Zn"
             "Pg==")
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;font-family:{html_slides.FONT_STACK};
    overflow:hidden}}
    .slide{{position:relative;width:1920px;height:1080px;overflow:hidden}}
    .photo{{position:absolute;inset:0;width:100%;height:100%;
    object-fit:cover}}
    .parda{{position:absolute;inset:0;background:rgb(20,40,70)}}
    .ichi{{position:absolute;left:0;right:0;top:400px;text-align:center;
    color:#FFFFFF}}
    h1{{font-size:88px}}
    .belgi{{position:absolute;left:100px;top:900px}}
    </style></head><body><div class="slide">
    <img class="photo" src="{photo}" alt="">
    <div class="parda"></div>
    <div class="ichi"><h1>MUQOVA SARLAVHASI</h1></div>
    <svg class="belgi" width="300" height="120">
      <rect width="300" height="120" fill="#FFFFFF"></rect>
      <text x="20" y="70" font-size="40" fill="#000000">Diagramma</text>
    </svg>
    </div></body></html>"""

    out = os.path.join("temp", "sinov_surat")
    os.makedirs(out, exist_ok=True)
    from playwright.sync_api import sync_playwright

    blocks = []
    with sync_playwright() as playwright:
        browser = html_render._launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=1)
            handle = context.new_page()
            handle.set_content(page, wait_until="load")
            blocks = html_extract.read_layout(handle)["blocks"]
            html_extract.capture_images(handle, blocks, out, 1)
            after = handle.evaluate(
                "() => getComputedStyle(document.querySelector('h1'))"
                ".visibility")
            context.close()
        finally:
            browser.close()

    shots = [b for b in blocks if b.get("path")]
    check("ikkala vizual ham suratga olindi", len(shots) == 2, str(len(shots)))
    check("matn qayta ko'rinadigan qilindi", after == "visible", str(after))

    from PIL import Image

    try:
        wide = next(b for b in shots if b["w"] > 1000)
        small = next(b for b in shots if b["w"] < 1000)

        image = Image.open(wide["path"]).convert("RGB")
        band = image.crop((300, 400, 1620, 520))
        check("fotosuratda sarlavha qolmadi",
              len(set(band.getdata())) == 1,
              f"{len(set(band.getdata()))} xil rang")
        check("parda rasmda qoldi",
              band.getpixel((10, 10)) == (20, 40, 70),
              str(band.getpixel((10, 10))))

        mark = Image.open(small["path"]).convert("RGB")
        check("diagramma o'z yozuvini saqladi",
              len(set(mark.getdata())) > 1,
              f"{len(set(mark.getdata()))} xil rang")
    finally:
        for block in shots:
            if os.path.exists(block["path"]):
                os.remove(block["path"])


def check_rotated_label():
    """Tik yozilgan o'q yozuvi PowerPointda ham tik tursin.

    Diagrammaning tik o'q yozuvi (`rotate(-90deg)` yoki
    `writing-mode: vertical-rl`) uchun brauzer ingichka va baland
    qamrov beradi. Uni shundayligicha matn qutisi qilsak, PowerPoint
    har harfni alohida qatorga tushirib yuboradi — slaydda chetda
    bir ustun harf turardi.
    """
    print("\n19) Burilgan o'q yozuvi")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;padding:90px;background:#FFFFFF;
    font-family:{html_slides.FONT_STACK};overflow:hidden}}
    .oq{{width:360px;font-size:24px;transform:rotate(-90deg);
    position:absolute;left:60px;top:500px}}
    .tik{{font-size:24px;writing-mode:vertical-rl;position:absolute;
    left:300px;top:400px}}
    .yotiq{{font-size:24px;position:absolute;left:700px;top:400px}}
    </style></head><body>
    <div class="oq">Iqtisodiyotga ta'sir (%)</div>
    <div class="tik">Hajmi</div>
    <div class="yotiq">Oddiy yozuv</div>
    </body></html>"""

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = html_render._launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080})
            handle = context.new_page()
            handle.set_content(page, wait_until="load")
            blocks = [b for b in html_extract.read_layout(handle)["blocks"]
                      if b["kind"] == "text"]
            context.close()
        finally:
            browser.close()

    found = {b["text"]: b for b in blocks}
    axis = found.get("Iqtisodiyotga ta'sir (%)")
    check("o'q yozuvi topildi", axis is not None, str(list(found)))
    if axis:
        check("burilish o'lchandi", axis.get("rotation") == -90,
              str(axis.get("rotation")))
        check("quti burilishdan oldingi o'lchamda",
              axis["w"] > axis["h"] and axis["w"] > 300,
              f"{axis['w']:.0f}x{axis['h']:.0f}")
        check("bitta qatorga sig'di", axis.get("lines") == 1,
              str(axis.get("lines")))

    upright = found.get("Hajmi")
    check("vertical-rl ham burilgan deb olindi",
          upright is not None and upright.get("rotation") == 90,
          str(upright.get("rotation") if upright else None))

    plain = found.get("Oddiy yozuv")
    check("oddiy yozuv burilmadi",
          plain is not None and not plain.get("rotation"),
          str(plain.get("rotation") if plain else None))


def check_side_gap():
    """Slaydning bir yoni bo'sh qolganini tekshiruv ko'rsin.

    Diagramma ko'pincha shunday buziladi: model ustunlarga qat'iy
    `width` berib, ularni `flex` qatoriga tiqadi — ustunlar chap
    chekkaga to'planadi va slaydning o'ng yarmi bo'm-bo'sh qoladi.
    Tepadan pastga qarab tekshiruvchi qoidalar buni ko'rmasdi.

    Markazga qo'yilgan blok (ikki yoni baravar bo'sh) xato emas —
    u ataylab shunday qilingan.
    """
    print("\n20) Bo'sh yon maydonini o'lchash")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    theme = themes.get("ko'k")
    head = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;padding:90px;background:#FFFFFF;
    font-family:{html_slides.FONT_STACK};overflow:hidden}}
    h2{{font-size:52px;color:#{theme.heading};margin-bottom:60px}}
    .ustun{{width:100px;background:#{theme.accent}}}
    .qator{{display:flex;gap:20px;align-items:flex-end;height:520px}}
    .keng{{justify-content:space-between}}
    .keng .ustun{{flex:1}}
    .markaz{{margin:0 auto;width:900px;height:520px;
    background:#{theme.accent_soft}}}
    .yon{{display:flex;gap:40px;height:520px}}
    .yon>div{{flex:1;background:#{theme.accent_soft}}}
    </style></head><body><h2>Sarlavha</h2>"""
    tail = "</body></html>"
    bars = "".join(f'<div class="ustun" style="height:{h}%"></div>'
                   for h in (90, 80, 70, 60, 50, 40, 30))

    pages = {
        # Ustunlar chap chekkada — xato.
        "chap": head + f'<div class="qator">{bars}</div>' + tail,
        # O'sha ustunlar butun enni egallagan — to'g'ri.
        "keng": head + f'<div class="qator keng">{bars}</div>' + tail,
        # Markazga qo'yilgan blok — xato emas.
        "markaz": head + '<div class="markaz"></div>' + tail,
        # Ikki ustunli slayd — xato emas.
        "ikki": head + '<div class="yon"><div></div><div></div></div>' + tail,
    }

    from playwright.sync_api import sync_playwright

    seen = {}
    problems = {}
    with sync_playwright() as playwright:
        browser = html_render._launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080})
            for name, html in pages.items():
                handle = context.new_page()
                handle.set_content(html, wait_until="load")
                seen[name] = html_extract.gap_area(handle)
                problems[name] = html_extract.check_layout(handle)
                handle.close()
            context.close()
        finally:
            browser.close()

    check("chap chekkaga siqilgani topildi", seen["chap"] is not None)
    check("butun enni egallagani bo'sh emas", seen["keng"] is None)
    check("markazdagi blok bo'sh emas", seen["markaz"] is None)
    check("ikki ustunli slayd bo'sh emas", seen["ikki"] is None)

    area = seen["chap"]
    if area:
        check("bo'sh yon o'ng tomonda", area["side"] == "right",
              str(area["side"]))
        check("maydon o'lchamlari to'g'ri",
              area["w"] > 1920 * 0.30 and area["h"] > 1080 * 0.15,
              f"{area['w']:.0f}x{area['h']:.0f}")
        check("bo'sh yon xato deb sanalmadi",
              not any("bir yoniga" in item for item in problems["chap"]),
              str(problems["chap"]))

        # Bo'sh joyga izoh qo'yiladi — slayd qayta chizilmaydi.
        filled = html_slides.fill_gap(
            pages["chap"], area, theme, "uz")
        check("izohsiz slayd o'zgarmaydi", filled == pages["chap"],
              "model chaqirilmasligi kerak edi")

    # Diagramma endi kod chizadi va u butun enni egallaydi — model
    # uni tor qilib qo'ya olmaydi.
    svg = deck_charts.draw(
        '<div class="chart" data-kind="bar" data-labels="a,b" '
        'data-series="X: 1,2"></div>', theme)
    check("diagramma butun enni egallaydi",
          f'width="{deck_charts.W}"' in svg, svg[:120])


def check_gap_text():
    """Bo'sh yonga diagramma izohi qo'yilsin.

    Slaydning bir yoni bo'sh qolsa uni QAYTA CHIZISH shart emas:
    joylashuv to'g'ri, shunchaki joy bor. O'sha joyga diagrammani
    tushuntiruvchi matn qo'yiladi — slayd ham to'ladi, mazmuni ham
    boyiydi.
    """
    print("\n21) Bo'sh yonga qo'yiladigan izoh")
    theme = themes.get("ko'k")
    page = ("<!DOCTYPE html><html><head><style>"
            ".q{width:600px;height:500px}</style></head><body>"
            '<div class="q">Diagramma</div></body></html>')
    area = {"side": "right", "x": 800.0, "y": 300.0, "w": 900.0, "h": 500.0}

    # Modelni chaqirmaymiz — matnni o'zimiz beramiz.
    izoh = ("Ko'rsatkich 2020-yildagi 60 foizdan 2026-yilga kelib 30 "
            "foizga tushgan. Bu <kurashish> choralari samara berayotganini "
            "bildiradi.")
    asl = html_slides.explain_visual
    html_slides.explain_visual = lambda *a, **k: izoh
    try:
        out = html_slides.fill_gap(page, area, theme, "uz")
    finally:
        html_slides.explain_visual = asl

    check("izoh slaydga qo'shildi", "foizga tushgan" in out, out[-200:])
    check("bo'sh joyga qo'yildi", "left:848px" in out, out[-260:])
    check("</body> ichida qoldi", out.rstrip().endswith("</body></html>"),
          out[-40:])
    check("asl mazmun o'zgarmadi", '<div class="q">Diagramma</div>' in out)
    check("teg qochirildi", "&lt;kurashish&gt;" in out and "<kurashish>" not in out)
    check("aksent chizig'i qo'yildi", 'class="rule"' in out)

    # Maydon juda kichik bo'lsa tegilmaydi.
    tor = html_slides.fill_gap(page, {"x": 0, "y": 0, "w": 150, "h": 500},
                               theme, "uz")
    check("tor joyga matn tiqilmaydi", tor == page)
    check("maydonsiz chaqiruv xavfsiz",
          html_slides.fill_gap(page, None, theme, "uz") == page)


def check_text_spill():
    """Matn o'z qutisidan chiqib ketgani topilsin.

    Sxemalarda model natija tugunini doira qilib chizadi va ichiga
    ikki so'zlik yorliq yozadi. Doiraga matn sig'maydi: harflar
    chetidan chiqib, bog'lovchi chiziqqa minadi. Brauzer buni aniq
    aytadi — mazmun qutidan kattami yoki yo'q.
    """
    print("\n22) Matn qutisiga sig'masligi")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    theme = themes.get("ko'k")
    head = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{width:1920px;height:1080px;padding:90px;background:#FFFFFF;
    font-family:{html_slides.FONT_STACK};overflow:hidden}}
    h2{{font-size:52px;color:#{theme.heading};margin-bottom:60px}}
    .doira{{width:110px;height:110px;border-radius:50%;
    background:#{theme.accent};color:#FFFFFF;font-size:28px;
    display:flex;align-items:center;justify-content:center;
    text-align:center}}
    .keng{{width:240px;height:240px}}
    .quti{{width:520px;padding:28px;background:#{theme.accent_soft};
    border-radius:16px;font-size:26px;color:#{theme.body}}}
    .qator{{display:flex;gap:48px;align-items:center;height:420px}}
    </style></head><body><h2>Sxema</h2>"""
    tail = "</body></html>"

    pages = {
        # Doiraga uzun yorliq — sig'maydi.
        "toshgan": head + '<div class="qator"><div class="doira">'
                   "Yashirin Iqtisodiyot</div></div>" + tail,
        # Qutisi matnga qarab cho'ziladi — sig'adi.
        "sigdi": head + '<div class="qator"><div class="quti">'
                 "Yashirin iqtisodiyot davlat nazoratidan tashqarida "
                 "qolgan faoliyat turlari.</div></div>" + tail,
        # Doirada qisqa raqam — sig'adi.
        "raqam": head + '<div class="qator"><div class="doira">01</div>'
                 "</div>" + tail,
        # Doira matnga yetarlicha keng — sig'adi.
        "keng": head + '<div class="qator"><div class="doira keng">'
                "Yashirin Iqtisodiyot</div></div>" + tail,
    }

    from playwright.sync_api import sync_playwright

    seen = {}
    with sync_playwright() as playwright:
        browser = html_render._launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080})
            for name, html in pages.items():
                handle = context.new_page()
                handle.set_content(html, wait_until="load")
                seen[name] = [item for item in html_extract.check_layout(handle)
                              if "sig'magan" in item]
                handle.close()
            context.close()
        finally:
            browser.close()

    check("doiradan toshgan matn topildi", bool(seen["toshgan"]),
          str(seen["toshgan"]))
    check("cho'ziladigan quti xato emas", not seen["sigdi"],
          str(seen["sigdi"]))
    check("doiradagi raqam xato emas", not seen["raqam"],
          str(seen["raqam"]))
    check("keng doira xato emas", not seen["keng"], str(seen["keng"]))

    # Sxemadagi qutilar endi bir xil bo'lishi SHART emas — ular
    # dizayn tizimidan kelgani uchun boshqacha bo'la olmaydi.
    css = deck_style.stylesheet(theme)
    check("kartochka bitta qoidadan keladi",
          css.count("\n.card{background:") == 1,
          str(css.count("\n.card{background:")))
    body = css.split("\n.card{background:")[1].split("}")[0]
    # Faqat qat'iy `height` taqiqlanadi. `min-height` xavfsiz: mazmun
    # ko'p bo'lsa quti baribir cho'ziladi, matn chiqib ketmaydi.
    import re as _re
    check("qutiga qat'iy balandlik berilmaydi",
          not _re.search(r"(?<!min-)(?<!max-)height:", body), body)
    check("matn uchun doira yo'q — faqat ikonka uchun",
          "border-radius:50%" in css and ".ikon-dot{" in css)


def check_colour_harmony():
    """To'q fonda qora matn qolmasin, yassi fon quruq ko'rinmasin.

    Mijoz taqdimotida to'q ko'k kartochka ichidagi ro'yxat qora
    rangda qolib, umuman o'qilmagan edi: uslubda `.item-text` ning
    to'q fon uchun varianti yo'q edi. Bu ikki yo'l bilan yopildi:
    uslubda to'q sirtdagi hamma matn sanab chiqildi, chizuvchida esa
    kontrast qorovuli qo'yildi — sinf unutilsa ham matn o'qiladigan
    rangga o'giriladi.
    """
    print("\n23) Rang uyg'unligi va gradient")
    if not html_render.available():
        check("brauzer o'rnatilgan", False, html_render._INSTALL_HINT)
        return

    theme = themes.get("ko'k")
    solid = ('<section class="slide"><div class="body"><div class="cols cols-2">'
             '<div class="card"><div class="card-title">Och</div>'
             '<div class="list"><div class="item"><span class="item-dot"></span>'
             '<div class="item-text">Och kartadagi band</div></div></div></div>'
             '<div class="card solid"><div class="card-title">To\'q</div>'
             '<div class="list"><div class="item"><span class="item-dot"></span>'
             '<div class="item-text"><b>Kalit.</b> To\'q kartadagi band</div>'
             '</div></div></div></div></div></section>')
    dark = ('<section class="slide dark"><div class="body">'
            '<h1 class="title big">Muqova</h1><p class="lead">Izoh</p>'
            '</div></section>')
    pages = html_slides.build_pages([solid, dark], theme)

    # Qasddan buzilgan uslub: to'q blokda to'q matn. Qorovul uni
    # o'qiladigan rangga o'girishi kerak.
    broken = ("<!DOCTYPE html><html><head><style>"
              "body{margin:0;width:1920px;height:1080px}"
              ".q{background:#10243F;padding:60px;width:900px}"
              ".q p{color:#1A2A40;font-size:40px}</style></head><body>"
              "<div class='q'><p>Ko'rinmas matn</p></div></body></html>")

    from playwright.sync_api import sync_playwright

    layouts = []
    with sync_playwright() as playwright:
        browser = html_render._launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080})
            for html in pages + [broken]:
                handle = context.new_page()
                handle.set_content(html, wait_until="load")
                layouts.append(html_extract.read_layout(handle))
                handle.close()
            context.close()
        finally:
            browser.close()

    def texts(layout):
        return {b["text"]: b for b in layout["blocks"] if b["kind"] == "text"}

    def light(colour):
        r, g, b = (int(colour[i:i + 2], 16) for i in (0, 2, 4))
        return (r + g + b) / 3 > 170

    first = texts(layouts[0])
    band = next((b for t, b in first.items() if "To'q kartadagi" in t), None)
    plain = first.get("Och kartadagi band")
    check("to'q kartada matn OCHIQ", band is not None and light(band["color"]),
          str(band and band["color"]))
    check("och kartada matn TO'Q", plain is not None and not light(plain["color"]),
          str(plain and plain["color"]))

    cover = texts(layouts[1])
    check("muqova sarlavhasi oq", "Muqova" in cover and
          light(cover["Muqova"]["color"]), str(cover.get("Muqova", {}).get("color")))
    ramps = [b for b in layouts[1]["blocks"]
             if b["kind"] == "rect" and b.get("gradient")]
    check("to'q varaq gradientli", bool(ramps), str(len(ramps)))
    check("gradient ikki tusli", bool(ramps) and len(ramps[0]["gradient"]["stops"]) >= 2)
    circles = [b for b in layouts[1]["blocks"]
               if b["kind"] == "rect" and b.get("circle")]
    check("bezak doiralari bor", len(circles) >= 2, str(len(circles)))

    fixed = texts(layouts[2]).get("Ko'rinmas matn")
    check("qorovul to'q fondagi to'q matnni ochdi",
          fixed is not None and light(fixed["color"]),
          str(fixed and fixed["color"]))

    # PowerPointda gradient haqiqiy to'ldirish bo'lsin.
    path = html_render.render(pages[1:], out_dir="temp", name="gradient")
    try:
        import zipfile
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        check("PowerPointda gradient to'ldirish", "gradFill" in xml)
    finally:
        if os.path.exists(path):
            os.remove(path)

    # Shrift telefonda ham o'qilsin.
    import re as _re
    css = deck_style.stylesheet(theme)

    def size(sel):
        m = _re.search(r"\n" + _re.escape(sel) + r"\{[^}]*?font-size:(\d+)px", css)
        return int(m.group(1)) if m else 0

    for sel, least in ((".item-text", 36), (".card-note", 30),
                       (".kpi-note", 30), (".note", 28), ("body", 28)):
        check(f"{sel} yetarlicha yirik", size(sel) >= least, f"{size(sel)}px")


def main():
    check_handler_names()
    check_prompt()
    check_design_system()
    check_charts()
    check_math()
    if html_render.available():
        check_fraction_boxes()
    check_split()
    check_no_quotas()
    check_outline()
    check_family_shape()
    check_writer()
    check_browser_setup()
    if check_shot():
        check_editable()
        check_layout_guard()
        check_decoration()
    check_icons()
    if html_render.available():
        check_accent_strip()
        check_inline_text()
        check_text_box_width()
        check_double_text()
    check_no_shadow()
    check_repair_keeps_images()
    if html_render.available():
        check_photo_has_no_text()
        check_rotated_label()
        check_side_gap()
    check_gap_text()
    if html_render.available():
        check_text_spill()
        check_colour_harmony()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} ta tekshiruv o'tmadi: {', '.join(FAILS[:5])}")
        return 1
    print("✅ HTML slaydlar chiziladi va tahrirlanadigan PPTX ga tushadi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
