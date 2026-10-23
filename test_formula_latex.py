"""Formulalar: mantiq belgilari rasmga chiziladi, model JSON'da bitta teskari chiziq bilan yozgan LaTeX o'qiladi.

    python test_formula_latex.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        FAILS.append(name)


from services.ai_service import _escape_latex_in_json
from services.document_service import mathtext_compat, render_latex_png

print("1) Rasm (logdagi formulalar)")
for latex in (r"Q(x) \implies \exists x P(x)", r"\forall x (P(x) \land Q(x)) \not\equiv P(a) \land Q(b)",
              r"\neg \exists x P(x) \iff \forall x \neg P(x)", r"\forall x (Talaba(x) \implies Oqiydi(x, Kitob))",
              r"a \lor b \le c", r"\\implies x"):
    check(f"chiziladi: {latex}", render_latex_png(latex) is not None)
check("\\left va \\leq tegilmaydi", mathtext_compat(r"\left( a \leq b \right)") == r"\left( a \leq b \right)")

print("\n2) JSON")
raw = r'{"formulas": [{"latex": "\neg \exists x P(x) \iff \forall x \neg P(x)", "explanation": "Izoh:\nikkinchi qator"}]}'
try:
    data = json.loads(_escape_latex_in_json(raw))
    item = data["formulas"][0]
    check("bitta teskari chiziqli LaTeX o'qiladi (Invalid \\escape yo'q)",
          item["latex"] == r"\neg \exists x P(x) \iff \forall x \neg P(x)", item)
    check("\\forall jimgina buzilmaydi (form feed emas)", "\f" not in item["latex"], item)
    check("oddiy \\n (yangi qator) saqlanadi", item["explanation"] == "Izoh:\nikkinchi qator", item)
except ValueError as exc:
    check("JSON o'qildi", False, exc)
ok = r'{"latex": "\\frac{a}{b} \\times 2"}'
check("to'g'ri ekranlangan JSON o'zgarmaydi", _escape_latex_in_json(ok) == ok)

print("\n3) Rejadagi formula bloki (ilgari: no attribute '_VISUAL_LABELS')")
from docx import Document
from services import doc_visuals
from services.document_service import DocumentService

service = DocumentService.__new__(DocumentService)
for lang, given in (("uz", "Berilgan"), ("ru", "Дано"), ("en", "Given")):
    doc = Document()
    service._add_planned_formula(doc, {"name": "Tenglama", "latex": r"a \implies b", "given": ["a=1"],
                                       "result": "b=2"}, doc_visuals.Numbering(lang), "Izoh")
    texts = [p.text for p in doc.paragraphs if p.text]
    check(f"formula bloki ({lang}): sarlavha, berilgan, rasm",
          any(t.startswith(given) for t in texts) and len(doc.inline_shapes) == 1, texts)

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
