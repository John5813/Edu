"""Kurs ishining ikki usuli va ustoz tuzatishlarini tekshiradi.

Ustoz tekshirgan ishdagi qizil tuzatishlar:

1. Kirish "Mavzuning dolzarbligi." dan boshlanadi.
2. "Ushbu kurs ishi" va "tadqiqot" iboralari ishlatilmaydi.
3. "Mavzuning o'rganilganlik darajasi" bandi umuman yo'q.
4. Bandlar raqamlanmaydi; vazifalar "maqsaddan kelib chiqib ... belgilab
   olindi:" deb beriladi va tire bilan yoziladi.
5. Tarkib bandida rejaning HAQIQIY soni turadi va u "xulosa va
   foydalanilgan adabiyotlar ro'yxatidan iborat" deb tugaydi.
6. Prezident snoskasi to'liq yoziladi.

Ikki usul: oddiy reja savollardan, murakkab reja boblardan iborat.

    python test_kurs_ishi_usul.py
"""

import asyncio
import glob
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, ".")
os.environ.setdefault("BOT_TOKEN", "test")

from services import course_work as cw  # noqa: E402

FAILS = []


def check(name, condition, detail=""):
    print(f"  ok   {name}" if condition else f"  XATO {name} — {detail}")
    if not condition:
        FAILS.append(name)


def check_rules():
    print("\n1) Kirish bandlari")
    simple = cw.point_keys(cw.SIMPLE)
    hard = cw.point_keys(cw.COMPLEX)
    check("oddiy usulda maqsad, vazifa, tarkib",
          simple == ("goal", "tasks", "structure"), str(simple))
    check("murakkab usulda predmet va obyekt ham",
          hard[:2] == ("subject", "object"), str(hard))
    check("o'rganilganlik darajasi hech qaysisida yo'q",
          not any("studied" in k or "degree" in k for k in simple + hard))

    labels = cw.point_labels("uz", cw.SIMPLE)
    check("bandlar raqamlanmaydi",
          not any(label[0].isdigit() for label in labels), str(labels))
    check("vazifalar sarlavhasi to'g'ri",
          "belgilab olindi:" in labels[1], labels[1])

    print("\n2) Tarkib bandi")
    for style, count, word in ((cw.SIMPLE, 4, "4 ta savol"),
                               (cw.SIMPLE, 5, "5 ta savol"),
                               (cw.COMPLEX, 3, "3 ta bob"),
                               (cw.COMPLEX, 4, "4 ta bob")):
        sentence = cw.structure_sentence("uz", style, count)
        check(f"{word} deb yoziladi", word in sentence, sentence)
        check(f"{word}: adabiyotlar aytilgan",
              "adabiyotlar" in sentence, sentence)

    print("\n3) Kirish qoidalari")
    rule = cw.intro_rule("uz", cw.SIMPLE)
    for phrase in ("Ushbu kurs ishi", "TADQIQOT", "o'rganilganlik"):
        check(f"«{phrase}» taqiqlangan", phrase in rule)

    print("\n4) Prezident snoskasi")
    full = cw.president_footnote("", "uz")
    for part in ("Mirziyoyev", "Murojaatnoma", "Toshkent", "www"):
        check(f"snoskada «{part}» bor", part in full, full)
    kept = cw.president_footnote(
        "Mirziyoyev Sh.M. Oliy Majlisga Murojaatnomasi. — Toshkent, 2025-yil. — www.president.uz")
    check("to'liq kelgan snoska saqlanadi", "2025" in kept, kept)


def check_echo():
    """Sarlavha matn ichida takrorlanmasinmi.

    Ustoz tekshirgan ishda "Kurs ishining predmeti. Kurs ishining
    predmeti O'zbekistonda..." deb ikki marta yozilgan va u takrorni
    chizib tashlagan.
    """
    print("\n5) Takrorlanuvchi sarlavha")
    cases = [
        ("subject", "Kurs ishining predmeti O'zbekistonda bozor iqtisodiyotiga o'tishdir."),
        ("object", "Kurs ishining obyekti — O'zbekiston iqtisodiy siyosatidir."),
        ("goal", "Kurs ishining maqsadi. Tizimni tahlil qilishdir."),
    ]
    for key, text in cases:
        cleaned = cw.strip_echo(text, "uz", key)
        label = cw.lead("uz", key).rstrip(".")
        check(f"«{key}» takrori olib tashlandi",
              not cleaned.lower().startswith(label.lower()), cleaned)
        check(f"«{key}» mazmuni saqlandi", len(cleaned) > 10, cleaned)

    check("takrorsiz matn tegilmaydi",
          cw.strip_echo("Tizimni tahlil qilishdir.", "uz", "goal")
          == "Tizimni tahlil qilishdir.")

    print("\n6) Vazifalar tozalanishi")
    one_line = cw.clean_tasks(
        "1. nazariy asoslarini o'rganish 2. bosqichlarni tahlil qilish "
        "3. mexanizmlarni baholash")
    check("bitta qatorda kelgani ajratildi", len(one_line) == 3, str(one_line))
    check("raqamlar olib tashlandi",
          not any(t[0].isdigit() for t in one_line), str(one_line))
    many = cw.clean_tasks("- birinchi\n- ikkinchi\n\n- uchinchi")
    check("qatorma-qator kelgani o'qildi", len(many) == 3, str(many))


