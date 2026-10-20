"""Mini App: 3D taqdimotning interaktiv pleyeri (statik kadr + Morph videolar, pleyer elementlarisiz)."""
import os
import pathlib
import re

from aiohttp import web

PAGE = pathlib.Path(__file__).with_name("slide_player.html")
MEDIA_NAME = re.compile(r"^(slide\d+_static\.jpg|morph_\d+_to_\d+\.mp4)$")
MEDIA_TYPES = {".jpg": "image/jpeg", ".mp4": "video/mp4"}
TOKEN = re.compile(r"^[0-9a-f-]{36}$")


async def handle_page(request: web.Request) -> web.Response:
    return web.Response(text=PAGE.read_text(encoding="utf-8"), content_type="text/html",
                        headers={"Cache-Control": "no-cache"})


async def handle_manifest(request: web.Request) -> web.Response:
    from services import slide_player
    from webapp.server import _authorize_token_request

    token = request.match_info.get("token", "")
    info, err = _authorize_token_request(request, token)
    if err is not None:
        return err
    if info.get("kind") != slide_player.KIND:
        return web.json_response({"error": "forbidden"}, status=403)
    status = info.get("status", "failed")
    if status == "pending" and not slide_player.is_running(token):
        status = "failed"                          # bot qayta ishga tushgan — render to'xtab qolgan
    body = {"status": status}
    if status == "ready":
        base = f"/player-media/{token}/"
        body["slides"] = [base + n for n in info["slides"]]
        body["morphs"] = [base + n for n in info["morphs"]]
    return web.json_response(body, headers={"Cache-Control": "no-store"})


async def handle_media(request: web.Request) -> web.StreamResponse:
    from services import slide_player

    token = request.match_info.get("token", "")
    name = request.match_info.get("name", "")
    if not TOKEN.match(token) or not MEDIA_NAME.match(name):
        return web.Response(status=404)
    path = os.path.join(slide_player.token_dir(token), name)
    if not os.path.isfile(path):
        return web.Response(status=404)
    return web.FileResponse(path, headers={"Content-Type": MEDIA_TYPES[os.path.splitext(name)[1]],
                                           "Cache-Control": "private, max-age=3600"})


def setup_slide_player_routes(app: web.Application) -> None:
    app.router.add_get("/player", handle_page)
    app.router.add_get("/api/player/{token}", handle_manifest)
    app.router.add_get("/player-media/{token}/{name}", handle_media)
