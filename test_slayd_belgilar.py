"""Zamonaviy taqdimot: fizika belgilari, katta harf va diagrammaning matn ustiga tushmasligi.

- \\hbar → ħ (ilgari tashlanardi: "iħ∂Ψ/∂t" → "i∂Ψ/∂t", "≥ ħ/2" → "≥ /2"), Ψ^{*} → Ψ* (ilgari "Ψ^(*)"),
  90^\\circ → 90° (ilgari "90^()");
- bezak uchun katta harf belgilarni buzmaydi: "Plank doimiysi h" → "PLANK DOIMIYSI h", ħ, ω, "n = 1";
- matn ostidagi diagramma matnga tegsa pastga suriladi; tegmasa yoki fon rasmi bo'lsa — joyida.

    python test_slayd_belgilar.py
"""
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


from services.premium_presentation import deck_math, pptx_build as pb

print("1) Formulalar")
cases = {
    r"$\Delta x \cdot \Delta p \geq \hbar/2$": "ħ/2",
    r"$E_n = (n+\frac{1}{2})\hbar\omega$": ")ħω",
    r"$|\Psi|^2 = \Psi^{*}\Psi$": "Ψ*Ψ",
    r"$\Psi^*(x,t)$": "Ψ*(x,t)",
    r"$A^\dagger$": "A†",
    r"$90^\circ$": "90°",
}
for latex, want in cases.items():
    out = deck_math.render(latex)
    check(f"{latex} → …{want}", want in out and "^(" not in out, out)
out = deck_math.render(r"$i\hbar \frac{\partial \Psi}{\partial t} = -\frac{\hbar^2}{2m}\nabla^2\Psi + V\Psi$")
check("Shredinger tenglamasida ikkala ħ ham bor", out.count("ħ") == 2 and out.startswith("iħ"), out)

print("\n2) Katta harf")
for text, want in (("Plank doimiysi h", "PLANK DOIMIYSI h"), ("Keltirilgan Plank doimiysi ħ", "KELTIRILGAN PLANK DOIMIYSI ħ"),
                   ("n = 1", "n = 1"), ("chastota ω", "CHASTOTA ω"), ("Oʻzbekiston tarixi", "OʻZBEKISTON TARIXI"),
                   ("u keldi", "U KELDI")):
    check(f"{text!r} → {want!r}", pb._upper(text) == want, pb._upper(text))

print("\n3) Diagramma matn ustiga tushmaydi")
long = ("Diagrammadagi ulushlar shartli misol bo‘lib, nutq 34%, harakat 26%, idrok 22%, bilish faoliyati 18% ni "
        "tashkil qiladi. Nutq yetakchi bo‘lsa-da, qolgan uch soha birgalikda 66% ni beradi — demak, dastur faqat "
        "nutqqa qaratilsa, ishning katta qismi qamrovsiz qoladi.")
text = {"kind": "text", "x": 160, "y": 400, "w": 800, "h": 150, "text": long, "size": 30, "lineHeight": 48,
        "lines": 3, "family": "Arial"}
height = pb._text_height(text)
check("matnning haqiqiy balandligi o'lchanadi (qutidan baland)", height and height > 150, height)
chart = {"kind": "image", "x": 160, "y": 560, "w": 800, "h": 400, "path": "x"}
pb._clear_overlaps([text, chart])
check("matnga tegayotgan diagramma matn ostiga surildi", chart["y"] >= 400 + height + 8 and chart["h"] == 400, chart)
check("diagramma varaqdan chiqmaydi", chart["y"] + chart["h"] <= pb.SLIDE_H_PX, chart)

low = {"kind": "image", "x": 160, "y": 600, "w": 800, "h": 440, "path": "x"}
pb._clear_overlaps([dict(text), low])
check("joy yetmasa — kichraytirib sig'diriladi", low["y"] >= 640 and low["y"] + low["h"] <= pb.SLIDE_H_PX and low["h"] < 440, low)

far = {"kind": "image", "x": 160, "y": 760, "w": 800, "h": 300, "path": "x"}
pb._clear_overlaps([dict(text, h=320, lines=7), far])
check("matnga tegmagan diagramma joyida qoladi", far["y"] == 760, far)
side = {"kind": "image", "x": 1100, "y": 560, "w": 600, "h": 400, "path": "x"}
pb._clear_overlaps([dict(text), side])
check("boshqa ustundagi rasm joyida qoladi", side["y"] == 560, side)
bg = {"kind": "image", "x": 0, "y": 0, "w": 1920, "h": 1080, "path": "x"}
pb._clear_overlaps([dict(text), bg])
check("fon rasmi joyida qoladi", bg["y"] == 0 and bg["h"] == 1080, bg)

print("\nNATIJA:", "HAMMASI O'TDI" if not FAILS else f"{len(FAILS)} ta xato: {FAILS}")
sys.exit(1 if FAILS else 0)
