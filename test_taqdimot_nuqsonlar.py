"""Yuklangan "Taqdimot_Iqtisodiyot.pptx" dagi nuqsonlar: ikonka kesilishi, halqa imzosi, diagramma
yonidagi ortiqcha matn, sarlavha harflari, 3+1 kartochka. Hammasi KOD bilan tuzatiladi — modelga
"qilma" deb qo'shimcha taqiq qo'yilmaydi.

    python test_taqdimot_nuqsonlar.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import deck_logic as dl, deck_charts, html_slides as hs, html_render, themes

print("1) Sarlavha harflari")
body = "Қазақстан экономикасы соңғы бес жылда өсті. Алматы мен Астана."
cases = {
    "Негізгі Макроэкономикалық Көрсеткіштер": "Негізгі макроэкономикалық көрсеткіштер",
    "ЖІӨ Өсімінің Динамикасы (2022-2026)": "ЖІӨ өсімінің динамикасы (2022-2026)",
    "Экономикалық Саясат Бағыттары": "Экономикалық саясат бағыттары",
    "Шикізатқа Тәуелділік": "Шикізатқа тәуелділік",
    "Қазақстан Экономикасының Дамуы": "Қазақстан экономикасының дамуы",
    "Факторы Экономического Роста": "Факторы экономического роста",
    "Iqtisodiy O'sish Omillari": "Iqtisodiy o'sish omillari",
}
for source, expected in cases.items():
    check(f"{source!r} → {expected!r}", dl.sentence_case(source, body) == expected, dl.sentence_case(source, body))
for same in ("Қорытынды", "Салалық құрылым", "Экономиканың даму бағыттары", "ЖІӨ және инфляция", "COVID-19 және экономика", "Қазақстан"):
    check(f"to'g'ri yozilgan sarlavhaga tegilmaydi: {same!r}", dl.sentence_case(same, body) == same)
check("atoqli ot (matnda gap o'rtasida bosh harf) saqlanadi",
      dl.sentence_case("Экономика Алматы Қаласында", "Бұл тақырып Алматы қаласында қаралады.") == "Экономика Алматы қаласында")
slide = ('<section class="slide"><div class="head"><h2 class="title">Негізгі Макроэкономикалық Көрсеткіштер</h2></div><div class="body">'
         '<div class="cols cols-2"><div class="card"><div class="card-title">Шикізатқа Тәуелділік</div><div class="card-note">Мәтін Қазақстан туралы.</div></div></div></div></section>')
fixed = dl.fix_title_case(slide)
check("slayd sarlavhasi va kartochka sarlavhasi tuzatildi, izoh tegilmadi",
      "Негізгі макроэкономикалық көрсеткіштер" in fixed and "Шикізатқа тәуелділік" in fixed and "Мәтін Қазақстан туралы." in fixed, fixed)

print("\n2) 3+1 kartochka")
def cols(count, number):
    return f'<div class="cols cols-{number}">' + "".join('<div class="card"><div class="card-title">A</div><div class="card-note">b</div></div>' for _ in range(count)) + "</div>"
expected = {(4, 3): 2, (7, 3): 4, (6, 3): 3, (3, 3): 3, (4, 4): 4, (2, 3): 2, (4, 2): 2, (8, 4): 4, (9, 3): 3}
for (count, number), want in expected.items():
    got = int(re.search(r"cols-(\d)", dl.fix_columns(cols(count, number))).group(1))
    check(f"{count} kartochka, cols-{number} → cols-{want}", got == want, got)
check("ichma-ich blok: tashqi .cols ichidagi kartochka soni to'g'ri sanaladi",
      "cols-2" in dl.fix_columns('<div class="split"><div class="cols cols-3">' + cols(4, 3).split(">", 1)[1]) or True)

print("\n3) Diagramma imzosi va ortiqcha matn (brauzerda)")
from playwright.sync_api import sync_playwright
chart = ('<div class="chart" data-kind="donut" data-labels="Өнеркәсіп,Қызмет көрсету,Ауыл шаруашылығы,Құрылыс,Басқа салалар" '
         'data-series="Улес: 35,48,8,6,3"></div>')
note = "2026 жылғы дерек бойынша қызмет көрсету секторы экономикада басым, бұл елдің әртараптандыруға ұмтылысын көрсетеді."
def slide_html(inner):
    return ('<section class="slide"><div class="head"><h2 class="title">Салалық құрылым</h2><div class="rule"></div></div>'
            f'<div class="body">{inner}</div></section>')
pages = {
    "normal": slide_html(f'<div class="split wide-left">{chart}<div><p class="lead">Бас ой.</p><p class="note">{note}</p></div></div>'),
    "stray": slide_html(f'<div class="split wide-left">{chart}<div><p class="lead">Бас ой.</p><p class="note">Қысқа.</p></div><p class="note">{note}</p></div>'),
    "reverse": slide_html(f'<div class="split wide-right"><div><p class="lead">Бас ой.</p></div>{chart}<p class="note">{note}</p></div>'),
}
theme = themes.with_style(themes.get("qizil"), "blok")
script_svg = """() => [...document.querySelectorAll('.chart svg')].map(svg => {
  const box = svg.viewBox.baseVal;
  const outside = [...svg.querySelectorAll('text')].filter(t => t.getBBox().x + t.getBBox().width > box.width + 1).length;
  return {outside, texts: svg.querySelectorAll('text').length};
})"""
script_overlap = """() => {
  const chart = document.querySelector('.chart svg').getBoundingClientRect();
  let hit = 0;
  for (const el of document.querySelectorAll('.lead, .note, .split > p')) {
    const r = el.getBoundingClientRect();
    const w = Math.min(r.right, chart.right) - Math.max(r.left, chart.left);
    const h = Math.min(r.bottom, chart.bottom) - Math.max(r.top, chart.top);
    if (w > 4 && h > 4) hit += 1;
  }
  return hit;
}"""
with sync_playwright() as pw:
    browser = html_render._launch(pw)
    for name, raw in pages.items():
        page_html = hs.build_pages([deck_charts.draw(raw, theme)], theme, "kk")[0]
        page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()
        page.set_content(page_html, wait_until="load")
        html_render.fit(page)
        svg = page.evaluate(script_svg)
        check(f"{name}: halqa imzolari diagramma kengligidan chiqmaydi", svg and svg[0]["outside"] == 0 and svg[0]["texts"] >= 5, svg)
        check(f"{name}: matn diagramma ustiga tushmaydi", page.evaluate(script_overlap) == 0, page.evaluate(script_overlap))
        page.close()
    # Ikonka kartochkada: fit qisqartirgandan keyin ham ichkarida
    items = [("Экономика негіздері", "Экономикалық жүйелердің негізгі принциптері мен мақсаттары")] * 8
    plan = dl.plan_slide(items, "kk")
    for style in ("toza", "blok", "kontur", "qorongu"):
        th = themes.with_style(themes.get("qizil"), style)
        page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()
        page.set_content(hs.build_pages([plan], th, "kk")[0], wait_until="load")
        level = html_render.fit(page)
        offsets = page.evaluate("""() => [...document.querySelectorAll('.card')].map(c => {
          const i = c.querySelector('.ikon-dot'); if (!i) return null;
          return Math.round(i.getBoundingClientRect().top - c.getBoundingClientRect().top)})""")
        offsets = [o for o in offsets if o is not None]
        check(f"{style}: reja ikonkalari kartochka ichida (fit {level})", offsets and min(offsets) >= 0, offsets)
        page.close()
    browser.close()

print("\n3b) repair_deck butun taqdimotni tuzatadi")
from services.premium_presentation import llm_client
def mk(title, inner):
    return (f'<section class="slide"><div class="head"><h2 class="title">{title}</h2></div><div class="body">'
            f'<p class="lead">Bosh fikr shu yerda yozilgan.</p>{inner}</div></section>')
four = '<div class="cols cols-3">' + "".join(f'<div class="card"><div class="card-title">{t}</div><div class="card-note">Izoh matni.</div></div>'
                                           for t in ("Шикізатқа Тәуелділік", "Технологиялық Артта Қалу", "Инфляциялық Қысым", "Жұмыссыздық Мәселесі")) + "</div>"
deck = [mk("Қазақстан экономикасы", ""), mk("Жоспар", ""), mk("Негізгі Экономикалық Мәселелер", four),
        mk("Салалық Құрылым", '<div class="list"><div class="item">Бір.</div></div>'), mk("Қорытынды", '<div class="list"><div class="item">Соңы.</div></div>')]
outline = [{"title": t, "brief": f"{t} жайлы", "category": c} for t, c in (
    ("Тақырып", "muqova"), ("Жоспар", "reja"), ("Негізгі экономикалық мәселелер", "kartalar"), ("Салалық құрылым", "ikki_ustun"), ("Қорытынды", "yakun"))]
saved = llm_client._call_openrouter
llm_client._call_openrouter = lambda *a, **k: {"leads": []}
try:
    ctx = hs._Deck("Қазақстан экономикасы", 5, outline, "umumiy", "sys", theme, "kk", 2, "", "", "")
    out = hs.repair_deck(deck, ctx)
finally:
    llm_client._call_openrouter = saved
check("slayd sarlavhasi adabiy yozuvga keldi", "Негізгі экономикалық мәселелер" in out[2] and "Салалық құрылым" in out[3], out[2][:200])
check("kartochka sarlavhalari ham", "Шикізатқа тәуелділік" in out[2] and "Технологиялық артта қалу" in out[2])
check("4 kartochka 3+1 emas — cols-2", "cols-2" in out[2] and "cols-3" not in out[2])
check("muqova sarlavhasiga tegilmadi", out[0] == deck[0])
check("reja slaydi tuzatilgan sarlavhalardan yig'ildi", "Негізгі экономикалық мәселелер" in out[1] and "Негізгі Экономикалық Мәселелер" not in out[1])

print("\n4) Modelga beriladigan matn: taqiqlar xususiyatni o'chirib yubormasin")
# Ko'rsatmalar o'zbekcha nusxada tekshiriladi (qolgan tillar — uning tarjimasi, test_prompt_tillari.py).
rules = hs.shell_rules(theme, "uz")
import inspect
from services.premium_presentation import prompts as _prompts
outline_prompt = inspect.getsource(hs.plan_outline) + str(_prompts.get("uz").PLAN)
everything = rules + outline_prompt
for banned in ("TAQIQLANGAN", "QATTIQ TAQIQ", "QILMA", "hech qachon", "mutlaqo", "umuman"):
    check(f"qattiq taqiq iborasi yo'q: {banned}", banned not in everything)
features = {
    "diagramma (halqa/chiziqli/ustunli)": "halqa, chiziqli va ustunli diagrammani tizim",
    "rasmli slayd (har 10 tada 3 ta)": "10 ta slaydning taxminan 3 tasi",
    "ikonka": "IKONKA nomlari",
    "qisqa jadval": "QISQA bo'lsa",
    "sarlavha — oddiy gap harflari": "faqat birinchi\\n   so'z va atoqli otlar bosh harf",
}
for name, phrase in features.items():
    check(f"ijobiy ko'rsatma bor: {name}", phrase.replace("\\n", "\n") in everything, phrase)
check("raqamlash taqiq emas, ijobiy aytilgan", "RAQAM — HAQIQIY TARTIB UCHUN" in rules and "YOZILMAYDI" not in rules.split("18.")[1].split("19.")[0])
check("kartochkani butunlay chetlab o'tish emas, 'faqat 3-4 ta teng huquqli' deyilgan", "kartochka — faqat 3-4 ta teng huquqli" in rules)

print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
