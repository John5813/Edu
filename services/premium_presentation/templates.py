"""Qat'iy slayd qoliplari — AI faqat mazmun beradi.

Ilgari AI har elementning koordinatasini o'zi tanlardi. Natijada
elementlar ustma-ust tushar, kod ularni surib, shriftni kichraytirib,
ba'zan slaydni AI ga qaytadan yozdirib tuzatardi, oxirida esa har slayd
rasmga aylantirilib vision model bilan tekshirilardi. Bitta taqdimotga
o'ttizga yaqin so'rov ketar, natija esa har safar boshqacha chiqardi.

Endi joylashuv shu yerda, kodda turadi. Har qolip — belgilangan
o'rinlar (`Slot`) to'plami: qayerda, qancha joy, qanday shrift va
qancha belgi sig'adi. AI faqat "qaysi qolip" va "o'rinlarga nima
yozilsin" deb javob beradi. O'rinlar ta'rifan ustma-ust tushmaydi,
shuning uchun tuzatuvchi ham, vizual tekshiruv ham kerak emas.

Sig'im ham shu yerda: matn belgilangan hajmdan oshsa oxirgi tugagan
gapigacha qirqiladi, ya'ni qutidan toshib chiqmaydi.
"""

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from .models import InfographicItem, VisualElement

# 16:9 slayd, dyuymda.
SLIDE_W = 13.333
SLIDE_H = 7.5

# Chekkalar va asosiy o'lchovlar — hamma qolip shulardan foydalanadi,
# shunda taqdimot bo'ylab sarlavha bir xil joyda turadi.
MARGIN = 0.9
CONTENT_W = SLIDE_W - 2 * MARGIN          # 11.533
TITLE_Y = 0.62
TITLE_H = 1.05
BODY_Y = 2.00
BODY_H = SLIDE_H - BODY_Y - 0.75          # 4.75
GUTTER = 0.5


@dataclass(frozen=True)
class Slot:
    """Slayddagi bitta belgilangan o'rin.

    `max_chars` va `max_items` — sig'im. Ular promptda AI ga aytiladi va
    kod tomonidan ham majburlanadi: AI ortiqcha yozsa matn qirqiladi.
    """

    name: str
    kind: str                 # title | text | bullets | quote | caption |
                              # image | chart | cards | steps | timeline |
                              # cycle | pyramid | scheme | kpi | number
    x: float
    y: float
    w: float
    h: float
    size: float = 18.0
    bold: bool = False
    italic: bool = False
    align: str = "left"
    tone: str = "body"        # body | heading | muted | invert | accent
    max_chars: int = 0
    max_items: int = 0
    required: bool = True


@dataclass(frozen=True)
class Template:
    """Bitta qolip: nimaga mos va qanday o'rinlardan iborat."""

    id: str
    purpose: str              # promptdagi bir qatorli tavsif
    slots: Tuple[Slot, ...]
    decor: str = "bar"        # bar | side | none | full | band
    background: str = "FFFFFF"

    def slot(self, name: str) -> Optional[Slot]:
        for item in self.slots:
            if item.name == name:
                return item
        return None

    @property
    def needs_image(self) -> bool:
        return any(s.kind == "image" for s in self.slots)

    @property
    def needs_chart(self) -> bool:
        return any(s.kind == "chart" for s in self.slots)

    @property
    def kinds(self) -> set:
        return {s.kind for s in self.slots}


# ───────────────────────────────────────────── qolip yasash yordamchilari

def _title(size: float = 30.0, y: float = TITLE_Y, w: float = CONTENT_W,
           align: str = "left", chars: int = 70) -> Slot:
    return Slot("title", "title", MARGIN, y, w, TITLE_H, size=size,
                bold=True, align=align, tone="heading", max_chars=chars)


def _text(name: str, x: float, y: float, w: float, h: float,
          size: float = 17.0, chars: int = 420, align: str = "left",
          tone: str = "body", required: bool = True) -> Slot:
    return Slot(name, "text", x, y, w, h, size=size, align=align,
                tone=tone, max_chars=chars, required=required)


def _bullets(name: str, x: float, y: float, w: float, h: float,
             items: int = 4, chars: int = 110, size: float = 17.0) -> Slot:
    return Slot(name, "bullets", x, y, w, h, size=size, tone="body",
                max_items=items, max_chars=chars)


# ─────────────────────────────────────────────────────── KATALOG

