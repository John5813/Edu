""""Rahmat" animatsiyasini tanlash oynasi (Telegram Mini App).

Taqdimot yuborilgach bot "🎬 Oxiriga animatsiya qo'shish" tugmasini beradi. Tugma `/anim?token=...` ni
ochadi: animatsiyalar Reels kabi varaqlanadi, foydalanuvchi birini tanlaydi — server taqdimot oxiriga
"Rahmat" sahifasini qo'shib, faylni bot orqali yuboradi. Har tanlov ASL taqdimotdan yig'iladi
(animatsiyalar ustma-ust qo'shilib ketmaydi).
"""
import asyncio
import logging
import os
import pathlib

from aiohttp import web

import webapp
from services.thanks_anim import catalog

logger = logging.getLogger(__name__)

PAGE = pathlib.Path(__file__).with_name("thanks_anim.html")
MEDIA = {"preview.mp4": "video/mp4", "poster.jpg": "image/jpeg"}
MAX_USES = 5
FEATURE = "thanks_anim"


async def handle_page(request: web.Request) -> web.Response:
    return web.Response(text=PAGE.read_text(encoding="utf-8"), content_type="text/html",
                        headers={"Cache-Control": "no-cache"})


async def handle_list(request: web.Request) -> web.Response:
    lang = request.query.get("lang", "uz")
    items = [{"key": a.key, "name": a.name(lang), "preview": f"/anim-media/{a.key}/preview.mp4",
              "poster": f"/anim-media/{a.key}/poster.jpg"} for a in catalog.available()]
    return web.json_response({"items": items})


async def handle_media(request: web.Request) -> web.StreamResponse:
    anim = catalog.get(request.match_info.get("key", ""))
    name = request.match_info.get("name", "")
    if anim is None or name not in MEDIA or not os.path.exists(anim.path(name)):
        return web.Response(status=404)
    return web.FileResponse(anim.path(name), headers={"Content-Type": MEDIA[name],
                                                      "Cache-Control": "public, max-age=86400"})


def _build(info: dict, anim) -> str:
    from services.premium_presentation import themes
    from services.thanks_anim.slide import add_thanks_slide

    theme = themes.for_deck(info.get("topic", ""), info.get("style", ""), info.get("volume", ""))
    src = info["file_path"]
    out = src[:-5] + f"_{anim.key}.pptx"
    return add_thanks_slide(src, out, anim, theme, info.get("language", "uz"), info.get("author", ""))


async def handle_choose(request: web.Request) -> web.Response:
    from webapp.server import _authorize_token_request

    token = request.match_info.get("token", "")
    info, err = _authorize_token_request(request, token)
    if err is not None:
        return err
    if info.get("kind") != "thanks_anim":
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)
    anim = catalog.get(str(body.get("key", "")))
    if anim is None:
        return web.json_response({"ok": False, "error": "unknown"}, status=400)
    if info.get("busy"):
        return web.json_response({"ok": False, "error": "busy"}, status=409)
    if info.get("uses", 0) >= MAX_USES:
        return web.json_response({"ok": False, "error": "limit"}, status=429)
    if not os.path.exists(info.get("file_path", "")):
        return web.json_response({"ok": False, "error": "expired"}, status=404)

    info["busy"] = True
    out = None
    try:
        out = await asyncio.get_running_loop().run_in_executor(None, _build, info, anim)
        bot = webapp.BOT
        if bot is None:
            raise RuntimeError("bot yo'q")
        from aiogram.types import FSInputFile

        name = os.path.basename(info.get("filename") or "Taqdimot.pptx")
        await bot.send_document(info["chat_id"], FSInputFile(out, filename=name),
                                caption=f"🎬 {anim.name(info.get('user_lang', 'uz'))}")
        info["uses"] = info.get("uses", 0) + 1
        info["busy"] = False
        webapp.save_tokens_to_disk()
        logger.info("Rahmat animatsiyasi qo'shildi: %s → %s", anim.key, info.get("chat_id"))
        return web.json_response({"ok": True})
    except Exception as exc:
        logger.exception("Rahmat animatsiyasi qo'shilmadi: %s", exc)
        return web.json_response({"ok": False, "error": "build"}, status=500)
    finally:
        info["busy"] = False
        if out and os.path.exists(out):
            try:
                os.remove(out)
            except OSError:
                pass


def setup_thanks_anim_routes(app: web.Application) -> None:
    app.router.add_get("/anim", handle_page)
    app.router.add_get("/api/anim/list", handle_list)
    app.router.add_get("/anim-media/{key}/{name}", handle_media)
    app.router.add_post("/api/anim/{token}", handle_choose)
