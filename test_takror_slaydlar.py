"""Bir xil shakldagi slaydlar: aniqlanadi va boshqa blok bilan qayta yozdiriladi.

    python test_takror_slaydlar.py
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import html_slides as hs, llm_client, themes
TH = themes.get("ko'k")

def slide(title, body):
    return (f'<section class="slide"><div class="head"><h2 class="title">{title}</h2><div class="rule"></div></div>'
            f'<div class="body">{body}</div></section>')

LIST_IMG = ('<div class="split"><div class="list"><div class="item">Virus genetik materiali RNK dan iborat</div>'
            '<div class="item">Replikatsiya hujayra ichida ketadi</div></div>'
            '<div class="rasm" data-prompt="virus"><p class="rasm-matn">Qo\'shimcha matn.</p></div></div>')
CARDS = ('<div class="cols cols-2"><div class="card"><div class="card-title">A</div><div class="card-note">izoh bir</div></div>'
         '<div class="card"><div class="card-title">B</div><div class="card-note">izoh ikki</div></div></div>')
STEPS = ('<div class="steps"><div class="step"><div class="step-title">Kirish</div><div class="step-text">hujayraga kiradi</div></div></div>')
PLAIN = '<div class="list"><div class="item">Yakuniy xulosa matni birinchi</div></div>'

cover = slide("Muqova", '<div class="lead">Mavzu</div>')
deck = [cover, slide("Ta'rif", LIST_IMG), slide("Tasnif", LIST_IMG), slide("Jarayon", STEPS),
        slide("Ebola", LIST_IMG), slide("Xulosa", PLAIN)]

check("shakl imzosi: ro'yxat + rasm", hs.shape_signature(deck[1]) == ("list", "rasm", "split"), hs.shape_signature(deck[1]))
flag = hs.repeated_slides(deck)
check("ketma-ket takror (3-slayd) va uchinchi marta takror (5-slayd) topiladi", flag == [2, 4], flag)
check("muqova va yakun hech qachon belgilanmaydi", 0 not in flag and 5 not in flag)
check("xilma-xil taqdimotda takror yo'q", hs.repeated_slides([cover, slide("a", LIST_IMG), slide("b", CARDS), slide("c", STEPS), slide("d", LIST_IMG), slide("e", PLAIN)]) == [])

calls = []
def fake_ok(system, user, **kw):
    calls.append(user)
    # Xuddi shu fikrlar, kartochkalarda.
    return slide("Tasnif", '<div class="cols cols-2"><div class="card"><div class="card-title">Genetik material</div>'
                 '<div class="card-note">Virus genetik materiali RNK dan iborat</div></div>'
                 '<div class="card"><div class="card-title">Replikatsiya</div>'
                 '<div class="card-note">Replikatsiya hujayra ichida ketadi</div></div></div>')

def fake_same(system, user, **kw):
    calls.append(user)
    return slide("Tasnif", LIST_IMG)

original = llm_client._call_openrouter_text
try:
    llm_client._call_openrouter_text = fake_ok
    out = hs.diversify(deck, TH)
    check("takror slayd boshqa blok bilan almashdi", hs.shape_signature(out[2]) == ("cols",), hs.shape_signature(out[2]))
    check("muqova, yakun va boshqa slaydlarga tegilmadi", out[0] == deck[0] and out[3] == deck[3] and out[5] == deck[5])
    check("so'rovda ishlatilgan shakllar va 'qaytarmang' aytilgan", any("QAYTARMANG" in c and "ro'yxat" in c for c in calls))
    check("qayta yozishlar soni cheklangan", len(calls) <= hs.MAX_REWORKS, len(calls))

    calls.clear()
    llm_client._call_openrouter_text = fake_same
    out = hs.diversify(deck, TH)
    check("model baribir bir xil shakl qaytarsa — slayd o'zgarmaydi", out == deck)

    llm_client._call_openrouter_text = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("tarmoq"))
    check("model xato qilsa — taqdimot buzilmaydi", hs.diversify(deck, TH) == deck)

    llm_client._call_openrouter_text = lambda *a, **k: slide("Boshqa", CARDS.replace("izoh bir", "butunlay boshqa matn").replace("izoh ikki", "yana boshqa").replace(">A<", ">Q<").replace(">B<", ">W<")).replace("Boshqa", "Mutlaqo boshqa mavzu haqida")
    kept = hs.rework_slide(deck[2], hs.shape_signature(deck[2]), [hs.shape_signature(deck[3])], TH)
    check("mazmuni yo'qolgan qayta yozish rad etiladi", kept == deck[2])
finally:
    llm_client._call_openrouter_text = original

# ── Oldingi bo'laklarda ishlatilgan shakllar keyingi so'rovga aytiladi
prompts = []
def fake_chunk(system, user, **kw):
    prompts.append(user)
    pages = [slide(f"Slayd {len(prompts)}.{i}", LIST_IMG) for i in range(3)]
    return f"\n{hs.MARKER}\n".join(pages)
def fake_plan(system, user, **kw):
    return {"slides": [{"brief": str(i), "category": "kartalar"} for i in range(1, 7)]}
orig_json, orig_reworks = llm_client._call_openrouter, hs.MAX_REWORKS
try:
    llm_client._call_openrouter_text, llm_client._call_openrouter = fake_chunk, fake_plan
    hs.MAX_REWORKS = 0
    hs.write_slides("Mavzu", 6, TH, "uz")
finally:
    llm_client._call_openrouter_text, llm_client._call_openrouter, hs.MAX_REWORKS = original, orig_json, orig_reworks
check("birinchi bo'lakda shakllar ro'yxati yo'q (hali slayd yo'q)", "HARD CONSTRAINT" not in prompts[0])
check("ikkinchi bo'lakka ishlatilgan shakllar va qat'iy taqiq (inglizcha) berildi",
      "HARD CONSTRAINT" in prompts[1] and "list+rasm+split" in prompts[1] and "FORBIDDEN" in prompts[1], prompts[1][-700:])

# ── Reja (outline): "reja" faqat 2-slayd, oxirgi slayd — xulosa, chala reja qayta so'raladi
def plan_with(items, calls):
    def fake(system, user, **kw):
        calls.append(user)
        return {"fan": "tibbiyot", "slides": items(len(calls))}
    orig = llm_client._call_openrouter
    llm_client._call_openrouter = fake
    try:
        return hs.plan_outline("Endoskopik xirurgiya", 12, "uz")["slides"]
    finally:
        llm_client._call_openrouter = orig

full = [{"brief": f"b{i}", "category": "matn_rasm"} for i in range(1, 13)]
full[1]["category"] = "reja"; full[10]["category"] = "reja"; full[11]["brief"] = "Endoskopik xirurgiya ta'rifi"
calls = []
outline = plan_with(lambda n: full, calls)
check("'reja' faqat 2-slaydda qoladi", [i + 1 for i, o in enumerate(outline) if o["category"] == "reja"] == [2], [o["category"] for o in outline])
check("oxirgi slayd — yakun va xulosa mazmuni (ta'rif emas)", outline[-1]["category"] == "yakun" and "Xulosa" in outline[-1]["brief"], outline[-1])
check("xulosa so'zli reja o'zgarishsiz", plan_with(lambda n: [dict(o, brief="Xulosa va natijalar") if i == 11 else o for i, o in enumerate(full)], [])[-1]["brief"] == "Xulosa va natijalar")

calls = []
outline = plan_with(lambda n: full[:8] if n == 1 else full, calls)
check("chala reja bir marta qayta so'raladi", len(calls) == 2 and len(outline) == 12, len(calls))
calls = []
outline = plan_with(lambda n: full[:8], calls)
check("qayta ham chala bo'lsa — yetmagan o'rinlar oddiy mavzu nomi bilan emas, 'yangi jihat' topshirig'i bilan to'ldiriladi",
      len(calls) == 2 and "YANGI" in outline[9]["brief"] and outline[9]["brief"] != "Endoskopik xirurgiya", outline[9])
check("so'nggi bo'lak so'rovida 'faqat XULOSA' aytilgan", "faqat XULOSA" in hs._user_prompt("M", 10, 3, 12, outline, [], 2, "", "", ""))
check("oxirgi bo'lak bo'lmasa bu qoida yo'q", "faqat XULOSA" not in hs._user_prompt("M", 4, 3, 12, outline, [], 2, "", "", ""))

check("reja promptida takror cheklovi bor", "2 martadan ko'p takrorlanmasin" in open("services/premium_presentation/html_slides.py", encoding="utf-8").read())

print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