def _build_catalogue() -> Dict[str, Template]:
    half = (CONTENT_W - GUTTER) / 2          # 5.52
    third = (CONTENT_W - 2 * GUTTER) / 3     # 3.51

    items: List[Template] = [
        # ── ochilish va yakun ────────────────────────────────────────
        Template(
            "cover",
            "muqova — taqdimot nomi va bir qatorli izoh",
            (
                Slot("title", "title", MARGIN, 2.35, CONTENT_W, 1.9,
                     size=40, bold=True, align="left", tone="heading",
                     max_chars=90),
                _text("subtitle", MARGIN, 4.35, CONTENT_W, 0.8, size=19,
                      chars=120, tone="muted"),
                _text("author", MARGIN, 6.35, CONTENT_W, 0.6, size=15,
                      chars=70, tone="muted", required=False),
            ),
            decor="side",
        ),
        Template(
            "section",
            "bo'lim ajratkich — katta raqam va bo'lim nomi",
            (
                Slot("number", "number", MARGIN, 2.25, 2.2, 1.9,
                     size=64, bold=True, align="left", tone="accent",
                     max_chars=3),
                Slot("title", "title", MARGIN + 2.5, 2.45, CONTENT_W - 2.5,
                     1.5, size=34, bold=True, tone="heading", max_chars=70),
                _text("subtitle", MARGIN + 2.5, 4.05, CONTENT_W - 2.5, 0.9,
                      size=17, chars=150, tone="muted", required=False),
            ),
            decor="band",
        ),
        Template(
            "closing",
            "yakuniy slayd — minnatdorchilik va bir qatorli xulosa",
            (
                Slot("title", "title", MARGIN, 2.9, CONTENT_W, 1.4,
                     size=36, bold=True, align="center", tone="heading",
                     max_chars=60),
                _text("subtitle", MARGIN + 1.5, 4.4, CONTENT_W - 3.0, 1.0,
                      size=18, chars=180, align="center", tone="muted",
                      required=False),
            ),
            decor="band",
        ),

        # ── matnli qoliplar ──────────────────────────────────────────
        Template(
            "statement",
            "bitta kuchli fikr — katta harflarda, boshqa hech narsasiz",
            (
                _title(),
                Slot("statement", "quote", MARGIN + 0.6, 2.6,
                     CONTENT_W - 1.2, 2.4, size=26, bold=False, italic=True,
                     align="center", tone="heading", max_chars=260),
                _text("note", MARGIN + 1.6, 5.4, CONTENT_W - 3.2, 0.8,
                      size=15, chars=140, align="center", tone="muted",
                      required=False),
            ),
        ),
        Template(
            "bullets",
            "sarlavha va 3-5 bandli ro'yxat",
            (
                _title(),
                _bullets("bullets", MARGIN, BODY_Y, CONTENT_W, BODY_H,
                         items=5, chars=130, size=18),
            ),
        ),
        Template(
            "text_block",
            "sarlavha va yaxlit tahliliy matn (ro'yxatsiz)",
            (
                _title(),
                _text("body", MARGIN, BODY_Y, CONTENT_W, BODY_H,
                      size=18, chars=900),
            ),
        ),
        Template(
            "two_text",
            "ikkita mustaqil ustun — har birida kichik sarlavha va matn",
            (
                _title(),
                Slot("left_title", "title", MARGIN, BODY_Y, half, 0.6,
                     size=20, bold=True, tone="accent", max_chars=40),
                _text("left_body", MARGIN, BODY_Y + 0.75, half, BODY_H - 0.75,
                      size=16, chars=420),
                Slot("right_title", "title", MARGIN + half + GUTTER, BODY_Y,
                     half, 0.6, size=20, bold=True, tone="accent",
                     max_chars=40),
                _text("right_body", MARGIN + half + GUTTER, BODY_Y + 0.75,
                      half, BODY_H - 0.75, size=16, chars=420),
            ),
        ),
        Template(
            "three_text",
            "uchta ustun — har birida kalit so'z va bir-ikki jumla",
            (
                _title(),
                Slot("one_title", "title", MARGIN, BODY_Y, third, 0.6,
                     size=18, bold=True, tone="accent", max_chars=30),
                _text("one_body", MARGIN, BODY_Y + 0.7, third, BODY_H - 0.7,
                      size=15, chars=260),
                Slot("two_title", "title", MARGIN + third + GUTTER, BODY_Y,
                     third, 0.6, size=18, bold=True, tone="accent",
                     max_chars=30),
                _text("two_body", MARGIN + third + GUTTER, BODY_Y + 0.7,
                      third, BODY_H - 0.7, size=15, chars=260),
                Slot("three_title", "title", MARGIN + 2 * (third + GUTTER),
                     BODY_Y, third, 0.6, size=18, bold=True, tone="accent",
                     max_chars=30),
                _text("three_body", MARGIN + 2 * (third + GUTTER),
                      BODY_Y + 0.7, third, BODY_H - 0.7, size=15, chars=260),
            ),
        ),
        Template(
            "compare",
            "ikki tomonni qiyoslash — chapda biri, o'ngda ikkinchisi",
            (
                _title(),
                Slot("left_title", "title", MARGIN + 0.3, BODY_Y + 0.25,
                     half - 0.6, 0.6, size=19, bold=True, align="center",
                     tone="heading", max_chars=36),
                _bullets("left_points", MARGIN + 0.3, BODY_Y + 1.0,
                         half - 0.6, BODY_H - 1.3, items=4, chars=90,
                         size=15),
                Slot("right_title", "title", MARGIN + half + GUTTER + 0.3,
                     BODY_Y + 0.25, half - 0.6, 0.6, size=19, bold=True,
                     align="center", tone="heading", max_chars=36),
                _bullets("right_points", MARGIN + half + GUTTER + 0.3,
                         BODY_Y + 1.0, half - 0.6, BODY_H - 1.3, items=4,
                         chars=90, size=15),
            ),
            decor="compare",
        ),

        # ── rasmli qoliplar ──────────────────────────────────────────
        Template(
            "image_right",
            "chapda matn, o'ngda rasm",
            (
                _title(w=half),
                _text("body", MARGIN, BODY_Y, half, BODY_H, size=17,
                      chars=560),
                Slot("image", "image", MARGIN + half + GUTTER, TITLE_Y,
                     half, SLIDE_H - TITLE_Y - 0.75, required=True),
            ),
        ),
        Template(
            "image_left",
            "chapda rasm, o'ngda matn",
            (
                Slot("image", "image", MARGIN, TITLE_Y, half,
                     SLIDE_H - TITLE_Y - 0.75),
                Slot("title", "title", MARGIN + half + GUTTER, TITLE_Y, half,
                     TITLE_H, size=28, bold=True, tone="heading",
                     max_chars=60),
                _text("body", MARGIN + half + GUTTER, BODY_Y, half, BODY_H,
                      size=17, chars=560),
            ),
        ),
        Template(
            "image_hero",
            "butun slaydni egallagan rasm, ustida sarlavha va bir jumla",
            (
                Slot("image", "image", 0.0, 0.0, SLIDE_W, SLIDE_H),
                Slot("title", "title", MARGIN, 4.55, CONTENT_W, 1.1,
                     size=34, bold=True, tone="invert", max_chars=60),
                _text("caption", MARGIN, 5.75, CONTENT_W, 0.9, size=17,
                      chars=170, tone="invert"),
            ),
            decor="full",
        ),
        Template(
            "image_band",
            "tepada keng rasm lentasi, pastida sarlavha va matn",
            (
                Slot("image", "image", 0.0, 0.0, SLIDE_W, 3.15),
                Slot("title", "title", MARGIN, 3.5, CONTENT_W, 0.9,
                     size=27, bold=True, tone="heading", max_chars=60),
                _text("body", MARGIN, 4.5, CONTENT_W, 2.3, size=16,
                      chars=520),
            ),
            decor="none",
        ),
        Template(
            "image_points",
            "chapda rasm, o'ngda sarlavha va qisqa bandlar",
            (
                Slot("image", "image", MARGIN, TITLE_Y, half - 0.4,
                     SLIDE_H - TITLE_Y - 0.75),
                Slot("title", "title", MARGIN + half + GUTTER - 0.4, TITLE_Y,
                     half + 0.4, TITLE_H, size=27, bold=True, tone="heading",
                     max_chars=60),
                _bullets("bullets", MARGIN + half + GUTTER - 0.4, BODY_Y,
                         half + 0.4, BODY_H, items=4, chars=100, size=16),
            ),
        ),

        # ── ma'lumot va raqam ────────────────────────────────────────
        Template(
            "chart_right",
            "chapda tahlil matni, o'ngda diagramma",
            (
                _title(w=half),
                _text("body", MARGIN, BODY_Y, half, BODY_H, size=16,
                      chars=520),
                Slot("chart", "chart", MARGIN + half + GUTTER, BODY_Y - 0.2,
                     half, BODY_H + 0.2),
            ),
        ),
        Template(
            "chart_hero",
            "katta diagramma va uning ostida bitta xulosa jumlasi",
            (
                _title(),
                Slot("chart", "chart", MARGIN, BODY_Y - 0.1, CONTENT_W,
                     BODY_H - 0.85),
                _text("takeaway", MARGIN, SLIDE_H - 1.35, CONTENT_W, 0.75,
                      size=16, chars=200, tone="muted"),
            ),
        ),
        Template(
            "kpi_row",
            "uchta asosiy raqam va ularning ostida izoh",
            (
                _title(),
                Slot("kpi", "kpi", MARGIN, BODY_Y + 0.15, CONTENT_W, 2.85,
                     max_items=3, max_chars=42),
                _text("note", MARGIN, BODY_Y + 3.25, CONTENT_W, 1.3,
                      size=16, chars=300, tone="muted", required=False),
            ),
        ),

        # ── tuzilma va jarayon ───────────────────────────────────────
        Template(
            "cards",
            "3-4 ta teng darajali omil — ikonkali kartochkalar",
            (
                _title(),
                Slot("cards", "cards", MARGIN, BODY_Y, CONTENT_W, BODY_H,
                     max_items=4, max_chars=95),
            ),
        ),
        Template(
            "steps",
            "tartibli bosqichlar — raqamlangan ketma-ketlik",
            (
                _title(),
                Slot("steps", "steps", MARGIN, BODY_Y, CONTENT_W, BODY_H,
                     max_items=4, max_chars=95),
            ),
        ),
        Template(
            "timeline",
            "yillar yoki davrlar ketma-ketligi",
            (
                _title(),
                Slot("timeline", "timeline", MARGIN, BODY_Y, CONTENT_W,
                     BODY_H, max_items=5, max_chars=85),
            ),
        ),
        Template(
            "cycle",
            "takrorlanadigan aylanma jarayon",
            (
                _title(),
                Slot("cycle", "cycle", MARGIN, BODY_Y, CONTENT_W, BODY_H,
                     max_items=4, max_chars=85),
            ),
        ),
        Template(
            "pyramid",
            "darajali ierarxiya — yuqoridan pastga kengayadi",
            (
                _title(),
                Slot("pyramid", "pyramid", MARGIN, BODY_Y, CONTENT_W,
                     BODY_H, max_items=4, max_chars=85),
            ),
        ),
        Template(
            "scheme",
            "tizim yoki tuzilma sxemasi — tarmoqlari bilan",
            (
                _title(),
                Slot("scheme", "scheme", MARGIN, BODY_Y - 0.15, CONTENT_W,
                     BODY_H - 0.7, max_items=5, max_chars=90),
                _text("note", MARGIN, SLIDE_H - 1.25, CONTENT_W, 0.65,
                      size=15, chars=180, tone="muted", required=False),
            ),
        ),
        Template(
            "quote",
            "iqtibos va uning muallifi",
            (
                Slot("quote", "quote", MARGIN + 0.8, 2.3, CONTENT_W - 1.6,
                     2.9, size=25, italic=True, align="center",
                     tone="heading", max_chars=300),
                _text("author", MARGIN + 0.8, 5.5, CONTENT_W - 1.6, 0.7,
                      size=17, align="center", tone="accent", chars=80),
            ),
            decor="band",
        ),
    ]
    return {item.id: item for item in items}


