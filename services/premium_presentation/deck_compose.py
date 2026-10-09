"""Kam matnli taqdimot: kompozitsiyalar (joylashuv) va ularning CSS i.

Ko'p matnli taqdimotda model tayyor bloklardan (kartochka, ro'yxat, matn va rasm ...) slaydni o'zi
teradi. Natija toza, lekin bir-biriga o'xshaydi: rasm doim o'ngda, matn bo'laklarga bo'linadi.

Kam matnli taqdimotda har slayd bitta KOMPOZITSIYA bo'yicha yoziladi: rasm chapda chetigacha, butun
fon ustida karta, tepada keng lenta, o'ngda tor ustun; to'q fondagi raqamlar, ikki yarim varaqli
qiyos, vaqt o'qi, formula, misol. Har kompozitsiyaning joyi va o'lchami CSS da qat'iy (sig'ishi
kafolatlangan), matn hajmi esa promptda har maydon uchun aytiladi — matn joyga qarab yoziladi,
keyin kichraytirilmaydi.

Kompozitsiyani reja kategoriyasidan KOD tanlaydi (`assign`): mazmun turi (raqam, jarayon, qiyos,
iqtibos ...) AI ning rejasidan keladi, rasmli slaydlarda esa rasm joyi navbatma-navbat almashadi —
ketma-ket ikki slayd bir xil ko'rinmaydi. Matn kompozitsiya tilida (sinf nomlari) emas, mijoz
tanlagan tilda yoziladi; tavsiflar `prompts.<til>.KAM` da.
"""
import re
import zlib
from typing import Dict, List

# ────────────────────────────────────────────────────────── kompozitsiyalar

