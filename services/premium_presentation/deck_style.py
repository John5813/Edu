"""Taqdimotning dizayn tizimi — CSS ni kod beradi, AI emas.

Nega shunday. Ilgari AI har slayd uchun butun HTML va CSS ni o'zi
yozardi. Erkinlik ko'p edi, lekin natija har safar boshqacha chiqardi:
bir slaydning cheti 72px, boshqasiniki 110px; bir sarlavha markazda,
ikkinchisi chapda; bir kartada soya bor, boshqasida yo'q. Slaydlar
bir-biriga o'xshamagani uchun taqdimot yig'iq ko'rinmasdi. Bundan
tashqari model qutiga qat'iy balandlik berib qo'yar, matn esa
chetidan chiqib ketardi.

Endi taqsimot boshqacha:

  CSS — shu yerda, bir marta va puxta yozilgan.
  AI — faqat MAZMUN yozadi: qaysi blok, ichida qanday matn.

Shuning uchun har slaydning cheti, shrift o'lchami, ranglari va
oraliqlari AYNAN bir xil. Erkinlik yo'qolmaydi: AI bloklarni
xohlagancha aralashtiradi, nechta ustun, qaysi tartib — o'zi
tanlaydi. Faqat piksel darajasida emas, tuzilish darajasida.

Muhim shart: hech bir blokka qat'iy balandlik berilmaydi. Hamma narsa
mazmunga qarab cho'ziladi, shuning uchun matn qutisidan chiqib keta
olmaydi.
"""

from typing import List

SLIDE_W = 1920
SLIDE_H = 1080

# Shrift ikki tomonga mos kelishi kerak: brauzer slaydni shu shrift
# bilan joylashtiradi, PowerPoint esa uni Arial bilan chizadi.
# Liberation Sans aynan Arial bilan o'lchovdosh.
SANS = "Arial, 'Liberation Sans', 'DejaVu Sans', sans-serif"
SERIF = "'Times New Roman', 'Liberation Serif', 'DejaVu Serif', serif"

# Chet. 1920 px da 96 px — bosma taqdimotlardagi odatdagi nisbat.
PAD = 96

_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px;overflow:hidden}
body{font-family:SANS;background:#BACKGROUND;color:#BODY;
font-size:24px;line-height:1.5;-webkit-font-smoothing:antialiased}

/* ── Varaq ─────────────────────────────────────────────────────── */
.slide{width:1920px;height:1080px;padding:96px;display:flex;
flex-direction:column;gap:56px;overflow:hidden}
.slide>.body{flex:1;display:flex;flex-direction:column;
justify-content:center;gap:48px;min-height:0}
/* Asosiy blok qolgan balandlikni EGALLAYDI — shunda varaqning
   pastki yarmi bo'sh qolmaydi. Izoh va sarlavha esa o'z bo'yida
   qoladi. */
.slide>.body>.cols,.slide>.body>.split,.slide>.body>.steps,
.slide>.body>table,.slide>.body>.list{flex:1 1 auto}
.slide>.body>.timeline{flex:none}
.slide>.body>.note,.slide>.body>.foot,.slide>.body>.lead,
.slide>.body>.formula{flex:none}
.slide>.body>.misol{flex:1 1 auto;justify-content:center}
.cols{align-content:stretch}
.cols>.kpi{justify-content:center}
.timeline .stop{justify-content:flex-start}

