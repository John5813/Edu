"""Taqdimot sozlamalarida «Rahmat» personajini tanlash (ixtiyoriy) va tayyor taqdimotga sahifani qo'shish.

Oqim (`bot/handlers/premium_presentation.py`): slaydlar soni va rasm/yozuv sozlamalaridan keyin — «🎬 Personaj
tanlash» yoki «❌ Kerak emas». Tanlangan personaj buyurtma xulosasida ko'rinadi (u yerdan almashtirish mumkin),
taqdimot tayyor bo'lganda oxiriga «Rahmat» sahifasi qo'shiladi. Narxga ta'sir qilmaydi — bepul.
Tanlov `thanks_key` bilan FSM ma'lumotida turadi ("" — personajsiz).
"""
import logging
import os
import shutil
import tempfile
from typing import List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from . import FEATURE
from .catalog import Animation, available, get

log = logging.getLogger(__name__)

CB = "prem_thx"          # callback_data oldi: open | skip | close | go:<i> | pick:<kalit>

TXT = {
    "uz": {
        "ask": ("🎬 <b>Oxirgi sahifa: animatsiyali «Rahmat» slaydi</b>\n\nTaqdimot oxiriga harakatlanadigan va "
                "ovoz chiqaradigan personajli «Rahmat» sahifasi qo'shiladi. Bu <b>mutlaqo tekin</b>.\n"
                "Xohlasangiz — personaj tanlang, xohlamasangiz — o'tkazib yuboring."),
        "pick": "🎬 Personaj tanlash", "change": "🎬 Personajni almashtirish", "no": "❌ Kerak emas",
        "choose": "✅ Tanlash", "back": "⬅️ Orqaga", "line": "🎬 Rahmat sahifasi", "none": "yo'q",
        "caption": "🎬 <b>{name}</b> ({i}/{n})\n\n<i>Shu personaj oxirgi «Rahmat» sahifasida harakatlanadi va ovoz "
                   "chiqaradi.</i>",
        "chosen": "✓ Tanlangan: <b>{name}</b>",
        "note": ("ℹ️ Oxirgi sahifadagi personaj, ovoz va yozuvlar PowerPoint'da «Slayd-shou» rejimida harakatlanadi. "
                 "Telefon ilovalari va PDF'da sahifa harakatsiz ko'rinishi mumkin."),
    },
    "ru": {
        "ask": ("🎬 <b>Последняя страница: анимированный слайд «Спасибо»</b>\n\nВ конец презентации добавится "
                "страница «Спасибо» с движущимся персонажем и звуком. Это <b>совершенно бесплатно</b>.\n"
                "Хотите — выберите персонажа, не хотите — пропустите."),
        "pick": "🎬 Выбрать персонажа", "change": "🎬 Сменить персонажа", "no": "❌ Не нужно",
        "choose": "✅ Выбрать", "back": "⬅️ Назад", "line": "🎬 Страница «Спасибо»", "none": "нет",
        "caption": "🎬 <b>{name}</b> ({i}/{n})\n\n<i>Этот персонаж будет двигаться и звучать на последней странице "
                   "«Спасибо».</i>",
        "chosen": "✓ Выбран: <b>{name}</b>",
        "note": ("ℹ️ Персонаж, звук и надписи на последней странице оживают в PowerPoint в режиме «Показ слайдов». "
                 "В мобильных приложениях и PDF страница может быть статичной."),
    },
    "en": {
        "ask": ("🎬 <b>Last page: an animated “Thank you” slide</b>\n\nA “Thank you” page with a moving, "
                "sounding character is added to the end of your deck. It is <b>completely free</b>.\n"
                "Pick a character if you like, or skip it."),
        "pick": "🎬 Choose a character", "change": "🎬 Change the character", "no": "❌ No, thanks",
        "choose": "✅ Choose", "back": "⬅️ Back", "line": "🎬 Thank-you page", "none": "none",
        "caption": "🎬 <b>{name}</b> ({i}/{n})\n\n<i>This character moves and makes sound on the final “Thank you” "
                   "page.</i>",
        "chosen": "✓ Selected: <b>{name}</b>",
        "note": ("ℹ️ The character, sound and text on the last page come alive in PowerPoint Slide Show mode. "
                 "Phone apps and PDF may show the page static."),
    },
}


