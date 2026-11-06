"""Reklama havolasi: `/go/<kod>` — Instagram reklamasining «Veb-sayt» manzili.

Bosish hisoblanadi (`database.ad_links`), so'ng odam botga `?start=ad_<kod>` bilan yo'naltiriladi — botda Start
bosganlar yangi / eski mijozga ajratiladi. Bosdi-yu botga kirmaganlar «adashib bosganlar» hisoblanadi.
Reklamani tekshiruvchi botlar (Meta, qidiruv tizimlari) va bir odamning tez-tez qayta bosishi sanalmaydi.
"""
import logging
import time
from typing import Dict, Tuple

from aiohttp import web

import webapp
from database import ad_links

log = logging.getLogger(__name__)

_RECENT: Dict[Tuple[str, str], float] = {}
REPEAT_SECONDS = 60.0                      # bir odam shuncha vaqt ichida qayta bossa — bitta bosish


def _client_ip(request: web.Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.remote) or "?"


def _repeat(code: str, visitor: str) -> bool:
    now = time.monotonic()
    if len(_RECENT) > 5000:
        for key in [k for k, t in _RECENT.items() if now - t > REPEAT_SECONDS]:
            _RECENT.pop(key, None)
    last = _RECENT.get((code, visitor))
    _RECENT[(code, visitor)] = now
    return last is not None and now - last < REPEAT_SECONDS


async def handle_go(request: web.Request) -> web.StreamResponse:
    code = request.match_info.get("code", "")
    agent = request.headers.get("User-Agent", "")
    target = ""
    try:
        from webapp.store import _bot_url

        target = _bot_url(ad_links.PREFIX + code if ad_links.valid(code) else "")
    except Exception as exc:                                           # noqa: BLE001
        log.warning("Reklama havolasi: bot manzili olinmadi: %s", exc)
    if ad_links.valid(code) and not ad_links.is_bot_agent(agent):
        try:
            if await ad_links.is_active(code):
                visitor = ad_links.visitor_hash(_client_ip(request), agent)
                if not _repeat(code, visitor):
                    await ad_links.record_hit(code, visitor)
        except Exception as exc:                                       # noqa: BLE001  (hisob xatosi mijozni to'smasin)
            log.warning("Reklama bosilishi yozilmadi (%s): %s", code, exc)
    # Bot nomi hali noma'lum bo'lsa — mijoz saytning o'ziga tushadi, havola buzilmaydi.
    raise web.HTTPFound(target or webapp.public_url("/"), headers={"Cache-Control": "no-store"})


def setup_ad_track_routes(app: web.Application) -> None:
    app.router.add_get("/go/{code}", handle_go)
