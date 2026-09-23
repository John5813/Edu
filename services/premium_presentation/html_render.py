"""HTML slaydni brauzerda ochib, PowerPointga o'giradi.

Slaydni rasm qilib qo'yish oson bo'lardi, lekin o'shanda mijoz matnni
tuzata olmaydi. Shuning uchun brauzerdan har bir elementning aniq
o'rni, o'lchami va uslubi o'qib olinadi va PowerPointda o'sha
o'rinlarga haqiqiy matn qutisi, shakl va jadval qo'yiladi: joylashuvni
brauzer hisoblagani uchun hech narsa ustma-ust tushmaydi, matn esa
tahrirlanadigan bo'lib qoladi. Diagramma va murakkab grafika (SVG)
rasm bo'lib qo'yiladi.

Joylashuvni o'qib bo'lmasa, o'sha slayd butunicha suratga olinadi —
bo'sh slayd chiqmaydi.

Brauzer bitta marta ishga tushiriladi va slaydlar navbat bilan
ochiladi: server kichik (1 vCPU / 2 GB), bir vaqtda ikkita Chromium
oynasi ochilsa xotira yetmaydi.
"""

import glob
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
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


# Playwright brauzerni O'Z versiyasi bo'yicha qidiradi: kutubxona
# yangilansa, u yangi raqamli papkani kutadi va serverdagi eski brauzerni
# ko'rmaydi ("Executable doesn't exist at .../chromium_headless_shell-1243").
# Shuning uchun brauzer diskdan o'zimiz ham qidiramiz.
#
# Playwright brauzerlarni shu yerda saqlaydi:
#   $PLAYWRIGHT_BROWSERS_PATH yoki ~/.cache/ms-playwright
# ichida chromium-<raqam>/ va chromium_headless_shell-<raqam>/ papkalari.
_BROWSER_GLOBS = (
    "chromium-*/chrome-linux/chrome",
    "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
)

# Tizimga o'rnatilgan brauzerlar — Playwright papkasi umuman bo'lmasa.
_SYSTEM_BROWSERS = (
    # Replit's Nix/browser toolchain exposes Chromium here. This is more
    # reliable than downloading Playwright's headless shell at runtime.
    "/repl/tools/bin/chromium",
    "/opt/pw-browsers/chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
)

_INSTALL_HINT = ("Serverda brauzer ishga tushmadi.\n"
                 "Qo'lda bajaring (root ostida):\n"
                 "  venv/bin/playwright install chromium\n"
                 "  venv/bin/playwright install-deps chromium")

# Chromium ishlashi uchun kerak bo'ladigan tizim kutubxonalari.
# `install-deps` ishlamay qolsa (masalan apt manbasi boshqacha), shu
# ro'yxat to'g'ridan-to'g'ri o'rnatiladi.
_SYSTEM_PACKAGES = (
    "libatk1.0-0", "libatk-bridge2.0-0", "libcups2", "libdrm2",
    "libxkbcommon0", "libxcomposite1", "libxdamage1", "libxfixes3",
    "libxrandr2", "libgbm1", "libpango-1.0-0", "libcairo2",
    "libasound2", "libnss3", "libnspr4", "fonts-liberation",
)

# Brauzer bor, lekin ishga tushmadi — sabab tizim kutubxonasida.
_MISSING_LIBRARY = "shared librar"

# Brauzer bir marta o'rnatiladi. Bir vaqtda ikkita buyurtma kelsa,
# ikkovi ham yuklab olishga urinmasin.
_INSTALL_LOCK = threading.Lock()
_install_done = False
_install_error = ""