def _t(lang: str) -> dict:
    return TXT.get(lang) or TXT["uz"]


def _name_lang(lang: str) -> str:
    return lang if lang in ("uz", "ru", "en") else "ru"        # qozoqcha nomlar yo'q — ruscha o'qiladi


def name_of(key: str, lang: str) -> str:
    anim = get(key)
    return anim.name(_name_lang(lang)) if anim else ""


def items() -> List[Animation]:
    return available()


async def offered(db) -> bool:
    """Taklif qilinadimi: funksiya admin tomonidan o'chirilmagan (sukut — yoqilgan) va personajlar bor."""
    if not items():
        return False
    try:
        return bool(await db.get_feature_status(FEATURE, default=True))
    except Exception as exc:                  # baza o'qilmasa — taklif qilinmaydi, taqdimot sozlamalari buzilmaydi
        log.warning("Rahmat animatsiyasi holati o'qilmadi: %s", exc)
        return False


def question_text(lang: str, chosen: str = "") -> str:
    text = _t(lang)["ask"]
    if chosen and get(chosen):
        text += "\n\n" + _t(lang)["chosen"].format(name=name_of(chosen, lang))
    return text


def question_markup(lang: str, chosen: str, back_row) -> InlineKeyboardMarkup:
    t = _t(lang)
    rows = [[InlineKeyboardButton(text=t["change"] if chosen and get(chosen) else t["pick"],
                                  callback_data=f"{CB}:open")],
            [InlineKeyboardButton(text=t["no"], callback_data=f"{CB}:skip")], back_row]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def start_index(chosen: str) -> int:
    for i, anim in enumerate(items()):
        if anim.key == chosen:
            return i
    return 0


def pager_caption(index: int, lang: str) -> str:
    lst = items()
    anim = lst[index % len(lst)]
    return _t(lang)["caption"].format(name=anim.name(_name_lang(lang)), i=index % len(lst) + 1, n=len(lst))


def pager_markup(index: int, lang: str) -> InlineKeyboardMarkup:
    lst = items()
    n = len(lst)
    index %= n
    t = _t(lang)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️", callback_data=f"{CB}:go:{(index - 1) % n}"),
         InlineKeyboardButton(text=f"{index + 1}/{n}", callback_data=f"{CB}:go:{index}"),
         InlineKeyboardButton(text="▶️", callback_data=f"{CB}:go:{(index + 1) % n}")],
        [InlineKeyboardButton(text=t["choose"], callback_data=f"{CB}:pick:{lst[index].key}")],
        [InlineKeyboardButton(text=t["no"], callback_data=f"{CB}:skip"),
         InlineKeyboardButton(text=t["back"], callback_data=f"{CB}:close")],
    ])


def summary_line(lang: str, chosen: str) -> str:
    t = _t(lang)
    name = name_of(chosen, lang)
    return f"{t['line']}: <b>{name or t['none']}</b>"


def summary_button(lang: str, chosen: str) -> InlineKeyboardButton:
    t = _t(lang)
    name = name_of(chosen, lang)
    return InlineKeyboardButton(text=f"{t['line']}: {name or t['none']}", callback_data=f"{CB}:open")


def note(lang: str) -> str:
    return _t(lang)["note"]


def apply(pptx_path: str, key: str, *, topic: str, style: str, volume: str, theme_key: str, language: str,
          author: str) -> Optional[str]:
    """Taqdimot (`pptx_path`) oxiriga tanlangan personajli «Rahmat» sahifasini qo'shadi (joyida). Xato — None."""
    from services.premium_presentation import themes

    from .slide import add_thanks_slide

    anim = get(key)
    if anim is None:
        return None
    work = tempfile.mkdtemp(prefix="thanks_apply_")
    try:
        out = os.path.join(work, "deck.pptx")
        theme = themes.for_deck(topic, style, volume, theme_key)
        add_thanks_slide(pptx_path, out, anim, theme, language, author)
        shutil.move(out, pptx_path)
        return pptx_path
    except Exception as exc:
        log.warning("Rahmat sahifasi qo'shilmadi (%s): %s", key, exc)
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)
