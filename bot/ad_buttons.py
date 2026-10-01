"""Reklama ostidagi tugmalar: admin yozadi, bot inline tugmaga aylantiradi.

Admin har qatorga bitta tugma yozadi:

    Botga o'tish | @slaydtopbot
    Saytimiz | https://example.uz
    Kanalimiz | https://t.me/kanal
    Taqdimot yaratish | taqdimot

Tugma uch xil bo'ladi:
  * havola — sayt, kanal, bot (`https://...`, `t.me/...`, `@nom`) — URL tugma;
  * ichki — botning o'z bo'limi (`taqdimot`, `referat`, `hisob`...): bosilganda
    foydalanuvchi uchun shu bo'lim ochiladi (xuddi pastki menyudagi tugma
    bosilgandek);
  * "Boshqa xizmatlar" ichidagi bo'limlar (`tezis`, `maqola`...) — ularning
    tayyor `os:` tugmasi ishlatiladi.
"""

import re
from typing import Dict, List, Tuple

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MAX_BUTTONS = 8
MAX_LABEL = 60

# kalit -> ("menu", translations kaliti) yoki ("cb", tayyor callback_data)
TARGETS: Dict[str, Tuple[str, str]] = {
    "taqdimot": ("menu", "main_menu.presentation"),
    "mustaqil": ("menu", "main_menu.independent_work"),
    "referat": ("menu", "main_menu.referat"),
    "kurs": ("menu", "main_menu.course_work"),
    "loyiha": ("menu", "main_menu.project_work"),
    "hisob": ("menu", "main_menu.my_account"),
    "tolov": ("menu", "main_menu.payment"),
    "namunalar": ("menu", "main_menu.samples"),
    "yordam": ("menu", "main_menu.help"),
    "boshqa": ("menu", "main_menu.other_services"),
    "tezis": ("cb", "os:tezis"),
    "maqola": ("cb", "os:maqola"),
    "diplom": ("cb", "os:diploma_work"),
    "bitiruv": ("cb", "os:bitiruv_ishi"),
    "dissertatsiya": ("cb", "os:dissertatsiya"),
}

ALIASES = {
    "presentation": "taqdimot", "slayd": "taqdimot", "mustaqilish": "mustaqil",
    "kursishi": "kurs", "loyihaishi": "loyiha", "balans": "hisob", "hisobim": "hisob",
    "tolov": "tolov", "toʻlov": "tolov", "diplomishi": "diplom", "dissertatsiya": "dissertatsiya",
    "sample": "namunalar", "namuna": "namunalar", "help": "yordam",
}

_USERNAME = re.compile(r"^@([A-Za-z][A-Za-z0-9_]{3,31})$")
_URL = re.compile(r"^https?://[^\s/]+\.[^\s/]+\S*$", re.IGNORECASE)


def keys_help() -> str:
    return ", ".join(TARGETS)


def _target(raw: str):
    """(kind, value) yoki None. kind: 'url' | 'menu' | 'cb'."""
    value = raw.strip()
    if not value:
        return None
    lowered = value.lower()
    if lowered.startswith(("t.me/", "telegram.me/")):
        value = "https://" + value
    if _URL.match(value):
        return "url", value
    match = _USERNAME.match(value)
    if match:
        return "url", f"https://t.me/{match.group(1)}"
    key = re.sub(r"[\s'’ʻ`-]", "", lowered)
    key = ALIASES.get(key, key)
    if key in TARGETS:
        kind, _ = TARGETS[key]
        return ("menu" if kind == "menu" else "cb"), key
    return None


def parse(text: str) -> Tuple[List[Dict], List[str]]:
    """Admin matnini tugmalar ro'yxatiga aylantiradi: (tugmalar, xatolar)."""
    buttons: List[Dict] = []
    errors: List[str] = []
    for number, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if "|" not in line:
            errors.append(f"{number}-qator: «|» belgisi yo'q (namuna: Sayt | https://example.uz)")
            continue
        label, raw_target = (part.strip() for part in line.split("|", 1))
        if not label:
            errors.append(f"{number}-qator: tugma matni bo'sh")
            continue
        if len(label) > MAX_LABEL:
            errors.append(f"{number}-qator: tugma matni {MAX_LABEL} belgidan oshmasin")
            continue
        target = _target(raw_target)
        if target is None:
            errors.append(f"{number}-qator: «{raw_target}» tushunarsiz — havola (https://...), @nom yoki bo'lim nomi kerak")
            continue
        kind, value = target
        buttons.append({"text": label, "kind": kind, "value": value})
    if len(buttons) > MAX_BUTTONS:
        errors.append(f"Tugmalar {MAX_BUTTONS} tadan oshmasin (hozir {len(buttons)} ta)")
    return buttons, errors


def markup(buttons: List[Dict]):
    """Saqlangan tugmalardan InlineKeyboardMarkup (tugma yo'q bo'lsa — None)."""
    rows = []
    for item in buttons or []:
        kind, value = item.get("kind"), item.get("value")
        if kind == "url":
            rows.append([InlineKeyboardButton(text=item["text"], url=value)])
        elif kind == "menu":
            rows.append([InlineKeyboardButton(text=item["text"], callback_data=f"ad:{value}")])
        elif kind == "cb":
            rows.append([InlineKeyboardButton(text=item["text"], callback_data=TARGETS[value][1])])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def menu_text(key: str, language: str):
    """Ichki `menu` tugma bosilganda yuboriladigan pastki-menyu matni."""
    from translations import get_text

    target = TARGETS.get(key)
    if not target or target[0] != "menu":
        return None
    return get_text(language, target[1])
