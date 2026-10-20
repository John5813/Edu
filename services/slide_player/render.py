"""PPTX → MP4 (PowerPoint o'zida) → FFmpeg bilan statik kadrlar va Morph bo'laklari.

Render usullari (`available()` tekshiradi):
  1. `SLIDE_RENDER_URL` — Windows VPS'dagi `tools/render_server.py` (bot Linux'da bo'lsa shu);
  2. Windows'ning o'zida PowerPoint COM (pywin32).

Video vaqt chizig'i (har slayd — `TRANS` soniya o'tish + `HOLD` soniya to'xtash; 1-slaydda o'tish yo'q):
  start(1) = 0;  start(i) = HOLD + (i-2) * (TRANS+HOLD)  (i >= 2);
  Morph (i-1 → i) = [start(i), start(i)+TRANS];  statik(i) = slayd tugashidan sal oldin.
"""
import asyncio
import logging
import os
import shutil
import subprocess
from typing import List, Optional

log = logging.getLogger(__name__)

HOLD = 2.0            # slayd to'xtab turadigan vaqt (soniya) — animatsiyalar shu vaqtda tugashi kerak
TRANS = 2.0           # o'tish (Morph) davomiyligi
FPS = 30
HEIGHT = 1080
RENDER_TIMEOUT = 900


class RenderUnavailable(RuntimeError):
    pass


def _remote() -> tuple:
    return os.environ.get("SLIDE_RENDER_URL", "").rstrip("/"), os.environ.get("SLIDE_RENDER_KEY", "")


def available() -> bool:
    if not shutil.which("ffmpeg"):
        return False
    if _remote()[0]:
        return True
    if os.name != "nt":
        return False
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    return True


def slide_start(index: int, hold: float = HOLD, trans: float = TRANS) -> float:
    """`index` — 0 dan boshlanadigan slayd raqami."""
    return 0.0 if index == 0 else hold + (index - 1) * (trans + hold)


def slide_end(index: int, count: int, hold: float = HOLD, trans: float = TRANS) -> float:
    return slide_start(index, hold, trans) + (hold if index == 0 else trans + hold)


def com_export(pptx: str, mp4: str, hold: float = HOLD, trans: float = TRANS) -> None:
    """Windows + PowerPoint: taqdimotni MP4 ga o'giradi (slayd vaqtlari yuqoridagi chizma bo'yicha)."""
    import time

    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    app = win32com.client.Dispatch("PowerPoint.Application")
    pres = None
    try:
        pres = app.Presentations.Open(os.path.abspath(pptx), WithWindow=False)
        for i, slide in enumerate(pres.Slides):
            t = slide.SlideShowTransition
            if i > 0:
                t.Duration = trans
            t.AdvanceOnTime = True
            t.AdvanceOnClick = False
            t.AdvanceTime = hold if i == 0 else hold + trans
        out = os.path.abspath(mp4)
        if os.path.exists(out):
            os.remove(out)
        pres.CreateVideo(out, True, 0, HEIGHT, FPS, 85)
        deadline = time.time() + RENDER_TIMEOUT
        while True:
            status = pres.CreateVideoStatus       # 1 — ketmoqda, 2 — navbatda, 3 — tayyor, 4 — xato
            if status == 3:
                break
            if status == 4 or time.time() > deadline:
                raise RuntimeError(f"PowerPoint video yaratolmadi (status={status})")
            time.sleep(1)
        time.sleep(1)
    finally:
        if pres is not None:
            pres.Close()
        pythoncom.CoUninitialize()


async def _remote_export(pptx: str, mp4: str) -> None:
    import aiohttp

    url, key = _remote()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    params = {"hold": str(HOLD), "trans": str(TRANS), "fps": str(FPS), "height": str(HEIGHT)}
    timeout = aiohttp.ClientTimeout(total=RENDER_TIMEOUT)
    with open(pptx, "rb") as src:
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.post(f"{url}/render", data=src, params=params, headers=headers) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"render server: {resp.status} {(await resp.text())[:200]}")
                with open(mp4, "wb") as dst:
                    async for chunk in resp.content.iter_chunked(1 << 20):
                        dst.write(chunk)


def _ffmpeg(*args: str) -> None:
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *args]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if done.returncode != 0:
        raise RuntimeError(f"ffmpeg: {done.stderr[-300:]}")


def cut(video: str, out_dir: str, count: int) -> dict:
    """Katta videodan: slideN_static.jpg va morph_N_to_M.mp4 (H.264, audiosiz, faststart)."""
    slides: List[str] = []
    morphs: List[Optional[str]] = []
    scale = f"scale=-2:'min({HEIGHT},ih)'"
    for i in range(count):
        name = f"slide{i + 1}_static.jpg"
        at = max(slide_end(i, count) - 0.15, 0.0)
        _ffmpeg("-ss", f"{at:.3f}", "-i", video, "-frames:v", "1", "-q:v", "3", os.path.join(out_dir, name))
        slides.append(name)
    for i in range(1, count):
        name = f"morph_{i}_to_{i + 1}.mp4"
        _ffmpeg("-ss", f"{slide_start(i):.3f}", "-t", f"{TRANS:.3f}", "-i", video, "-an", "-vf", scale,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", os.path.join(out_dir, name))
        morphs.append(name)
    return {"slides": slides, "morphs": morphs}


async def build_package(pptx: str, out_dir: str) -> dict:
    """PPTX → `out_dir` ichida statik kadrlar va Morph bo'laklari; manifest ma'lumotini qaytaradi."""
    from pptx import Presentation

    if not available():
        raise RenderUnavailable("render usuli sozlanmagan")
    count = len(Presentation(pptx).slides)
    os.makedirs(out_dir, exist_ok=True)
    full = os.path.join(out_dir, "_full.mp4")
    try:
        if _remote()[0]:
            await _remote_export(pptx, full)
        else:
            await asyncio.get_running_loop().run_in_executor(None, com_export, pptx, full)
        return await asyncio.get_running_loop().run_in_executor(None, cut, full, out_dir, count)
    finally:
        if os.path.exists(full):
            os.remove(full)
