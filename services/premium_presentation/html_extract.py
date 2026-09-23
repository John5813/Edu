"""Brauzerdagi slaydni PowerPointning haqiqiy elementlariga aylantiradi.

Slaydni rasm qilib qo'yish oson, lekin mijoz matnni tuzata olmaydi.
Gamma ham rasm bermaydi — uning slaydlari tahrirlanadi. Shu modul
o'rtadagi yo'lni bajaradi: AI slaydni HTML bilan chizadi, brauzer uni
joylashtiradi, biz esa brauzerdan HAR BIR elementning aniq o'rnini,
o'lchamini va uslubini o'qib olamiz va PowerPointda o'sha o'rinlarga
haqiqiy matn qutisi, shakl va jadval qo'yamiz.

Shunda ikki narsa birdan bo'ladi: joylashuvni brauzer hisoblagani uchun
hech narsa ustma-ust tushmaydi, matn esa tahrirlanadigan bo'lib qoladi.

Diagramma va murakkab grafika (SVG) rasm bo'lib qoladi — ularni shakl
bilan qayta chizish foyda bermaydi.
"""

import json
import logging
import os
from typing import Dict, List

log = logging.getLogger("html_extract")

SLIDE_W_PX = 1920
SLIDE_H_PX = 1080
SLIDE_W_IN = 13.333
SLIDE_H_IN = 7.5

# 1920 px kengligi 13.333 dyuymga to'g'ri keladi.
PX_TO_EMU = SLIDE_W_IN * 914400 / SLIDE_W_PX
# 1920 px = 960 punkt, ya'ni ikki piksel bir punkt.
PX_TO_PT = SLIDE_W_IN * 72 / SLIDE_W_PX

# Brauzerdagi shrift nomini PowerPoint biladigan nomga o'giramiz.
# Liberation Sans/Serif — Arial va Times New Roman bilan o'lchovdosh:
# brauzer birini, PowerPoint ikkinchisini chizsa ham matn bir xil joyni
# egallaydi.
_SANS = "Arial"
_SERIF = "Times New Roman"
_MONO = "Courier New"

