import base64
import glob
import json
import logging
import os
import re
import subprocess
import uuid

import requests

from . import config

log = logging.getLogger("qa")


def pptx_to_images(pptx_path: str) -> list[str]:
    """LibreOffice + pdftoppm orqali har slaydni JPG'ga aylantiradi."""
    work_dir = os.path.join(config.WORK_DIR, f"qa_{uuid.uuid4().hex[:8]}")
    os.makedirs(work_dir, exist_ok=True)

    try:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", work_dir, pptx_path],
            check=True, timeout=120, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.error("LibreOffice mavjud emas yoki xato: %s", e)
        return []

    pdf_path = os.path.join(work_dir, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
    if not os.path.exists(pdf_path):
        log.error("PDF konvertatsiya muvaffaqiyatsiz: %s", pdf_path)
        return []

    try:
        subprocess.run(
            ["pdftoppm", "-jpeg", "-r", "150", pdf_path, os.path.join(work_dir, "slide")],
            check=True, timeout=120, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        # poppler har muhitda o'rnatilgan bo'lmaydi; PyMuPDF allaqachon
        # loyihada bor (yuklangan PDF'larni o'qish uchun) va shu ishni
        # bajara oladi, shuning uchun QA butunlay to'xtab qolmaydi.
        log.info("pdftoppm ishlamadi (%s), PyMuPDF bilan urinamiz", e)
        return _render_with_pymupdf(pdf_path, work_dir)

    return sorted(glob.glob(os.path.join(work_dir, "slide-*.jpg")))


def _render_with_pymupdf(pdf_path: str, work_dir: str) -> list[str]:
    """PDF sahifalarini PyMuPDF orqali JPG qiladi — poppler o'rniga."""
    try:
        import pymupdf as _pdf
    except ImportError:
        try:
            import fitz as _pdf
        except ImportError:
            log.error("Na pdftoppm, na PyMuPDF mavjud — vizual QA ishlamaydi")
            return []

    images = []
    try:
        with _pdf.open(pdf_path) as document:
            for number, page in enumerate(document, start=1):
                pixmap = page.get_pixmap(dpi=150)
                out_path = os.path.join(work_dir, f"slide-{number:03d}.jpg")
                pixmap.save(out_path)
                images.append(out_path)
    except Exception as e:
        log.error("PyMuPDF orqali rasmga aylantirish xatosi: %s", e)
        return []
    return images


def discard_images(images: list) -> None:
    """QA rasmlarini va ular turgan katalogni darhol o'chiradi.

    Har tekshiruv PDF va bir nechta JPG qoldiradi — 8 slaydli taqdimotda
    ~2 MB. Ular davriy tozalashni kutib yotsa, disk bandligi taqdimot
    sonidan ortib boradi.
    """
    directories = set()
    for path in images or []:
        directories.add(os.path.dirname(path))
        try:
            os.remove(path)
        except OSError:
            pass
    for directory in directories:
        if not directory or os.path.basename(directory).startswith("qa_") is False:
            continue
        try:
            for leftover in os.listdir(directory):
                os.remove(os.path.join(directory, leftover))
            os.rmdir(directory)
        except OSError:
            pass


def _b64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# Vision qaytaradigan tuzatish darajalari. Har biri boshqa narxga tushadi,
# shuning uchun model eng arzonini tanlashi kerak: ko'chirish bepul, slaydni
# qayta yaratish esa yangi model chaqiruvi.
LEVEL_OK = 0        # muammo yo'q
LEVEL_NUDGE = 1     # matnni surish yoki chegara ichiga tortish — kod hal qiladi
LEVEL_SIMPLIFY = 2  # ortiqcha element yoki ma'lumot olib tashlanadi
LEVEL_REBUILD = 3   # slayd qaytadan loyihalanadi

_REGION_KINDS = {"overlap", "offscreen", "small", "contrast", "clutter"}


def _clamp01(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _regions(raw) -> list[dict]:
    """Vision bergan sohalarni tekshirib, slayd duymiga aylantiradi.

    Model normallashtirilgan (0..1) koordinatalarda javob beradi, chunki u
    rasm o'lchamini bilmaydi. Bu yerda ular slayd duymiga o'tkaziladi.
    """
    out = []
    for entry in (raw or [])[:8]:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind", "")).strip().lower()
        if kind not in _REGION_KINDS:
            continue
        x = _clamp01(entry.get("x"))
        y = _clamp01(entry.get("y"))
        w = _clamp01(entry.get("w"))
        h = _clamp01(entry.get("h"))
        if w <= 0 or h <= 0:
            continue
        out.append({
            "kind": kind,
            "x": x * SLIDE_W,
            "y": y * SLIDE_H,
            "w": min(w, 1.0 - x) * SLIDE_W,
            "h": min(h, 1.0 - y) * SLIDE_H,
            "note": str(entry.get("note", ""))[:200],
        })
    return out


SLIDE_W = 13.333
SLIDE_H = 7.5


def check_slide_image(image_path: str, slide_context: str) -> dict:
    """Vision model orqali slaydni tekshiradi va tuzatish darajasini belgilaydi."""
    if not config.OPENROUTER_API_KEY:
        return {"level": LEVEL_OK, "issue": "", "remove": None, "regions": []}

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""Professional taqdimot slaydini QATTIQ va HALOL bahola, so'ng
uni TUZATISH uchun aniq ko'rsatma ber. Faqat qarab chiqish emas — muammoli
joyni belgilab ket.

Slayd konteksti: {slide_context}

TEKSHIRILADIGAN MEZONLAR:
1. MATN USTMA-UST — ikki matn bloki bir-birini yopganmi, o'qib bo'lmayaptimi?
2. TOSHIB KETISH — matn yoki element slayd chetidan chiqib ketganmi?
3. MATN O'LCHAMI — sarlavha ≥ 28pt, kichik sarlavha ≥ 16pt, tana ≥ 13pt.
4. KONTRAST — to'q fonda to'q matn yoki och fonda och matn bormi?
5. ORTIQCHA ELEMENT — mavzuga mos kelmaydigan diagramma yoki rasm bormi?
6. TIQILINCH — slayd shu qadar to'laki, hech narsani o'qib bo'lmaydimi?

TUZATISH DARAJASINI TANLA — eng arzonini, ortig'ini emas:
  0 — muammo yo'q.
  1 — joylashuv muammosi: matn ustma-ust yoki chetdan chiqqan, lekin mazmun
      joyida. Elementni surish yoki ichkariga tortish yetarli.
  2 — slaydda ortiqcha narsa bor: mantiqsiz diagramma, keraksiz rasm yoki
      juda ko'p matn. Bittasini olib tashlash kerak ("remove" ni to'ldir).
  3 — slayd tuzilishi buzuq: bir nechta blok bir-biriga xalaqit beradi va
      surish bilan tuzalmaydi. Slayd soddaroq qilib qayta yoziladi.

MUHIM: 3-darajani faqat 1 va 2 yordam bermaydigan holatda tanla — u eng
qimmat yo'l. Joylashuv muammosini har doim 1-daraja deb belgila.

"regions" — muammoli joylar. Koordinatalar 0..1 oralig'ida, slayd chap
yuqori burchagiga nisbatan (x=0 chap chekka, x=1 o'ng chekka).
kind: overlap | offscreen | small | contrast | clutter

Faqat JSON:
{{"level": 0,
  "issue": "aniq muammo tavsifi yoki bo'sh",
  "remove": null,
  "regions": [{{"kind":"overlap","x":0.42,"y":0.55,"w":0.30,"h":0.12,
                "note":"ikki matn bloki ustma-ust"}}]}}"""

    payload = {
        "model": config.OPENROUTER_VISION_MODEL,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{_b64(image_path)}",
                        "detail": "high"
                    }},
                ],
            }
        ],
    }
    try:
        resp = requests.post(config.OPENROUTER_URL, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        cleaned = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(cleaned)

        # Eski javob shakli ("ok": false) ham tushunilsin.
        if "level" not in result:
            result["level"] = LEVEL_OK if result.get("ok", True) else LEVEL_REBUILD
        try:
            level = int(result.get("level", LEVEL_OK))
        except (TypeError, ValueError):
            level = LEVEL_OK
        result["level"] = max(LEVEL_OK, min(level, LEVEL_REBUILD))
        result["regions"] = _regions(result.get("regions"))

        log.info("Vision QA: daraja=%s | %s | %s soha",
                 result["level"], (result.get("issue") or "")[:100],
                 len(result["regions"]))
        return result
    except Exception as e:
        log.error("Vision QA xatosi: %s", e)
        return {"level": LEVEL_OK, "issue": "", "remove": None, "regions": []}
