"""Premium taqdimot oqimini Telegramsiz, bitta buyruq bilan sinash.

Replit shell'da ishga tushiring (OPENROUTER_API_KEY o'sha yerda turibdi):

    python test_premium_presentation.py "Mehnat iqtisodiyoti" --slides 8

Skript AI dan brief oladi, tekshiruvlardan o'tkazadi, PPTX chizadi va nima
bo'lganini bosqichma-bosqich ko'rsatadi. Xato chiqsa — to'liq matnini
chiqaradi, uni menga yuborsangiz sabab darrov ma'lum bo'ladi.
"""

import argparse
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Premium taqdimot oqimini sinash")
    parser.add_argument("topic", help="Taqdimot mavzusi")
    parser.add_argument("--slides", type=int, default=8, help="Slaydlar soni (default: 8)")
    parser.add_argument("--level", type=int, default=2, choices=[1, 2, 3],
                        help="1=maktab, 2=student, 3=akademik (default: 2)")
    parser.add_argument("--language", default="uz", choices=["uz", "ru", "en"])
    parser.add_argument("--preferences", default="", help="Qo'shimcha istaklar")
    args = parser.parse_args()

    from services.premium_presentation import config
    from services.premium_presentation.pipeline import (
        canvas_validation_and_fix,
        generate_brief_chunked,
        run_visual_qa_and_fix,
    )
    from services.premium_presentation.renderer import build_presentation

    if not config.OPENROUTER_API_KEY:
        print("❌ OPENROUTER_API_KEY topilmadi. Replit Secrets'ga qo'shing.")
        return 1

    print(f"\n{'=' * 60}")
    print(f"Mavzu       : {args.topic}")
    print(f"Slaydlar    : {args.slides}   Daraja: {args.level}   Til: {args.language}")
    print(f"Matn modeli : {config.OPENROUTER_TEXT_MODEL}")
    print(f"Vizual QA   : {'yoqilgan (' + config.OPENROUTER_VISION_MODEL + ')' if config.VISUAL_QA_ENABLED else 'o‘chiq'}")
    print(f"Rasm modeli : {config.TOGETHER_IMAGE_MODEL if config.TOGETHER_API_KEY else 'TOGETHER_API_KEY yo‘q — rasmsiz'}")
    print(f"{'=' * 60}\n")

    started = time.time()

    print("1/4 Brief so'ralmoqda...")
    brief = generate_brief_chunked(
        args.topic, args.slides,
        progress_cb=lambda done, total: print(f"      bo'lak {done}/{total}"),
        level=args.level, preferences=args.preferences, language=args.language,
    )
    print(f"      ✅ {len(brief.slides)} slayd | {time.time() - started:.0f}s")

    print("2/4 Struktura tekshiruvi...")
    brief = canvas_validation_and_fix(brief, args.topic, language=args.language)
    print("      ✅ o'tdi")

    print("3/4 PPTX chizilmoqda...")
    pptx_path = build_presentation(brief)

    print("4/4 Yakuniy tekshiruv...")
    final_path = run_visual_qa_and_fix(pptx_path, brief, args.topic, args.language)

    _report(brief, final_path, time.time() - started)
    return 0


def _report(brief, path: str, elapsed: float) -> None:
    """Har slaydda nima borligini ko'rsatadi — sifatni shu yerdan chamalash mumkin."""
    print(f"\n{'=' * 60}")
    print(f"✅ TAYYOR: {path}")
    print(f"   {os.path.getsize(path) / 1024:.0f} KB | {elapsed:.0f} soniya")
    print(f"{'=' * 60}\n")

    smallest = 999.0
    for slide in brief.slides:
        kinds: dict = {}
        for element in slide.canvas.elements:
            kinds[element.type] = kinds.get(element.type, 0) + 1
            if element.type == "text" and element.size:
                smallest = min(smallest, element.size)
        summary = ", ".join(f"{count} {name}" for name, count in sorted(kinds.items()))
        print(f"  {slide.index:>2}. [{slide.role:<10}] {slide.title[:44]:<44} | {summary}")

    print(f"\n  Eng kichik shrift: {smallest:.0f}pt (13pt dan past bo'lmasligi kerak)")
    print("\n  Faylni yuklab olib PowerPoint'da oching va ko'ring:")
    print("   • matnlar ustma-ust tushmaganmi?")
    print("   • matn slayddan chiqib ketmaganmi?")
    print("   • ranglar va tuzilma professional ko'rinadimi?\n")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        print("\n❌ XATO — quyidagi matnni to'liq nusxalab yuboring:\n")
        traceback.print_exc()
        sys.exit(1)
