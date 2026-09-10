"""Chizma rang sxemalari — har ish boshqa rangda chiqishi uchun.

Ilgari `charts.py` da bitta `BLUE_RAMP` bor edi va u hamma chizmada
ishlatilardi, shuning uchun har loyiha ishi bir xil ko'rinardi. Bu yerda
oltita sxema bor; qaysi biri ishlatilishini `variety.py` hal qiladi.

Kategorik qatorlar dataviz validatoridan o'tgan sakkiz rangdan olingan va
har biri boshqa joydan boshlanadi. Oltalasi ham `validate_palette.js`
tekshiruvidan o'tgan (light rejim): rangni ajrata olmaydiganlar uchun ham
qo'shni juftlar farqi chegaradan yuqori.

Holat ranglari (yaxshi/ogohlantirish/xavfli) ataylab aylantirilmaydi — ular
rang emas, ma'no tashiydi.
"""

from dataclasses import dataclass
from typing import Dict, List

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e3e2df"

# Holat ranglari — barcha sxemalarda bir xil.
STATUS: Dict[int, str] = {1: "#0ca30c", 2: "#fab219", 3: "#ec835a", 4: "#d03b3b"}

_CATEGORICAL = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#4a3aa7", "#e34948",
]


@dataclass(frozen=True)
class Palette:
    key: str
    # Kattalik uchun bitta hue: ochdan to'qqa. Qo'shni qadamlar yorug'ligi
    # yetarlicha farq qiladi, aks holda ustunlar bir-biridan ajralmaydi.
    ramp: List[str]
    # Turlar uchun — qat'iy tartib, aylantirilmaydi.
    categorical: List[str]

    @property
    def lead(self) -> str:
        return self.ramp[2]


def _rotated(start: int, count: int = 6) -> List[str]:
    doubled = _CATEGORICAL + _CATEGORICAL
    return doubled[start:start + count]


PALETTES: Dict[str, Palette] = {
    "blue": Palette("blue",
                    ["#87b3e8", "#5493de", "#2770c9", "#1d5496", "#12355e"],
                    _rotated(0)),
    "aqua": Palette("aqua",
                    ["#83ecc6", "#4ee4ae", "#20d091", "#189b6c", "#0f6144"],
                    _rotated(2)),
    "violet": Palette("violet",
                      ["#b6afe3", "#978cd7", "#7466ca", "#503fb4", "#2d2467"],
                      _rotated(6)),
    "amber": Palette("amber",
                     ["#fbd074", "#fabc38", "#eaa106", "#ae7804", "#6d4b03"],
                     _rotated(3)),
    "magenta": Palette("magenta",
                       ["#ea85ab", "#e15187", "#cc2463", "#981a4a", "#60112e"],
                       _rotated(4)),
    "orange": Palette("orange",
                      ["#f29e7d", "#ed7545", "#da4d15", "#a23a10", "#66240a"],
                      _rotated(1)),
}

PALETTE_KEYS = list(PALETTES)
DEFAULT_PALETTE = PALETTES["blue"]


def get(key: str) -> Palette:
    return PALETTES.get(key, DEFAULT_PALETTE)


def on_fill(fill: str) -> str:
    """Fon ustida o'qiladigan matn rangi — yorqinlikdan hisoblanadi."""
    h = (fill or "").lstrip("#")
    if len(h) != 6:
        return INK
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return INK if luminance > 0.62 else "#ffffff"


def shades(palette: Palette, values: List[float]) -> List[str]:
    """Qiymatlarni kattaligi bo'yicha ramp qadamlariga taqsimlaydi."""
    if not values:
        return []
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [palette.ramp[0]] * len(values)
    for rank, index in enumerate(order):
        step = int(rank / max(len(values) - 1, 1) * (len(palette.ramp) - 1))
        out[index] = palette.ramp[step]
    return out
