"""Windows VPS'da ishlaydigan render serveri: PPTX qabul qiladi, PowerPoint orqali MP4 qaytaradi.

Talab: Windows + Microsoft PowerPoint, `pip install pywin32 aiohttp`.
Ishga tushirish:  set SLIDE_RENDER_KEY=maxfiy_kalit  &&  python tools/render_server.py
Bot tomonda:      SLIDE_RENDER_URL=http://<vps>:8765   SLIDE_RENDER_KEY=maxfiy_kalit
PowerPoint bir vaqtda bitta eksportni yaxshi ko'taradi — so'rovlar navbat bilan bajariladi.
"""
import asyncio
import hmac
import os
import sys
import tempfile

from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.slide_player import render  # noqa: E402

KEY = os.environ.get("SLIDE_RENDER_KEY", "")
LOCK = asyncio.Lock()


async def handle_render(request: web.Request) -> web.StreamResponse:
    if KEY and not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {KEY}"):
        return web.Response(status=401)
    try:
        hold = float(request.query.get("hold", render.HOLD))
        trans = float(request.query.get("trans", render.TRANS))
    except ValueError:
        return web.Response(status=400, text="bad params")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in.pptx"), os.path.join(tmp, "out.mp4")
        with open(src, "wb") as f:
            async for chunk in request.content.iter_chunked(1 << 20):
                f.write(chunk)
        async with LOCK:
            try:
                await asyncio.get_running_loop().run_in_executor(None, render.com_export, src, dst, hold, trans)
            except Exception as exc:  # noqa: BLE001
                return web.Response(status=500, text=str(exc)[:300])
        return web.Response(body=open(dst, "rb").read(), content_type="video/mp4")


if __name__ == "__main__":
    app = web.Application(client_max_size=200 * 1024 * 1024)
    app.router.add_post("/render", handle_render)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8765")))