async def check_documents():
    print("\n7) Ikki usulda hujjat")
    from services.document_service import DocumentService

    body = "Milliy boylik iqtisodiyotning moddiy asosini tashkil etadi. " * 45
    base = dict(
        language="uz",
        introduction="Hammaga ma'lumki, iqtisodiyot o'zgardi. " * 16,
        intro_points={
            # Ataylab takror bilan: kod uni olib tashlashi kerak.
            "subject": "Kurs ishining predmeti milliy boylikning shakllanishidir.",
            "object": "Kurs ishining obyekti O'zbekiston iqtisodiyotidir.",
            "goal": "Milliy boylikdan foydalanish yo'llarini o'rganish.",
            "tasks": "o'rnini o'rganish\nomillarni tahlil qilish\nyo'nalishlarni aniqlash",
        },
        conclusion="Xulosa. " * 20,
        references=["Karimov B. — Toshkent, 2019."],
        presidential_opening={
            "text": "Prezident shu soha haqida alohida to'xtaldi. " * 5,
            "source": cw.president_footnote("", "uz"),
        },
    )
    service = DocumentService()

    async def render(content):
        path = await service.create_course_work(
            "O'zbekiston milliy boyligi", content, "Ortiqov Orif", "uz")
        work = tempfile.mkdtemp()
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                        "--outdir", work, path], capture_output=True, timeout=300)
        produced = glob.glob(os.path.join(work, "*.pdf"))
        import pymupdf
        with pymupdf.open(produced[0]) as document:
            pages = [page.get_text() for page in document]
        os.remove(path)
        return pages

    simple = dict(base, plan_style="oddiy",
                  sections=[{"title": f"{i}-savol nomi", "content": body}
                            for i in range(1, 5)])
    pages = await render(simple)
    toc, intro = pages[1], "\n".join(pages[2:4])
    check("oddiy rejada savollar raqamlangan",
          all(f"{i}. " in toc for i in range(1, 5)), toc[:90])
    check("oddiy rejada bob yo'q", "BOB" not in toc, toc[:90])
    check("kirish dolzarblikdan boshlanadi",
          "Mavzuning dolzarbligi." in " ".join(intro.split()[:8]),
          " ".join(intro.split()[:8]))
    check("vazifalar tire bilan", "- o'rnini o'rganish" in intro.replace("\n", " ")
          or "- o'rnini" in intro)
    check("tarkibda 4 ta savol", "4 ta savol" in intro.replace("\n", " "))
    check("bandlar raqamsiz",
          "1. Kurs ishining" not in intro and "3. Mavzuning" not in intro)

    hard = dict(base, plan_style="murakkab",
                chapters=[{"number": i, "title": f"{i}-bob", "subsections": [
                    {"number": f"{i}.{j}", "title": f"{i}.{j} mavzu",
                     "content": body} for j in (1, 2)]} for i in (1, 2, 3)])
    pages = await render(hard)
    toc, intro = pages[1], "\n".join(pages[2:4])
    check("murakkab rejada boblar bor", "BOB" in toc, toc[:90])
    check("tarkibda 3 ta bob", "3 ta bob" in intro.replace("\n", " "))
    check("predmet va obyekt bor",
          "predmeti" in intro and "obyekti" in intro)
    flat = " ".join(intro.split())
    check("sarlavha matnda takrorlanmaydi",
          "predmeti. Kurs ishining predmeti" not in flat
          and "obyekti. Kurs ishining obyekti" not in flat, flat[:120])


async def main():
    check_rules()
    check_echo()
    await check_documents()
    print()
    if FAILS:
        print(f"❌ {len(FAILS)} ta tekshiruv o'tmadi: {', '.join(FAILS[:5])}")
        return 1
    print("✅ Ikki usul ham ustoz talabiga mos.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
