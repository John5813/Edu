"""Visible HTML headings must survive conversion to editable PPTX text."""
import os
import sys
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:test")

from services.premium_presentation import html_extract, pptx_build

FAILS = []


def check(name, condition, detail=""):
    print(("  ok   " if condition else "  XATO ") + name +
          ("" if condition else f" — {detail}"))
    if not condition:
        FAILS.append(name)


class FakePage:
    def evaluate(self, script):
        return ["Sarlavha ko'rinishi", "Bosh fikr ko'rinishi"]


print("1) Muhim HTML matni PPTX matn bloklarida tekshiriladi")
layout = {"blocks": [
    {"kind": "text", "text": "Sarlavha ko'rinishi"},
    {"kind": "text", "text": "Bosh fikr ko'rinishi"},
]}
check("sarlavha va bosh gap mavjud bo'lsa, tushib qolgan matn yo'q",
      html_extract.missing_key_text(FakePage(), layout) == [])
layout["blocks"].pop()
check("bosh gap tushib qolsa, bo'shliq aniqlanadi",
      html_extract.missing_key_text(FakePage(), layout) == ["Bosh fikr ko'rinishi"])


print("2) PPTX matn elementi tushib qolsa, chala slayd bekor qilinadi")
deck = pptx_build.new_presentation()
with patch.object(pptx_build, "_add_text"):
    try:
        pptx_build.add_slide(deck, {"blocks": [{
            "kind": "text", "text": "Yo'qolmasligi kerak", "x": 100, "y": 100,
            "w": 500, "h": 100, "lines": 1, "size": 30,
        }]})
    except RuntimeError as exc:
        error = str(exc)
    else:
        error = ""
check("matn yo'qolishi xato sifatida qaytadi", "matn bloki" in error, error)
check("qisman chizilgan slayd o'chirildi", len(deck.slides) == 0, len(deck.slides))

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