/* To'q fonli varaq: ajratkich va muqova. */
.slide.dark{background:#BAND;color:#INVERT}
.slide.dark .title,.slide.dark .lead,.slide.dark .kpi-value,
.slide.dark .card-title{color:#INVERT}
.slide.dark .note,.slide.dark .card-note,.slide.dark .sub{color:#SOFTINK}
.slide.dark .card{background:#BANDCARD}
.slide.dark .rule{background:#ACCENT}

/* ── Sarlavhalar ───────────────────────────────────────────────── */
.title{font-size:60px;line-height:1.18;font-weight:700;color:#HEADING;
letter-spacing:-0.5px}
.title.big{font-size:84px;line-height:1.1}
.sub{font-size:30px;line-height:1.4;color:#MUTED;font-weight:400}
.lead{font-size:34px;line-height:1.45;color:#BODY;max-width:1400px}
.lead.huge{font-size:52px;line-height:1.35;font-weight:700;color:#HEADING}
.note{font-size:22px;line-height:1.6;color:#MUTED;max-width:1500px}
.rule{width:120px;height:6px;background:#ACCENT;border-radius:3px;
flex:none}

/* Sarlavha guruhi — sarlavha, ostida ingichka chiziq. */
.head{display:flex;flex-direction:column;gap:24px;flex:none}

/* ── Panjara ───────────────────────────────────────────────────── */
.cols{display:grid;gap:40px;align-items:stretch}
.cols-2{grid-template-columns:repeat(2,1fr)}
.cols-3{grid-template-columns:repeat(3,1fr)}
.cols-4{grid-template-columns:repeat(4,1fr)}
.row{display:flex;gap:40px;align-items:stretch}
.row>*{flex:1}
.split{display:grid;grid-template-columns:1fr 1fr;gap:64px;
align-items:center}
.split.wide-left{grid-template-columns:1.25fr 1fr}
.split.wide-right{grid-template-columns:1fr 1.25fr}

/* ── Kartochka ─────────────────────────────────────────────────── */
.card{background:#SOFT;border-radius:18px;padding:44px;
display:flex;flex-direction:column;justify-content:center;gap:18px}
.card.line{border-top:6px solid #ACCENT;border-radius:0 0 18px 18px}
.card.solid{background:#BAND;color:#INVERT}
.card.solid .card-title{color:#INVERT}
.card.solid .card-note{color:#SOFTINK}
.card-num{font-size:44px;font-weight:700;color:#ACCENT;line-height:1}
.card-title{font-size:30px;font-weight:700;color:#HEADING;line-height:1.25}
.card-note{font-size:22px;line-height:1.55;color:#BODY}

/* ── Ikonka ────────────────────────────────────────────────────── */
/* Ikonka HAR DOIM o'z qatorida turadi: matn oqimiga qo'yilsa
   harflarning ustiga minib qolardi. */
.ikon{width:56px;height:56px;flex:none;display:block}
.ikon-dot{width:96px;height:96px;border-radius:50%;background:#SOFT;
display:flex;align-items:center;justify-content:center;flex:none}
.slide.dark .ikon-dot,.card.solid .ikon-dot{background:#BANDCARD}
.ikon-row{display:flex;gap:32px;align-items:center}

/* ── Ko'rsatkich ───────────────────────────────────────────────── */
.kpi{display:flex;flex-direction:column;gap:12px;align-items:flex-start}
.kpi-value{font-size:88px;line-height:1;font-weight:700;color:#ACCENT;
letter-spacing:-2px}
.kpi-label{font-size:26px;font-weight:700;color:#HEADING}
.kpi-note{font-size:21px;line-height:1.5;color:#MUTED}

/* ── Ro'yxat ───────────────────────────────────────────────────── */
.list{display:flex;flex-direction:column;justify-content:center;
gap:28px}
.item{display:flex;gap:24px;align-items:flex-start}
.item-dot{width:14px;height:14px;border-radius:50%;background:#ACCENT;
flex:none;margin-top:14px}
.item-text{font-size:25px;line-height:1.5;color:#BODY}
.item-text b{color:#HEADING}

/* ── Qadamlar ──────────────────────────────────────────────────── */
.steps{display:flex;align-items:stretch;gap:0}
.steps .card{flex:1}
.steps .arrow{width:56px;flex:none;display:flex;align-items:center;
justify-content:center;color:#ACCENT;font-size:38px;font-weight:700}

/* ── Vaqt o'qi ─────────────────────────────────────────────────── */
.timeline{display:flex;gap:0;align-items:stretch}
.timeline .stop{flex:1;display:flex;flex-direction:column;gap:18px;
align-items:center;text-align:center;justify-content:flex-start;
border-top:4px solid #SOFT;padding:0 24px}
.timeline .bead{width:22px;height:22px;border-radius:50%;
background:#ACCENT;flex:none;margin-top:-13px}
.timeline .when{font-size:28px;font-weight:700;color:#ACCENT}
.timeline .what{font-size:21px;line-height:1.5;color:#BODY}

/* ── Iqtibos ───────────────────────────────────────────────────── */
.quote{font-family:SERIF;font-size:42px;line-height:1.45;font-style:italic;
color:#HEADING;max-width:1500px}
.quote-by{font-size:24px;color:#MUTED;margin-top:28px}
.quote-mark{font-family:SERIF;font-size:120px;line-height:0.7;
color:#ACCENT;opacity:1}

/* ── Jadval ────────────────────────────────────────────────────── */
table{width:100%;border-collapse:collapse;font-size:22px}
th{background:#ACCENT;color:#INVERT;font-weight:700;text-align:left;
padding:20px 24px}
td{padding:18px 24px;border-bottom:1px solid #SOFT;color:#BODY;
vertical-align:top}
tr:nth-child(even) td{background:#SOFT}

/* ── Formula ───────────────────────────────────────────────────── */
/* Formula alohida ko'rinsin: matn oqimiga tiqilgan formula
   o'qilmaydi. Serif shrift matematik yozuvga mos tushadi. */
.formula{background:#SOFT;border-left:8px solid #ACCENT;
border-radius:0 14px 14px 0;padding:36px 44px;display:flex;
flex-direction:column;gap:18px;align-items:flex-start}
.formula-body{font-family:SERIF;font-size:46px;line-height:1.5;
color:#HEADING}
.formula-note{font-size:21px;line-height:1.5;color:#MUTED}
.slide.dark .formula{background:#BANDCARD}
.slide.dark .formula-body{color:#INVERT}

/* Kasr ustma-ust yoziladi. `up` va `dn` alohida element bo'lgani
   uchun ular PowerPointda ham ustma-ust tushadi, oradagi chiziq esa
   alohida tasma bo'lib chiqadi. */
.frac{display:inline-grid;vertical-align:middle;text-align:center;
margin:0 8px}
.frac .up{padding:0 10px 6px}
.frac .dn{padding:6px 10px 0;border-top:3px solid #HEADING}

/* ── Ishlangan misol ───────────────────────────────────────────── */
.misol{background:#SOFT;border-radius:18px;padding:40px;
display:flex;flex-direction:column;gap:22px}
.misol-tag{font-size:20px;font-weight:700;letter-spacing:2px;
text-transform:uppercase;color:#ACCENT}
.misol-task{font-size:30px;font-weight:700;color:#HEADING;
line-height:1.35}
.misol-steps{display:flex;flex-direction:column;gap:18px}
.misol-step{display:flex;gap:20px;align-items:flex-start}
.misol-num{width:38px;height:38px;border-radius:50%;background:#ACCENT;
color:#INVERT;font-size:20px;font-weight:700;flex:none;display:flex;
align-items:center;justify-content:center}
.misol-text{font-size:24px;line-height:1.5;color:#BODY}
.misol-answer{font-size:26px;font-weight:700;color:#HEADING;
border-top:3px solid #ACCENT;padding-top:20px}

/* ── Diagramma ─────────────────────────────────────────────────── */
.chart{width:100%;display:flex;align-items:center;
justify-content:center;min-height:0}
.chart svg{display:block;width:auto;height:auto;max-width:100%;
max-height:100%}

/* ── Pastki qator ──────────────────────────────────────────────── */
.foot{font-size:20px;color:#MUTED;flex:none}
"""


def stylesheet(theme) -> str:
    """Tanlangan rang sxemasidagi CSS."""
    # To'q fon ustidagi kartochka va ikkilamchi matn: aksentni to'q
    # fonga qorishtiramiz, shunda "oq quti" kabi ajralib turmaydi.
    band_card = _mix(theme.band, theme.invert, 0.12)
    soft_ink = _mix(theme.band, theme.invert, 0.72)
    swap = {
        "SANS": SANS,
        "SERIF": SERIF,
        "BACKGROUND": theme.background,
        "HEADING": theme.heading,
        "BODY": theme.body,
        "MUTED": theme.muted,
        "ACCENT": theme.accent,
        "SOFT": theme.accent_soft,
        "BAND": theme.band,
        "INVERT": theme.invert,
        "BANDCARD": band_card,
        "SOFTINK": soft_ink,
    }
    css = _CSS
    # Uzun kalitlar avval almashtiriladi: "BACKGROUND" ichida "BAND"
    # yo'q, lekin "BANDCARD" ichida "BAND" bor.
    for key in sorted(swap, key=len, reverse=True):
        css = css.replace(key, swap[key])
    return css


def _mix(base: str, other: str, ratio: float) -> str:
    """Ikki rangni aralashtiradi (0 — base, 1 — other)."""
    try:
        a = [int(base[i:i + 2], 16) for i in (0, 2, 4)]
        b = [int(other[i:i + 2], 16) for i in (0, 2, 4)]
    except (ValueError, IndexError):
        return base
    return "".join(
        f"{int(round(x * (1 - ratio) + y * ratio)):02X}" for x, y in zip(a, b))


def page(theme, body: str) -> str:
    """Slayd mazmunini to'liq HTML hujjatga o'raydi."""
    return ("<!DOCTYPE html><html><head><meta charset=\"utf-8\"><style>"
            + stylesheet(theme) + "</style></head><body>"
            + body.strip() + "</body></html>")


def wrap_all(theme, bodies: List[str]) -> List[str]:
    return [page(theme, body) for body in bodies if body and body.strip()]


# ────────────────────────────────────────────────────────── blok lug'ati

# AI shu bloklardan slayd yig'adi. Har biri tayyor CSS ga tayanadi,
# shuning uchun o'lchami, oralig'i va rangi kafolatlangan. Erkinlik
# bloklarni tanlash va aralashtirishda qoladi.
BLOCKS = """VARAQNING TUZILISHI (har slayd shunday boshlanadi):

<section class="slide">
  <div class="head">
    <h2 class="title">Slayd sarlavhasi</h2>
    <div class="rule"></div>
  </div>
  <div class="body">
    ... shu yerga quyidagi bloklardan bir-ikkitasi ...
  </div>
</section>

`body` ichidagi narsa varaqning qolgan balandligini o'zi egallaydi —
bo'sh joyni siz hisoblamaysiz.

BLOKLAR:

1. MUQOVA (birinchi slayd; `head` yozilmaydi):
<section class="slide dark">
  <div class="body">
    <h1 class="title big">Mavzu nomi</h1>
    <div class="rule"></div>
    <p class="lead">Bir jumlalik izoh.</p>
    <p class="note">Tayyorladi: ... | Fan: ... | 2026</p>
  </div>
</section>

2. AJRATKICH (har 4-5 slaydda bitta; `head` yozilmaydi):
<section class="slide dark">
  <div class="body">
    <h2 class="title big">Bo'lim nomi</h2>
    <div class="rule"></div>
    <p class="lead">Bo'limni ochadigan bitta jumla.</p>
  </div>
</section>

3. KARTOCHKALAR (2, 3 yoki 4 ta; reja ham shu):
<div class="cols cols-3">
  <div class="card line">
    <div class="ikon-dot"><img class="ikon" data-icon="NOM" alt=""></div>
    <div class="card-num">01</div>
    <div class="card-title">Qisqa sarlavha</div>
    <div class="card-note">Ikki qatorlik izoh.</div>
  </div>
  ... yana kartalar ...
</div>

4. KO'RSATKICHLAR (2-4 ta yirik raqam):
<div class="cols cols-3">
  <div class="kpi">
    <div class="kpi-value">42%</div>
    <div class="kpi-label">Nimani bildiradi</div>
    <div class="kpi-note">Bir qatorlik izoh.</div>
  </div>
</div>

5. RO'YXAT (matnli slaydda):
<div class="list">
  <div class="item"><span class="item-dot"></span>
    <div class="item-text"><b>Kalit so'z.</b> Qolgan jumla.</div></div>
</div>

6. IKKI USTUN (chapda matn, o'ngda diagramma yoki kartalar):
<div class="split">
  <div class="list"> ... </div>
  <div class="chart" data-kind="bar" ...></div>
</div>
`split wide-left` yoki `split wide-right` bilan nisbatni o'zgartirasiz.

7. QADAMLAR (jarayon — o'q bilan):
<div class="steps">
  <div class="card"><div class="card-title">1-qadam</div>
    <div class="card-note">Izoh.</div></div>
  <div class="arrow">&#8594;</div>
  <div class="card"> ... </div>
</div>

8. VAQT O'QI:
<div class="timeline">
  <div class="stop"><span class="bead"></span>
    <div class="when">2003</div>
    <div class="what">Nima bo'lgani.</div></div>
  ... mavzu talab qilgancha to'xtash ...
</div>
Chiziq o'zi chiziladi — siz chizmaysiz.

9. QIYOSLASH (ikki tomon):
<div class="cols cols-2">
  <div class="card"><div class="card-title">Ijobiy</div>
    <div class="list"> ... </div></div>
  <div class="card solid"><div class="card-title">Salbiy</div>
    <div class="list"> ... </div></div>
</div>

10. JADVAL:
<table><tr><th>Ustun</th><th>Ustun</th></tr>
<tr><td>Qiymat</td><td>Qiymat</td></tr></table>

11. IQTIBOS:
<div>
  <div class="quote-mark">&#8220;</div>
  <p class="quote">Iqtibos matni.</p>
  <p class="quote-by">— Muallif, lavozimi</p>
</div>

12. BAYONOT (bitta yirik fikr):
<p class="lead huge">Bitta kuchli jumla.</p>

13. IKONKALAR QATORI (bezak sifatida):
<div class="ikon-row">
  <div class="ikon-dot"><img class="ikon" data-icon="NOM" alt=""></div>
  ... yana ikonkalar ...
</div>

14. FORMULA (matematika, fizika, iqtisod uchun):
<div class="formula">
  <div class="formula-body">Formulaning o'zi</div>
  <div class="formula-note">Belgilar nimani bildiradi.</div>
</div>
Formulani LaTeX bilan yozing — tizim uni chiroyli belgilarga
o'giradi: $x^2$ → x², $\frac{a}{b}$ → ustma-ust kasr,
$\to$ → →, $\infty$ → ∞, $\sqrt{x}$ → √(x), $a_1$ → a₁.

15. ISHLANGAN MISOL (masala va uning yechimi):
<div class="misol">
  <div class="misol-tag">Misol</div>
  <div class="misol-task">Masalaning shartini yozing.</div>
  <div class="misol-steps">
    <div class="misol-step"><span class="misol-num">1</span>
      <div class="misol-text">Birinchi qadam.</div></div>
    <div class="misol-step"><span class="misol-num">2</span>
      <div class="misol-text">Ikkinchi qadam.</div></div>
  </div>
  <div class="misol-answer">Javob: ...</div>
</div>

DIAGRAMMA — siz chizmaysiz, faqat ma'lumot berasiz:
<div class="chart" data-kind="bar" data-labels="2016,2018,2020"
     data-series="Patentlar: 12,18,24|Nashrlar: 20,28,35"
     data-unit="ming dona"></div>
  data-kind: bar (ustunli), line (chiziqli) yoki donut (ulushlar).
  donut uchun bitta qator bering: data-series="Ulush: 45,30,25".
  Diagrammadan keyin ALBATTA <p class="note"> bilan 2-3 gaplik izoh:
  raqam nimani bildiradi, nega shunday, qanday xulosa chiqadi."""
