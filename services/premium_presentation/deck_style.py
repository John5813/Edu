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
font-size:30px;line-height:1.5;-webkit-font-smoothing:antialiased}

/* ── Varaq ─────────────────────────────────────────────────────── */
.slide{width:1920px;height:1080px;padding:96px;display:flex;
flex-direction:column;gap:56px;overflow:hidden}
.slide>.body{flex:1;display:flex;flex-direction:column;
justify-content:safe center;gap:48px;min-height:0}
/* Asosiy blok qolgan balandlikni EGALLAYDI — shunda varaqning
   pastki yarmi bo'sh qolmaydi. Izoh va sarlavha esa o'z bo'yida
   qoladi. */
.slide>.body>.split,
.slide>.body>table,.slide>.body>.list{flex:1 1 auto}
.slide>.body>.cols{flex:0 1 auto;align-content:center}
/* Qadam kartochkasi ichida bir-ikki gap bo'ladi — butun varaq
   bo'yiga cho'zilsa pastki yarmi bo'sh qoladi. */
.slide>.body>.steps{flex:0 1 auto}
.slide>.body>.timeline{flex:none}
.slide>.body>.note,.slide>.body>.foot,.slide>.body>.lead,
.slide>.body>.formula{flex:none}
.slide>.body>.misol{flex:1 1 auto;justify-content:center}
.cols{align-content:stretch}
.cols>.kpi{justify-content:center}
.timeline .stop{justify-content:flex-start}

/* ── To'q sirt ─────────────────────────────────────────────────── */
/* Ajratkich, muqova va to'q kartochka. Ichidagi HAMMA matn ochiq
   rangga o'tishi kerak: bitta sinf unutilsa, to'q ko'k fonda qora
   matn qolib, umuman o'qilmaydi. Shuning uchun ro'yxat to'liq
   sanaladi, chizuvchida esa qo'shimcha qorovul bor. */
