"""Reklama ostidagi tugmalar: admin tanlaydi, bot inline tugmaga aylantiradi.

Tugma ikki xil bo'ladi:
  * havola — sayt, kanal yoki bot (`https://...`, `t.me/...`, `@nom`). Admin
    manzilni yuboradi va tugma ustiga yoziladigan nomni O'ZI qo'yadi, shuning
    uchun foydalanuvchi manzilni ko'rmaydi;
  * ichki — botning o'z bo'limi (taqdimot, referat, hisob...): bosilganda
    foydalanuvchi uchun shu bo'lim ochiladi (xuddi pastki menyudagi tugma
    bosilgandek). Admin ro'yxatdan tanlaydi.
"""

import re
from typing import Dict, List, Optional, Tuple

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MAX_BUTTONS = 8
MAX_LABEL = 60

# kalit -> ("menu", translations kaliti, nom kaliti) yoki ("cb", tayyor callback_data, nom kaliti)
TARGETS: Dict[str, Tuple[str, str, str]] = {
    "taqdimot": ("menu", "main_menu.presentation", "main_menu.presentation"),
    "mustaqil": ("menu", "main_menu.independent_work", "main_menu.independent_work"),
    "referat": ("menu", "main_menu.referat", "main_menu.referat"),
    "kurs": ("menu", "main_menu.course_work", "main_menu.course_work"),
    "loyiha": ("menu", "main_menu.project_work", "main_menu.project_work"),
    "hisob": ("menu", "main_menu.my_account", "main_menu.my_account"),
    "tolov": ("menu", "main_menu.payment", "main_menu.payment"),
    "pul": ("menu", "main_menu.referral", "main_menu.referral"),      # to'lov bo'limidagi «Pul ishlab topish»
    "namunalar": ("menu", "main_menu.samples", "main_menu.samples"),
    "yordam": ("menu", "main_menu.help", "main_menu.help"),
    "boshqa": ("menu", "main_menu.other_services", "main_menu.other_services"),
    "tezis": ("cb", "os:tezis", "main_menu.tezis"),
    "maqola": ("cb", "os:maqola", "main_menu.maqola"),
    "diplom": ("cb", "os:diploma_work", "main_menu.diploma_work"),
    "bitiruv": ("cb", "os:bitiruv_ishi", "main_menu.bitiruv_ishi"),
    "dissertatsiya": ("cb", "os:dissertatsiya", "main_menu.dissertatsiya"),
}

_USERNAME = re.compile(r"^@([A-Za-z][A-Za-z0-9_]{3,31})$")
_URL = re.compile(r"^https?://[^\s/]+\.[^\s/]+\S*$", re.IGNORECASE)


def target_name(key: str, language: str = "uz") -> str:
    """Bo'limning menyudagi nomi (adminga ro'yxatda va standart tugma nomi sifatida)."""
    from translations import get_text

    return get_text(language, TARGETS[key][2])


def normalize_link(raw: str) -> Optional[str]:
    """Sayt, kanal yoki bot manzilini to'liq URL qiladi (yaroqsiz bo'lsa — None)."""
    value = (raw or "").strip()
    if not value:
        return None
    if value.lower().startswith(("t.me/", "telegram.me/")):
        value = "https://" + value
    if _URL.match(value):
        return value
    match = _USERNAME.match(value)
    if match:
        return f"https://t.me/{match.group(1)}"
    return None


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
