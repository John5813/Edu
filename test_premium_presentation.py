"""Premium taqdimot oqimini Telegramsiz, bitta buyruq bilan sinash.

Serverda ishga tushiring (OPENROUTER_API_KEY o'sha yerda turibdi):

    python test_premium_presentation.py "Mehnat iqtisodiyoti" --slides 8

Skript AI dan reja oladi (qaysi qolip, o'rinlarga nima yoziladi),
slaydlarni chizadi va nima bo'lganini bosqichma-bosqich ko'rsatadi.
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Premium taqdimot oqimini sinash")
    parser.add_argument("topic", help="Taqdimot mavzusi")
    parser.add_argument("--slides", type=int, default=8, help="Slaydlar soni")
    parser.add_argument("--level", type=int, default=2, choices=[1, 2, 3],
                        help="1=maktab, 2=student, 3=akademik")
    parser.add_argument("--language", default="uz", choices=["uz", "ru", "en"])
    parser.add_argument("--theme", default="", help="Rang sxemasi kaliti")
    parser.add_argument("--preferences", default="", help="Qo'shimcha istaklar")
    parser.add_argument("--no-images", action="store_true",
                        help="Rasm so'ramasdan chizish — tez va bepul")
    args = parser.parse_args()

    from services.premium_presentation import composer, deck, themes

    theme = themes.get(args.theme) if args.theme else themes.suggest(args.topic)
    print(f"\n🎨 Rang sxemasi: {theme.name}")

    print("\n1) Reja so'ralmoqda...")
    planned = composer.plan_deck(
        args.topic, args.slides, language=args.language, level=args.level,
        preferences=args.preferences)
    print(f"   {len(planned)} slayd, {len({p.layout for p in planned})} xil qolip")
    for index, item in enumerate(planned, 1):
        title = str(item.content.get("title", ""))[:48]
        print(f"   {index:>2}. [{item.layout:<12}] {title}")

    print("\n2) Slaydlar chizilmoqda...")
    path = deck.build(planned, theme, with_images=not args.no_images)
    report = deck.LAST_IMAGE_REPORT
    print(f"   Tayyor: {path}")
    print(f"   Rasm: {report['wanted']} ta so'raldi, {report['failed']} ta chiqmadi")

    print("\n   Faylni PowerPoint'da oching va ko'ring:")
    print("    • matnlar ustma-ust tushmaganmi? (qolipda bunday bo'lmasligi kerak)")
    print("    • matn slayddan chiqib ketmaganmi?")
    print("    • ranglar tanlangan sxemada turibdimi?\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        print("\n❌ XATO — quyidagi matnni to'liq nusxalab yuboring:\n")
        traceback.print_exc()
        sys.exit(1)