# Har kompozitsiyaning HTML qolipi. "…" — model to'ldiradigan joy; tavsif va so'z chegarasi
# `prompts.<til>.KAM["layouts"]` da (tilga bog'liq), qolip esa hamma til uchun bitta.
LAYOUTS: Dict[str, str] = {
    "muqova": """<section class="slide dark">
  <div class="body">
    <h1 class="title big">…</h1>
    <div class="rule"></div>
    <p class="lead">…</p>
  </div>
</section>""",
    "rasm_chap": """<section class="slide k k-rasm-chap">
  <div class="rasm" data-prompt="english description of a realistic photo"><p class="rasm-matn">…</p></div>
  <div class="k-text">
    <h2 class="title">…</h2>
    <p class="lead">…</p>
    <p class="k-p">…</p>
  </div>
</section>""",
    "rasm_ong": """<section class="slide k k-rasm-ong">
  <div class="k-text">
    <h2 class="title">…</h2>
    <p class="k-p">…</p>
  </div>
  <div class="rasm" data-prompt="english description of a realistic photo"><p class="rasm-matn">…</p></div>
</section>""",
    "rasm_tepa": """<section class="slide k k-rasm-tepa">
  <div class="rasm" data-prompt="english description of a wide realistic photo"><p class="rasm-matn">…</p></div>
  <div class="k-text">
    <h2 class="title">…</h2>
    <p class="k-p">…</p>
  </div>
</section>""",
    "rasm_fon": """<section class="slide k k-rasm-fon">
  <div class="rasm" data-prompt="english description of a realistic photo"><p class="rasm-matn">…</p></div>
  <div class="k-text">
    <h2 class="title">…</h2>
    <p class="k-p">…</p>
  </div>
</section>""",
    "iqtibos": """<section class="slide k k-iqtibos">
  <div class="rasm" data-prompt="english description of a realistic photo"><p class="rasm-matn">…</p></div>
  <div class="k-text">
    <h2 class="title">…</h2>
    <p class="quote">…</p>
    <p class="quote-by">— …</p>
    <p class="k-p">…</p>
  </div>
</section>""",
    "raqamlar": """<section class="slide k k-raqamlar">
  <div class="k-text">
    <h2 class="title">…</h2>
    <div class="k-row">
      <div class="k-kpi"><div class="k-num"><p class="k-v">…</p><p class="k-u">…</p></div><p class="k-l">…</p><p class="k-d">…</p></div>
      … (2-4 × k-kpi)
    </div>
    <p class="k-src">…</p>
  </div>
</section>""",
    "bosqichlar": """<section class="slide k k-bosqichlar">
  <div class="k-text">
    <h2 class="title">…</h2>
    <p class="lead">…</p>
    <div class="k-row">
      <div class="k-step"><p class="k-n">01</p><p class="k-h">…</p><p class="k-d">…</p></div>
      … (3-5 × k-step)
    </div>
  </div>
</section>""",
    "vaqt": """<section class="slide k k-vaqt">
  <div class="rasm" data-prompt="english description of a realistic photo"><p class="rasm-matn">…</p></div>
  <div class="k-text">
    <h2 class="title">…</h2>
    <div class="k-axis">
      <div class="k-stop"><p class="k-y">…</p><p class="k-yd">…</p></div>
      … (3-5 × k-stop)
    </div>
  </div>
</section>""",
    "qiyos": """<section class="slide k k-qiyos">
  <h2 class="title">…</h2>
  <div class="k-half a">
    <p class="k-q">…</p>
    <p class="k-h2">…</p>
    <div class="k-items"><p class="k-li"><i></i><span>…</span></p> … (3 × k-li)</div>
  </div>
  <div class="k-half b">
    <p class="k-q">…</p>
    <p class="k-h2">…</p>
    <div class="k-items"><p class="k-li"><i></i><span>…</span></p> … (3 × k-li)</div>
  </div>
</section>""",
    "diagramma": """<section class="slide k k-diagramma">
  <div class="k-text">
    <h2 class="title">…</h2>
    <p class="lead">…</p>
    ⟨chart⟩
    <p class="k-p">…</p>
  </div>
</section>""",
    "formula": """<section class="slide k k-formula">
  <div class="k-text">
    <h2 class="title">…</h2>
    <div class="k-pair">
      <div class="formula"><div class="formula-body">$…$</div><div class="formula-note">…</div></div>
      <div class="k-col"><p class="lead">…</p><p class="k-p">…</p></div>
    </div>
  </div>
</section>""",
    "misol": """<section class="slide k k-misol">
  <div class="k-text">
    <h2 class="title">…</h2>
    <div class="misol">
      <div class="misol-tag">…</div>
      <div class="misol-task">…</div>
      <div class="misol-steps">
        <div class="misol-step"><span class="misol-num">1</span><div class="misol-text">…</div></div>
        … (2-4 × misol-step)
      </div>
      <div class="misol-answer">…</div>
    </div>
  </div>
  <div class="rasm" data-prompt="english description of a realistic photo"><p class="rasm-matn">…</p></div>
</section>""",
    "kartalar": """<section class="slide k k-kartalar">
  <div class="k-text">
    <h2 class="title">…</h2>
    <p class="lead">…</p>
    <div class="k-row">
      <div class="k-card"><p class="k-h">…</p><p class="k-d">…</p></div>
      … (3-5 × k-card)
    </div>
  </div>
</section>""",
    "yakun": """<section class="slide k k-yakun">
  <div class="k-text">
    <h2 class="title">…</h2>
    <p class="lead">…</p>
    <p class="k-ln"><i></i><span>…</span></p>
    … (3 × k-ln)
  </div>
</section>""",
}

# Rasm joyi navbatma-navbat almashadigan kompozitsiyalar ("matn_rasm" kategoriyasi).
PHOTO_LAYOUTS = ("rasm_chap", "rasm_ong", "rasm_tepa")
# Endi yozilmaydigan kompozitsiyalar: "butun fon rasm, ustida oq karta" juda oddiy ko'rinardi. Qolipi
# faqat avval saqlangan taqdimotlarni o'qish uchun turadi; modelga taklif qilinmaydi.
RETIRED = ("rasm_fon",)
# Rasmi bo'lgan kompozitsiyalar (rasm kvotasini hisoblashda).
WITH_PHOTO = PHOTO_LAYOUTS + ("iqtibos",)
# Rasm ixtiyoriy kompozitsiyalar: rasm kvotasidan ortiq bo'lsa rasm bloki olib tashlanadi.
OPTIONAL_PHOTO = ("vaqt", "misol")

