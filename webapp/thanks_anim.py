""""Rahmat" personajini tanlash oynasi (Telegram Mini App).

Taqdimot sozlamalaridagi «🎬 Personaj tanlash» tugmasi `/anim` ni ochadi: personajlar Reels kabi varaqlanadi
(video namuna, ovoz bilan), foydalanuvchi birini tanlaydi. Tanlov botga `t.me/<bot>?start=thx_<kalit>` havolasi
orqali qaytadi (bot buyurtma holatini yangilaydi) — mini ilova shundan keyin yopiladi. Server tomonida holat
saqlanmaydi, token ham kerak emas: ro'yxat va namuna videolar hammaga ochiq (maxfiy narsa yo'q).
"""
import logging
import os
import pathlib

from aiohttp import web

import webapp
from services.thanks_anim import catalog

logger = logging.getLogger(__name__)

PAGE = pathlib.Path(__file__).with_name("thanks_anim.html")
MEDIA = {"preview.mp4": "video/mp4", "poster.jpg": "image/jpeg"}


async def handle_page(request: web.Request) -> web.Response:
    return web.Response(text=PAGE.read_text(encoding="utf-8"), content_type="text/html",
                        headers={"Cache-Control": "no-cache"})


async def handle_list(request: web.Request) -> web.Response:
    lang = request.query.get("lang", "uz")
    lang = lang if lang in ("uz", "ru", "en") else "ru"            # qozoqcha nomlar yo'q — ruscha o'qiladi
    # Havolaga fayl o'zgargan vaqti qo'shiladi (`?v=`): namuna yangilanganda (deploy) Telegram brauzeri eski rasmni
    # keshdan ko'rsatib qolmaydi — media bir kun keshlanadi, shuning uchun havola o'zi yangilanishi kerak.
    def versioned(anim, name: str) -> str:
        return f"/anim-media/{anim.key}/{name}?v={int(os.path.getmtime(anim.path(name)))}"

    items = [{"key": a.key, "name": a.name(lang), "preview": versioned(a, "preview.mp4"),
              "poster": versioned(a, "poster.jpg")} for a in catalog.available()]
    return web.json_response({"items": items, "bot": webapp.BOT_USERNAME})


async def handle_media(request: web.Request) -> web.StreamResponse:
    anim = catalog.get(request.match_info.get("key", ""))
    name = request.match_info.get("name", "")
    if anim is None or name not in MEDIA or not os.path.exists(anim.path(name)):
        return web.Response(status=404)
    return web.FileResponse(anim.path(name), headers={"Content-Type": MEDIA[name],
                                                      "Cache-Control": "public, max-age=86400"})


def setup_thanks_anim_routes(app: web.Application) -> None:
    app.router.add_get("/anim", handle_page)
    app.router.add_get("/api/anim/list", handle_list)
    app.router.add_get("/anim-media/{key}/{name}", handle_media)
