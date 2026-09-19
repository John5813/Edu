"""Oddiy rejani qo'lda yozish va hajmni to'ldirishni tekshiradi.

Mijoz oddiy usulni tanlaganda unga bobli namuna ko'rsatilmasligi kerak:
oddiy rejada bob yo'q, raqamlangan savollar bor. Savollar soni
mijozning ixtiyorida — ikkitami, o'ntami. Matn hajmi shu songa
bo'linadi va har bo'lim buyurtma qilingan hajm to'lguncha yoziladi.
Bo'limlar bir-biriga mantiqan ulanishi ham shu yerda sinaladi.

    python test_oddiy_reja.py
"""

import asyncio
import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("BOT_TOKEN", "test")

from services import ai_service as ai  # noqa: E402
from services import course_work as cw  # noqa: E402

import bot.handlers.documents as handlers  # noqa: E402

FAILS = []


def check(name, condition, detail=""):
    print(f"  ok   {name}" if condition else f"  XATO {name} — {detail}")
    if not condition:
        FAILS.append(name)


def check_prompt():
    print("\n1) Qo'lda yozish namunasi")
    for language in ("uz", "ru", "en"):
        text = handlers._simple_plan_prompt(language)
        check(f"«{language}» namunasida bob yo'q",
              not any(word in text.upper()
                      for word in ("BOB", "ГЛАВА", "CHAPTER")), text[:80])
        check(f"«{language}» namunasi raqamlangan",
              "1. " in text and "2. " in text, text[:80])
        check(f"«{language}» da 1.1 ko'rinish yo'q", "1.1" not in text)


def check_parse():
    print("\n2) Qo'lda yozilgan savollarni o'qish")
    plain = handlers._parse_manual_questions(
        "1. Mehnat bozorining mohiyati\n"
        "2. Bandlikni ta'minlash yo'llari\n"
        "3. Xorijiy tajriba")
    check("uchta savol o'qildi", len(plain) == 3, str(plain))
    check("raqam sarlavhada qolmadi",
          not any(item[0].isdigit() for item in plain), str(plain))

    wrapped = handlers._parse_manual_questions(
        "1. Aholi bandligini ta'minlash va ijtimoiy himoyaning\n"
        "nazariy asoslari\n"
        "2. Bugungi holat tahlili")
    check("ikki qatorga bo'lingan savol bitta qoldi",
          len(wrapped) == 2, str(wrapped))
    check("davomi qo'shildi", wrapped[0].endswith("nazariy asoslari"),
          wrapped[0])

    check("tire bilan yozilgani ham o'qiladi",
          len(handlers._parse_manual_questions("- Birinchi\n- Ikkinchi")) == 2)
    check("raqamsiz yozilgani ham o'qiladi",
          len(handlers._parse_manual_questions("Birinchi savol")) == 1)

    many = handlers._parse_manual_questions(
        "\n".join(f"{i}. {i}-savol" for i in range(1, 15)))
    check("o'ntadan ortig'i kesiladi", len(many) == 10, str(len(many)))
    check("ikkitasi ham qabul qilinadi",
          len(handlers._parse_manual_questions("1. Bir\n2. Ikki")) == 2)

    print("\n3) Mijozga ko'rsatiladigan reja")
    shown = handlers._format_questions(["Birinchi savol", "Ikkinchi savol"], "uz")
    check("savollar raqamlangan", "<b>1.</b>" in shown and "<b>2.</b>" in shown)
    check("ko'rsatilganda bob yo'q", "BOB" not in shown.upper(), shown[:80])


def check_word_split():
    print("\n4) Hajm savollar soniga bo'linadi")
    two = ai._subsection_word_target(2, 20, 25)
    ten = ai._subsection_word_target(10, 20, 25)
    low_two, _ = ai._target_bounds(two)
    low_ten, _ = ai._target_bounds(ten)
    check("ikkita savolda bo'lim uzun", low_two > low_ten * 3,
          f"{two} / {ten}")
    check("o'nta savolda ham bo'sh qolmaydi", low_ten >= 180, ten)
    check("chegara to'g'ri o'qiladi", ai._target_bounds("380-440") == (380, 440))
    check("bitta son ham o'qiladi", ai._target_bounds("500") == (500, 500))


class _Recorder:
    """So'rovlarni yozib boradigan soxta model."""

    def __init__(self, words: int):
        self.words = words
        self.prompts = []

    async def __call__(self, messages, max_tokens=None, temperature=None, **kw):
        self.prompts.append(messages[-1]["content"])
        return "Gap. " * self.words