# Reja kategoriyasi → kompozitsiya. Mazmun turini reja (AI) belgilaydi, ko'rinishni — kod.
CATEGORY_LAYOUT = {
    "muqova": "muqova", "reja": "reja", "yakun": "yakun",
    "iqtibos": "iqtibos", "korsatkichlar": "raqamlar", "jarayon": "bosqichlar",
    "vaqt_oqi": "vaqt", "qiyoslash": "qiyos", "ikki_ustun": "qiyos", "diagramma": "diagramma",
    "formula": "formula", "misol": "misol", "kartalar": "kartalar", "tuzilma": "kartalar",
    "jadval": "kartalar",
}

# Bitta slayddagi matn (sarlavhasiz) shundan oshsa — slayd qisqartirib qayta yoziladi.
# Kam matnli sahifaning punktlari vektor infografikada keng joy oladi: izoh 12-20 so'z (ilgari 12-15
# so'z — slayd bo'sh ko'rinardi).
WORD_LIMIT = {"kam": 110, "kop": 100}


def assign(outline: List[Dict], topic: str = "") -> List[Dict]:
    """Har slaydga kompozitsiya (`layout`) beradi.

    Rasmli slaydlarda rasm joyi navbat bilan almashadi; boshlanish nuqtasi mavzuga qarab — ikki
    taqdimot bir xil tartibda boshlanmasin. Ketma-ket kelgan ikki rasmli slayd hech qachon bir xil
    joylashuvda bo'lmaydi.
    """
    turn = zlib.crc32((topic or "").encode("utf-8")) % len(PHOTO_LAYOUTS)
    previous = ""
    for item in outline:
        category = item.get("category") or ""
        if category == "matn_rasm":
            layout = PHOTO_LAYOUTS[turn % len(PHOTO_LAYOUTS)]
            if layout == previous:
                turn += 1
                layout = PHOTO_LAYOUTS[turn % len(PHOTO_LAYOUTS)]
            turn += 1
        else:
            layout = CATEGORY_LAYOUT.get(category, "kartalar")
        item["layout"] = layout
        previous = layout
    return outline


def layout_for(category: str, neighbours=()) -> str:
    """Bitta slayd uchun kompozitsiya (saytda sahifani qayta yozishda): rasmli bo'lsa qo'shnilaridan
    farq qiladigan rasm joyi tanlanadi."""
    if category != "matn_rasm":
        return CATEGORY_LAYOUT.get(category, "kartalar")
    for layout in PHOTO_LAYOUTS:
        if layout not in neighbours:
            return layout
    return PHOTO_LAYOUTS[0]


def catalogue(language: str = "uz") -> str:
    """Modelga beriladigan kompozitsiyalar ro'yxati: qolip va (taqdimot tilida) tavsif."""
    from . import prompts

    texts = prompts.get(language).KAM["layouts"]
    texts_chart = prompts.get(language).KAM["chart_slot"]
    parts = []
    for key, html in LAYOUTS.items():
        if key in RETIRED:
            continue
        note = texts.get(key)
        if note:
            parts.append(f"[{key}] — {note}\n" + html.replace("⟨chart⟩", texts_chart))
    return "\n\n".join(parts)


def shell(language: str, marker: str) -> str:
    """Kam matnli taqdimotning tizim prompti (taqdimot tilida)."""
    from . import prompts

    K = prompts.get(language).KAM
    return prompts.fill(K["shell"], target=prompts.target(language), layouts=catalogue(language),
                        marker=marker)


