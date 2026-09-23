"""HTML slaydni brauzerda suratga oladi va PPTX ga yig'adi.

Slaydning ko'rinishi endi HTML/CSS bilan belgilanadi, ya'ni uni
python-pptx bilan qayta chizish shart emas: brauzer nima ko'rsatsa,
PowerPointda ham aynan o'sha turadi. Har slayd 1920×1080 PNG bo'lib,
13.333×7.5 dyuymli varaqni to'liq egallaydi.

Brauzer bitta marta ishga tushiriladi va slaydlar navbat bilan
olinadi: server kichik (1 vCPU / 2 GB), bir vaqtda ikkita Chromium
oynasi ochilsa xotira yetmaydi.
"""

import logging
import os
import tempfile
from typing import List

log = logging.getLogger("html_render")

SLIDE_W_PX = 1920
SLIDE_H_PX = 1080
SLIDE_W_IN = 13.333
SLIDE_H_IN = 7.5

# Chromium root ostida ishlaganda sandbox bilan darhol yopiladi.
_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--hide-scrollbars",
]

# Sahifa tashqi fayl so'ramaydi, shuning uchun "networkidle" ni kutish
# shart emas — u ba'zan bekorga sekundlar yeydi.
_WAIT_UNTIL = "load"
_TIMEOUT_MS = 30000


# Playwright brauzerni o'z versiyasi bo'yicha qidiradi. Kutubxona
# yangilangan, brauzer esa eski bo'lsa ("Executable doesn't exist"),
# shu yo'llar bo'yicha topilgani ishlatiladi. Serverda `playwright
# install chromium` qilingan bo'lsa, bu ro'yxatga umuman kerak
# bo'lmaydi.
_FALLBACK_BROWSERS = (
    os.getenv("PREMIUM_CHROMIUM_PATH", ""),
    "/opt/pw-browsers/chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
)


def _executable() -> str:
    """Playwright topolmasa ishlatiladigan brauzer yo'li."""
    for path in _FALLBACK_BROWSERS:
        if path and os.path.exists(path):
            return path
    return ""


def available() -> bool:
    """Playwright va brauzer shu serverda bormi."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False
    return True


def _launch(playwright):
    """Brauzerni ishga tushiradi — kerak bo'lsa zaxira yo'l bilan."""
    try:
        return playwright.chromium.launch(headless=True, args=_LAUNCH_ARGS)
    except Exception as exc:
        path = _executable()
        if not path:
            raise
        log.warning("Playwright brauzerni topmadi (%s), %s ishlatiladi",
                    str(exc).splitlines()[0][:120], path)
        return playwright.chromium.launch(
            headless=True, args=_LAUNCH_ARGS, executable_path=path)


def shoot(html_slides: List[str], out_dir: str = "temp") -> List[str]:
    """Har HTML hujjatni PNG qilib saqlaydi va yo'llarini qaytaradi.

    Bitta slayd chizilmasa, qolganlari baribir chiqadi — taqdimot
    bitta xato tufayli butunlay yo'qolmaydi.
    """
    from playwright.sync_api import sync_playwright

    os.makedirs(out_dir, exist_ok=True)
    paths: List[str] = []

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": SLIDE_W_PX, "height": SLIDE_H_PX},
                device_scale_factor=1,
            )
            try:
                page = context.new_page()
                for index, html in enumerate(html_slides, 1):
                    path = os.path.join(
                        out_dir, f"slide_{os.getpid()}_{index:02d}.png")
                    try:
                        page.set_content(html, wait_until=_WAIT_UNTIL,
                                         timeout=_TIMEOUT_MS)
                        page.screenshot(path=path, type="png",
                                        clip={"x": 0, "y": 0,
                                              "width": SLIDE_W_PX,
                                              "height": SLIDE_H_PX})
                        paths.append(path)
                    except Exception as exc:
                        log.error("%d-slayd chizilmadi: %s", index, exc)
            finally:
                context.close()
        finally:
            browser.close()

    log.info("Slaydlar suratga olindi: %d/%d", len(paths), len(html_slides))
    return paths


def build_pptx(image_paths: List[str], out_dir: str = "temp",
               name: str = "taqdimot") -> str:
    """PNG larni to'liq varaqni egallagan slaydlarga aylantiradi."""
    from pptx import Presentation
    from pptx.util import Inches

    if not image_paths:
        raise RuntimeError("Birorta slayd suratga olinmadi")

    presentation = Presentation()
    presentation.slide_width = Inches(SLIDE_W_IN)
    presentation.slide_height = Inches(SLIDE_H_IN)
    blank = presentation.slide_layouts[6]

    for path in image_paths:
        slide = presentation.slides.add_slide(blank)
        slide.shapes.add_picture(
            path, left=0, top=0,
            width=presentation.slide_width,
            height=presentation.slide_height)

    os.makedirs(out_dir, exist_ok=True)
    handle, out_path = tempfile.mkstemp(
        prefix=f"{name}_", suffix=".pptx", dir=out_dir)
    os.close(handle)
    presentation.save(out_path)
    return out_path


def render(html_slides: List[str], out_dir: str = "temp",
           name: str = "taqdimot") -> str:
    """HTML → PNG → PPTX. Vaqtinchalik rasmlar o'chiriladi."""
    images = shoot(html_slides, out_dir)
    try:
        return build_pptx(images, out_dir, name)
    finally:
        for path in images:
            try:
                os.remove(path)
            except OSError:
                pass