.slide.dark{background:linear-gradient(135deg,#BAND 0%,#BANDDEEP 100%);
color:#INVERT}
.slide.dark .title,.slide.dark .lead,.slide.dark .kpi-value,
.slide.dark .card-title,.slide.dark .item-text,.slide.dark .item-text b,
.slide.dark .quote,.slide.dark .misol-task,.slide.dark .misol-answer,
.slide.dark .formula-body,.slide.dark .kpi-label,.slide.dark .when,
.slide.dark .what,.slide.dark .misol-tag,.slide.dark td,
.slide.dark th{color:#INVERT}
.slide.dark .note,.slide.dark .card-note,.slide.dark .sub,
.slide.dark .kpi-note,.slide.dark .formula-note,.slide.dark .misol-text,
.slide.dark .quote-by,.slide.dark .foot{color:#SOFTINK}
.slide.dark .card,.slide.dark .formula,.slide.dark .misol{background:#BANDCARD}
.slide.dark .kpi{border-left-color:#ACCENT}
.slide.dark .rule,.slide.dark .item-dot,.slide.dark .bead,
.slide.dark .misol-num,.slide.dark .quote-mark{background:#ACCENT}
.slide.dark .quote-mark{background:none;color:#ACCENT}
.slide.dark .frac .dn{border-top-color:#INVERT}
.slide.dark .timeline .stop{border-top-color:#BANDCARD}
.slide.dark tr:nth-child(even) td{background:#BANDCARD}
.slide.dark td{border-bottom-color:#BANDCARD}

/* Bezak: to'q varaqqa chuqurlik beradigan yumshoq doiralar. Ular
   `position:fixed` — joylashuvga tegmaydi, matnning orqasida
   turadi va PowerPointda oddiy shakl bo'lib chiqadi. */
.bezak{position:fixed;border-radius:50%;z-index:0}
/* Bezak mazmun ORTIDA turadi: u ikonka yoki kartochka ustiga
   chiqmasin. */
.slide>.head,.slide>.body{position:relative;z-index:1}
.bezak-a{width:560px;height:560px;right:-120px;top:-150px;
background:#BANDGLOW}
.bezak-b{width:300px;height:300px;left:-60px;bottom:-60px;
background:#BANDSOFT}

/* ── Sarlavhalar ───────────────────────────────────────────────── */
.title{font-size:66px;line-height:1.18;font-weight:700;color:#HEADING;
letter-spacing:-0.5px}
.title.big{font-size:96px;line-height:1.08;
letter-spacing:-1.5px}
.sub{font-size:36px;line-height:1.4;color:#MUTED;font-weight:400}
.lead{font-size:42px;line-height:1.45;color:#BODY;max-width:1400px}
.lead.huge{font-size:60px;line-height:1.35;font-weight:700;color:#HEADING}
.note{font-size:30px;line-height:1.6;color:#MUTED;max-width:1500px}
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
align-items:safe center}
.split.wide-left{grid-template-columns:1.25fr 1fr}
/* Matn va rasm. Rasm chiqmasa o'rnida qo'shimcha matn turadi —
   kartochka ko'rinishida, chap tomonidagi matn bilan teng bo'yda. */
.rasm{align-self:stretch;display:flex;flex-direction:column;
justify-content:center;gap:24px;border-radius:18px;padding:48px;
background:linear-gradient(160deg,#SOFT 0%,#SOFTER 100%);
border-left:8px solid #ACCENT;min-height:420px}
.rasm-matn{font-size:36px;line-height:1.5;color:#BODY}
.rasm.photo-in{padding:0;border:0;background:none;overflow:hidden}
.rasm .photo{width:100%;height:100%;min-height:420px;object-fit:cover;
border-radius:18px;display:block}
.slide.dark .rasm{background:#BANDCARD}
.slide.dark .rasm-matn{color:#FFFFFF}
.split.wide-right{grid-template-columns:1fr 1.25fr}

/* ── Kartochka ─────────────────────────────────────────────────── */
.card{background:linear-gradient(160deg,#SOFT 0%,#SOFTER 100%);
border-radius:18px;padding:44px;min-height:280px;
display:flex;flex-direction:column;justify-content:center;gap:18px}
.card.line{border-bottom:8px solid var(--tone,#ACCENT);
border-radius:18px 18px 0 0}

/* ── Rangli kartochkalar ───────────────────────────────────────── */
/* Har kartochka o'z rangini oladi: ikonka shu rangdagi doira ichida
   oq bo'lib turadi, kartochka shu rangning och tusida, pastida shu
   rangdagi tasma. Eski tizimda aynan shunday edi va eng jonli
   ko'rinadigan qismi shu edi. */
.cols>*:nth-child(5n+1),.ikon-row>*:nth-child(5n+1){--tone:#TONE1;--tint:#TINT1}
.cols>*:nth-child(5n+2),.ikon-row>*:nth-child(5n+2){--tone:#TONE2;--tint:#TINT2}
.cols>*:nth-child(5n+3),.ikon-row>*:nth-child(5n+3){--tone:#TONE3;--tint:#TINT3}
.cols>*:nth-child(5n+4),.ikon-row>*:nth-child(5n+4){--tone:#TONE4;--tint:#TINT4}
.cols>*:nth-child(5n+5),.ikon-row>*:nth-child(5n+5){--tone:#TONE5;--tint:#TINT5}
.cols>.card{background:var(--tint)}
/* Ikonka kartochkaning tepa chetiga yarim chiqib turadi. */
.cols>.card>.ikon-dot:first-child{margin-top:-96px;align-self:center}
.cols:has(>.card>.ikon-dot:first-child){padding-top:56px}
/* Ikonkali kartochkada mazmun tepadan boshlanadi — aks holda doira
   har kartochkada har xil balandlikda turardi. Pastida shu rangdagi
   tasma. */
.cols>.card:has(>.ikon-dot:first-child){justify-content:flex-start;
border-bottom:8px solid var(--tone);border-radius:18px 18px 0 0}
.card.solid,.cols>.card.solid{background:#BAND;color:#INVERT}
.card.solid .card-title,.card.solid .item-text,.card.solid .item-text b,
.card.solid .kpi-value,.card.solid .kpi-label,
.card.solid .misol-task{color:#INVERT}
.card.solid .card-note,.card.solid .kpi-note,
.card.solid .misol-text{color:#SOFTINK}
.card.solid .item-dot,.card.solid .misol-num{background:#ACCENT}
.card-num{font-size:50px;font-weight:700;color:#ACCENT;line-height:1}
.card-title{font-size:42px;font-weight:700;color:#HEADING;line-height:1.25}
.card-note{font-size:33px;line-height:1.55;color:#BODY}

/* ── Ikonka ────────────────────────────────────────────────────── */
/* Ikonka HAR DOIM o'z qatorida turadi: matn oqimiga qo'yilsa
   harflarning ustiga minib qolardi. */
.ikon{width:54px;height:54px;flex:none;display:block}
.ikon-dot{width:104px;height:104px;border-radius:50%;
background:var(--tone,#ACCENT);
display:flex;align-items:center;justify-content:center;flex:none}
.ikon-row{display:flex;gap:32px;align-items:center}

/* ── Ko'rsatkich ───────────────────────────────────────────────── */
.kpi{display:flex;flex-direction:column;gap:14px;align-items:flex-start;
border-left:6px solid #ACCENT;padding-left:32px}
.kpi-value{font-size:96px;line-height:1;font-weight:700;color:#ACCENT;
letter-spacing:-2px}
.kpi-label{font-size:36px;font-weight:700;color:#HEADING}
.kpi-note{font-size:32px;line-height:1.5;color:#MUTED}

/* ── Ro'yxat ───────────────────────────────────────────────────── */
.list{display:flex;flex-direction:column;justify-content:safe center;
gap:34px}
.item{display:flex;gap:24px;align-items:flex-start}
.item-dot{width:16px;height:16px;border-radius:50%;background:#ACCENT;
flex:none;margin-top:23px}
.item-text{font-size:38px;line-height:1.5;color:#BODY}
.item-text b{color:#HEADING}

/* Ro'yxat bandidagi ikonka: nuqta o'rnida rangli doira ichida oq
   ikonka. Har band o'z rangida. */
.item-ikon{width:68px;height:68px;border-radius:50%;flex:none;
background:var(--tone,#ACCENT);display:flex;align-items:center;
justify-content:center}
.item-ikon .ikon{width:36px;height:36px}
.item:has(>.item-ikon){align-items:center;gap:30px}
.list>.item:nth-child(5n+1){--tone:#TONE1}
.list>.item:nth-child(5n+2){--tone:#TONE2}
.list>.item:nth-child(5n+3){--tone:#TONE3}
.list>.item:nth-child(5n+4){--tone:#TONE4}
.list>.item:nth-child(5n+5){--tone:#TONE5}

/* ── Qadamlar ──────────────────────────────────────────────────── */
.steps{display:flex;align-items:stretch;gap:0}
.steps .card{flex:1}
.steps>.card:nth-child(4n+1){--tone:#TONE1;--tint:#TINT1}
.steps>.card:nth-child(4n+3){--tone:#TONE2;--tint:#TINT2}
.steps>.card:nth-child(4n+5){--tone:#TONE3;--tint:#TINT3}
.steps>.card:nth-child(4n+7){--tone:#TONE4;--tint:#TINT4}
.steps>.card{background:var(--tint)}
.steps>.card>.ikon-dot:first-child{margin-top:-96px;align-self:center}
.steps:has(>.card>.ikon-dot:first-child){padding-top:56px}
.steps>.card:has(>.ikon-dot:first-child){justify-content:flex-start;
border-bottom:8px solid var(--tone);border-radius:18px 18px 0 0}
.steps .arrow{width:56px;flex:none;display:flex;align-items:center;
justify-content:center;color:#ACCENT;font-size:38px;font-weight:700}

/* ── Vaqt o'qi ─────────────────────────────────────────────────── */
.timeline{display:flex;gap:0;align-items:stretch}
.timeline .stop{flex:1;display:flex;flex-direction:column;gap:18px;
align-items:center;text-align:center;justify-content:flex-start;
border-top:4px solid #SOFT;padding:0 24px}
.timeline .bead{width:22px;height:22px;border-radius:50%;
background:#ACCENT;flex:none;margin-top:-13px}
.timeline .when{font-size:36px;font-weight:700;color:#ACCENT}
.timeline .what{font-size:30px;line-height:1.5;color:#BODY}

/* ── Iqtibos ───────────────────────────────────────────────────── */
.quote{font-family:SERIF;font-size:48px;line-height:1.45;font-style:italic;
color:#HEADING;max-width:1500px}
.quote-by{font-size:28px;color:#MUTED;margin-top:28px}
.quote-mark{font-family:SERIF;font-size:120px;line-height:0.7;
color:#ACCENT;opacity:1}

/* ── Jadval ────────────────────────────────────────────────────── */
table{width:100%;border-collapse:collapse;font-size:30px}
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
.formula-body{font-family:SERIF;font-size:54px;line-height:1.5;
color:#HEADING}
.formula-note{font-size:30px;line-height:1.5;color:#MUTED}
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
.misol-tag{font-size:24px;font-weight:700;letter-spacing:2px;
text-transform:uppercase;color:#ACCENT}
.misol-task{font-size:36px;font-weight:700;color:#HEADING;
line-height:1.35}
.misol-steps{display:flex;flex-direction:column;gap:18px}
.misol-step{display:flex;gap:20px;align-items:flex-start}
.misol-num{width:48px;height:48px;border-radius:50%;background:#ACCENT;
color:#INVERT;font-size:24px;font-weight:700;flex:none;display:flex;
align-items:center;justify-content:center}
.misol-text{font-size:32px;line-height:1.5;color:#BODY}
.misol-answer{font-size:32px;font-weight:700;color:#HEADING;
border-top:3px solid #ACCENT;padding-top:20px}

/* ── Diagramma ─────────────────────────────────────────────────── */
.chart{width:100%;display:flex;align-items:center;
justify-content:center;min-height:0}
.chart svg{display:block;width:auto;height:auto;max-width:100%;
max-height:100%}

/* ── Pastki qator ──────────────────────────────────────────────── */
.foot{font-size:24px;color:#MUTED;flex:none}
"""


def stylesheet(theme) -> str:
    """Tanlangan rang sxemasidagi CSS."""
    # To'q fon ustidagi kartochka va ikkilamchi matn: aksentni to'q
    # fonga qorishtiramiz, shunda "oq quti" kabi ajralib turmaydi.
    band_card = _mix(theme.band, theme.invert, 0.12)
    soft_ink = _mix(theme.band, theme.invert, 0.72)
    # To'q fon yassi bir rang bo'lsa quruq ko'rinadi. Aksentga
    # ozgina burilgan ikkinchi tus gradient uchun chuqurlik beradi.
    band_deep = _mix(theme.band, theme.accent, 0.32)
    band_glow = _mix(theme.band, theme.accent, 0.20)
    band_soft = _mix(theme.band, theme.invert, 0.07)
    # Kartochka foni ham bir tusdan ikkinchisiga ozgina o'tsin —
    # yassi rang quruq ko'rinadi.
    softer = _mix(theme.accent_soft, theme.background, 0.55)
    # Ikonka ranglari: sariq, ko'k, marjon, yashil, binafsha. Ular
    # mavzu rangidan mustaqil — eski tizimda ham shunday edi va eng
    # jonli ko'rinadigan narsa shu edi. Birinchisi mavzu aksenti.
    tones = [theme.accent] + [t for t in _TONES
                              if _far(t, theme.accent)][:4]
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
        "BANDDEEP": band_deep,
        "BANDGLOW": band_glow,
        "BANDSOFT": band_soft,
        "SOFTER": softer,
        **{f"TONE{i + 1}": tone for i, tone in enumerate(tones)},
        **{f"TINT{i + 1}": _mix(tone, "FFFFFF", 0.87)
           for i, tone in enumerate(tones)},
        "SOFTINK": soft_ink,
    }
    css = _CSS
    # Uzun kalitlar avval almashtiriladi: "BACKGROUND" ichida "BAND"
    # yo'q, lekin "BANDCARD" ichida "BAND" bor.
    for key in sorted(swap, key=len, reverse=True):
        css = css.replace(key, swap[key])
    return css


_TONES = ("E8A33D", "2F7BE0", "EE6C3A", "1FAE7A", "7B61FF", "D6457A")


def _far(one: str, two: str) -> bool:
    """Ikki rang ko'zga yetarlicha farq qiladimi."""
    try:
        a = [int(one[i:i + 2], 16) for i in (0, 2, 4)]
        b = [int(two[i:i + 2], 16) for i in (0, 2, 4)]
    except (ValueError, IndexError):
        return True
    return sum(abs(x - y) for x, y in zip(a, b)) > 140


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

2. MATN VA RASM (bir tomonda matn, bir tomonda rasm):
<div class="split">
  <div class="list"> ... </div>
  <div class="rasm" data-prompt="english description of a documentary photo">
    <p class="rasm-matn">Rasm chiqmasa uning o'rnida turadigan qo'shimcha
    matn: shu mavzuni to'ldiruvchi 2-3 gap (misol, sabab yoki ahamiyat).</p>
  </div>
</div>
`data-prompt` — rasmning inglizcha tavsifi (matn va yozuvsiz). Rasm
chiqsa `rasm-matn` o'rniga rasm turadi; chiqmasa matn qoladi —
shuning uchun u to'liq, mazmunli bo'lsin.

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
    <div class="kpi-note">Raqam nimani anglatishi va nega muhimligini
    tushuntiruvchi 1-2 to'liq gap.</div>
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
  donut uchun bitta qator bering: data-series="Ulush: 45,30,25"
  va nomlarini data-labels ga yozing: data-labels="AQSh,Yevropa,Osiyo".
  Diagramma ostidagi <p class="note"> da raqam nimani bildirishi,
  nega shunday ekani va undan qanday xulosa chiqishi tushuntiriladi."""