def install_browser(timeout: int = 900) -> str:
    """Brauzerni o'zimiz yuklab olamiz. Xato matnini qaytaradi ("" — joyida).

    Serverda `playwright install` ni qo'lda bajarish oson tushib
    ketardi: kutubxona yangilangach, u yangi brauzerni kutadi va eskisi
    yaramaydi. Shuning uchun brauzer topilmasa, kod o'zi yuklab oladi —
    bu bir marta bo'ladi va keyin hamma buyurtmada tayyor turadi.
    """
    global _install_done, _install_error

    with _INSTALL_LOCK:
        if _executable():
            _install_done = True
            return ""
        if _install_done:
            return _install_error or "brauzer o'rnatilmadi"

        command = [sys.executable, "-m", "playwright", "install", "chromium"]
        log.warning("Brauzer topilmadi — yuklab olinmoqda: %s",
                    " ".join(command))
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=timeout)
        except Exception as exc:
            _install_done = True
            _install_error = str(exc)[:300]
            log.error("Brauzerni yuklab bo'lmadi: %s", _install_error)
            return _install_error

        _install_done = True
        if _executable():
            log.info("Brauzer o'rnatildi: %s", _executable())
            _install_error = ""
            return ""

        _install_error = ((result.stderr or result.stdout or "").strip()[-300:]
                          or f"chiqish kodi {result.returncode}")
        log.error("Brauzer o'rnatilmadi: %s", _install_error)
        return _install_error


_DEPS_LOCK = threading.Lock()
_deps_done = False


def install_dependencies(timeout: int = 900) -> str:
    """Chromium uchun tizim kutubxonalarini o'rnatadi.

    Brauzerning o'zi yuklab olinsa ham, u GTK kutubxonalarisiz ishga
    tushmaydi: "libatk-1.0.so.0: cannot open shared object file". Bu
    kutubxonalar apt orqali o'rnatiladi va buning uchun root kerak —
    bot odatda root ostida ishlaydi, shuning uchun o'zi bajara oladi.
    """
    global _deps_done

    with _DEPS_LOCK:
        if _deps_done:
            return ""
        _deps_done = True

        environment = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
        commands = [
            [sys.executable, "-m", "playwright", "install-deps", "chromium"],
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "--no-install-recommends",
             *_SYSTEM_PACKAGES],
        ]

        failure = ""
        for command in commands:
            log.warning("Tizim kutubxonalari: %s", " ".join(command[:4]))
            try:
                result = subprocess.run(command, capture_output=True,
                                        text=True, timeout=timeout,
                                        env=environment)
            except Exception as exc:
                failure = str(exc)[:200]
                continue
            if result.returncode == 0:
                # Birinchi buyruq yetib qolsa, qolganlari kerak emas.
                if command[0] != "apt-get" or command[1] != "update":
                    log.info("Tizim kutubxonalari o'rnatildi")
                    return ""
                continue
            failure = (result.stderr or result.stdout or "").strip()[-200:]

        log.error("Tizim kutubxonalarini o'rnatib bo'lmadi: %s", failure)
        return failure or "apt ishlamadi"


def _browser_roots() -> List[str]:
    roots = []
    configured = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if configured and configured != "0":
        roots.append(configured)
    roots.append(os.path.expanduser("~/.cache/ms-playwright"))
    # Bot boshqa foydalanuvchi ostida ishga tushirilgan bo'lishi mumkin,
    # brauzer esa root ostida o'rnatilgan bo'ladi.
    roots.append("/root/.cache/ms-playwright")
    return [root for root in roots if os.path.isdir(root)]


def _executable() -> str:
    """Diskdagi eng yangi Chromium — Playwright topolmaganda ishlatiladi."""
    override = os.getenv("PREMIUM_CHROMIUM_PATH", "").strip()
    if override and os.path.exists(override):
        return override

    found = []
    for root in _browser_roots():
        for pattern in _BROWSER_GLOBS:
            found.extend(glob.glob(os.path.join(root, pattern)))
    if found:
        # Papka nomidagi raqam — build raqami; eng kattasi eng yangisi.
        def build_number(path: str) -> int:
            match = re.search(r"-(\d+)[/\\]", path)
            return int(match.group(1)) if match else 0

        return max(found, key=build_number)

    for path in _SYSTEM_BROWSERS:
        if os.path.exists(path):
            return path
    return ""


def available() -> bool:
    """Playwright ham, brauzer ham shu serverda bormi.

    Ilgari bu faqat kutubxona import bo'lishini tekshirardi va brauzer
    yo'qligi mijoz to'lovdan keyin bilinardi.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False
    return bool(_executable())


def prepare(install: bool = True) -> str:
    """Bot ishga tushganda chaqiriladi: brauzer tayyorligini ta'minlaydi.

    Xato matnini qaytaradi; hammasi joyida bo'lsa — bo'sh satr. Buyurtma
    kelguncha yuklab olinsa, mijoz kutib qolmaydi.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return "playwright kutubxonasi o'rnatilmagan"
    if not _executable():
        if not install:
            return "brauzer o'rnatilmagan"
        failure = install_browser()
        if failure:
            return failure

    # Brauzer borligi yetarli emas: u tizim kutubxonalarisiz ishga
    # tushmaydi. Buni bot ishga tushganda bilib olgan yaxshi — mijoz
    # to'lovdan keyin emas.
    return _launch_check(install)


