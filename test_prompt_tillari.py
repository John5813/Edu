"""Zamonaviy taqdimot promptlari tanlangan tilda: ruscha taqdimotga ruscha, inglizchaga inglizcha, qozoqchaga
qozoqcha prompt (ko'rsatma ham, namunalar ham). O'zbekcha ko'rsatma bilan "ruscha yoz" deyilganda model
chalg'ib, ruscha taqdimotga o'zbekcha sarlavhalar aralashtirardi.

- to'rtala modulda bir xil nomlar, bir xil bo'limlar va bir xil ⟨o'rinlar⟩;
- ruscha/inglizcha/qozoqcha promptlarning hech birida o'zbekcha so'z yo'q (qobiq, bloklar namunasi, slayd
  so'rovi, reja, tuzatish, umumlashtiruvchi gap, qayta yozish, diagramma, saytdagi qayta yozish);
- bugungi sana qoidasi ham o'sha tilda; o'zbekcha promptlar avvalgidek.

    python test_prompt_tillari.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import (chart_data, deck_compose, deck_shape, html_slides, llm_client, prompts,
                                           slide_edit, themes)

LANGS = ("uz", "ru", "en", "kk")
MODULES = {l: prompts.get(l) for l in LANGS}
NAMES = ("TARGET", "SHELL", "BLOCKS", "CATEGORIES", "SHAPE_NAMES", "FAMILIES", "GUIDANCE", "DEPTH", "USER",
         "SHAPES", "CONCLUSION_BRIEF", "BRIEF_FALLBACK", "PLAN", "REPAIR", "LEADS", "REWORK", "THICKEN", "FIX",
         "PROBLEM_WORDS", "EXPLAIN", "PLAIN", "CHART", "EDIT", "YEAR_RULE", "KAM", "PHOTO_BRIEF")
SLOT = re.compile(r"⟨(\w+)⟩")


def slots(value):
    if isinstance(value, dict):
        return {k: slots(v) for k, v in value.items()}
    if isinstance(value, str):
        return sorted(set(SLOT.findall(value)))
    return None


print("1) Modullar bir xil tuzilgan")
for name in NAMES:
    check(f"{name} hamma tilda bor", all(hasattr(MODULES[l], name) for l in LANGS),
          [l for l in LANGS if not hasattr(MODULES[l], name)])
for name in ("USER", "SHAPES", "PLAN", "REPAIR", "LEADS", "EXPLAIN", "PLAIN", "CHART", "EDIT", "DEPTH",
             "CATEGORIES", "FAMILIES", "SHAPE_NAMES", "KAM"):
    keys = {l: sorted(getattr(MODULES[l], name)) for l in LANGS}
    check(f"{name}: bo'limlar bir xil", all(keys[l] == keys["uz"] for l in LANGS), keys)
for name in ("SHELL", "GUIDANCE", "USER", "SHAPES", "PLAN", "REPAIR", "LEADS", "REWORK", "THICKEN", "FIX",
             "EXPLAIN", "PLAIN", "CHART", "EDIT", "BRIEF_FALLBACK", "KAM", "PHOTO_BRIEF"):
    shape = {l: slots(getattr(MODULES[l], name)) for l in LANGS}
    check(f"{name}: ⟨o'rinlar⟩ bir xil", all(shape[l] == shape["uz"] for l in LANGS),
          {l: shape[l] for l in LANGS if shape[l] != shape["uz"]})
check("kam matnli kompozitsiyalar tavsifi hamma tilda bir xil",
      all(sorted(MODULES[l].KAM["layouts"]) == sorted(MODULES["uz"].KAM["layouts"]) for l in LANGS))
check("kategoriya kalitlari hamma tilda bir xil (lotin)",
      all(set(MODULES[l].CATEGORIES) == set(html_slides.CATEGORY_KEYS) for l in LANGS))
check("muammo iboralari: har tilda bir xil kalitlar",
      all(set(MODULES[l].PROBLEM_WORDS) == set(MODULES["en"].PROBLEM_WORDS) for l in ("ru", "kk")))


def everything(language):
    """Bitta taqdimotda modelga boradigan HAMMA prompt (haqiqiy funksiyalar orqali)."""
    theme = themes.get("ko'k")
    P = prompts.get(language)
    outline = [{"title": "Cover", "brief": "b", "category": "muqova"},
               {"title": "Plan", "brief": "b", "category": "reja"},
               {"title": "T", "brief": "b", "category": "diagramma", "chart_note": chart_data.fallback_note(language)}]
    parts = [html_slides.shell_rules(theme, language),
             html_slides._user_prompt("Topic", 1, 3, 9, outline, ["idea"], 2, "source", "prefs", "A",
                                      "tarix", shapes=[("cols",), ("cols",), ("cols",)], written=["X"],
                                      language=language),
             html_slides._user_prompt("Topic", 7, 3, 9, outline, [], 1, "", "", "", "hisob", language=language),
             deck_shape.guidance("aniq", language), html_slides.catalogue_text(language),
             html_slides._conclusion_brief(language),
             # Kam matnli taqdimot: qobiq (kompozitsiyalar), slayd so'rovi, rasm talabi.
             deck_compose.shell(language, html_slides.MARKER),
             html_slides._user_prompt("Topic", 3, 3, 9, [dict(o, layout=deck_compose.CATEGORY_LAYOUT.get(o["category"], ""))
                                                        for o in outline] + [{"title": "P", "brief": "b",
                                                        "category": "matn_rasm", "layout": "rasm_fon"}],
                                      ["idea"], 2, "", "", "", "tarix", language=language, volume="kam"),
             prompts.fill(P.KAM["photo"], layout="rasm_chap", brief="b"), P.KAM["photo_brief"], P.PHOTO_BRIEF]
    captured = []
    real_json, real_text = llm_client._call_openrouter, llm_client._call_openrouter_text

    def fake_json(system, user, *a, **k):
        captured.append(system + "\n" + user)
        return {"slides": [], "leads": [], "fan": "umumiy"}

    def fake_text(system, user, *a, **k):
        captured.append(system + "\n" + user)
        return ""
    llm_client._call_openrouter, llm_client._call_openrouter_text = fake_json, fake_text
    try:
        html_slides.plan_outline("Topic about economic growth and forecast calculation", 9, language)
        html_slides.plan_outline("Topic about economic growth and forecast calculation", 9, language, volume="kam")
        long = ('<section class="slide"><div class="head"><h2 class="title">A</h2></div><div class="body">'
                + "<p>" + " ".join(["12"] * 140) + "</p></div></section>")
        for volume in ("kop", "kam"):
            ctx_long = html_slides._Deck("Topic", 5, outline + outline[:2], "umumiy", "", theme, language, 2, "", "", "",
                                         volume)
            html_slides.shorten_long([long] * 5, ctx_long)
        slide = '<section class="slide"><div class="head"><h2 class="title">A</h2></div><div class="body"><p>t</p></div></section>'
        ctx = html_slides._Deck("Topic", 9, outline, "umumiy", "", theme, language, 2, "", "", "")
        html_slides.add_leads([slide] * 5, ctx)
        html_slides.rework_slide(slide, ("cols",), [("cols",), ("list",)], theme, language)
        html_slides._thicken(slide, "sys", theme, language)
        html_slides.fix_slide(slide, ["2 ta element slayddan chiqib ketgan (1920x1080 dan tashqarida yoki manfiy "
                                      "o'rinda): «a», «b» va boshqalar", "1 joyda matn ustiga matn tushgan: «a» bilan «b»"],
                              theme, language)
        html_slides.explain_visual('<section class="slide"><svg></svg></section>', theme, language)
        html_slides._plain_slide("Topic", "brief", 3, 9, language)
        chart_data.research("Topic", "Title", "brief", "halqa", language)
        deck = {"topic": "Topic", "language": language, "pages": [slide] * 4,
                "outline": [{"title": f"S{i}", "brief": "b", "category": "kartalar"} for i in range(4)]}
        slide_edit.plan_edit(deck, 2, "make it a donut chart")
        slide_edit._write(dict(deck, volume="kam"), 2, {"category": "matn_rasm", "title": "T", "brief": "b"},
                          "add a photo")
    finally:
        llm_client._call_openrouter, llm_client._call_openrouter_text = real_json, real_text
    data = {"kind": "bar", "labels": ["2020", "2021"], "series": [("", [1.0, 2.0])], "unit": "%", "xlabel": "",
            "source": "World Bank", "approx": True, "forecast": True, "label": "Source:", "lang": language}
    E = P.EDIT
    parts += captured + [chart_data.note_for(data, language), prompts.fill(E["request"], instruction="X"),
                         prompts.fill(E["redo"], n=3, total=9, category="kartalar", note=P.CATEGORIES["kartalar"]),
                         prompts.fill(E["neighbours"], previous="A", next="B"), E["photo"], E["chart_retry"]]
    with prompts.use(language):
        parts.append(llm_client._with_today("x"))
    return "\n".join(parts), captured


# O'zbekcha so'zlar (texnik kalitlar — kategoriya, oila nomi, sinf nomi, JSON kaliti — olib tashlangandan keyin).
UZBEK = re.compile(r"(?<![\w-])(va|uchun|bilan|slayd\w*|mavzu\w*|yoz\w*|kerak|emas|faqat|yoki|bo'l\w*|o'z\w*|"
                   r"matn|rasm|reja|qator\w*|ham|har|bir|ta|joyda|tashqarida|boshqalar|sarlavha\w*|"
                   r"taqdimot\w*|diagramma\w*|kartochka\w*|ko'rsatkich\w*)(?![\w-])", re.IGNORECASE)
TECHNICAL = re.compile(
    r"`[^`]*`|<[^>]+>|\{[^{}]*\}|\[[^\]]*\]|'[a-z_]+'|data-[a-z-]+=\"[^\"]*\"|\b(" + "|".join(
        list(html_slides.CATEGORY_KEYS) + list(deck_shape.FAMILY_KEYS)
        + list(deck_compose.LAYOUTS)
        + ["halqa", "ustunli", "chiziqli", "chart_kind", "ikon", "rasm-matn", "par-col", "misol", "fan",
           "kpi", "lead", "note", "calc", "steps", "timeline", "split", "cols", "list", "quote", "chart", "table",
           "formula", "ikon-dot", "ikon-row"]) + r")\b")


def leftovers(text):
    cleaned = TECHNICAL.sub(" ", text.replace(html_slides.icon_list(), " "))
    return sorted(set(m.group(0).lower() for m in UZBEK.finditer(cleaned)))


print("\n2) Boshqa tildagi promptlarda o'zbekcha so'z yo'q")
texts = {}
for language in ("ru", "en", "kk"):
    text, captured = everything(language)
    texts[language] = text
    check(f"{language}: modelga ketgan so'rovlar to'liq yig'ildi", len(captured) >= 8, len(captured))
    check(f"{language}: o'zbekcha so'z qolmagan", not leftovers(text), leftovers(text)[:20])
cyr = lambda t: len(re.findall(r"[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]", t))
lat_words = lambda t: re.findall(r"(?<![\w`'\"=/.-])[A-Za-z]{4,}(?![\w`'\"=/.-])",
                                 TECHNICAL.sub(" ", t.replace(html_slides.icon_list(), " ")))
for language in ("ru", "kk"):
    stray = [w for w in lat_words(texts[language])
             if w.lower() not in {"lorem", "ipsum", "json", "html", "latex", "swot", "true", "false", "line", "donut",
                                  "approx", "forecast", "reason", "labels", "series", "name", "values", "unit",
                                  "xlabel", "source", "kind", "slides", "title", "brief", "category", "leads",
                                  "points", "text", "english", "description", "documentary", "photo",
                                  "data", "range", "vars", "dark", "body", "head", "rule", "item", "card", "solid",
                                  "wide", "left", "right", "arrow", "stop", "bead", "when", "what", "slide", "section",
                                  "class", "icon", "abs", "sqrt", "exp", "max", "min", "infty", "frac", "auto",
                                  "big", "style", "script", "width", "height", "margin", "padding", "eurostat",
                                  "oecd", "dot", "cover", "plan", "topic", "world", "bank", "make", "chart",
                                  # sinov kiritmalari (mavzu, istak, g'oya)
                                  "about", "economic", "growth", "calculation", "forecast", "idea", "prefs"}]
    check(f"{language}: lotin yozuvidagi so'z faqat texnik", len(stray) <= 3, sorted(set(stray))[:30])
    check(f"{language}: prompt asosan kirillda", cyr(texts[language]) > 10000, cyr(texts[language]))

print("\n3) Tilga xos joylar")
check("ruscha qobiq ruscha boshlanadi", html_slides.shell_rules(themes.get("ko'k"), "ru").startswith("Ты — автор"))
check("inglizcha qobiq", html_slides.shell_rules(themes.get("ko'k"), "en").startswith("You are the author"))
check("qozoqcha qobiq", html_slides.shell_rules(themes.get("ko'k"), "kk").startswith("Сен презентацияның авторы"))
check("bloklar namunasi ham tilda (sarlavha namunasi)",
      "Заголовок слайда" in html_slides.shell_rules(themes.get("ko'k"), "ru")
      and "Slide title" in html_slides.shell_rules(themes.get("ko'k"), "en")
      and "Слайд тақырыбы" in html_slides.shell_rules(themes.get("ko'k"), "kk"))
check("reja slaydi yorlig'i tilda", "«План презентации»" in html_slides._user_prompt(
    "T", 1, 3, 9, [], [], 2, "", "", "", language="ru"))
with prompts.use("ru"):
    ru_today = llm_client._with_today("x")
with prompts.use("kk"):
    kk_today = llm_client._with_today("x")
check("bugungi sana qoidasi tilda", "СЕГОДНЯ" in ru_today and "БҮГІН" in kk_today and "BUGUN" in llm_client._with_today("x"))
check("diagramma ko'rsatmasi tilda", "ГОТОВАЯ ДИАГРАММА" in chart_data.note_for(
    {"kind": "bar", "labels": ["a", "b"], "series": [("", [1, 2])], "unit": "", "source": "S", "label": "Источник:",
     "lang": "ru"}))
check("brauzer xatolari tilda", "выходят за слайд" in html_slides._localize_problem(
    "2 ta element slayddan chiqib ketgan (1920x1080 dan tashqarida yoki manfiy o'rinda)", prompts.get("ru")))

print("\n4) O'zbekcha promptlar avvalgidek")
uz = html_slides.shell_rules(themes.get("ko'k"), "uz")
check("o'zbekcha qobiq", uz.startswith("Sen taqdimot muallifi") and "haqiqiy va muallifi aniq" in uz
      and "so'zma-so'z" in uz)
check("kirill o'zbekcha: kirill qoidasi", "KIRILL" in html_slides.shell_rules(themes.get("ko'k"), "uz-cyrl"))
check("o'zbekcha slayd so'rovi", "faqat XULOSA" in html_slides._user_prompt("M", 7, 3, 9, [], [], 2, "", "", ""))

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