_TITLE_BLOCK = re.compile(r"<h[12]\b[^>]*>.*?</h[12]>", re.IGNORECASE | re.DOTALL)
_PROMPT_ATTR = re.compile(r'\sdata-prompt\s*=\s*(["\']).*?\1', re.IGNORECASE | re.DOTALL)
_RASM_TEXT = re.compile(r'<p\b[^>]*\bclass\s*=\s*["\'][^"\']*\brasm-matn\b[^>]*>.*?</p>',
                        re.IGNORECASE | re.DOTALL)
_CHART_DIV = re.compile(r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*\b(?:chart|calc)\b[^>]*>\s*</div>',
                        re.IGNORECASE | re.DOTALL)


def words(body: str) -> int:
    """Slayddagi o'qiladigan matn so'zlari: sarlavha, rasm tavsifi, rasm o'rnidagi zaxira matn va
    diagramma ma'lumoti hisobga kirmaydi."""
    from . import deck_logic

    text = _TITLE_BLOCK.sub(" ", body or "")
    text = _RASM_TEXT.sub(" ", _PROMPT_ATTR.sub("", text))
    text = _CHART_DIV.sub(" ", text)
    return len(deck_logic.plain(text).split())


def too_long(body: str, volume: str) -> bool:
    return words(body) > WORD_LIMIT.get(volume, WORD_LIMIT["kop"])


