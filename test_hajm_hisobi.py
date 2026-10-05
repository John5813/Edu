"""Hajm hisobi: tanlangan son titul/muqova va rejadan KEYINGI varaqlar.

Mustaqil ish, referat va taqdimotda xulosa va adabiyotlar shu songa kiradi,
titul (muqova) va reja varag'i esa qo'shimcha.

    python test_hajm_hisobi.py
"""
import asyncio, os, random, re, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services import ai_service as ai_module, doc_toc
from services.ai_service import AIService, document_word_plan, _target_bounds
from services.document_service import DocumentService

print("1) Slaydlar soni")
ai = AIService.__new__(AIService)
check("asosiy slaydlar = son - 2 (kirish va xulosa hisobda)",
      [ai.main_slide_count(n) for n in (10, 15, 20)] == [8, 13, 18], [ai.main_slide_count(n) for n in (10, 15, 20)])
for n in (10, 15, 20):
    prompt = ai._get_presentation_prompt_uz("Mavzu", n)
    check(f"{n} slayd: so'rovda jami {n + 3} (muqova, reja, rahmat qo'shimcha)", f"jami {n + 3} slayd" in prompt, prompt[:200])
    prompt_ru = ai._get_presentation_prompt_ru("Тема", n)
    prompt_en = ai._get_presentation_prompt_en("Topic", n)
    check(f"{n} slayd: ru/en ham", f"всего {n + 3} слайдов" in prompt_ru and f"total {n + 3} slides" in prompt_en)

def deck(mains):
    slides = [{"layout": "cover", "title": "T"}, {"layout": "plan", "title": "Reja"},
              {"layout": "intro", "title": "Kirish", "content": "x"}]
    slides += [{"layout": "", "title": f"M{i}", "content": "c"} for i in range(mains)]
    slides += [{"layout": "conclusion", "title": "Xulosa", "content": "x"}, {"layout": "thanks", "title": ""}]
    return {"slides": slides}

for n in (10, 15, 20):
    out = ai._normalize_slide_structure(deck(30), n, "uz")["slides"]
    kinds = [s["layout"] for s in out]
    mains = [k for k in kinds if k not in ("cover", "plan", "intro", "conclusion", "thanks", "table")]
    counted = [k for k in kinds if k not in ("cover", "plan", "thanks", "table")]
    check(f"{n} slayd: asosiy {n - 2} ta", len(mains) == n - 2, len(mains))
    check(f"{n} slayd: muqova va rejadan keyingi (kirish + asosiy + xulosa) = {n}", len(counted) == n, len(counted))
    check(f"{n} slayd: zich 'Tahlil jadvali' slaydi qo'shilmaydi", "table" not in kinds, kinds)
    check(f"{n} slayd: muqova birinchi, reja ikkinchi, xulosa va rahmat oxirida",
          kinds[:2] == ["cover", "plan"] and kinds[-2:] == ["conclusion", "thanks"], kinds)

print("\n2) Premium oqim")
from services.premium_presentation import html_slides
seen = {}
orig_plan = html_slides.plan_outline
def fake_plan(topic, count, language, level=2):
    seen["count"] = count
    raise RuntimeError("stop")
html_slides.plan_outline = fake_plan
try:
    html_slides.write_slides("Mavzu", 10, None, "uz")
except RuntimeError:
    pass
html_slides.plan_outline = orig_plan
check("10 slayd so'ralsa premium reja 12 slaydlik (muqova + reja qo'shimcha)", seen.get("count") == 12, seen)

print("\n3) Hujjat hajmi")
WORDS = "iqtisodiy rivojlanish jarayonida muhim ahamiyat kasb etadi chunki zamonaviy texnologiyalar bozor sharoitida samaradorlikni oshiradi va natijada mamlakat taraqqiyoti uchun asos yaratadi".split()
def text(n, seed):
    r = random.Random(seed); out = []
    while len(out) < n:
        sentence = [r.choice(WORDS) for _ in range(r.randint(10, 16))]
        sentence[0] = sentence[0].capitalize(); sentence[-1] += "."
        out += sentence
    return " ".join(out[:n]).rstrip(".") + "."

def mid(span):
    low, high = _target_bounds(span)
    return (low + high) // 2

async def content_pages(kind, words):
    content = {"title": "Sinov", "language": "uz", "author_name": "Aliyev Jasur",
               "sections": [{"title": f"Bo'lim {i}", "content": text(w, i)} for i, w in enumerate(words)],
               "references": [f"Muallif {i}. Kitob {i}. Toshkent: Nashriyot, 2020. 200 b." for i in range(12)]}
    svc = DocumentService.__new__(DocumentService)
    svc.documents_dir = tempfile.mkdtemp(); svc.use_icons = True
    make = svc.create_independent_work if kind == "iw" else svc.create_referat
    path = await make("Sinov", content, extras=None)
    return len(doc_toc._page_lines(path)) - 2          # titul va reja varag'isiz

for kind in ("iw", "referat"):
    for low, high, sections in ((10, 15, 6), (15, 20, 9), (20, 25, 12), (25, 30, 15)):
        plan = document_word_plan(low, high, sections - 2)
        words = [mid(plan["intro"])] + [mid(plan["body"])] * (sections - 2) + [mid(plan["conclusion"])]
        pages = asyncio.run(content_pages(kind, words))
        check(f"{kind} {low}-{high}: titul va rejadan keyin {pages} varaq (maqsad {low}-{high} oralig'ida)",
              low <= pages <= high, pages)
# Model bir oz kam yozsa ham tanlangan eng kam hajmdan tushmasin
for kind in ("iw", "referat"):
    plan = document_word_plan(10, 15, 4)
    words = [int(mid(plan["intro"]) * 0.88)] + [int(mid(plan["body"]) * 0.88)] * 4 + [int(mid(plan["conclusion"]) * 0.88)]
    pages = asyncio.run(content_pages(kind, words))
    check(f"{kind} 10-15: model 12% kam yozsa ham {pages} varaq (>= 10)", pages >= 10, pages)
# Mijoz rejasi: savollar soni hajmni o'zgartirmaydi
for questions in (2, 3, 7):
    plan = document_word_plan(10, 15, questions)
    words = [mid(plan["intro"])] + [mid(plan["body"])] * questions + [mid(plan["conclusion"])]
    pages = asyncio.run(content_pages("iw", words))
    check(f"mijoz rejasi {questions} savol: {pages} varaq (10-15 oralig'ida)", 10 <= pages <= 15, pages)

print("\n4) So'rovdagi matn uzunligi")
prompts = []
async def fake_request(self, messages, **kwargs):
    prompts.append(messages[-1]["content"])
    return text(300, len(prompts))
orig = AIService._make_request
AIService._make_request = fake_request
try:
    plan = document_word_plan(10, 15, 4)
    asyncio.run(ai._generate_section_content("Mavzu", "Asosiy bo'lim", 3, 6, "referat", "uz", word_plan=plan))
    asyncio.run(ai._generate_section_content("Mavzu", "Kirish", 1, 6, "referat", "uz", word_plan=plan))
    asyncio.run(ai._generate_section_content("Mavzu", "Xulosa", 6, 6, "referat", "uz", word_plan=plan))
finally:
    AIService._make_request = orig
check("asosiy bo'lim so'rovida hisoblangan chegara", plan["body"] in prompts[0], (plan, prompts[0][:200]))
check("kirish so'rovida hisoblangan chegara", plan["intro"] in prompts[1], prompts[1][:200])
check("xulosa so'rovida hisoblangan chegara", plan["conclusion"] in prompts[2], prompts[2][:200])

print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
