"""Kurs ishi rejasining tuzilishini tekshiradi.

Sinaladigan narsalar:

1. Hujjatda "bo'lim" emas, "bob" yoziladi.
2. Kurs ishi qaysi hajmda bo'lmasin uch bobdan iborat, har bobda odatda
   ikkita mavzu bo'ladi va matn hajmi bitta so'rovga sig'adi.
3. Qo'lda yozilgan reja qanday yozilgan bo'lsa shundayligicha qoladi:
   bir bobga ikkita, boshqasiga uchta mavzu yozilsa ham o'zgartirilmaydi,
   hajm esa shu songa qarab hisoblanadi.
4. O'zbekiston mavzularida boblar ketma-ketligi qat'iy: konseptual —
   bugungi holat — istiqbollar.

Ishga tushirish:

    python test_kurs_ishi_reja.py
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("BOT_TOKEN", "test")

from bot.handlers.documents import _parse_manual_plan  # noqa: E402
from services import uzbekistan  # noqa: E402
from services.ai_service import (  # noqa: E402
    _MAX_WORDS_PER_SUBSECTION,
    _WORDS_PER_REQUEST,
    _subsection_word_target,
    _subsections_per_chapter,
    get_ai_service,
)
from utils.ai_text import token_budget  # noqa: E402

FAILS = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  XATO {name} — {detail}")
        FAILS.append(name)


def check_chapter_word():
    print("\n1) Hujjatdagi atama")
    from services.document_service import DocumentService

    service = DocumentService()
    for name, reader in (("kurs ishi", service._get_course_work_texts),
                         ("bitiruv ishi", service._get_graduation_work_texts),
                         ("dissertatsiya", service._get_dissertation_texts)):
        check(f"{name} — BOB", reader("uz")["chapter"] == "BOB", reader("uz")["chapter"])


def check_volume():
    print("\n2) Bob va mavzular soni")
    sizes = ((15, 20), (20, 25), (25, 30), (30, 35), (40, 50), (50, 60))
    for low, high in sizes:
        per = _subsections_per_chapter(low, high)
        total = 3 * per
        target = _subsection_word_target(total, low, high)
        words = int(target.split("-")[-1])
        check(f"{low}-{high} varaq: bobga {per} ta mavzu", per == 2, str(per))
        check(f"{low}-{high} varaq: bitta mavzu {target} so'z",
              words <= _MAX_WORDS_PER_SUBSECTION, target)

        # Uzun bo'lim bir necha so'rovga bo'linadi; har so'rov token
        # chegarasidan pastda qolishi kerak, aks holda matn qirqiladi.
        parts = min(-(-words // _WORDS_PER_REQUEST), 3)
        chunk = f"{int(words // parts * 0.9)}-{words // parts}"
        budget = token_budget(chunk, "uz")
        check(f"{low}-{high} varaq: {parts} ta so'rov, har biri sig'adi",
              budget < 8000, f"{chunk} -> {budget}")

    every = [_subsections_per_chapter(lo, hi) for lo, hi in sizes]
    check("hamma hajmda bobga ikkita mavzu", every == [2] * len(sizes), str(every))


def check_manual_plan():
    print("\n3) Qo'lda yozilgan reja")

    # Mijoz yozgani: rim raqami o'rniga "ll", nuqtasiz, kichik harf bilan.
    loose = _parse_manual_plan(
        "bob mustaqillik\n1.1 erkinlik\n1.2 tinchlik\n"
        "ll bob qadriat\n2.1 milliy qadriyatlar\n2.2 zamonaviy qadriyatlar\n2.3 tarbiya\n"
        "lll bob kelajak\n3.1 yoshlar\n3.2 taraqqiyot"
    )
    check("uchta bob o'qildi", len(loose) == 3, str(len(loose)))
    check("bob nomlari to'g'ri",
          [c["title"] for c in loose] == ["mustaqillik", "qadriat", "kelajak"],
          str([c["title"] for c in loose]))
    counts = [len(c["subsections"]) for c in loose]
    check("mavzular soni o'zgartirilmadi", counts == [2, 3, 2], str(counts))

    formal = _parse_manual_plan(
        "I BOB. MILLIY BOYLIK TUSHUNCHASI\n  1.1. Tushunchasi va tasnifi\n"
        "  1.2. Baholash usullari\n\nII BOB. TAHLIL\n  2.1. Hozirgi holat\n  2.2. Muammolar"
    )
    check("rasmiy formatda bob nomi butun",
          formal[0]["title"] == "MILLIY BOYLIK TUSHUNCHASI", formal[0]["title"])

    ru = _parse_manual_plan(
        "ГЛАВА I. Теоретические основы\n1.1 Понятие\n1.2 Классификация\n"
        "ГЛАВА II. Анализ\n2.1 Состояние\n2.2 Проблемы"
    )
    check("ruscha rejada raqam sarlavhaga qo'shilmadi",
          ru[0]["title"] == "Теоретические основы", ru[0]["title"])

    en = _parse_manual_plan(
        "CHAPTER 1 — Foundations\n1.1 Concepts\n1.2 Methods\n"
        "CHAPTER 2 — Practice\n2.1 Analysis\n2.2 Results"
    )
    check("inglizcha rejada raqam sarlavhaga qo'shilmadi",
          en[0]["title"] == "Foundations", en[0]["title"])

    dashed = _parse_manual_plan(
        "1-bob: Nazariy asoslar\n- Tushuncha\n- Tasnif\n"
        "2-bob: Amaliyot\n- Tahlil\n- Natija\n- Xulosa"
    )
    check("tire bilan yozilgan mavzular o'qildi",
          [len(c["subsections"]) for c in dashed] == [2, 3],
          str([len(c["subsections"]) for c in dashed]))

    # Hajm mavzular soniga qarab hisoblanadi: ikkita mavzu yozgan mijoz
    # uchun har biri uzunroq bo'ladi.
    two = int(_subsection_word_target(6, 20, 25).split("-")[-1])
    three = int(_subsection_word_target(9, 20, 25).split("-")[-1])
    check("kam mavzuda har biri uzunroq", two > three, f"{two} vs {three}")


def check_wrapped_plan():
    """Ikki qatorga bo'lingan sarlavha bitta mavzu bo'lib qolsinmi.

    Mijoz rejani nusxalab tashlaganda uzun sarlavha ikki qatorga
    bo'lingan edi. Har qator alohida mavzu deb olinib, ikkita mavzu
    yozilgan bob beshta mavzuga bo'linib ketgandi.
    """
    print("\n5) Ikki qatorga bo'lingan sarlavhalar")
    pasted = (
        "I BOB. AHOLI BANDLIGINI TA'MINLASH VA IJTIMOIY HIMOYANING\n"
        "NAZARIY ASOSLARI\n"
        " 1.1. Aholi bandligi va ijtimoiy himoya tushunchasi, mazmuni va\n"
        "      asosiy tamoyillari\n"
        " 1.2. Bandlikni ta'minlash va ijtimoiy himoya modellari: jahon\n"
        "      tajribasi\n\n"
        "II BOB. O'ZBEKISTONDA BANDLIK VA IJTIMOIY HIMOYA TIZIMINING\n"
        "HOZIRGI HOLATI\n"
        " 2.1. Mehnat bozori, bandlik va ishsizlik ko'rsatkichlari tahlili\n"
        " 2.2. Ijtimoiy nafaqalar, moddiy yordam va kam ta'minlangan\n"
        "      oilalarni qo'llab-quvvatlash amaliyoti\n\n"
        "III BOB. BANDLIKNI TA'MINLASH VA IJTIMOIY HIMOYANI\n"
        "TAKOMILLASHTIRISH ISTIQBOLLARI\n"
        " 3.1. Tizimdagi muammolar va ularni hal etish yo'llari\n"
        " 3.2. Bandlik va ijtimoiy himoyani rivojlantirish prognozi va\n"
        "      takliflar"
    )
    plan = _parse_manual_plan(pasted)
    counts = [len(c["subsections"]) for c in plan]
    check("uchta bob", len(plan) == 3, str(len(plan)))
    check("har bobda ikkitadan mavzu", counts == [2, 2, 2], str(counts))
    check("bob nomi butun qo'shildi",
          plan[0]["title"].endswith("NAZARIY ASOSLARI"), plan[0]["title"])
    check("mavzu nomi butun qo'shildi",
          plan[0]["subsections"][0].endswith("asosiy tamoyillari"),
          plan[0]["subsections"][0])
    check("ikkinchi mavzu ham butun",
          plan[0]["subsections"][1].endswith("jahon tajribasi"),
          plan[0]["subsections"][1])

    # To'rt bobga uchtadan yozilgan reja ham o'zgarmasin.
    four = _parse_manual_plan("\n".join(
        f"{roman} BOB. {roman}-bob nomi\n" + "\n".join(
            f" {index}.{sub}. {index}.{sub}-mavzu" for sub in (1, 2, 3))
        for index, roman in enumerate(["I", "II", "III", "IV"], 1)
    ))
    check("to'rt bob saqlandi", len(four) == 4, str(len(four)))
    check("har bobda uchtadan",
          [len(c["subsections"]) for c in four] == [3, 3, 3, 3],
          str([len(c["subsections"]) for c in four]))


async def check_plan_review():
    """AI reja tuzilishiga tegmasligi kerak."""
    print("\n6) AI rejani tahrirlashi")
    service = get_ai_service()
    plan = [
        {"title": "nazariy asoslar", "subsections": ["tushuncha", "tasnif"]},
        {"title": "hozirgi holat", "subsections": ["tahlil", "muammolar", "natija"]},
    ]

    async def polite(messages, **kwargs):
        return json.dumps({"chapters": [
            {"title": chapter["title"].capitalize(),
             "subsections": [s.capitalize() for s in chapter["subsections"]]}
            for chapter in plan
        ]}, ensure_ascii=False)

    service._make_request = polite
    fixed = await service.review_manual_plan(plan, "Mavzu", "uz")
    check("boblar soni saqlandi", len(fixed) == 2, str(len(fixed)))
    check("mavzular soni saqlandi",
          [len(c["subsections"]) for c in fixed] == [2, 3],
          str([len(c["subsections"]) for c in fixed]))
    check("imlo tuzatildi", fixed[0]["title"][0].isupper(), fixed[0]["title"])

    # AI bob qo'shib yuborsa — mijoznikida qolsin.
    async def greedy(messages, **kwargs):
        return json.dumps({"chapters": [
            {"title": "Bir", "subsections": ["a", "b"]},
            {"title": "Ikki", "subsections": ["c", "d", "e"]},
            {"title": "Uch", "subsections": ["f", "g"]},
        ]})

    service._make_request = greedy
    kept = await service.review_manual_plan(plan, "Mavzu", "uz")
    check("AI bob qo'shsa mijoznikida qoladi", kept == plan, str(len(kept)))

    # AI mavzu qo'shib yuborsa ham.
    async def padded(messages, **kwargs):
        return json.dumps({"chapters": [
            {"title": "Bir", "subsections": ["a", "b", "c"]},
            {"title": "Ikki", "subsections": ["d", "e", "f"]},
        ]})

    service._make_request = padded
    kept = await service.review_manual_plan(plan, "Mavzu", "uz")
    check("AI mavzu qo'shsa mijoznikida qoladi", kept == plan, str(kept[0]))

    # Javob buzilgan bo'lsa ham reja yo'qolmasin.
    async def broken(messages, **kwargs):
        return "javob JSON emas"

    service._make_request = broken
    kept = await service.review_manual_plan(plan, "Mavzu", "uz")
    check("buzuq javobda reja yo'qolmaydi", kept == plan)


def check_plan_message():
    """Mijozga ko'rsatiladigan matn."""
    print("\n7) Mijozga ko'rsatiladigan reja")
    import bot.handlers.documents as handlers

    text = handlers._format_plan([
        {"title": "Nazariy asoslar", "subsections": ["Tushuncha", "Tasnif"]},
        {"title": "Hozirgi <holat> & tahlil", "subsections": ["Bir", "Ikki"]},
    ], "uz")
    check("bob raqami rim raqamida", "I BOB." in text and "II BOB." in text)
    check("mavzular raqamlangan", "1.1." in text and "2.2." in text, text)
    # Bob nomi katta harfga o'tkazilgandan keyin ekranlanadi.
    check("HTML belgilari ekranlandi", "&lt;HOLAT&gt;" in text and "&amp;" in text, text)
    check("buzilgan HTML yo'q", "&#X27;" not in text)