def _launch_check(install: bool) -> str:
    """Brauzerni haqiqatan ishga tushirib ko'radi."""
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as playwright:
            browser = _launch(playwright) if install else \
                playwright.chromium.launch(headless=True, args=_LAUNCH_ARGS,
                                           executable_path=_executable())
            browser.close()
        return ""
    except Exception as exc:
        return str(exc).strip().splitlines()[0][:300]


def _launch(playwright):
    """Brauzerni ishga tushiradi — uch usulni ketma-ket sinab.

    1. Playwright o'zi bilgan brauzer (odatdagi holat).
    2. To'liq Chromium: yangi Playwright `headless=True` uchun alohida
       "headless shell" ni kutadi, serverda esa ko'pincha faqat to'liq
       Chromium o'rnatilgan bo'ladi.
    3. Diskdan topilgan brauzer yo'li.
    """
    attempts = []
    try:
        return playwright.chromium.launch(headless=True, args=_LAUNCH_ARGS)
    except Exception as exc:
        attempts.append(str(exc).splitlines()[0][:160])

    try:
        return playwright.chromium.launch(
            headless=True, args=_LAUNCH_ARGS, channel="chromium")
    except Exception as exc:
        attempts.append(str(exc).splitlines()[0][:160])

    path = _executable()
    if not path:
        # Brauzer umuman yo'q — o'zimiz yuklab olamiz.
        failure = install_browser()
        path = _executable()
        if not path:
            raise RuntimeError(
                f"{_INSTALL_HINT}\n\nO'rnatish xatosi: {failure}\n"
                + "\n".join(attempts))
        try:
            return playwright.chromium.launch(headless=True, args=_LAUNCH_ARGS)
        except Exception as exc:
            attempts.append(str(exc).splitlines()[0][:160])

    try:
        log.warning("Playwright brauzerni topmadi (%s) — %s ishlatiladi",
                    attempts[0], path)
        return playwright.chromium.launch(
            headless=True, args=_LAUNCH_ARGS, executable_path=path)
    except Exception as exc:
        attempts.append(str(exc).splitlines()[0][:160])

    # Brauzer bor, lekin ishga tushmadi. Deyarli har doim sabab bitta:
    # GTK kutubxonalari o'rnatilmagan. Ularni o'rnatib, qayta sinaymiz.
    if not any(_MISSING_LIBRARY in attempt.lower() for attempt in attempts):
        joined = "\n".join(attempts)
        if _MISSING_LIBRARY not in joined.lower():
            log.info("Brauzer ishga tushmadi — kutubxonalar sinab ko'riladi")
    failure = install_dependencies()
    try:
        return playwright.chromium.launch(
            headless=True, args=_LAUNCH_ARGS, executable_path=path)
    except Exception as exc:
        attempts.append(str(exc).splitlines()[0][:200])

    raise RuntimeError(
        f"{_INSTALL_HINT}\n\nKutubxona xatosi: {failure}\n"
        + "\n".join(attempts[-2:]))


def _open_page(context, html: str):
    page = context.new_page()
    page.set_content(html, wait_until=_WAIT_UNTIL, timeout=_TIMEOUT_MS)
    return page


def shoot(html_slides: List[str], out_dir: str = "temp") -> List[str]:
    """Har HTML hujjatni to'liq PNG qilib saqlaydi.

    Tahrirlanadigan slayd asosiy yo'l; bu yerdagi surat ko'rish va
    tekshirish uchun kerak (do'kondagi namunalar ham shundan olinadi).
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


def _save(presentation, out_dir: str, name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    handle, out_path = tempfile.mkstemp(
        prefix=f"{name}_", suffix=".pptx", dir=out_dir)
    os.close(handle)
    presentation.save(out_path)
    return out_path


def build_pptx(image_paths: List[str], out_dir: str = "temp",
               name: str = "taqdimot") -> str:
    """PNG larni to'liq varaqni egallagan slaydlarga aylantiradi."""
    from . import pptx_build

    if not image_paths:
        raise RuntimeError("Birorta slayd suratga olinmadi")

    presentation = pptx_build.new_presentation()
    for path in image_paths:
        pptx_build.add_picture_slide(presentation, path)
    return _save(presentation, out_dir, name)