CATALOGUE: Dict[str, Template] = _build_catalogue()
TEMPLATE_IDS = tuple(CATALOGUE)

# Ochilish va yakun uchun ajratilgan qoliplar — ular o'rtada
# takrorlanmasligi kerak.
OPENING_IDS = ("cover",)
CLOSING_IDS = ("closing", "quote")
# O'rtada ishlatiladigan qoliplar.
BODY_IDS = tuple(
    key for key in CATALOGUE
    if key not in OPENING_IDS and key not in ("closing",)
)


def get(template_id: str) -> Template:
    """Qolipni nomi bo'yicha beradi; nomi noto'g'ri bo'lsa — matnli qolip.

    AI ro'yxatda yo'q nom qaytarishi mumkin. Bunda taqdimot to'xtamaydi:
    mazmun eng universal qolipga tushadi.
    """
    return CATALOGUE.get((template_id or "").strip().lower(),
                         CATALOGUE["text_block"])


def catalogue_prompt() -> str:
    """Promptga qo'yiladigan qoliplar ro'yxati.

    Har qator: qolip nomi, nimaga mosligi va qaysi o'rinlarni qanday
    sig'im bilan to'ldirish kerakligi. AI koordinata o'ylamaydi —
    faqat shu o'rinlarni to'ldiradi.
    """
    lines = []
    for template in CATALOGUE.values():
        parts = []
        for slot in template.slots:
            if slot.kind in ("bullets", "cards", "steps", "timeline",
                             "cycle", "pyramid", "scheme", "kpi"):
                parts.append(
                    f"{slot.name}: {slot.max_items} tagacha band, "
                    f"har biri {slot.max_chars} belgigacha"
                )
            elif slot.kind == "image":
                parts.append("image: rasm tavsifi (ingliz tilida, matnsiz)")
            elif slot.kind == "chart":
                parts.append("chart: diagramma ma'lumoti")
            elif slot.kind == "number":
                parts.append("number: 1-2 belgili raqam")
            else:
                optional = "" if slot.required else ", ixtiyoriy"
                parts.append(f"{slot.name}: {slot.max_chars} belgigacha{optional}")
        lines.append(f"- {template.id} — {template.purpose}\n    " +
                     "; ".join(parts))
    return "\n".join(lines)
