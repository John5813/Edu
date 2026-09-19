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
import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("BOT_TOKEN", "test")

from bot.handlers.documents import _parse_manual_plan  # noqa: E402
from services import uzbekistan  # noqa: E402
from services.ai_service import (  # noqa: E402
    _MAX_WORDS_PER_SUBSECTION,
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
        check(f"{low}-{high} varaq: bobga {per} ta mavzu",
              2 <= per <= 4, str(per))
        check(f"{low}-{high} varaq: bitta mavzu {target} so'z",
              words <= _MAX_WORDS_PER_SUBSECTION + 100, target)
        check(f"{low}-{high} varaq: javob token chegarasiga sig'adi",
              token_budget(target, "uz") < 8000, str(token_budget(target, "uz")))

    common = [_subsections_per_chapter(lo, hi) for lo, hi in sizes[:4]]
    check("odatdagi hajmlarda bobga ikkita mavzu", common == [2, 2, 2, 2], str(common))


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
    await check_chapter_arc()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} ta tekshiruv o'tmadi: {', '.join(FAILS)}")
        return 1
    print("✅ Kurs ishi rejasi talab qilinganidek tuziladi.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
