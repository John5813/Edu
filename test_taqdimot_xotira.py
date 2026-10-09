"""Taqdimot xotirasi: AI taqdimot tugaguncha oldin yozganlarini chatdagidek eslab turadi.

- 1-bo'lak tarixsiz; keyingi har bo'lak oldingi slaydlarni suhbat tarixi sifatida oladi (foydalanuvchi:
  «N-slayddan boshlab ...» → assistent: o'sha slaydlar), so'rovda «davomi qilib yozing» yo'riqnomasi bor;
- qayta yozish (qisqartirish, tuzatish) butun taqdimotni ko'radi, qayta yozilgan slayd tarixda yangilanadi;
- taqdimot tayyor bo'lgach xotira o'chadi; ikki buyurtmaning xotirasi aralashmaydi;
- tarix katta bo'lsa eng eski bo'laklar qisqa matnga aylanadi (so'rov haddan oshmaydi);
- tarix model so'roviga system va joriy so'rov orasida ketadi;
- tarixiy/gumanitar mavzuda diagramma kvotasi majburlanmaydi (YaIM diagrammasi sovet davri va mustaqillik
  orasiga tushib, xronologiyani uzgan edi), reja voqealar ketma-ketligida so'raladi.

    python test_taqdimot_xotira.py
"""
import contextvars, os, re, sys, threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import (deck_logic, deck_memory, html_slides, llm_client, pipeline, prompts,
                                           themes)

CATS = ["muqova", "reja", "kartalar", "ikki_ustun", "jarayon", "kartalar", "qiyoslash", "tuzilma", "kartalar",
        "ikki_ustun", "jarayon", "yakun"]
CALLS = []
PLAN_PROMPTS = []


def slide(number, extra=""):
    return (f'<section class="slide"><div class="head"><h2 class="title">Davr {number}</h2></div>'
            f'<div class="body"><div class="list"><div class="item"><div class="item-text">FAKT-{number}: '
            f'{number}-slayd voqeasi va uning sababi.{extra}</div></div><div class="item"><div class="item-text">'
            f'Natija {number}.</div></div></div></div></section>')


def fake_json(system, user, *a, **k):
    if '"slides"' in user:
        PLAN_PROMPTS.append(user)
        return {"fan": "tarix", "slides": [{"title": f"Davr {i + 1}", "brief": f"mazmun {i + 1}", "category": c}
                                           for i, c in enumerate(CATS)]}
    return {}


def fake_text(system, user, *a, history=None, **k):
    CALLS.append({"user": user, "history": list(history or [])})
    wanted = [int(n) for n in re.findall(r"^\s*→\s*(\d+)\.", user, re.M)]
    out = []
    for number in wanted:
        # 5-slayd ataylab juda uzun: qisqartirish so'raladi.
        if number == 5 and "JUDA UZUN" not in user:
            out.append(slide(number, " uzoq tafsilot" * 70))
        else:
            out.append(slide(number, " QISQA" if "JUDA UZUN" in user else ""))
    return "\n===SLIDE_BREAK===\n".join(out)


def run(topic, count=10, language="uz"):
    CALLS.clear(); PLAN_PROMPTS.clear()
    real = llm_client._call_openrouter, llm_client._call_openrouter_text
    llm_client._call_openrouter, llm_client._call_openrouter_text = fake_json, fake_text
    try:
        return html_slides.write_slides(topic, count, themes.for_deck(topic, "", "kop"), language)
    finally:
        llm_client._call_openrouter, llm_client._call_openrouter_text = real


def chunk_calls():
    return [c for c in CALLS if "JUDA UZUN" not in c["user"] and re.search(r"^\s*→", c["user"], re.M)]


print("1) Har bo'lak oldingi slaydlarni suhbat tarixi sifatida ko'radi")
pages = run("Mustaqillik g'oyalarining tarixiy asoslari")
chunks = chunk_calls()
check("12 slayd 4 bo'lakda yozildi", len(pages) == 12 and len(chunks) >= 4, (len(pages), len(chunks)))
check("1-bo'lak tarixsiz", chunks[0]["history"] == [], chunks[0]["history"][:1])
second, fourth = chunks[1]["history"], chunks[3]["history"]
check("2-bo'lak: 1-3 slaydlar tarixda (foydalanuvchi → assistent)",
      [m["role"] for m in second] == ["user", "assistant"] and "FAKT-3" in second[1]["content"]
      and "Hozir 1-slayddan boshlab 3 ta slayd kerak." == second[0]["content"], second)
told = "\n".join(m["content"] for m in fourth)
check("4-bo'lak: 1-9 slaydlarning hammasi tarixda", all(f"FAKT-{n}:" in told for n in range(1, 10)), told[:300])
check("tarixda 10-12 slaydlar yo'q (hali yozilmagan)", "FAKT-10:" not in told)
check("so'rovda «davomi qilib yozing» yo'riqnomasi (tarix bo'lsa)",
      prompts.get("uz").USER["memory"] in chunks[1]["user"] and prompts.get("uz").USER["memory"] not in chunks[0]["user"])

print("2) Qayta yozish butun taqdimotni ko'radi va tarixni yangilaydi")
longs = [c for c in CALLS if "JUDA UZUN" in c["user"]]
check("uzun 5-slayd qisqartirish uchun qayta so'raldi", longs, len(CALLS))
whole = "\n".join(m["content"] for m in longs[0]["history"]) if longs else ""
check("qisqartirishda butun taqdimot (1-12) tarixda", all(f"FAKT-{n}:" in whole for n in range(1, 13)), whole[:200])
after = CALLS[CALLS.index(longs[0]) + 1:] if longs else []
later = "\n".join(m["content"] for c in after for m in c["history"])
check("keyingi so'rovlarda 5-slaydning yangi (qisqa) varianti, eskisi yo'q",
      not after or ("QISQA" in later and "uzoq tafsilot" not in later), later[:200])
