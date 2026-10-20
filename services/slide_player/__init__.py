""""📱 Mini App'da ko'rish": 3D taqdimot serverda videoga o'giriladi, telefonda esa interaktiv pleyerda varaqlanadi.

Oqim: bot taqdimotni yuboradi → tugma (token bilan) → fonda render (`render.py`) → mini oyna
(`webapp/slide_player.py`) tayyor bo'lguncha holatni so'rab turadi → statik kadr + Morph videolar.
"""
import asyncio
import logging
import os
import shutil
import time
import uuid

from . import render

log = logging.getLogger(__name__)

KIND = "slide_player"
KEEP_SECONDS = 24 * 60 * 60
STORE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "temp", "slide_player")

BUTTON = {"uz": "📱 Mini App'da ko'rish", "ru": "📱 Смотреть в Mini App", "en": "📱 View in Mini App",
          "kk": "📱 Mini App-та қарау"}
OFFER = {
    "uz": "📱 Taqdimotni telefonda ham, Morph animatsiyalari bilan, PowerPoint'dagidek ko'rishingiz mumkin.",
    "ru": "📱 Презентацию можно смотреть и на телефоне — с Morph-анимациями, как в PowerPoint.",
    "en": "📱 You can also view the deck on your phone, with Morph animations, just like in PowerPoint.",
    "kk": "📱 Презентацияны телефоннан да, PowerPoint сияқты Morph анимацияларымен көруге болады.",
}

_running: dict = {}          # token -> asyncio.Task (GC'dan saqlash va "to'xtab qolgan"ni aniqlash uchun)


def is_running(token: str) -> bool:
    return token in _running


def token_dir(token: str) -> str:
    return os.path.join(STORE, token)


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
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


async def _job(token: str, pptx: str) -> None:
    import webapp

    info = webapp.DOC_TOKENS.get(token)
    try:
        pkg = await render.build_package(pptx, token_dir(token))
        if info is not None:
            info.update(status="ready", slides=pkg["slides"], morphs=pkg["morphs"])
    except Exception as exc:                      # noqa: BLE001
        log.exception("Mini App pleyer tayyorlanmadi: %s", exc)
        if info is not None:
            info["status"] = "failed"
    finally:
        _running.pop(token, None)
        try:
            os.remove(pptx)
        except OSError:
            pass
        webapp.save_tokens_to_disk()


def offer(pptx_path: str, *, user_id: int, chat_id: int, user_lang: str = "uz"):
    """Nusxani saqlab, fonda renderni boshlaydi va tugmani qaytaradi (sozlanmagan/xato bo'lsa — None)."""
    import webapp
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    if not webapp.WEBAPP_DOMAIN or not render.available():
        return None
    try:
        _cleanup()
        token = str(uuid.uuid4())
        folder = token_dir(token)
        os.makedirs(folder, exist_ok=True)
        kept = os.path.join(folder, "src.pptx")
        shutil.copy(pptx_path, kept)
        webapp.DOC_TOKENS[token] = {"kind": KIND, "user_id": user_id, "chat_id": chat_id, "status": "pending",
                                    "slides": [], "morphs": [], "_expires": time.time() + KEEP_SECONDS}
        webapp.save_tokens_to_disk()
        _running[token] = asyncio.get_running_loop().create_task(_job(token, kept))
    except Exception as exc:                      # noqa: BLE001
        log.warning("Mini App pleyer taklif qilinmadi: %s", exc)
        return None
    lang = user_lang if user_lang in BUTTON else "uz"
    url = webapp.public_url(f"/player?token={token}&lang={lang}")
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=BUTTON[lang], web_app=WebAppInfo(url=url))]])


def offer_text(user_lang: str) -> str:
    return OFFER.get(user_lang, OFFER["uz"])
