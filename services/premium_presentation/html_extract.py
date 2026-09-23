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

  const hex2 = (n) => Math.max(0, Math.min(255, Math.round(n)))
    .toString(16).padStart(2, "0").toUpperCase();

  const parse = (value) => {
    const m = String(value || "").match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(",").map((x) => parseFloat(x));
    const alpha = p.length > 3 ? p[3] : 1;
    if (alpha < 0.02) return null;
    return {r: p[0], g: p[1], b: p[2], a: alpha};
  };

  // Elementning ko'rinadigan shaffofligi: o'ziniki va hamma
  // ota-onalariniki ko'paytiriladi.
  const chainOpacity = (el) => {
    let value = 1;
    let node = el;
    while (node && node !== document.documentElement) {
      value *= parseFloat(getComputedStyle(node).opacity || "1");
      node = node.parentElement;
    }
    return value;
  };

  // Elementning ORQASIDAGI rang: eng yaqin shaffof bo'lmagan fon.
  // Gradient ham fonni to'liq yopadi — uni hisobga olmasak, to'q
  // gradientli varaqning orqasi "oq" deb topilib, oq sarlavha
  // qoraytirilib yuborilardi.
  const behind = (el) => {
    let node = el.parentElement;
    while (node) {
      const colour = parse(getComputedStyle(node).backgroundColor);
      if (colour && colour.a > 0.95) return colour;
      const ramp = gradient(node);
      if (ramp && ramp.stops.length) {
        const a = unhex(ramp.stops[0].colour);
        const b = unhex(ramp.stops[ramp.stops.length - 1].colour);
        return {r: (a.r + b.r) / 2, g: (a.g + b.g) / 2,
                b: (a.b + b.b) / 2, a: 1};
      }
      node = node.parentElement;
    }
    return {r: 255, g: 255, b: 255, a: 1};
  };

  // Shaffof rangni orqa fon bilan aralashtiramiz. PowerPointda shakl
  // shaffofligini berish noqulay, aralashtirilgani esa ko'zga aynan
  // brauzerdagidek ko'rinadi. Aralashtirmasak, ozgina ko'k bezak
  // slaydda to'q ko'k plastina bo'lib chiqadi.
  const rgbOver = (value, el, extraAlpha) => {
    const colour = parse(value);
    if (!colour) return null;
    const alpha = colour.a * (extraAlpha === undefined ? 1 : extraAlpha);
    if (alpha < 0.02) return null;
    if (alpha > 0.98) return hex2(colour.r) + hex2(colour.g) + hex2(colour.b);
    const base = behind(el);
    const mix = (a, b) => a * alpha + b * (1 - alpha);
    return hex2(mix(colour.r, base.r))
         + hex2(mix(colour.g, base.g))
         + hex2(mix(colour.b, base.b));
  };

  // Rangning ko'z uchun yorqinligi (WCAG). Ikki rangning nisbati
  // 4.5 dan past bo'lsa matn o'qilmay qoladi.
  const lum = (c) => {
    const f = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };

  const ratio = (a, b) => {
    const hi = Math.max(lum(a), lum(b)), lo = Math.min(lum(a), lum(b));
    return (hi + 0.05) / (lo + 0.05);
  };

  const unhex = (value) => ({
    r: parseInt(value.slice(0, 2), 16),
    g: parseInt(value.slice(2, 4), 16),
    b: parseInt(value.slice(4, 6), 16),
  });

  // `linear-gradient(135deg, #A 0%, #B 100%)` → PowerPoint tushunadigan
  // ko'rinish. Yassi bitta rang quruq ko'rinadi, gradient esa
  // chuqurlik beradi — PowerPointda u haqiqiy gradient to'ldirish
  // bo'lib chiqadi.
  const gradient = (el) => {
    const image = getComputedStyle(el).backgroundImage || "";
    if (image.indexOf("linear-gradient") < 0) return null;
    const stops = [];
    const colours = image.match(/rgba?\([^)]+\)\s*[\d.]*%?/g) || [];
    for (let i = 0; i < colours.length; i += 1) {
      const colour = parse(colours[i]);
      if (!colour) continue;
      const spot = colours[i].match(/([\d.]+)%\s*$/);
      stops.push({
        colour: hex2(colour.r) + hex2(colour.g) + hex2(colour.b),
        at: spot ? parseFloat(spot[1]) / 100
                 : (colours.length > 1 ? i / (colours.length - 1) : 0),
      });
    }
    if (stops.length < 2) return null;
    const turn = image.match(/(-?[\d.]+)deg/);
    return {stops, angle: turn ? parseFloat(turn[1]) : 180};
  };

  const box = (el) => {
    const r = el.getBoundingClientRect();
    return {x: r.left, y: r.top, w: r.width, h: r.height};
  };

  // Element ko'rinadigan maydon: slayd va `overflow: hidden` qo'ygan
  // ota-onalar bilan kesishmasi.
  const shownArea = (el, r) => {
    let box = {l: 0, t: 0, rr: W, b: H};
    let node = el.parentElement;
    while (node && node !== document.documentElement) {
      const style = getComputedStyle(node);
      if (style.overflow !== "visible" || style.overflowX !== "visible"
          || style.overflowY !== "visible") {
        const p = node.getBoundingClientRect();
        box = {l: Math.max(box.l, p.left), t: Math.max(box.t, p.top),
               rr: Math.min(box.rr, p.right), b: Math.min(box.b, p.bottom)};
      }
      node = node.parentElement;
    }
    const w = Math.min(r.x + r.w, box.rr) - Math.max(r.x, box.l);
    const h = Math.min(r.y + r.h, box.b) - Math.max(r.y, box.t);
    return Math.max(w, 0) * Math.max(h, 0);
  };

  const visible = (el, r) => {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden") return false;
    if (chainOpacity(el) < 0.04) return false;
    if (r.w < 1 || r.h < 1) return false;
    // Elementning yarmidan ko'pi kesilib ketgan bo'lsa, uni qo'ymaymiz:
    // brauzerda ko'rinmagan narsa slaydda ingichka chiziq bo'lib
    // chiqib qolardi.
    return shownArea(el, r) >= r.w * r.h * 0.5;
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

  // Bola element matn oqimining ichida turadimi (<b>, <span>, <a>)?
  // Shunday bolalar ota abzatsning bir qismi: ularni alohida quti
  // qilib olsak, matn ikkiga bo'linib, ustma-ust tushadi.
  const RECURSE_TAGS = new Set(["SVG", "CANVAS", "IMG", "VIDEO", "TABLE"]);

  const inlineOnly = (el) => {
    for (const child of el.children) {
      if (child.tagName === "BR") continue;
      if (RECURSE_TAGS.has(child.tagName)) return false;
      // Kasr ustma-ust yoziladi: uni ota matnga qo'shib olsak,
      // surat va maxraj yonma-yon bitta qatorga tushib, formula
      // ma'nosini yo'qotardi.
      if (child.classList && child.classList.contains("frac")) return false;
      const display = getComputedStyle(child).display || "";
      if (!display.startsWith("inline")) return false;
    }
    return true;
  };

  // Matn nechta qatorga joylashgan.
  const lineCount = (el, r) => {
    const height = parseFloat(getComputedStyle(el).lineHeight);
    if (!height || !isFinite(height)) return 1;
    return Math.max(1, Math.round(r.h / height));
  };

  const align = (value) => {
    if (value === "center") return "center";
    if (value === "right" || value === "end") return "right";
    if (value === "justify") return "justify";
    return "left";
  };

  // Element burilganmi. Diagrammaning tik o'q yozuvi ("Hajmi, %")
  // odatda `rotate(-90deg)` yoki `writing-mode: vertical-rl` bilan
  // yoziladi. `getBoundingClientRect` bunday elementning ingichka va
  // baland QAMROVINI beradi; uni shundayligicha matn qutisi qilsak,
  // PowerPoint har harfni alohida qatorga tushirib yuboradi.
  const spin = (el) => {
    const s = getComputedStyle(el);
    const matrix = String(s.transform || "");
    const m = matrix.match(/matrix\(([^)]+)\)/);
    if (m) {
      const p = m[1].split(",").map((x) => parseFloat(x));
      const deg = Math.round(Math.atan2(p[1], p[0]) * 180 / Math.PI);
      if (Math.abs(deg) >= 5) return deg;
    }
    const mode = String(s.writingMode || "");
    if (mode.indexOf("vertical") === 0) return 90;
    return 0;
  };

  // Burilgan elementning burilishdan OLDINGI qutisi, qamrovning
  // markazida turadi. PowerPoint ham shaklni markazi atrofida
  // buradi, shuning uchun ikkisi bir joyga tushadi.
  const flatBox = (el, r, turn) => {
    if (!turn || !el.offsetWidth || !el.offsetHeight) return r;
    return {x: r.x + r.w / 2 - el.offsetWidth / 2,
            y: r.y + r.h / 2 - el.offsetHeight / 2,
            w: el.offsetWidth, h: el.offsetHeight};
  };

  // Ikki matnni taqqoslash kaliti.
  const key = (value) => String(value || "")
    .replace(/\s+/g, " ").trim().toLowerCase();

  // Matn xiralashtirilgan qatlamdami? Dizaynda sarlavha ortiga
  // `filter: blur(...)` bilan nusxa qo'yib "nur" chiziladi. Brauzerda
  // u yumshoq dog', PowerPointda esa o'sha matnning ikkinchi, to'q
  // nusxasi bo'lib chiqadi — shuning uchun bunday matn olinmaydi.
  const blurry = (el) => /blur\(/.test(getComputedStyle(el).filter || "");

  // "SalomSalom" yoki "Salom Salom" — bitta matn ikki marta yozilgan.
  // Bu sarlavha ichiga soya uchun qo'yilgan <span> nusxasidan kelib
  // chiqadi: brauzer ikkalasini ustma-ust chizadi, innerText esa
  // ikkalasini ham qaytaradi.
  const undouble = (value) => {
    const t = String(value || "").trim();
    if (t.length < 12 || t.indexOf("\n") >= 0) return value;
    if (t.length % 2 === 0) {
      const half = t.length / 2;
      if (t.slice(0, half) === t.slice(half)) return t.slice(0, half);
    }
    const mid = (t.length - 1) / 2;
    if (Number.isInteger(mid) && t[mid] === " "
        && t.slice(0, mid) === t.slice(mid + 1)) return t.slice(0, mid);
    return value;
  };

  const walk = (el, soft) => {
    const r = box(el);
    const s = getComputedStyle(el);
    const tag = el.tagName.toLowerCase();
    const faded = soft || blurry(el);
    if (!visible(el, r)) {
      // O'zi ko'rinmasa ham, bolasi ko'rinishi mumkin (masalan katta
      // idish slayddan chiqqan, ichidagi matn esa joyida).
      if (s.display !== "none" && s.visibility !== "hidden") {
        for (const child of el.children) {
          if (child.tagName !== "BR") walk(child, faded);
        }
      }
      return;
    }

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
            headerFill = headerFill || rgbOver(style.backgroundColor, cell);
            headerColor = headerColor || rgbOver(style.color, cell);
          } else if (!bodyColor) {
            bodyColor = rgbOver(style.color, cell);
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
    const shown = chainOpacity(el);
    const fill = rgbOver(s.backgroundColor, el, shown);
    const sides = {
      top: parseFloat(s.borderTopWidth) || 0,
      right: parseFloat(s.borderRightWidth) || 0,
      bottom: parseFloat(s.borderBottomWidth) || 0,
      left: parseFloat(s.borderLeftWidth) || 0,
    };
    const widths = [sides.top, sides.right, sides.bottom, sides.left];
    const uniform = widths.every((w) => Math.abs(w - widths[0]) < 0.6);
    // Faqat bitta tomonda chegara bo'lsa (dizaynda ko'p uchraydigan
    // aksent chizig'i), uni butun shaklga ramka qilib qo'ysak
    // kartochka qutiga aylanib qoladi. Bunday chiziq alohida tasma
    // bo'lib chiziladi.
    const borderWidth = uniform ? widths[0] : 0;
    const borderColor = borderWidth > 0
      ? rgbOver(s.borderTopColor, el, shown) : null;
    const ramp = gradient(el);
    if ((fill || borderColor || ramp) && tag !== "body" && tag !== "html") {
      // border-radius foizda berilishi mumkin ("50%"). Uni pikselga
      // o'girmasak, doira PowerPointda burchagi yumaloq kvadrat
      // bo'lib chiqadi.
      const raw = s.borderTopLeftRadius || "0";
      const short = Math.max(Math.min(r.w, r.h), 1);
      let radius = parseFloat(raw) || 0;
      if (raw.indexOf("%") >= 0) radius = short * radius / 100;
      out.push({
        kind: "rect", fill, gradient: ramp, ...r,
        border: borderColor, borderWidth,
        radius,
        circle: radius * 2 >= short * 0.95,
      });
    }

    // Bir tomonlama aksent chizig'i — alohida tasma.
    if (!uniform) {
      const strips = {
        top: {x: r.x, y: r.y, w: r.w, h: sides.top},
        bottom: {x: r.x, y: r.y + r.h - sides.bottom, w: r.w, h: sides.bottom},
        left: {x: r.x, y: r.y, w: sides.left, h: r.h},
        right: {x: r.x + r.w - sides.right, y: r.y, w: sides.right, h: r.h},
      };
      const colours = {
        top: s.borderTopColor, bottom: s.borderBottomColor,
        left: s.borderLeftColor, right: s.borderRightColor,
      };
      for (const side of ["top", "bottom", "left", "right"]) {
        if (sides[side] < 1) continue;
        const colour = rgbOver(colours[side], el, shown);
        if (!colour) continue;
        out.push({kind: "rect", fill: colour, ...strips[side],
                  border: null, borderWidth: 0, radius: 0, circle: false});
      }
    }

    // Matn qutisi. Bolalari faqat oqim ichidagi elementlar bo'lsa
    // (<b>, <span>, <a>), butun matn BITTA quti bo'ladi: aks holda
    // "<b>" ning matni otasidan tushib qolar va uning ustiga alohida
    // quti bo'lib chiqar edi.
    const whole = inlineOnly(el);
    const text = undouble(whole
      ? (el.innerText || "").replace(/[^\S\n]+/g, " ")
          .replace(/\n{3,}/g, "\n\n").trim()
      : ownText(el));

    // Matnning ko'rinish kuchi: qatlam shaffofligi va harf rangining
    // shaffofligi. Gradient sarlavhada harf rangi shaffof bo'ladi
    // (`-webkit-text-fill-color: transparent`) — matn fon bilan
    // chiziladi. Ikki nusxadan qaysi biri haqiqiy ekanini shu raqam
    // aytadi.
    const inkColour = parse(s.webkitTextFillColor || s.color);
    const ink = shown * (inkColour ? inkColour.a : 0.01);

    // Matn o'z foni ustida ko'rinadimi. Uslubda bitta sinf unutilsa
    // (masalan to'q kartochka ichidagi ro'yxat), qora matn to'q ko'k
    // fonda qolib ketardi. Bu yerda tekshiriladi va kerak bo'lsa
    // o'qiladigan rangga o'giriladi — mijoz ko'rinmas matn olmaydi.
    let paint = rgbOver(s.color, el, shown) || "000000";
    if (text) {
      const back = behind(el);
      if (ratio(unhex(paint), back) < 3.2) {
        const light = {r: 255, g: 255, b: 255};
        const dark = {r: 17, g: 17, b: 17};
        paint = ratio(light, back) >= ratio(dark, back)
          ? "FFFFFF" : "111111";
      }
    }

    if (text && !faded) {
      const turn = spin(el);
      const tr = flatBox(el, r, turn);
      out.push({
        kind: "text", text, ink, rotation: turn, ...tr,
        size: parseFloat(s.fontSize) || 16,
        weight: parseInt(s.fontWeight, 10) || 400,
        italic: s.fontStyle === "italic",
        color: paint,
        align: align(s.textAlign),
        family: s.fontFamily || "",
        lineHeight: parseFloat(s.lineHeight) || 0,
        upper: s.textTransform === "uppercase",
        letterSpacing: parseFloat(s.letterSpacing) || 0,
        lines: lineCount(el, tr),
      });
    }

    for (const child of el.children) {
      if (child.tagName === "BR") continue;
      // Matni otasiga qo'shib olindi — ichiga kirmaymiz. Rasm va
      // jadval esa baribir alohida olinadi.
      if (whole && text && !RECURSE_TAGS.has(child.tagName)) continue;
      walk(child, faded);
    }
  };

  for (const child of document.body.children) walk(child, false);

  // Bir matn ikki elementdan kelgan bo'lsa (soya, kontur yoki nur
  // uchun qo'yilgan nusxa), brauzerda ular ustma-ust tushib bitta
  // bo'lib ko'rinadi. PowerPointda esa ikkita alohida quti bo'lib,
  // matn ikki marta yozilgandek chiqadi. Shu yerda nusxa olib
  // tashlanadi: ko'rinadigani — ranggi to'qroq bo'lgani, tenglikda
  // esa keyin chizilgani (ustida turgani) qoladi.
  const dropDoubles = () => {
    const texts = out.filter((b) => b.kind === "text");
    const gone = new Set();
    for (let i = 0; i < texts.length; i += 1) {
      for (let j = i + 1; j < texts.length; j += 1) {
        const a = texts[i], b = texts[j];
        if (gone.has(a) || gone.has(b)) continue;
        if (key(a.text) !== key(b.text)) continue;
        const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
        const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
        if (w <= 0 || h <= 0) continue;
        const small = Math.min(a.w * a.h, b.w * b.h);
        if (w * h < small * 0.5) continue;
        gone.add(b.ink > a.ink + 0.05 ? a : a.ink > b.ink + 0.05 ? b : a);
      }
    }
    return out.filter((b) => !gone.has(b));
  };

  return {
    background: rgbOver(getComputedStyle(document.body).backgroundColor,
                        document.body) || "FFFFFF",
    backgroundGradient: gradient(document.body),
    blocks: dropDoubles(),
  };
}
"""


# Slaydni chizishdan OLDIN tekshiradigan skript. Brauzer HTML ni
# qanday joylashtirganini biz ko'rmaymiz, AI esa ba'zan varaqdan
# chiqib ketadigan yoki matn ustiga matn qo'yadigan kod yozadi. Shu
# tekshiruv muammoni topadi va slayd bir marta qayta so'raladi.
_CHECK_SCRIPT = r"""
() => {
  const W = window.innerWidth, H = window.innerHeight;
  const problems = [];
  const texts = [];

  const own = (el) => {
    let text = "";
    for (const node of el.childNodes) {
      if (node.nodeType === 3) text += node.nodeValue;
    }
    return text.trim();
  };

  let outside = 0, tallest = 0, lowest = 0;
  for (const el of document.body.querySelectorAll("*")) {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;

    const text = own(el);
    if (text) {
      texts.push({r, text, el});
      lowest = Math.max(lowest, r.bottom);
      tallest = tallest || r.top;
      tallest = Math.min(tallest, r.top);
    }

    // Slayddan chiqib ketgan: butun ekranni egallagan fon bundan mustasno.
    if (r.width < W * 0.98 || r.height < H * 0.98) {
      if (r.left < -8 || r.top < -8 || r.right > W + 8 || r.bottom > H + 8) {
        outside += 1;
      }
    }
  }
  if (outside) {
    problems.push(outside + " ta element slayddan chiqib ketgan "
      + "(1920x1080 dan tashqarida yoki manfiy o'rinda)");
  }

  // Matn ustiga matn tushganmi. Ota va uning ichidagi element
  // sanalmaydi: ular bir matnning bo'laklari, chizuvchi ularni
  // bitta quti qilib qo'yadi.
  let collisions = 0;
  for (let i = 0; i < texts.length; i += 1) {
    for (let j = i + 1; j < texts.length; j += 1) {
      const first = texts[i].el, second = texts[j].el;
      if (first.contains(second) || second.contains(first)) continue;
      const a = texts[i].r, b = texts[j].r;
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w <= 2 || h <= 2) continue;
      const small = Math.min(a.width * a.height, b.width * b.height);
      if (w * h > small * 0.35) collisions += 1;
    }
  }
  if (collisions) {
    problems.push(collisions + " joyda matn ustiga matn tushgan");
  }

  // Bir matn ikki marta yozilganmi. Soya, kontur yoki nur uchun
  // qo'yilgan nusxa brauzerda bittadek ko'rinadi, PowerPointda esa
  // ikkita alohida quti bo'lib chiqadi. Chizuvchi nusxani olib
  // tashlaydi, lekin HTML ning o'zi ham tuzatilgani ma'qul: nusxa
  // sarlavha qutisini kengaytirib, joylashuvni ham buzadi.
  let doubled = 0;
  for (let i = 0; i < texts.length; i += 1) {
    for (let j = i + 1; j < texts.length; j += 1) {
      const a = texts[i].r, b = texts[j].r;
      if (texts[i].text.replace(/\s+/g, " ").trim().toLowerCase()
          !== texts[j].text.replace(/\s+/g, " ").trim().toLowerCase()) continue;
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w <= 0 || h <= 0) continue;
      const small = Math.min(a.width * a.height, b.width * b.height);
      if (w * h < small * 0.5) continue;
      doubled += 1;
    }
  }
  if (doubled) {
    problems.push(doubled + " ta matn ikki marta yozilgan (soya yoki nur "
      + "uchun nusxa qo'yilgan) — har matn bitta elementda bo'lsin");
  }

  // Matn o'z qutisiga sig'maganmi. Sxemadagi doiraga uzun yorliq
  // yozilsa, harflar doiraning chetidan chiqib ketadi va qo'shni
  // chiziqqa minadi — slayd tartibsiz ko'rinadi. Brauzer buni
  // `scrollWidth`/`scrollHeight` bilan aniq aytadi: mazmun qutidan
  // kattami yoki yo'q.
  // Matnning o'zi qayerga chizilganini brauzerdan Range bilan
  // so'raymiz. `scrollHeight` yetarli emas: markazga tekislangan
  // matn qutidan ikki tomonga baravar toshsa, u buni ko'rsatmaydi.
  const spillsOut = (el) => {
    const box = el.getBoundingClientRect();
    for (const node of el.childNodes) {
      if (node.nodeType !== 3 || !node.nodeValue.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      const r = range.getBoundingClientRect();
      if (r.width < 1 && r.height < 1) continue;
      if (r.left < box.left - 3 || r.right > box.right + 3
          || r.top < box.top - 3 || r.bottom > box.bottom + 3) return true;
    }
    return false;
  };

  let spill = 0;
  for (const el of document.body.querySelectorAll("*")) {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    if (!own(el)) continue;
    if (el.clientWidth < 8 || el.clientHeight < 8) continue;
    if (spillsOut(el)) spill += 1;
  }
  if (spill) {
    problems.push(spill + " ta blokda matn qutisiga sig'magan (chetidan "
      + "chiqib ketgan) — qutiga qat'iy balandlik berilmasin yoki "
      + "yorliq qisqartirilsin");
  }

  // Pastki yarmi butunlay bo'sh qolganmi.
  if (texts.length && lowest < H * 0.62) {
    problems.push("mazmun slaydning yuqori qismiga to'plangan, pastki "
      + Math.round(100 - lowest * 100 / H) + "% bo'sh qolgan");
  }

  // Mazmun ichida katta bo'sh tasma qolganmi: sarlavha tepada, qolgani
  // pastda — o'rtasi bo'm-bo'sh. Bu slaydni "uzilgan" qilib ko'rsatadi.
  if (texts.length > 1) {
    const bands = texts
      .map((t) => ({top: t.r.top, bottom: t.r.bottom}))
      .sort((a, b) => a.top - b.top);
    let reach = bands[0].bottom;
    let gap = 0;
    for (const band of bands.slice(1)) {
      if (band.top > reach) gap = Math.max(gap, band.top - reach);
      reach = Math.max(reach, band.bottom);
    }
    // Chegara keng olingan: sarlavha bilan mazmun orasidagi odatdagi
    // nafas ~37% gacha boradi va u xato emas. Faqat mazmun bir chetga
    // siqilib, o'rtada katta teshik qolganda shikoyat qilamiz.
    if (gap > H * 0.42) {
      problems.push("mazmun o'rtasida " + Math.round(gap * 100 / H)
        + "% balandlikda bo'sh tasma qolgan");
    }
  }

  return problems;
}
"""


# Slaydning bir yoni bo'sh qolganini o'lchaydi. Diagramma ko'pincha
# shunday chiqadi: ustunlar qatori chap chekkaga siqilib qoladi va
# o'ng yarmi bo'm-bo'sh turadi. Bu xato emas — slaydni qayta chizish
# shart emas. Bo'sh yonga diagrammani tushuntiruvchi matn qo'yiladi,
# shunda slayd ham to'ladi, mazmuni ham boyiydi.
#
# Balandligi bo'yicha ustma-ust tushgan bo'laklar bitta qator deb
# olinadi va o'sha qatorning eni o'lchanadi. Markazga qo'yilgan blok
# (ikki yoni baravar bo'sh) tegilmaydi — u ataylab shunday.
_GAP_SCRIPT = r"""
() => {
  const W = window.innerWidth, H = window.innerHeight;
  const chunks = [];

  const own = (el) => {
    let text = "";
    for (const node of el.childNodes) {
      if (node.nodeType === 3) text += node.nodeValue;
    }
    return text.trim();
  };

  for (const el of document.body.querySelectorAll("*")) {
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const r = el.getBoundingClientRect();
    if (r.width <= 8 || r.height <= 8) continue;
    if (r.width >= W * 0.95) continue;
    const fill = style.backgroundColor || "";
    const solid = fill.indexOf("rgba(0, 0, 0, 0)") < 0 && fill !== "transparent";
    const drawn = ["IMG", "SVG", "CANVAS", "TABLE"].indexOf(el.tagName) >= 0;
    if (!own(el) && !solid && !drawn) continue;
    chunks.push({top: r.top, bottom: r.bottom, left: r.left, right: r.right});
  }

  const rows = [];
  for (const r of chunks.sort((a, b) => a.top - b.top)) {
    const row = rows.length ? rows[rows.length - 1] : null;
    if (row && r.top < row.bottom - 2) {
      row.left = Math.min(row.left, r.left);
      row.right = Math.max(row.right, r.right);
      row.bottom = Math.max(row.bottom, r.bottom);
    } else {
      rows.push({top: r.top, bottom: r.bottom, left: r.left, right: r.right});
    }
  }

  let best = null;
  for (const row of rows) {
    if (row.bottom - row.top < H * 0.15) continue;
    const leftGap = row.left, rightGap = W - row.right;
    const far = Math.max(leftGap, rightGap);
    const near = Math.min(leftGap, rightGap);
    if (far <= W * 0.30 || near >= W * 0.15) continue;
    const area = {
      side: rightGap >= leftGap ? "right" : "left",
      x: rightGap >= leftGap ? row.right : 0,
      y: row.top,
      w: far,
      h: row.bottom - row.top,
    };
    if (!best || area.w * area.h > best.w * best.h) best = area;
  }
  return best;
}
"""


def gap_area(page):
    """Slaydning bo'sh qolgan yon maydoni (yoki None)."""
    try:
        return page.evaluate(_GAP_SCRIPT)
    except Exception as exc:
        log.warning("Bo'sh yon o'lchanmadi: %s", exc)
        return None