async def check_volume():
    print("\n5) Hajm to'lguncha matn olinadi")
    service = ai.AIService()

    # Model har safar juda qisqa javob beradi — hajm to'lmaguncha
    # davomi so'ralishi kerak.
    short = _Recorder(30)
    service._make_request = short
    text = await service._generate_subsection_content(
        "Mavzu", "Bob", "Bo'lim", "uz", "600-700")
    check("qisqa javobda davomi so'raladi", len(short.prompts) > 1,
          f"{len(short.prompts)} ta so'rov")
    check("so'rovlar cheksiz emas",
          len(short.prompts) <= ai._MAX_SUBSECTION_REQUESTS,
          f"{len(short.prompts)} ta so'rov")
    check("matn qo'shilib boradi", ai._word_count(text) > 30, str(ai._word_count(text)))

    # Model so'ralganini to'liq yozsa — ortiqcha so'rov bo'lmaydi.
    full = _Recorder(700)
    service._make_request = full
    await service._generate_subsection_content(
        "Mavzu", "Bob", "Bo'lim", "uz", "600-700")
    check("hajm to'lsa qo'shimcha so'rov yo'q", len(full.prompts) == 1,
          f"{len(full.prompts)} ta so'rov")

    # Uzun bo'lim bo'laklarga bo'linadi.
    chunked = _Recorder(1100)
    service._make_request = chunked
    await service._generate_subsection_content(
        "Mavzu", "Bob", "Bo'lim", "uz", "2200-2400")
    check("uzun bo'lim bo'laklab yoziladi", len(chunked.prompts) >= 2,
          f"{len(chunked.prompts)} ta so'rov")


def check_flow():
    print("\n6) Bo'limlar orasidagi mantiqiy bog'liqlik")
    service = ai.AIService()
    rule = service._flow_rule(
        {"plan": ["Birinchi savol", "Ikkinchi savol", "Uchinchi savol"],
         "before": "Birinchi savol", "after": "Uchinchi savol",
         "tail": "Oldingi bo'lim shu gap bilan tugadi."}, "uz")
    check("butun reja ko'rsatiladi", "Uchinchi savol" in rule, rule[:80])
    check("oldingi bo'lim aytiladi", "Oldingi bo'lim" in rule)
    check("keyingi bo'lim aytiladi", "Keyingi bo'lim" in rule)
    check("oldingi matnning oxiri beriladi",
          "shu gap bilan tugadi" in rule, rule[-80:])
    check("bo'sh bo'lsa qoida ham bo'sh", service._flow_rule(None, "uz") == "")

    flow = ai._plan_flow(
        [{"title": "I bob", "subsections": ["1.1 mavzu", "1.2 mavzu"]},
         {"title": "II bob", "subsections": ["2.1 mavzu", "2.2 mavzu"]}],
        1, 0, "oldingi matn")
    check("murakkab rejada o'rin topiladi",
          flow["before"] == "1.2 mavzu" and flow["after"] == "2.2 mavzu",
          str(flow))
    check("butun reja tekis ro'yxatga yoyildi", len(flow["plan"]) == 4,
          str(flow["plan"]))


async def check_generation():
    print("\n7) Ikkitadan o'ntagacha savol")
    service = ai.AIService()
    recorder = _Recorder(400)
    service._make_request = recorder
    service._generate_course_intro = lambda *a, **k: _done("Kirish matni.")
    service._generate_intro_points = lambda *a, **k: _done({"goal": "Maqsad."})
    service._generate_course_conclusion = lambda *a, **k: _done("Xulosa.")
    service._generate_references = lambda *a, **k: _done(["Manba"])
    service.generate_table_data = lambda *a, **k: _done({})
    service.add_uzbek_opening = lambda *a, **k: _done(None)

    for count in (2, 10):
        plan = [{"title": f"{i}-savol", "subsections": []}
                for i in range(1, count + 1)]
        content = {"title": "Mavzu", "chapters": [], "sections": [],
                   "introduction": "", "intro_points": {}, "conclusion": "",
                   "references": []}
        recorder.prompts.clear()
        result = await service._simple_course_work(
            content, "Mavzu", "uz", 20, 25, plan)
        check(f"{count} ta savol saqlandi",
              len(result["sections"]) == count, str(len(result["sections"])))
        check(f"{count} ta savolda matn bor",
              all(s["content"].strip() for s in result["sections"]))
        joined = " ".join(recorder.prompts)
        check(f"{count} ta savolda reja modelga beriladi",
              "Ishning butun rejasi" in joined, joined[:80])

    check("tarkib jumlasida savol soni haqiqiy",
          "10 ta savol" in cw.structure_sentence("uz", cw.SIMPLE, 10))


def _done(value):
    future = asyncio.get_event_loop().create_future()
    future.set_result(value)
    return future


async def main():
    check_prompt()
    check_parse()
    check_word_split()
    await check_volume()
    check_flow()
    await check_generation()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} ta tekshiruv o'tmadi: {', '.join(FAILS[:5])}")
        return 1
    print("✅ Oddiy reja qo'lda ham yoziladi, hajm har holda to'ladi.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
