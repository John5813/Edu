"""Lokal ikonkalarni slayd rangiga bo'yab beradi.

`assets/icons/` dagi 141 ta PNG bitta rangdagi siluet, foni shaffof. Shu
sababli ularni istalgan rangga bo'yash mumkin: shaffoflik qatlami niqob
bo'lib xizmat qiladi. Bitta fayl har qanday mavzuga va har qanday rang
sxemasiga yaraydi — yangi rasm generatsiya qilish (pul, kutish, harf
buzilishi) umuman shart emas.
"""
import functools
import hashlib
import logging
import os

log = logging.getLogger("icon_render")

_HERE = os.path.dirname(os.path.abspath(__file__))
ICONS_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "assets", "icons"))

# 96x96 slaydda ~0.5" da o'tkir, lekin 1" dan katta doirada yumshoq ko'rinadi.
RENDER_SIZE = 256


@functools.lru_cache(maxsize=1)
def icon_names() -> tuple[str, ...]:
    """Mavjud ikonkalar nomi (kengaytmasiz), alifbo tartibida."""
    try:
        names = [
            f[:-4] for f in os.listdir(ICONS_DIR)
            if f.endswith(".png") and f != "default.png"
        ]
    except OSError as exc:
        log.error("Ikonka papkasi o'qilmadi (%s): %s", ICONS_DIR, exc)
        return ()
    return tuple(sorted(names))


def resolve(name: str | None, fallback_text: str = "",
            used: set[str] | None = None) -> str | None:
    """Ikonka faylini topadi.

    Avval AI bergan aniq nom (`innovation`) tekshiriladi — prompt unga
    mavjud nomlar ro'yxatini beradi. Nom ro'yxatda bo'lmasa, uch tilli
    kalit-so'z lug'ati bo'yicha qidiriladi.
    """
    if name:
        candidate = os.path.join(ICONS_DIR, f"{name.strip().lower()}.png")
        if os.path.isfile(candidate):
            if used is not None:
                used.add(os.path.basename(candidate))
            return candidate

    text = " ".join(part for part in (name or "", fallback_text) if part).strip()
    if not text:
        return None
    try:
        from services.icon_service import find_icon_path
    except Exception as exc:  # pragma: no cover - import muhiti
        log.warning("icon_service mavjud emas: %s", exc)
        return None

    path = find_icon_path(text, used=used)
    if path is None and used:
        # Takrorlanmaslik qoidasi bir taqdimotda ikonkalarni tugatib
        # qo'yardi: qatordagi to'rt kartochkadan oxirgisi ikonkasiz qolar
        # edi. Ikonkasiz kartochkadan ko'ra takrorlangani yaxshiroq.
        path = find_icon_path(text)
    if path and used is not None:
        used.add(os.path.basename(path))
    return path


def _cache_dir() -> str:
    from . import config
    path = os.path.join(config.WORK_DIR, "icons")
    os.makedirs(path, exist_ok=True)
    return path


def tinted(icon_path: str, color: str) -> str | None:
    """Ikonkani berilgan rangga bo'yab, PNG sifatida saqlaydi va yo'lini qaytaradi.

    Natija keshlanadi: bitta taqdimotda bir ikonka bir necha marta uchrasa
    ham fayl bir marta tayyorlanadi.
    """
    if not icon_path or not os.path.isfile(icon_path):
        return None

    rgb = _rgb(color)
    key = hashlib.md5(f"{os.path.basename(icon_path)}|{rgb}|{RENDER_SIZE}".encode()).hexdigest()[:12]
    out_path = os.path.join(_cache_dir(), f"{key}.png")
    if os.path.isfile(out_path):
        return out_path

    try:
        from PIL import Image
    except ImportError as exc:
        log.error("Pillow yo'q, ikonka bo'yalmaydi: %s", exc)
        return icon_path

    try:
        with Image.open(icon_path) as src:
            glyph = src.convert("RGBA")
            if glyph.size != (RENDER_SIZE, RENDER_SIZE):
                glyph = glyph.resize((RENDER_SIZE, RENDER_SIZE), Image.LANCZOS)
            alpha = glyph.getchannel("A")
            tinted_img = Image.new("RGBA", glyph.size, rgb + (0,))
            tinted_img.putalpha(alpha)
            tinted_img.save(out_path, "PNG", optimize=True)
    except Exception as exc:
        log.error("Ikonka bo'yashda xato (%s): %s", icon_path, exc)
        return icon_path

    return out_path


def _rgb(hex_str: str | None) -> tuple[int, int, int]:
    h = (hex_str or "FFFFFF").lstrip("#").strip()
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    if len(h) != 6:
        return (255, 255, 255)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (255, 255, 255)


def _luminance(hex_str: str) -> float:
    channels = [c / 255 for c in _rgb(hex_str)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ink_on(fill: str | None) -> str:
    """Fon rangi ustida o'qiladigan siyoh rangini tanlaydi.

    Qaror haqiqiy kontrast bo'yicha: oddiy yorqinlik formulasi o'rta
    to'qlikdagi ranglarda oq ikonkani tanlab, uni fonda yo'qotardi.
    """
    fill = fill or "000000"

    def ratio(colour: str) -> float:
        a, b = _luminance(colour), _luminance(fill)
        high, low = max(a, b), min(a, b)
        return (high + 0.05) / (low + 0.05)

    return "1B2A4A" if ratio("1B2A4A") >= ratio("FFFFFF") else "FFFFFF"
