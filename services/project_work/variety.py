"""Chizma shakli va rang sxemasini tanlaydi — hech biri ketma-ket takrorlanmasin.

Ilgari artefakt turi bilan chizma funksiyasi qat'iy bog'langan edi: byudjet
har doim gorizontal ustun, risklar har doim matritsa. Shu sababli har loyiha
ishi bir xil ko'rinardi.

Endi har artefakt uchun bir nechta TO'G'RI shakl bor va tanlov ikki darajada
takrorlanishdan qochadi:

  • hujjat ichida — shakllar qaytarilmasdan tanlanadi;
  • ishlar orasida — oxirgi ishlarda ishlatilgani chetlab o'tiladi.

Tanlov tasodifiy emas, urug'li (seeded): bir xil buyurtma qayta yaratilsa
bir xil natija chiqadi. Sof tasodifiy bo'lsa, mijoz shikoyat qilganda
natijani takrorlab bo'lmasdi.
"""

import hashlib
import json
import logging
import os
import random
import threading
from typing import Dict, List, Optional

from . import palettes
from .specs import (
    ARTIFACT_BREAKEVEN,
    ARTIFACT_BUDGET,
    ARTIFACT_CASHFLOW,
    ARTIFACT_COSTS,
    ARTIFACT_FORECAST,
    ARTIFACT_MARKETING,
    ARTIFACT_RISKS,
    ARTIFACT_SCHEME,
    ARTIFACT_TIMELINE,
)

logger = logging.getLogger(__name__)

# Har artefakt uchun mumkin bo'lgan shakllar. Ro'yxatdagi har bir shakl
# o'sha ma'lumot uchun to'g'ri bo'lishi shart — bu "tasodifiy chizma" emas.
FORMS: Dict[str, List[str]] = {
    # kattalikni taqqoslash
    ARTIFACT_BUDGET: ["bar", "lollipop", "donut", "waterfall"],
    # bosqichlar ketma-ketligi
    ARTIFACT_TIMELINE: ["gantt", "milestones", "steps"],
    # ikki o'lchov + og'irlik. Matritsa olib tashlandi: u rangli katakchalar
    # to'ri bo'lib, mijozga hech narsa aytmasdi.
    ARTIFACT_RISKS: ["bubble", "radar"],
    # vaqt bo'yicha o'zgarish
    ARTIFACT_FORECAST: ["line", "area", "column"],
    # tuzilma — bitta shakl, chunki u ierarxiyani ko'rsatadi
    ARTIFACT_SCHEME: ["structure"],
    # sotuv prognozi: hajm va tushum, yoki kanallar bo'yicha samara
    ARTIFACT_MARKETING: ["sales_columns", "sales_area", "channels"],
    # chiqim tarkibi: ulush, Pareto yoki doimiy/o'zgaruvchi ajratmasi
    ARTIFACT_COSTS: ["donut", "pareto", "fixed_variable"],
    # zararsizlik nuqtasi — bitta hisob, ikki ko'rinish
    ARTIFACT_BREAKEVEN: ["lines", "profit"],
    # pul oqimi: kirim-chiqim ustunlari yoki sharshara
    ARTIFACT_CASHFLOW: ["bars", "waterfall"],
}

# `data/` — Python paketi (icons_map.py shu yerda), shuning uchun ish
# vaqtidagi holat u yerga yozilmaydi: paketni tozalash kodni o'chirib
# yuborishi mumkin edi.
# Taqdimotdagi diagramma turlari. Bir guruh ichidagilar bir xil ma'lumotni
# ko'rsata oladi, shuning uchun ularni almashtirish xavfsiz. Guruhlar
# orasida almashtirilmaydi: doiraviy diagramma vaqt qatorini ko'rsata
# olmaydi, radar esa ulushni.
CHART_SWAPS: List[List[str]] = [
    ["column", "bar"],
    ["line", "area"],
    ["pie", "donut"],
    ["radar"],
    ["scatter"],
]

_STATE_PATH = os.path.join("runtime", "variety_state.json")
_STATE_LOCK = threading.Lock()
_MEMORY = 3          # oxirgi nechta ishni eslab qolamiz
_MAX_USERS = 500     # fayl cheksiz o'smasin


class Variety:
    """Bitta hujjat uchun tanlangan sxema va shakllar."""

    def __init__(self, palette: palettes.Palette, forms: Dict[str, str]):
        self.palette = palette
        self._forms = forms

    def form(self, artifact: str) -> str:
        options = FORMS.get(artifact) or []
        return self._forms.get(artifact) or (options[0] if options else "")

    def as_dict(self) -> dict:
        return {"palette": self.palette.key, "forms": dict(self._forms)}