# Sahifadagi elementni o'qiydigan skript. U DOM bo'ylab yuradi va har
# elementdan faqat brauzer HISOBLAGAN qiymatlarni oladi — CSS ni o'zimiz
# talqin qilmaymiz.
_SCRIPT = r"""
() => {
  const W = window.innerWidth, H = window.innerHeight;
  const out = [];
  let shotIndex = 0;

  const rgb = (value) => {
    const m = String(value || "").match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(",").map((x) => parseFloat(x));
    if (p.length > 3 && p[3] < 0.05) return null;          // shaffof
    const hex = (n) => Math.max(0, Math.min(255, Math.round(n)))
      .toString(16).padStart(2, "0").toUpperCase();
    return hex(p[0]) + hex(p[1]) + hex(p[2]);
  };

  const box = (el) => {
    const r = el.getBoundingClientRect();
    return {x: r.left, y: r.top, w: r.width, h: r.height};
  };

  const visible = (el, r) => {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden") return false;
    if (parseFloat(s.opacity || "1") < 0.05) return false;
    if (r.w < 1 || r.h < 1) return false;
    if (r.x > W || r.y > H || r.x + r.w < 0 || r.y + r.h < 0) return false;
    return true;
  };

  // Elementning O'ZIGA tegishli matn (bolalarinikisiz).
  // <br> qator ko'chirishni bildiradi: uni yo'qotsak, ikki satr
  // "sarlavhaning davomi" bo'lib yopishib qolardi.
  const ownText = (el) => {
    const lines = [];
    let current = "";
    for (const node of el.childNodes) {
      if (node.nodeType === 3) {
        current += node.nodeValue;
      } else if (node.nodeType === 1 && node.tagName === "BR") {
        lines.push(current);
        current = "";
      }
    }
    lines.push(current);
    return lines
      .map((line) => line.replace(/[^\S\n]+/g, " ").trim())
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  };

  const align = (value) => {
    if (value === "center") return "center";
    if (value === "right" || value === "end") return "right";
    if (value === "justify") return "justify";
    return "left";
  };

  const walk = (el) => {
    const r = box(el);
    if (!visible(el, r)) return;
    const s = getComputedStyle(el);
    const tag = el.tagName.toLowerCase();

    // Diagramma va rasm — suratga olinadi, ichiga kirilmaydi.
    if (tag === "svg" || tag === "canvas" || tag === "img" || tag === "video") {
      el.setAttribute("data-pptx-shot", String(shotIndex));
      out.push({kind: "image", shot: shotIndex, ...r});
      shotIndex += 1;
      return;
    }

    // Jadval — PowerPointning o'z jadvaliga aylanadi.
    if (tag === "table") {
      const rows = [];
      const widths = [];
      const heights = [];
      let headerFill = null, headerColor = null, bodyColor = null, size = 12;
      for (const tr of el.querySelectorAll("tr")) {
        const cells = [];
        const cs = tr.querySelectorAll("th, td");
        if (!cs.length) continue;
        heights.push(tr.getBoundingClientRect().height);
        cs.forEach((cell, index) => {
          const style = getComputedStyle(cell);
          if (rows.length === 0) {
            widths.push(cell.getBoundingClientRect().width);
            headerFill = headerFill || rgb(style.backgroundColor);
            headerColor = headerColor || rgb(style.color);
          } else if (!bodyColor) {
            bodyColor = rgb(style.color);
          }
          size = parseFloat(style.fontSize) || size;
          cells.push({
            text: (cell.innerText || "").replace(/\s+/g, " ").trim(),
            bold: (parseInt(style.fontWeight, 10) || 400) >= 600,
            align: align(style.textAlign),
          });
        });
        rows.push(cells);
      }
      if (rows.length) {
        out.push({kind: "table", rows, widths, heights, size,
                  headerFill, headerColor, bodyColor, ...r});
      }
      return;
    }

    // Fon yoki chegarasi bor blok — PowerPointda shakl bo'ladi.
    const fill = rgb(s.backgroundColor);
    const borderWidth = parseFloat(s.borderTopWidth) || 0;
    const borderColor = borderWidth > 0 ? rgb(s.borderTopColor) : null;
    if ((fill || borderColor) && tag !== "body" && tag !== "html") {
      out.push({
        kind: "rect", fill, ...r,
        border: borderColor, borderWidth,
        radius: parseFloat(s.borderTopLeftRadius) || 0,
      });
    }

    // O'z matni bo'lsa — matn qutisi.
    const text = ownText(el);
    if (text) {
      out.push({
        kind: "text", text, ...r,
        size: parseFloat(s.fontSize) || 16,
        weight: parseInt(s.fontWeight, 10) || 400,
        italic: s.fontStyle === "italic",
        color: rgb(s.color) || "000000",
        align: align(s.textAlign),
        family: s.fontFamily || "",
        lineHeight: parseFloat(s.lineHeight) || 0,
        upper: s.textTransform === "uppercase",
        letterSpacing: parseFloat(s.letterSpacing) || 0,
      });
    }

    for (const child of el.children) {
      if (child.tagName !== "BR") walk(child);
    }
  };

  for (const child of document.body.children) walk(child);
  return {
    background: rgb(getComputedStyle(document.body).backgroundColor),
    blocks: out,
  };
}
"""


def read_layout(page) -> Dict:
    """Sahifadagi elementlarning o'rni, o'lchami va uslubini o'qiydi."""
    return page.evaluate(_SCRIPT)


def capture_images(page, blocks: List[Dict], out_dir: str, slide: int) -> None:
    """Diagramma va rasmlarni alohida suratga oladi.

    Har bir surat o'z elementining o'lchamida olinadi, shuning uchun
    PowerPointda cho'zilmaydi.
    """
    for block in blocks:
        if block.get("kind") != "image":
            continue
        path = os.path.join(
            out_dir, f"vis_{os.getpid()}_{slide:02d}_{block['shot']:02d}.png")
        try:
            element = page.query_selector(f'[data-pptx-shot="{block["shot"]}"]')
            if element is None:
                continue
            element.screenshot(path=path, omit_background=True)
            block["path"] = path
        except Exception as exc:
            log.warning("Slayd %d: vizual %s suratga olinmadi: %s",
                        slide, block["shot"], exc)


def font_name(family: str) -> str:
    """Brauzer shriftini PowerPoint biladigan nomga o'giradi.

    Faqat RO'YXATDAGI BIRINCHI nom qaraladi: brauzer aynan o'shani
    ishlatadi. Butun qatorga qarash xato edi — "Arial, 'Liberation
    Sans', sans-serif" ichida "serif" so'zi bor va hamma matn serif
    bo'lib chiqardi.
    """
    first = str(family or "").split(",")[0].strip().strip("'\"").lower()
    if "mono" in first or "courier" in first:
        return _MONO
    if first.endswith("serif") and not first.endswith("sans-serif"):
        return _SERIF
    if any(word in first for word in ("times", "georgia", "garamond",
                                      "liberation serif", "dejavu serif")):
        return _SERIF
    return _SANS
