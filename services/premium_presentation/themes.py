"""Taqdimot rang sxemalari.

Rang bitta joyda turadi: qolip faqat "bu matn sarlavhami, izohmi,
urg'umi" deb aytadi (`Slot.tone`), rangni esa shu modul beradi. Shuning
uchun sxemani almashtirish butun taqdimotni qayta bo'yaydi — qolip
kodiga tegmasdan.

Mijoz sxemani o'zi tanlaydi; tanlamasa mavzuga qarab mos keladigani
olinadi (masalan tibbiyot mavzusiga yashil, moliyaga to'q ko'k).
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Theme:
    """Bitta rang sxemasi.

    `invert` — to'q fon yoki rasm ustidagi matn rangi; `chart` esa
    diagramma qatorlari uchun ketma-ketlik.
    """

    key: str
    name: str                 # mijozga ko'rsatiladigan nom
    background: str           # slayd foni
    heading: str              # sarlavhalar
    body: str                 # asosiy matn
    muted: str                # izoh, ikkinchi darajali matn
    accent: str               # urg'u: raqam, kalit so'z, bezak
    accent_soft: str          # urg'uning och varianti — panel foni
    invert: str = "FFFFFF"    # to'q fon ustidagi matn
    dark: str = ""            # to'q bezak (ajratkich slayd foni)
    chart: Tuple[str, ...] = ()

    @property
    def band(self) -> str:
        """Ajratkich va yakuniy slayd foni."""
        return self.dark or self.accent


def _theme(key, name, background, heading, body, muted, accent,
           accent_soft, dark, chart) -> Theme:
    return Theme(key=key, name=name, background=background, heading=heading,
                 body=body, muted=muted, accent=accent,
                 accent_soft=accent_soft, dark=dark, chart=tuple(chart))


THEMES: Dict[str, Theme] = {t.key: t for t in (
    _theme("ko'k", "Ko'k — universal, ishbilarmon",
           "FFFFFF", "10243F", "27374D", "6B7A90", "1F6FEB", "E8F1FE",
           "10243F", ("1F6FEB", "54A0FF", "0B3C91", "8FC0FF", "173B6C")),
    _theme("to'q ko'k", "To'q ko'k — jiddiy, akademik",
           "FFFFFF", "0B1B33", "1F2D45", "68758C", "2E5AAC", "E7EDF9",
           "0B1B33", ("2E5AAC", "6E93D6", "13305F", "A8C0E8", "1C4179")),
    _theme("yashil", "Yashil — tabiat, tibbiyot, ekologiya",
           "FFFFFF", "0F2E22", "234437", "6C8478", "1E8E5A", "E4F5EC",
           "0F2E22", ("1E8E5A", "57C98C", "0C5C39", "9BE0BC", "146B47")),
    _theme("zumrad", "Zumrad — zamonaviy, texnologik",
           "FFFFFF", "07302E", "1B4744", "6B8886", "0F9B8E", "E1F5F3",
           "07302E", ("0F9B8E", "4FCFC3", "0A6B63", "98E3DC", "137A72")),
    _theme("binafsha", "Binafsha — ijodiy, ta'lim",
           "FFFFFF", "241340", "382454", "7A6E93", "6B3FD4", "EFE9FC",
           "241340", ("6B3FD4", "9B78EA", "44219B", "C3ACF5", "533099")),
    _theme("qizil", "Qizil — kuchli, e'tibor tortadigan",
           "FFFFFF", "3A1113", "52201F", "8E7573", "C1272D", "FBE9E9",
           "3A1113", ("C1272D", "E4675C", "87161B", "F2A6A0", "A32026")),
    _theme("to'q sariq", "To'q sariq — energiya, tadbirkorlik",
           "FFFFFF", "3A2408", "553A14", "8D7A5F", "D97706", "FDF0DC",
           "3A2408", ("D97706", "F0A94A", "96530A", "F8CE94", "B26205")),
    _theme("kulrang", "Kulrang — quruq, rasmiy hisobot",
           "FFFFFF", "1B1F24", "343A42", "737C87", "455A70", "ECEFF3",
           "1B1F24", ("455A70", "7D93A8", "2C3B4C", "A9BACA", "5E7285")),
)}

DEFAULT_KEY = "ko'k"
THEME_KEYS: List[str] = list(THEMES)

# Mavzuda shu so'z uchrasa — shu sxema. Mijoz o'zi tanlamaganda
# ishlatiladi: tibbiyot haqidagi taqdimot qizil emas, yashil bo'lgani
# tabiiyroq.
_HINTS = (
    ("yashil", ("tibbiyot", "sog'liq", "shifo", "ekologi", "tabiat", "atrof-muhit",
                "qishloq xo'jali", "oziq-ovqat", "медицин", "эколог", "health",
                "ecology", "agricult", "green")),
    ("to'q ko'k", ("moliya", "bank", "budjet", "byudjet", "soliq", "iqtisod",
                   "investitsiya", "audit", "финанс", "банк", "эконом",
                   "finance", "bank", "econom")),
    ("zumrad", ("texnologi", "raqamli", "dastur", "sun'iy intellekt", "internet",
                "kompyuter", "innovatsi", "технолог", "цифров", "tech",
                "digital", "software", "innovation")),
    ("binafsha", ("ta'lim", "pedagog", "maktab", "talaba", "san'at", "madaniyat",
                  "adabiyot", "образован", "педагог", "искусств", "educat",
                  "school", "art", "culture")),
    ("to'q sariq", ("tadbirkor", "biznes", "marketing", "savdo", "reklama",
                    "startap", "бизнес", "маркетинг", "business", "startup")),
    ("qizil", ("xavfsizlik", "favqulodda", "inqiroz", "jinoyat", "harbiy",
               "безопасн", "кризис", "security", "crisis", "emergency")),
    ("kulrang", ("huquq", "qonun", "normativ", "statistika", "hisobot",
                 "прав", "закон", "статистик", "law", "legal", "report")),
)


def get(key: str) -> Theme:
    """Sxemani kaliti bo'yicha beradi; topilmasa — sukutdagisi."""
    return THEMES.get((key or "").strip().lower(), THEMES[DEFAULT_KEY])


def suggest(topic: str) -> Theme:
    """Mavzuga mos sxema — mijoz o'zi tanlamaganda."""
    text = (topic or "").lower()
    for key, words in _HINTS:
        if any(word in text for word in words):
            return THEMES[key]
    return THEMES[DEFAULT_KEY]


def choices() -> List[Theme]:
    """Mijozga ko'rsatiladigan ro'yxat."""
    return list(THEMES.values())
