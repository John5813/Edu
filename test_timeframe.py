"""Yil bilan bog'liq promptlarni tekshiradi.

Diagramma va jadvallar eski yillarda (masalan 2023) tugab qolmasligi kerak.
Shuning uchun yil hech qayerda kodga yozilmaydi — `services.timeframe`
bugungi sanadan hisoblaydi. Bu skript o'sha qoidani sinaydi:

    python test_timeframe.py
"""

import re
import sys
from datetime import date

sys.path.insert(0, ".")

from services import timeframe


FAILS = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  XATO {name} — {detail}")
        FAILS.append(name)


def check_timeframe():
    print("\n1) services/timeframe.py")
    now = date.today().year
    check("current_year bugungi yil", timeframe.current_year() == now,
          f"{timeframe.current_year()} != {now}")
    check("last_full_year joriy yildan oshmaydi",
          now - 1 <= timeframe.last_full_year() <= now)
    history = timeframe.history_years()
    check("history_years oxirgi yil bilan tugaydi",
          history[-1] == timeframe.last_full_year(), str(history))
    check("history_years ketma-ket", history == list(range(history[0], history[-1] + 1)),
          str(history))
    forecast = timeframe.forecast_years()
    check("forecast_years joriy yildan boshlanadi", forecast[0] == now, str(forecast))

    for lang in ("uz", "ru", "en"):
        rule = timeframe.year_rule(lang)
        check(f"year_rule({lang}) joriy yilni aytadi", str(now) in rule, rule[:60])
        headers = timeframe.year_headers(lang)
        check(f"year_headers({lang}) oxirgi yilni beradi",
              str(timeframe.last_full_year()) in headers, str(headers))


def check_prompts():
    print("\n2) Promptlarda qotib qolgan yil yo'qligi")
    files = [
        "services/ai_service.py",
        "services/document_service.py",
        "services/project_work/content.py",
        "services/premium_presentation/llm_client.py",
    ]
    stale = re.compile(r"(?<![\d_])20(1\d|2[0-4])(?![\d])")
    for path in files:
        bad = []
        for num, line in enumerate(open(path, encoding="utf-8"), 1):
            if "timeframe" in line or "history_years" in line:
                continue
            if stale.search(line):
                bad.append(f"{path}:{num}")
        check(f"{path} da eski yil yo'q", not bad, ", ".join(bad))


def check_reaches_prompts():
    print("\n3) Yil qoidasi promptlarga yetib boradimi")
    from services.ai_service import get_ai_service

    src = open("services/ai_service.py", encoding="utf-8").read()
    for lang in ("uz", "ru", "en"):
        check(f"ai_service {lang} promptida year_rule",
              f'timeframe.year_rule("{lang}")' in src or f"timeframe.year_rule('{lang}')" in src)

    pw = open("services/project_work/content.py", encoding="utf-8").read()
    check("loyiha ishi promptlarida year_rule",
          pw.count("timeframe.year_rule(language)") >= 4,
          str(pw.count("timeframe.year_rule(language)")))

    from services.premium_presentation import llm_client
    brief = llm_client._with_today(llm_client.SYSTEM_PROMPT_BRIEF)
    now = str(timeframe.current_year())
    check("premium brief promptida bugungi yil", now in brief)
    check("premium briefda {LAST_YEAR} qolmagan", "{LAST_YEAR}" not in brief)
    check("premium briefda {YEAR_SPAN} qolmagan", "{YEAR_SPAN}" not in brief)

    regen = llm_client._with_today(llm_client.SYSTEM_PROMPT_REGEN)
    check("premium regen promptida bugungi yil", now in regen)

    # Placeholder faqat system promptda almashtiriladi — user promptda qolsa
    # model uni matn deb o'qiydi.
    client_src = open("services/premium_presentation/llm_client.py", encoding="utf-8").read()
    after = client_src[client_src.index("def _call_openrouter("):]
    check("placeholder faqat system promptlarda",
          "{LAST_YEAR}" not in after and "{YEAR_SPAN}" not in after)

    service = get_ai_service()

    marks = {"uz": "BUGUN", "ru": "СЕГОДНЯ", "en": "TODAY"}
    builders = {
        "uz": service._get_presentation_prompt_uz,
        "ru": service._get_presentation_prompt_ru,
        "en": service._get_presentation_prompt_en,
    }
    for lang, build in builders.items():
        prompt = build("Raqamli iqtisodiyot", 14)
        check(f"oddiy taqdimot {lang} promptida yil qoidasi", marks[lang] in prompt)
        check(f"oddiy taqdimot {lang} misolida yangi yil",
              str(timeframe.last_full_year()) in prompt)
        check(f"oddiy taqdimot {lang} da {{last_year}} qolmagan",
              "{last_year}" not in prompt)

    example = service._build_example_slides_json("Mavzu", 6, "uz")
    check("taqdimot misolida {last_year} qolmagan", "{last_year}" not in example)
    check("taqdimot misolida yangi yil bor", str(timeframe.last_full_year()) in example)


def main():
    check_timeframe()
    check_prompts()
    check_reaches_prompts()
    print()
    if FAILS:
        print(f"❌ {len(FAILS)} ta tekshiruv o'tmadi: {', '.join(FAILS)}")
        return 1
    print("✅ Hammasi joyida — yillar bugungi sanadan olinadi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