def check_layout(page) -> List[str]:
    """Slaydning joylashuvidagi ko'zga tashlanadigan xatolar ro'yxati."""
    try:
        return [str(item) for item in (page.evaluate(_CHECK_SCRIPT) or [])]
    except Exception as exc:
        log.warning("Joylashuvni tekshirib bo'lmadi: %s", exc)
        return []


def read_layout(page) -> Dict:
    """Sahifadagi elementlarning o'rni, o'lchami va uslubini o'qiydi."""
    return page.evaluate(_SCRIPT)


# Brauzerning element surati ELEMENTNI emas, sahifaning o'sha
# joyini oladi: rasm ustida turgan matn ham suratga tushadi. Muqovada
# butun slaydni egallagan fotosurat bo'lgani uchun sarlavha, ost
# sarlavha va pastki qator rasmning ichiga ham kirib qolardi — keyin
# biz o'sha matnlarni yana haqiqiy matn qutisi qilib ustiga qo'yardik
# va matn ikki marta yozilgandek ko'rinardi.
#
# Shuning uchun surat olishdan oldin rasm ustidagi MATNLAR
# vaqtincha yashiriladi. Bezak qatlamlari (masalan to'q parda)
# yashirilmaydi: ular PowerPointda alohida shakl bo'lib chiqmaydi,
# rasmning ichida qolgani to'g'ri. `visibility: hidden` joylashuvni
# o'zgartirmaydi, shuning uchun qolgan hamma narsa o'z o'rnida qoladi.
_HIDE_SCRIPT = r"""
(shot) => {
  const target = document.querySelector('[data-pptx-shot="' + shot + '"]');
  if (!target) return 0;
  const r = target.getBoundingClientRect();

  // Elementning O'ZIGA tegishli matni bormi (bolalarinikisiz).
  const hasOwnText = (el) => {
    for (const node of el.childNodes) {
      if (node.nodeType === 3 && node.nodeValue.trim()) return true;
    }
    return false;
  };

  const hidden = [];
  for (const el of document.body.querySelectorAll("*")) {
    if (el === target || el.contains(target) || target.contains(el)) continue;
    if (!hasOwnText(el)) continue;
    const b = el.getBoundingClientRect();
    if (b.width < 1 || b.height < 1) continue;
    if (b.right <= r.left || b.left >= r.right
        || b.bottom <= r.top || b.top >= r.bottom) continue;
    hidden.push([el, el.style.getPropertyValue("visibility"),
                 el.style.getPropertyPriority("visibility")]);
    el.style.setProperty("visibility", "hidden", "important");
  }
  window.__pptxHidden = hidden;
  return hidden.length;
}
"""

_SHOW_SCRIPT = r"""
() => {
  for (const item of (window.__pptxHidden || [])) {
    const el = item[0];
    if (item[1]) el.style.setProperty("visibility", item[1], item[2]);
    else el.style.removeProperty("visibility");
  }
  window.__pptxHidden = [];
}
"""


def capture_images(page, blocks: List[Dict], out_dir: str, slide: int) -> None:
    """Diagramma va rasmlarni alohida suratga oladi.

    Har bir surat o'z elementining o'lchamida olinadi, shuning uchun
    PowerPointda cho'zilmaydi. Rasm ustidagi matn suratga tushmaydi —
    u PowerPointda alohida, tahrirlanadigan quti bo'lib qo'yiladi.
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
            try:
                page.evaluate(_HIDE_SCRIPT, block["shot"])
                element.screenshot(path=path, omit_background=True)
            finally:
                page.evaluate(_SHOW_SCRIPT)
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