_SECTION_CLASS = re.compile(r'<section\b[^>]*\bclass\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def layout_of(body: str) -> str:
    """Slayd qaysi kompozitsiyada yozilgan ("" — kompozitsiyasiz, ko'p matnli blok)."""
    match = _SECTION_CLASS.search(body or "")
    if not match:
        return ""
    for name in match.group(1).split():
        if name.startswith("k-") and name[2:].replace("-", "_") in LAYOUTS:
            return name[2:].replace("-", "_")
    return ""


# ──────────────────────────────────────────────────────────────── CSS
#
# Kalit so'zlar (#HEADING, #ACCENT, HEADFONT ...) `deck_style.stylesheet` da rang sxemasi bilan
# almashtiriladi. Faqat tekis rang, chiziqli gradient va chegara: `html_extract` ularni PowerPointning
# haqiqiy shakllariga o'tkazadi. Rasm ustidagi karta — alohida quti (rasm suratiga matn tushmaydi).

CSS = """
/* ── Kam matnli taqdimot: kompozitsiyalar ─────────────────────────── */
.slide.k{padding:0;display:block;position:relative;gap:0}
.k .k-text{position:absolute;display:flex;flex-direction:column;justify-content:center;gap:36px}
.k .title{font-family:HEADFONT;font-size:66px;line-height:1.15;color:#HEADING;font-weight:700}
.k .lead{font-family:HEADFONT;font-size:44px;line-height:1.35;color:#HEADING;max-width:none}
.k .k-p{font-size:36px;line-height:1.6;color:#BODY}
.k .k-src{font-size:24px;line-height:1.4;color:#MUTED}
.k .rasm{position:absolute;min-height:0;margin:0;border-radius:0;border:0;padding:56px;
justify-content:center}
.k .rasm.photo-in{padding:0;background:none}
.k .rasm .photo{min-height:0;width:100%;height:100%;border-radius:0;object-fit:cover}
.k .rasm-matn{font-size:34px}

/* Rasm chapda, chetigacha */
.k-rasm-chap .rasm{left:0;top:0;width:820px;height:1080px}
.k-rasm-chap .k-text{left:920px;right:110px;top:96px;bottom:96px}
/* Rasm o'ngda, tor ustun */
.k-rasm-ong .rasm{right:96px;top:96px;width:560px;height:888px;border-radius:18px;overflow:hidden}
.k-rasm-ong .rasm .photo{border-radius:18px}
.k-rasm-ong .k-text{left:110px;width:1040px;top:96px;bottom:96px}
/* Tepada keng rasm, pastda sarlavha va matn yonma-yon */
.k-rasm-tepa .rasm{left:0;top:0;width:1920px;height:500px}
.k-rasm-tepa .k-text{left:110px;right:110px;top:500px;bottom:0;flex-direction:row;
align-items:center;gap:96px}
.k-rasm-tepa .title{flex:0 0 620px}
.k-rasm-tepa .k-p{flex:1}
/* Butun fon rasm, ustida karta */
.k-rasm-fon .rasm{left:0;top:0;width:1920px;height:1080px}
.k-rasm-fon .k-text{right:96px;bottom:96px;width:920px;padding:56px 64px;gap:28px;
background:#BACKGROUND;justify-content:flex-start}
.k-rasm-fon .title{font-size:56px}
/* Iqtibos: rasm chapda, katta iqtibos */
.k-iqtibos .rasm{left:0;top:0;width:760px;height:1080px}
.k-iqtibos .k-text{left:860px;right:120px;top:96px;bottom:96px;gap:40px}
.k-iqtibos .title{font-family:SANS;font-size:30px;line-height:1.3;color:#ACCENT;letter-spacing:1px}
.k .quote{font-family:SERIF;font-style:italic;font-size:54px;line-height:1.35;color:#HEADING}
.k .quote-by{font-size:30px;color:#MUTED}
/* Raqamlar: to'q fon */
.slide.k-raqamlar,.slide.k-yakun{background:linear-gradient(135deg,#BAND 0%,#BANDDEEP 100%)}
.k-raqamlar .k-text{left:110px;right:110px;top:96px;bottom:96px;gap:72px}
.k-raqamlar .title{color:#INVERT}
.k .k-row{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:64px}
.k-v{font-family:HEADFONT;font-size:128px;line-height:1.15;color:#GLOWINK;font-weight:700}
.k-num{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.k-u{font-family:HEADFONT;font-size:48px;line-height:1.2;color:#GLOWINK;font-weight:700}
.k-l{font-size:42px;line-height:1.25;color:#INVERT;font-weight:700;margin-top:24px}
.k .k-d{font-size:32px;line-height:1.5;color:#BODY}
.k-raqamlar .k-kpi .k-d{color:#SOFTINK;margin-top:10px}
.k-raqamlar .k-text .k-src{color:#SOFTINK}
/* Bosqichlar */
.k-bosqichlar .k-text,.k-kartalar .k-text,.k-diagramma .k-text,.k-formula .k-text{
left:110px;right:110px;top:96px;bottom:96px;gap:48px}
.k-step{padding:0 36px;border-left:2px solid #ACCENT}
.k-step:first-child{border-left:0;padding-left:0}
.k-n{font-family:HEADFONT;font-size:100px;line-height:1.15;color:#ACCENT;margin-bottom:8px}
.k .k-h{font-family:HEADFONT;font-size:42px;line-height:1.25;color:#HEADING;font-weight:700;
margin-bottom:12px}
/* Vaqt o'qi (rasm ixtiyoriy) */
.k-vaqt .rasm{left:96px;top:96px;width:520px;height:888px;border-radius:18px;overflow:hidden}
.k-vaqt .rasm .photo{border-radius:18px}
.k-vaqt .k-text{left:110px;right:110px;top:96px;bottom:96px;gap:52px}
.k-vaqt:has(.rasm) .k-text{left:720px}
.k-axis{display:flex;flex-direction:column;gap:36px;border-left:4px solid #ACCENT;padding-left:48px}
.k-y{font-family:HEADFONT;font-size:54px;line-height:1.15;color:#ACCENT;font-weight:700}
.k-yd{font-size:34px;line-height:1.45;color:#BODY;margin-top:10px}
/* Qiyos: ikki yarim varaq */
.k-qiyos>.title{position:absolute;left:96px;top:72px;width:768px;font-family:SANS;font-size:32px;
line-height:1.3;color:#ACCENT;letter-spacing:1px;z-index:1}
.k-half{position:absolute;top:0;bottom:0;width:960px;padding:170px 96px 110px;display:flex;
flex-direction:column;gap:28px;justify-content:center}
.k-half.a{left:0;background:#BACKGROUND}
.k-half.b{right:0;background:linear-gradient(160deg,#BAND 0%,#BANDDEEP 100%)}
.k-q{font-size:30px;line-height:1.3;color:#MUTED}
.k-h2{font-family:HEADFONT;font-size:58px;line-height:1.15;color:#HEADING;font-weight:700}
.k-items{display:flex;flex-direction:column;gap:22px}
.k-li{display:flex;gap:24px;align-items:baseline;font-size:38px;line-height:1.45;color:#BODY}
.k-li i{flex:none;width:16px;height:16px;border-radius:8px;background:#ACCENT;
transform:translateY(-6px)}
.k-half.b .k-h2,.k-half.b .k-li{color:#INVERT}
.k-half.b .k-q{color:#GLOWINK}
.k-half.b .k-li i{background:#GLOWINK}
/* Diagramma: butun kenglikda */
.k-diagramma .chart{width:1500px;align-self:center}
/* Formula */
.k-pair{display:grid;grid-template-columns:1.1fr 1fr;gap:96px;align-items:center}
.k-col{display:flex;flex-direction:column;gap:28px}
.k-formula .formula-body{font-size:76px}
/* Misol (rasm ixtiyoriy) */
.k-misol .rasm{right:96px;top:96px;width:520px;height:888px;border-radius:18px;overflow:hidden}
.k-misol .rasm .photo{border-radius:18px}
.k-misol .k-text{left:110px;right:110px;top:96px;bottom:96px;gap:32px}
.k-misol:has(.rasm) .k-text{right:720px}
/* Kartalar */
.k-card{background:#SOFT;border-radius:18px;padding:44px;display:flex;flex-direction:column;gap:12px}
/* Xulosa: to'q fon */
.k-yakun .k-text{left:160px;right:160px;top:96px;bottom:96px;gap:44px}
.k-yakun .title{font-family:SANS;font-size:32px;line-height:1.3;color:#GLOWINK;letter-spacing:1px}
.k-yakun .lead{color:#INVERT;font-size:58px}
.k-ln{display:flex;gap:28px;align-items:center;font-size:38px;line-height:1.4;color:#SOFTINK}
.k-ln i{flex:none;width:8px;height:56px;background:#GLOWINK}

/* Muqova: varaqning chap yarmi — to'q fonda katta sarlavha, o'ng yarmi — rasm */
.slide.cover-photo>.body.cover-split{display:block;position:relative;padding:0;height:1080px}
.slide.cover-photo .rasm.cover-img{position:absolute;left:960px;top:0;width:960px;height:1080px}
.slide.cover-photo .cover-text{position:absolute;left:0;top:0;width:960px;height:1080px;
padding:110px 96px 120px;gap:40px;justify-content:flex-end;
background:linear-gradient(160deg,#BAND 0%,#BANDDEEP 100%)}
.slide.cover-photo .title.big{font-size:112px;line-height:1.15;color:#INVERT}
/* Uzun mavzu nomi: sig'dirish bosqichlarida sarlavha kichrayadi (umumiy `.fit2 .title` bu yerga yetmaydi). */
.slide.cover-photo.fit1 .title.big{font-size:96px}
.slide.cover-photo.fit2 .title.big{font-size:84px}
.slide.cover-photo.fit3 .title.big{font-size:72px}
.slide.cover-photo .cover-text .lead,.slide.cover-photo .cover-text .sub,
.slide.cover-photo .cover-text .note{color:#SOFTINK;font-size:40px;line-height:1.4}
.slide.cover-photo .cover-text .rule{background:#GLOWINK;width:120px;height:8px}
"""