def choose(seed_parts, user_id: Optional[int] = None) -> Variety:
    """Sxema va shakllarni tanlaydi, oldingi ishlardagilarni chetlab o'tadi."""
    seed = "|".join(str(part) for part in seed_parts if part is not None)
    rng = random.Random(hashlib.sha256(seed.encode("utf-8")).hexdigest())

    history = _history(user_id)
    used_palettes = {entry.get("palette") for entry in history}
    used_forms: Dict[str, set] = {}
    for entry in history:
        for artifact, form in (entry.get("forms") or {}).items():
            used_forms.setdefault(artifact, set()).add(form)
    # Eng oxirgi ish — u bilan ketma-ket bir xil bo'lish eng ko'zga tashlanadi.
    previous = history[-1] if history else {}
    last_forms = previous.get("forms") or {}

    palette_key = _pick(palettes.PALETTE_KEYS, used_palettes, rng,
                        last=previous.get("palette"))
    forms: Dict[str, str] = {}
    taken: set = set()
    for artifact in sorted(FORMS):
        options = FORMS[artifact]
        # Hujjat ichida bir shakl ikki marta ishlatilmasin.
        fresh = [f for f in options if f not in taken]
        forms[artifact] = _pick(fresh or options, used_forms.get(artifact, set()),
                                rng, last=last_forms.get(artifact))
        taken.add(forms[artifact])

    chosen = Variety(palettes.get(palette_key), forms)
    _remember(user_id, chosen)
    return chosen


def choose_palette(seed_parts, user_id: Optional[int] = None):
    """Faqat rang sxemasini tanlaydi — taqdimot uchun shakl tanlash boshqacha."""
    seed = "|".join(str(part) for part in seed_parts if part is not None)
    rng = random.Random(hashlib.sha256(seed.encode("utf-8")).hexdigest())
    history = _history(user_id)
    used = {entry.get("palette") for entry in history}
    key = _pick(palettes.PALETTE_KEYS, used, rng,
                last=(history[-1].get("palette") if history else None))
    chosen = Variety(palettes.get(key), {})
    _remember(user_id, chosen)
    return chosen.palette


def spread_chart_types(types: List[str], seed_parts) -> List[str]:
    """Bir taqdimotda bir xil diagramma turi takrorlanmasin.

    Almashtirish faqat mos guruh ichida bo'ladi: modelning ma'lumotga qarab
    tanlagan turi to'g'ri, faqat u ko'p marta bir xil chiqadi.
    """
    seed = "|".join(str(part) for part in seed_parts if part is not None)
    rng = random.Random(hashlib.sha256(seed.encode("utf-8")).hexdigest())

    groups = {name: group for group in CHART_SWAPS for name in group}
    used: set = set()
    out: List[str] = []
    for chart_type in types:
        group = groups.get(chart_type, [chart_type])
        fresh = [option for option in group if option not in used]
        if not fresh:
            # Guruh tugadi: uni qaytadan ochamiz, shunda turlar navbatlashadi
            # (ustun, gorizontal, ustun…) — uch marta ketma-ket bir xil emas.
            used -= set(group)
            fresh = list(group)
        pick = rng.choice(fresh)
        used.add(pick)
        out.append(pick)
    return out


def _pick(options: List[str], avoid: set, rng: random.Random,
          last: Optional[str] = None) -> str:
    """Iloji bo'lsa yaqinda ishlatilmaganini tanlaydi.

    Variantlar soni xotiradan kam bo'lsa (risklarda atigi ikkita shakl bor),
    hammasi "ishlatilgan" bo'lib chiqadi. Bunda ham hech bo'lmaganda eng
    oxirgi ishdagi shakl chetlab o'tiladi — mijoz ketma-ket ikkita bir xil
    chizmani aynan shu holatda sezadi.
    """
    if not options:
        return ""
    fresh = [option for option in options if option not in avoid]
    if fresh:
        return rng.choice(fresh)
    not_last = [option for option in options if option != last]
    return rng.choice(not_last or options)


# ─────────────────────────────────────────────────────────────── xotira
#
# Ma'lumotlar bazasiga ustun qo'shish shart emas: bu yerda saqlanadigan
# narsa faqat "oxirgi marta qaysi sxema ishlatilgan" degan maslahat.
# Fayl o'qilmasa yoki yozilmasa, tanlov baribir ishlaydi — shunchaki
# takrorlanmaslik kafolati zaiflashadi.

def _load() -> dict:
    try:
        with open(_STATE_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _history(user_id: Optional[int]) -> List[dict]:
    if user_id is None:
        return []
    entries = _load().get(str(user_id))
    return entries if isinstance(entries, list) else []


def _remember(user_id: Optional[int], chosen: Variety) -> None:
    if user_id is None:
        return
    with _STATE_LOCK:
        data = _load()
        entries = data.get(str(user_id))
        if not isinstance(entries, list):
            entries = []
        entries.append(chosen.as_dict())
        data[str(user_id)] = entries[-_MEMORY:]

        if len(data) > _MAX_USERS:
            for key in list(data)[: len(data) - _MAX_USERS]:
                data.pop(key, None)

        try:
            os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
            tmp_path = f"{_STATE_PATH}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            os.replace(tmp_path, _STATE_PATH)
        except OSError as e:
            logger.warning("Chizma tanlovi eslab qolinmadi: %s", e)
