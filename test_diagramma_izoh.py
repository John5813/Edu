"""Diagramma: bir birlikdagi qatorlar bitta diagrammada, izoh (legend) bir-biriga tushmaydi.

Foydalanuvchi taqdimotida (qozoqcha) uch foizli qator ikkiga bo'linib, kichigi nomsiz alohida
diagramma bo'lib qolgan va izoh yozuvlari ustma-ust tushgan edi.

    python test_diagramma_izoh.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); os.chdir(HERE)
os.environ.setdefault("BOT_TOKEN", "1:x")

FAILS = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  XATO ") + name + ("" if cond else f" — {detail}"))
    if not cond: FAILS.append(name)

from services.premium_presentation import deck_charts, html_render, themes
theme = themes.get("yashil")

NAMES = ["Теңеудің оң қабылдануы", "Теңеудің бейтарап қабылдануы", "Теңеудің теріс қабылдануы"]
series = "|".join(f"{n}: {v}" for n, v in zip(NAMES, ["75,78,80,82,85", "15,12,10,8,6", "10,10,10,10,9"]))
tag = (f'<div class="chart" data-kind="bar" data-labels="2022,2023,2024,2025,2026" '
       f'data-series="{series}" data-unit="%"></div>')

print("1) Bir birlikdagi uch qator — bitta diagramma")
out = deck_charts.draw(tag, theme)
check("bitta svg, stack yo'q", out.count("<svg") == 1 and "chart-stack" not in out, out.count("<svg"))
check("uchala nom izohda", all(n in out for n in NAMES))

print("2) Birliklar qavsda farq qilsa — ajratiladi")
two = deck_charts.draw('<div class="chart" data-kind="line" data-labels="1,2,3" '
                       'data-series="Aholi (mlrd): 7.9,8,8.1|Urbanizatsiya (%): 57,58,59"></div>', theme)
check("ikkita diagramma", two.count("<svg") == 2 and "chart-stack" in two)
huge = deck_charts.draw('<div class="chart" data-kind="bar" data-labels="a,b,c" '
                        'data-series="Daromad: 5000,6000,7000|Ulush: 5,6,7"></div>', theme)
check("o'lchami benihoya farq qilsa ham ajratiladi", huge.count("<svg") == 2)
check("yolg'iz qator panelida nomi yozilgan", ">Ulush<" in huge, huge[:200])

print("3) Izoh yozuvlari brauzerda ustma-ust tushmaydi")
from playwright.sync_api import sync_playwright
script = """() => {
  const svg = document.querySelector('.chart svg');
  const box = svg.viewBox.baseVal;
  const items = [...svg.querySelectorAll('rect[rx="5"], text')].filter(e => e.tagName === 'rect' || e.getAttribute('text-anchor') === 'start');
  const texts = [...svg.querySelectorAll('text')].filter(t => %s.includes(t.textContent));
  const boxes = texts.map(t => { const r = t.getBBox(); return {x: r.x, y: r.y, w: r.width, h: r.height, t: t.textContent}; });
  let overlap = 0, outside = 0;
  for (let i = 0; i < boxes.length; i++) {
    if (boxes[i].x + boxes[i].w > box.width) outside++;
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 1 && Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 1) overlap++;
    }
  }
  return {overlap, outside, count: boxes.length};
}""" % str(NAMES).replace("'", '"')
longs = ["Теңеудің оң қабылдануы және оның өсу қарқыны", "Теңеудің бейтарап қабылдануы", "Теңеудің теріс қабылдануы",
         "Тағы бір ұзын атаулы қатар мысалы"]
many_series = "|".join(f"{n}: {v}" for n, v in zip(longs, ["75,78,80,82,85", "15,12,10,8,6", "10,10,10,10,9", "30,31,32,33,34"]))
many = deck_charts.draw(f'<div class="chart" data-kind="line" data-labels="1,2,3,4,5" data-series="{many_series}"></div>', theme)
with sync_playwright() as pw:
    browser = html_render._launch(pw)
    for label, svg_html, names in (("3 qator", out, NAMES), ("4 uzun qator", many, longs)):
        page = browser.new_context(viewport={"width": 1920, "height": 1080}).new_page()
        page.set_content(f"<html><body style='margin:0'>{svg_html}</body></html>")
        result = page.evaluate(script.replace(str(NAMES).replace("'", '"'), str(names).replace("'", '"')))
        check(f"{label}: izoh yozuvlari kesishmaydi va chetdan chiqmaydi",
              result["overlap"] == 0 and result["outside"] == 0 and result["count"] == len(names), result)
        page.close()

print("\nXATO:" if FAILS else "\nHAMMASI YAXSHI", FAILS or "")
sys.exit(1 if FAILS else 0)