async def check_long_subsection():
    """Uzun bo'lim bir necha so'rovga bo'linib yozilsinmi.

    Katta hajmda har bobda ikkitadan mavzu qolishi uchun bitta mavzuga
    ikki mingga yaqin so'z tushadi. Bitta so'rovda bunchasi chiqmaydi —
    javob token chegarasiga urilib qirqilardi.
    """
    print("\n8) Uzun bo'limni bo'laklab yozish")
    service = get_ai_service()
    prompts = []
    # Model so'ralgan hajmni to'liq yozadi: shunda so'rovlar soni faqat
    # bo'laklarga bog'liq bo'ladi. Hajm to'lmagan holat alohida —
    # test_oddiy_reja.py da sinaladi.
    words = [1300]

    async def fake(messages, **kwargs):
        prompts.append(messages[-1]["content"])
        return "Birinchi bo'lak matni. " * (words[0] // 3)

    service._make_request = fake

    prompts.clear()
    await service._generate_subsection_content("Mavzu", "Bob", "Kichik", "uz", "560-690")
    check("qisqa bo'lim bitta so'rovda", len(prompts) == 1, str(len(prompts)))
    check("qisqa bo'limda bo'lak qoidasi yo'q",
          "bo'lagi" not in prompts[0])

    prompts.clear()
    text = await service._generate_subsection_content(
        "Mavzu", "Bob", "Kichik", "uz", "1930-2360")
    check("uzun bo'lim ikki so'rovda", len(prompts) == 2, str(len(prompts)))
    check("birinchi bo'lak xulosa qilmaydi",
          "Hali xulosa qilmang" in prompts[0])
    check("ikkinchi bo'lakka avvalgisi berildi",
          "Allaqachon yozilgani" in prompts[1])
    check("matn qo'shib yozildi", len(text.split()) > 50, str(len(text.split())))

    for language, marker in (("ru", "часть"), ("en", "part")):
        prompts.clear()
        await service._generate_subsection_content(
            "Topic", "Chapter", "Sub", language, "1930-2360")
        check(f"{language} tilida ham bo'laklanadi",
              len(prompts) == 2 and marker in prompts[0],
              str(len(prompts)))


async def check_chapter_arc():
    print("\n4) O'zbekiston mavzularida boblar ketma-ketligi")
    service = get_ai_service()

    arc = service._chapter_arc("O'zbekistonda ijtimoiy himoya tizimi", "uz")
    check("konseptual bob aytilgan", "konseptual" in arc, arc[:60])
    check("bugungi holat aytilgan", "bugungi holat" in arc, arc[:60])
    check("istiqbollar aytilgan", "istiqbollar" in arc, arc[:60])
    check("boshqa mavzuda qoida yo'q", service._chapter_arc("Fotosintez", "uz") == "")

    for language in ("ru", "en"):
        text = service._chapter_arc("Uzbekistan tax policy", language)
        check(f"{language} tilida ham qoida bor", bool(text.strip()), text[:40])

    # Ikki qoida bir-biriga zid bo'lmasin.
    uzbek_rule = service._plan_rule("uz", "O'zbekiston iqtisodiyoti")
    other_rule = service._plan_rule("uz", "Fotosintez")
    check("O'zbekiston mavzusida shablon taqiqi olib tashlandi",
          "shablondan" not in uzbek_rule)
    check("boshqa mavzuda shablon taqiqi qoldi", "shablondan" in other_rule)

    captured = {}

    async def fake_request(messages, **kwargs):
        captured["prompt"] = messages[-1]["content"]
        raise RuntimeError("to'xtatildi")

    service._make_request = fake_request
    await service._generate_chapter_titles("O'zbekiston bank tizimi", 3, "uz")
    prompt = captured.get("prompt", "")
    check("bob promptida ketma-ketlik bor", "BOBLAR TUZILISHI" in prompt)
    check("bob promptida zid band yo'q", "shablondan" not in prompt)
    check("promptda 'bob' deyiladi", "ta bob sarlavhasini" in prompt)


async def main():
    check_chapter_word()
    check_volume()
    check_manual_plan()
    check_wrapped_plan()
    await check_plan_review()
    check_plan_message()
    await check_long_subsection()
    await check_chapter_arc()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} ta tekshiruv o'tmadi: {', '.join(FAILS)}")
        return 1
    print("✅ Kurs ishi rejasi talab qilinganidek tuziladi.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
