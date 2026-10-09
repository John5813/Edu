""""Rahmat" animatsiyasi: taqdimot yuborilgach mijoz uning oxiriga harakatlanuvchi personajli sahifa qo'shadi.

Oqim: bot taqdimotni yuboradi → (funksiya yoqilgan bo'lsa) "🎬 Oxiriga animatsiya qo'shish" tugmasi →
mini oyna (`webapp/thanks_anim.py`) → tanlov → server sahifani qo'shib faylni bot orqali yuboradi.
Taqdimot yaratish bosqichlariga tegilmaydi — mijoz bilmasdan tanlab qo'ymaydi.
"""
import logging
import os
import shutil
import time
import uuid
from typing import Optional

log = logging.getLogger(__name__)

FEATURE = "thanks_anim"          # "🎛 Funksiyalar boshqaruvi" dagi nom; sukut bo'yicha o'chiq
KEEP_SECONDS = 24 * 60 * 60      # asl taqdimot shuncha saqlanadi (tanlov shu muddatda)
STORE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "temp", "thanks_anim")

BUTTON = {"uz": "🎬 Oxiriga animatsiya qo'shish", "ru": "🎬 Добавить анимацию в конец",
          "en": "🎬 Add an animation at the end"}
DECLINE = {"uz": "❌ Kerak emas", "ru": "❌ Не нужно", "en": "❌ No, thanks"}
OFFER = {"uz": "✨ Taqdimotingiz oxiriga harakatlanuvchi personajli «Rahmat» sahifasini qo'shishingiz mumkin.",
         "ru": "✨ Можно добавить в конец презентации страницу «Спасибо» с анимированным персонажем.",
         "en": "✨ You can add a “Thank you” page with an animated character to the end of your deck."}


def _cleanup() -> None:
    now = time.time()
    try:
        names = os.listdir(STORE)
    except FileNotFoundError:
        return
    for name in names:
        path = os.path.join(STORE, name)
        try:
            if now - os.path.getmtime(path) > KEEP_SECONDS:
                os.remove(path)
        except OSError:
            pass


def offer(pptx_path: str, *, topic: str, style: str, volume: str, language: str, author: str, filename: str,
          user_id: int, chat_id: int, user_lang: str = "uz"):
    """Taqdimot nusxasini saqlab, mini oynani ochadigan tugmani qaytaradi (xato bo'lsa — None)."""
    import webapp
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    from .catalog import available

    if not available() or not webapp.WEBAPP_DOMAIN:
        return None
    try:
        os.makedirs(STORE, exist_ok=True)
        _cleanup()
        token = str(uuid.uuid4())
        kept = os.path.join(STORE, token + ".pptx")
        shutil.copy(pptx_path, kept)
        webapp.DOC_TOKENS[token] = {
            "kind": "thanks_anim", "file_path": kept, "topic": topic, "style": style, "volume": volume,
            "language": language, "author": author, "filename": filename, "user_id": user_id,
            "chat_id": chat_id, "user_lang": user_lang, "uses": 0, "_expires": time.time() + KEEP_SECONDS,
        }
        webapp.save_tokens_to_disk()
    except Exception as exc:
        log.warning("Rahmat animatsiyasi taklif qilinmadi: %s", exc)
        return None
    lang = user_lang if user_lang in BUTTON else "uz"
    url = webapp.public_url(f"/anim?token={token}&lang={lang}")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=BUTTON[lang], web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(text=DECLINE[lang], callback_data=f"tanim_no:{token}")],
    ])


def decline(token: str, user_id: int) -> None:
    """Mijoz "Kerak emas" ni bosdi: token va saqlangan nusxa o'chiriladi (faqat egasi uchun)."""
    import webapp

    info = webapp.DOC_TOKENS.get(token)
    if not info or info.get("kind") != "thanks_anim" or info.get("user_id") != user_id:
        return
    webapp.DOC_TOKENS.pop(token, None)
    webapp.save_tokens_to_disk()
    try:
        os.remove(info.get("file_path", ""))
    except OSError:
        pass


def offer_text(user_lang: str) -> str:
    return OFFER.get(user_lang, OFFER["uz"])
