"""Oddiy rejali kurs ishida diagramma va jadval bo'lishini tekshiradi.

Ilgari vizual elementlar faqat murakkab rejada (boblarda) bo'lardi,
oddiy rejada esa savollar ostida quruq matn qolardi. Endi ikkalasida
ham AI mavzuga qarab qaysi bo'limga diagramma, qaysinisiga jadval
kerakligini o'zi tanlaydi, har birining ostida esa 3-5 gaplik izoh
turadi.

    python test_kurs_ishi_vizual.py
"""

import asyncio
import glob
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, ".")
os.environ.setdefault("BOT_TOKEN", "test")

from services import ai_service as ai  # noqa: E402

FAILS = []


def check(name, condition, detail=""):
    print(f"  ok   {name}" if condition else f"  XATO {name} — {detail}")
    if not condition:
        FAILS.append(name)


def check_quota():
    print("\n1) Nechta element so'raladi")
    for count in (2, 4, 10):
        quota = ai._visual_quota(count)
        total = sum(quota.values())
        check(f"{count} bo'limga {total} element",
              0 < total <= count, str(quota))
        check(f"{count} bo'limda diagramma ham, jadval ham bor",
              quota["charts"] >= 1 and quota["tables"] >= 1, str(quota))
    check("ko'p bo'limda ham cheklangan",
          sum(ai._visual_quota(40).values()) <= 9, str(ai._visual_quota(40)))


async def check_planner():
    print("\n2) AI rejasi o'qilishi")
    service = ai.AIService()
    prompts = []

    async def fake(messages, **kwargs):
        prompts.append(messages[-1]["content"])
        return """{"visuals": [
          {"subsection": "1", "kind": "chart", "chart_type": "column",
           "title": "Bandlik dinamikasi", "categories": ["2024", "2025", "2026"],
           "series": [{"name": "Band aholi", "values": [13.9, 14.1, 14.4]}],
           "explanation": "Birinchi gap. Ikkinchi gap. Uchinchi gap. To'rtinchi gap."},
          {"subsection": "2", "kind": "table", "title": "Hududlar kesimi",
           "headers": ["Hudud", "2025", "2026"],
           "rows": [["Toshkent", "1 200", "1 260"], ["Samarqand", "980", "1 010"]],
           "explanation": "Bir. Ikki. Uch. To'rt. Besh."},
          {"subsection": "3", "kind": "table", "title": "Izohsiz jadval",
           "headers": ["A"], "rows": [["1"]], "explanation": ""},
          {"subsection": "9", "kind": "chart", "title": "Yo'q bo'lim",
           "categories": ["a"], "series": [], "explanation": "Izoh."}
        ]}"""

    service._make_request = fake
    plan = await service.plan_document_visuals(
        "Aholi bandligi", [("1", "Mohiyati"), ("2", "Holati"), ("3", "Istiqbol")],
        "uz", charts=1, tables=1, formulas=1)

    kinds = [item["kind"] for item in plan]
    check("diagramma ham, jadval ham rejada", "chart" in kinds and "table" in kinds,
          str(kinds))
    check("izohsiz element rad etildi", len(plan) == 2, str(len(plan)))
    check("ro'yxatda yo'q bo'lim olinmadi",
          all(item["subsection"] in ("1", "2", "3") for item in plan), str(plan))
    check("promptda jadval so'ralgan", "jadval" in prompts[0], prompts[0][:80])
    check("izoh uzunligi aytilgan", "3-5 ta to'liq gap" in prompts[0])


async def check_document():
    print("\n3) Hujjatda haqiqatan chiqishi")
    from services.document_service import DocumentService

    body = "Mehnat bozori holati yildan yilga o'zgarib bormoqda. " * 40
    content = {
        "title": "Aholi bandligi",
        "language": "uz",
        "plan_style": "oddiy",
        "introduction": "Hammaga ma'lumki, mehnat bozori o'zgardi. " * 16,
        "intro_points": {"goal": "Tahlil qilish.",
                         "tasks": ["Birinchi vazifa", "Ikkinchi vazifa"]},
        "sections": [{"title": f"{i}-savol nomi", "content": body}
                     for i in range(1, 4)],
        "visuals": [
            {"subsection": "1", "kind": "chart", "chart_type": "column",
             "title": "Bandlik dinamikasi",
             "categories": ["2024", "2025", "2026"],
             "series": [{"name": "Band aholi", "values": [13.9, 14.1, 14.4]}],
             "explanation": "Diagrammada band aholi soni ko'rsatilgan. "
                            "Ko'rsatkich uch yil davomida o'sgan. "
                            "O'sish yangi ish o'rinlari bilan bog'liq. "
                            "Bu tendensiya saqlanib qolishi kutilmoqda."},
            {"subsection": "2", "kind": "table", "title": "Hududlar kesimi",
             "headers": ["Hudud", "2025-yil", "2026-yil"],
             "rows": [["Toshkent shahri", "1 200", "1 260"],
                      ["Samarqand viloyati", "980", "1 010"],
                      ["Farg'ona viloyati", "1 040", "1 075"]],
             "explanation": "Jadvalda hududlar bo'yicha bandlik keltirilgan. "
                            "Toshkent shahrida ko'rsatkich eng yuqori. "
                            "Farg'ona viloyatida o'sish sekinroq. "
                            "Buning sababi migratsiya oqimida. "
                            "Shu bois hududiy dasturlar zarur."},
        ],
        "conclusion": "Xulosa. " * 20,
        "references": ["Karimov B. — Toshkent, 2024."],
    }

    service = DocumentService()
    path = await service.create_course_work(
        "Aholi bandligini ta'minlash", content, "Ortiqov Orif", "uz")
    work = tempfile.mkdtemp()
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", work, path], capture_output=True, timeout=300)
    produced = glob.glob(os.path.join(work, "*.pdf"))
    check("PDF yaratildi", bool(produced), work)
    if not produced:
        return

    import pymupdf
    with pymupdf.open(produced[0]) as document:
        pages = [page.get_text() for page in document]
        images = sum(len(page.get_images()) for page in document)
    os.remove(path)
    text = " ".join(" ".join(page.split()) for page in pages)

    check("diagramma rasmi qo'yildi", images >= 1, str(images))
    check("diagramma raqamlangan", "1-rasm." in text, text[:0] or "yo'q")
    check("jadval sarlavhasi bor", "1-jadval." in text)
    check("jadval kataklari tushdi",
          "Samarqand viloyati" in text and "1 010" in text)
    check("diagramma izohi to'liq",
          "Ko'rsatkich uch yil davomida o'sgan." in text)
    check("jadval izohi to'liq",
          "Shu bois hududiy dasturlar zarur." in text)


async def main():
    check_quota()
    await check_planner()
    await check_document()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} ta tekshiruv o'tmadi: {', '.join(FAILS[:5])}")
        return 1
    print("✅ Oddiy rejada ham diagramma, jadval va izohlar bor.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