def render(html_slides: List[str], out_dir: str = "temp",
           name: str = "taqdimot", repair=None) -> str:
    """HTML → tahrirlanadigan PPTX.

    Har slayd brauzerda ochiladi, joylashuvi o'qiladi va PowerPointning
    haqiqiy matn qutilari, shakllari va jadvallariga aylanadi. Bir slayd
    o'qilmasa, o'sha slaydning o'zi surat bo'lib tushadi — qolganlari
    baribir tahrirlanadi.

    `repair(html, problems) -> html` berilsa, joylashuvi buzilgan slayd
    bir marta qayta chizdiriladi: AI HTML ni brauzersiz yozadi va
    ba'zan varaqdan chiqib ketadigan yoki matn ustiga matn qo'yadigan
    kod chiqaradi. Buni faqat brauzer ko'radi.
    """
    from playwright.sync_api import sync_playwright

    from . import html_extract, pptx_build

    if not html_slides:
        raise RuntimeError("Slayd yo'q")

    os.makedirs(out_dir, exist_ok=True)
    presentation = pptx_build.new_presentation()
    temporary: List[str] = []
    editable = 0

    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            context = browser.new_context(
                viewport={"width": SLIDE_W_PX, "height": SLIDE_H_PX},
                device_scale_factor=1,
            )
            try:
                for index, html in enumerate(html_slides, 1):
                    page = None
                    try:
                        page = _open_page(context, html)

                        if repair is not None:
                            problems = html_extract.check_layout(page)
                            if problems:
                                log.warning("%d-slayd joylashuvi: %s",
                                            index, "; ".join(problems))
                                fixed = repair(html, problems)
                                if fixed and fixed != html:
                                    page.close()
                                    page = _open_page(context, fixed)
                                    left = html_extract.check_layout(page)
                                    if len(left) > len(problems):
                                        # Tuzatish yomonlashtirdi — eskisi
                                        # qaytariladi.
                                        page.close()
                                        page = _open_page(context, html)
                                    else:
                                        log.info("%d-slayd tuzatildi", index)

                        layout = html_extract.read_layout(page)
                        blocks = layout.get("blocks") or []
                        if not blocks:
                            raise RuntimeError("element topilmadi")
                        html_extract.capture_images(
                            page, blocks, out_dir, index)
                        temporary.extend(
                            block["path"] for block in blocks
                            if block.get("path"))
                        pptx_build.add_slide(presentation, layout)
                        editable += 1
                    except Exception as exc:
                        log.warning("%d-slayd o'qilmadi (%s) — surat qilinadi",
                                    index, exc)
                        _picture_fallback(presentation, page, out_dir,
                                          index, temporary)
                    finally:
                        if page is not None:
                            try:
                                page.close()
                            except Exception:
                                pass
            finally:
                context.close()
        finally:
            browser.close()

    log.info("Taqdimot tayyor: %d/%d slayd tahrirlanadi",
             editable, len(html_slides))
    try:
        return _save(presentation, out_dir, name)
    finally:
        for path in temporary:
            try:
                os.remove(path)
            except OSError:
                pass


def _picture_fallback(presentation, page, out_dir: str, index: int,
                      temporary: List[str]) -> None:
    """Slayd o'qilmasa — o'sha slaydning suratini qo'yadi."""
    if page is None:
        return
    path = os.path.join(out_dir, f"fallback_{os.getpid()}_{index:02d}.png")
    try:
        page.screenshot(path=path, type="png",
                        clip={"x": 0, "y": 0,
                              "width": SLIDE_W_PX, "height": SLIDE_H_PX})
        temporary.append(path)
        from . import pptx_build
        pptx_build.add_picture_slide(presentation, path)
    except Exception as exc:
        log.error("%d-slayd butunlay chiqmadi: %s", index, exc)
