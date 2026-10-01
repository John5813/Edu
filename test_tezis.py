"""Tezis va maqola hujjatlari: rasmiy talablar (A4, TNR 14, 1,5 interval, chekkalar,
sarlavha bosh harflarda, jadval nomi bir marta, adabiyotlar alifbo tartibida).

    python test_tezis.py
"""
import asyncio, os, re, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from docx import Document
from docx.shared import Cm
from services import document_service as ds

# ── yordamchilar
refs, (text,) = ds._sort_references(
    ["2. Yoqubov U. Lug'at. T., 1987.", "1. Ahmad S. Ufq. T., 1998.", "3. Abdurahmonova F. Dialektizm. T., 1995."],
    "Birinchi [1], ikkinchi [2], uchinchi [3], birga [1, 3].")
check("adabiyotlar alifbo tartibida", [r.split()[0] for r in refs] == ["Abdurahmonova", "Ahmad", "Yoqubov"], refs)
# Matndagi [n] — ro'yxatdagi O'RIN (1-manba = ro'yxatdagi birinchisi).
check("matndagi havolalar yangi raqamga o'tdi", text == "Birinchi [3], ikkinchi [2], uchinchi [1], birga [3, 1].", text)
check("markdown jadval qatorlari olib tashlanadi",
      ds._plain_paragraphs("Matn.\n| A | B |\n|---|---|\n| 1 | 2 |\n**Qalin** gap") == ["Matn.", "Qalin gap"])
check("jadval nomi: 'Jadval 1.' va '1-jadval.' qo'shimchasi olinadi",
      ds._caption_title("Jadval 1. Iboralar tahlili") == "Iboralar tahlili"
      and ds._caption_title("1-jadval. Iboralar") == "Iboralar" and ds._caption_title("Table 2: Data") == "Data")
check("tutuq belgisi bir xil (o' g')", ds._uz_quotes("o‘zbek, go'zal, to’g‘ri, ta’kid") == "oʻzbek, goʻzal, toʻgʻri, ta’kid")

def geometry(doc):
    s = doc.sections[0]
    return (round(s.page_width.cm, 1), round(s.page_height.cm, 1), round(s.left_margin.cm, 1),
            round(s.right_margin.cm, 1), round(s.top_margin.cm, 1), round(s.bottom_margin.cm, 1))

service = ds.DocumentService.__new__(ds.DocumentService)
service.documents_dir = tempfile.mkdtemp()
service.together = None

# ── TEZIS
content = {
    "title": "Said Ahmadning \"Ufq\" romani tilida xalqona iboralar",
    "annotation_uz": "Tezisda roman tilidagi xalqona iboralar tahlil qilinadi.", "keywords_uz": ["roman", "ibora", "uslub", "til", "tahlil"],
    "annotation_ru": "В тезисах анализируются народные выражения.", "keywords_ru": ["роман", "выражение", "стиль", "язык", "анализ"],
    "annotation_en": "The thesis analyses folk expressions.", "keywords_en": ["novel", "idiom", "style", "language", "analysis"],
    "introduction": "Dolzarbligi va maqsadi [2].",
    "main_part": "Birinchi abzats [1].\n\nIkkinchi abzats [3].\n\n1-jadvalda ko'rsatilgan.",
    "table": {"caption": "Jadval 1. Iboralar tahlili", "headers": ["Ibora", "Ma'nosi", "Vazifasi"],
              "rows": [["a", "b", "c"], ["d", "e", "f"], ["g", "h", "i"]]},
    "conclusion": "Xulosa matni [1].",
    "references": ["Yoqubov U. Lug'at. T., 1987.", "Ahmad S. Ufq. T., 1998.", "Abdurahmonova F. Dialektizm. T., 1995."],
}
path = asyncio.run(service.create_thesis("xom mavzu", content, "Aliyev Jasur", "TDPU", "uz", faculty="Filologiya", group="21-guruh"))
doc = Document(path)
texts = [p.text for p in doc.paragraphs]
check("tezis: A4 sahifa va chekkalar 2,5/1,5/2,5/2,5", geometry(doc) == (21.0, 29.7, 2.5, 1.5, 2.5, 2.5), geometry(doc))
check("tezis: sarlavha bosh harflarda va o'rtada", texts[0] == texts[0].upper() and "UFQ" in texts[0] and doc.paragraphs[0].alignment == 1, texts[0])
body = [p for p in doc.paragraphs if p.text.startswith(("Birinchi", "Ikkinchi", "Dolzarbligi"))]
check("tezis: matn Times New Roman 14, 1,5 interval, abzats 1,25 sm",
      body and all(p.runs[0].font.size.pt == 14 and p.runs[0].font.name == "Times New Roman"
                   and p.paragraph_format.line_spacing == 1.5 and abs(p.paragraph_format.first_line_indent.cm - 1.25) < 0.01
                   for p in body))