check("taqdimotda ham qisqa variant", "uzoq tafsilot" not in "".join(pages))

print("3) Taqdimot tayyor bo'lgach xotira o'chadi, buyurtmalar aralashmaydi")
check("write_slides tugagach xotira yo'q", deck_memory.current() is None)
seen = {}


def order(name):
    with deck_memory.session():
        deck_memory.remember(1, [slide(1, f" {name}")], "1")
        threading.Event().wait(0.05)
        seen[name] = "\n".join(m["content"] for m in deck_memory.history())

threads = [threading.Thread(target=contextvars.copy_context().run, args=(order, n)) for n in ("ALFA", "BETA")]
for t in threads: t.start()
for t in threads: t.join()
check("ikki parallel buyurtma: har biri faqat o'zinikini ko'radi",
      "ALFA" in seen["ALFA"] and "BETA" not in seen["ALFA"] and "BETA" in seen["BETA"] and "ALFA" not in seen["BETA"],
      seen)
with deck_memory.session() as outer:
    with deck_memory.session() as inner:
        same = inner is outer
check("ichma-ich sessiya tashqi xotirani davom ettiradi (pipeline → write_slides)", same)
check("pipeline xotirani butun yaratish davomida ushlab turadi",
      "deck_memory.session()" in open("services/premium_presentation/pipeline.py").read())

print("4) Katta tarix: eski bo'laklar qisqa matnga aylanadi")
memory = deck_memory.Memory()
for start in range(1, 31, 3):
    memory.remember(start, [slide(n, " batafsil" * 150) + "<svg><path d='" + "M0 0 " * 200 + "'/></svg>"
                            for n in range(start, start + 3)], f"{start}")
messages = memory.messages()
size = sum(len(m["content"]) for m in messages)
check("tarix hajmi chegarada", size <= deck_memory.MAX_CHARS + 3 * deck_memory.PLAIN_LIMIT, size)
check("eng eski bo'lak — qisqa matn, mazmuni saqlangan", "<section" not in messages[1]["content"]
      and "FAKT-1:" in messages[1]["content"] and "Davr 1" in messages[1]["content"], messages[1]["content"][:200])
check("eng yangi bo'lak — to'liq HTML", "<section" in messages[-1]["content"])
check("ikonka chizmasi tarixga kirmaydi", "M0 0 M0 0" not in "".join(m["content"] for m in messages))

print("5) Tarix model so'rovida system va joriy so'rov orasida")
sent = {}
real_request = llm_client._request
llm_client._request = lambda kind, payload, **k: sent.update(payload) or {
    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
try:
    llm_client._call_openrouter_text("SYS", "HOZIR", history=[{"role": "user", "content": "A"},
                                                           {"role": "assistant", "content": "B"}])
finally:
    llm_client._request = real_request
check("xabarlar tartibi: system, user A, assistant B, user HOZIR",
      [(m["role"], m["content"][:6]) for m in sent["messages"]][1:] == [("user", "A"), ("assistant", "B"), ("user", "HOZIR")]
      and sent["messages"][0]["role"] == "system", sent.get("messages"))

print("6) Ruscha taqdimotda yo'riqnoma ruscha")
run("История Казахского ханства", 6, "ru")
ru_chunks = chunk_calls()
check("ruscha: tarixli so'rovda ruscha yo'riqnoma", any(prompts.get("ru").USER["memory"] in c["user"] for c in ru_chunks[1:])
      and not any(prompts.get("uz").USER["memory"] in c["user"] for c in ru_chunks))
check("ruscha: tarixdagi navbat ham ruscha", any("слайд" in c["history"][0]["content"] for c in ru_chunks if c["history"]))

print("7) Tarixiy va gumanitar mavzuda diagramma majburlanmaydi")
check("kvota: tarix va gumanitar — 0, boshqalar avvalgidek",
      [deck_logic.chart_quota(12, f) for f in ("tarix", "gumanitar", "ijtimoiy", "")] == [0, 0, 2, 2])
run("O'zbekistonda mustaqillik g'oyalarining tarixiy asoslari")
check("reja so'rovida diagramma kvotasi yo'q, xronologik tartib so'ralgan",
      PLAN_PROMPTS and "kamida" not in PLAN_PROMPTS[0] and prompts.get("uz").PLAN["narrative"] in PLAN_PROMPTS[0],
      PLAN_PROMPTS[:1])
outline = [{"title": f"T{i}", "brief": "b", "category": c} for i, c in enumerate(CATS)]
check("tarixiy rejaga diagramma qo'shilmaydi",
      not any(o["category"] == "diagramma" for o in html_slides.ensure_charts([dict(o) for o in outline], "uz", "tarix")))
check("iqtisodiy rejaga diagramma avvalgidek qo'shiladi",
      sum(o["category"] == "diagramma" for o in html_slides.ensure_charts([dict(o) for o in outline], "uz", "ijtimoiy")) == 2)
PLAN_PROMPTS.clear()
real = llm_client._call_openrouter
llm_client._call_openrouter = fake_json
try:
    html_slides.plan_outline("Inflyatsiya va uning oqibatlari", 12, "uz")
finally:
    llm_client._call_openrouter = real
check("iqtisodiy mavzu rejasida diagramma qoidasi bor", PLAN_PROMPTS and "kamida 2 ta" in PLAN_PROMPTS[0])

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