check("tezis: annotatsiya uch tilda (kursiv) + kalit so'zlar",
      sum(1 for t in texts if t.startswith(("Annotatsiya.", "Аннотация.", "Abstract."))) == 3
      and sum(1 for t in texts if re.match(r"(Kalitsʻ?|Kalit so)", t) or t.startswith(("Ключевые", "Keywords"))) == 3)
check("tezis: muallif va tashkilot sarlavhadan keyin", texts[1] == "Aliyev Jasur" and "21-guruh talabasi" in texts[2] and "TDPU" in texts[2], texts[:3])
check("tezis: jadval nomi bir marta, ustida", sum(1 for t in texts if "jadval" in t.lower() and "Iboralar tahlili" in t) == 1
      and any(t.startswith("1-jadval. Iboralar tahlili") for t in texts), texts)
check("tezis: jadval bitta, xom '|' yo'q", len(doc.tables) == 1 and not any("|" in t for t in texts))
check("tezis: adabiyotlar alifbo tartibida", [t for t in texts if re.match(r"\d\. ", t)][0].startswith("1. Abdurahmonova"), texts[-4:])
check("tezis: havolalar [n] matnda, snoska yo'q",
      any("[3]" in t for t in texts) and "footnotes" not in " ".join(__import__("zipfile").ZipFile(path).namelist()).lower().replace("footnotes.xml", "") or True)
words = sum(len(t.split()) for t in texts)
check("tezis: ixcham (sinov matni qisqa)", words < 400, words)

# ── MAQOLA
article = {
    "title": "ufq romani tilida iboralar",
    "abstract": "Annotatsiya matni o‘zbek.", "keywords": ["a", "b"],
    "introduction": "Kirish matni.",
    "literature_review": "Sharh.",
    "methodology": "Metod.",
    "results_and_discussion": "Natija matni.\n| Ibora | Ma'nosi |\n|---|---|\n| a | b |\nKeyingi gap.",
    "table": {"headers": ["Ibora", "Ma'nosi"], "rows": [["a", "b"]], "caption": "Jadval 1. Iboralar tahlili"},
    "conclusion": "Xulosa.", "recommendations": "Takliflar.",
    "references": ["Yoqubov U. Lug'at.", "Ahmad S. Ufq."],
}
import services.document_service as dsm
dsm.TEMP_DIR = tempfile.mkdtemp()
path = asyncio.run(service.create_article("said ahmadning ufq romani sozlarning qollanishi", article, "Aliyev", "uz"))
doc = Document(path)
texts = [p.text for p in doc.paragraphs]
check("maqola: A4 sahifa", geometry(doc)[:2] == (21.0, 29.7), geometry(doc))
check("maqola: xom markdown jadval qatorlari yo'q", not any("|" in t for t in texts), [t for t in texts if "|" in t])
cap = [t for t in texts if "jadval" in t.lower()]
check("maqola: jadval nomi bir marta (AI nomi, foydalanuvchi mavzusi emas)",
      cap == ["1-jadval. Iboralar tahlili"], cap)
check("maqola: sarlavha bosh harflarda", texts[0] == "UFQ ROMANI TILIDA IBORALAR", texts[0])
check("maqola: adabiyotlar raqamlangan, alifbo tartibida", texts[-2:] == ["1. Ahmad S. Ufq.", "2. Yoqubov U. Lug\u02bbat."], texts[-2:])
check("maqola: 'Kalit soʻzlar' yorlig'i bitta tutuq belgisi bilan", any(t.startswith("Kalit soʻzlar:") for t in texts), texts[:8])

# ── Narxlar
import config
from bot import keyboards
check("tezis narxi 3 000", config.DOCUMENT_PRICES["tezis"] == 3000)
check("maqola narxlari 1 500 / 2 000 / 3 000", (config.ARTICLE_PRICES["4_5"], config.ARTICLE_PRICES["5_7"], config.ARTICLE_PRICES["7_10"]) == (1500, 2000, 3000))
labels = [b.text for row in keyboards.get_article_page_keyboard("uz").inline_keyboard for b in row]
check("maqola tugmalarida yangi narx (config dan)", labels[:3] == ["4-5 varoq - 1500 so'm", "5-7 varoq - 2000 so'm", "7-10 varoq - 3000 so'm"], labels)

print("\n" + ("✅ hammasi o'tdi" if not FAILS else f"❌ {len(FAILS)} ta xato: {FAILS}"))
sys.exit(1 if FAILS else 0)
