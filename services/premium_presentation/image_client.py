import base64
import logging
import os
import random
import threading
import time
import uuid

import requests

from . import config

log = logging.getLogger("image_client")

# Professional photography prefix — sifatni oshiradi
_QUALITY_PREFIX = (
    "professional photography, photorealistic, sharp focus, high detail, "
    "8k resolution, natural lighting, clean composition, "
)

# FLUX.1-schnell distillyatsiya qilingan model: Together uni 1-4 qadam bilan
# qabul qiladi, undan yuqorisi "steps must be <= 4" HTTP 400 beradi.
_MAX_SCHNELL_STEPS = 4

# `steps` ni hamma model qabul qilmaydi: FLUX.2-pro uni noma'lum parametr deb
# rad etadi. Shuning uchun u faqat quyidagi oilalarga yuboriladi.
_STEPS_MODELS = ("schnell", "dev", "flex")

# 429 ni oldini olish uchun so'rovlar orasidagi eng kichik oraliq.
_RATE_LOCK = threading.Lock()
_last_request_at = 0.0

_MAX_RETRY_WAIT = 30.0


def _build_prompt(raw_prompt: str) -> str:
    """AI bergan promptga professional sifat prefiksi qo'shadi."""
    return _QUALITY_PREFIX + raw_prompt.strip()


def _steps(model_name: str) -> int | None:
    """Model qabul qiladigan qadam sonini qaytaradi, qabul qilmasa None."""
    model = (model_name or "").lower()
    if not any(family in model for family in _STEPS_MODELS):
        return None
    steps = max(1, int(getattr(config, "TOGETHER_IMAGE_STEPS", 4)))
    if "schnell" in model:
        steps = min(steps, _MAX_SCHNELL_STEPS)
    return steps


# Ishlab turgan rasm modeli — birinchi muvaffaqiyatli so'rovdan keyin
# eslab qolinadi, shunda qolgan rasmlar uchun ishlamaydigan modellar
# qayta sinalmaydi (har biri 3 urinish va bir necha o'n soniya edi).
_WORKING_MODEL = None
# Oxirgi xato sababi — chaqiruvchi uni adminga ko'rsatishi uchun.
LAST_ERROR = ""
# Har model bo'yicha oxirgi xato: admin qaysi model nima sababdan
# ishlamaganini bir qarashda ko'rishi uchun. Faqat oxirgi sabab
# ko'rsatilganda "FLUX.1-schnell ishlamadi" deb chiqar, qolgan uchtasi
# nega rad etilgani noma'lum qolardi.
LAST_ERRORS: dict = {}


# Together katalogidan topilgan rasm modellari. Ro'yxatdagi nomlar
# hisobdan hisobga farq qiladi: bir hisobda FLUX.1-schnell serverless,
# boshqasida "non-serverless" deb rad etiladi. Shuning uchun taxmin
# qilish o'rniga katalog o'qiladi.
_CATALOGUE: list = []
_CATALOGUE_TRIED = False

# Katalogdagi modellarni saralash tartibi: sifatlisi oldinda, bepuli
# oxirida — lekin bepuli ham ishlagani ishlamaganidan yaxshiroq.
_PREFERENCE = (
    "flux.1.1-pro", "flux.2-pro", "flux.1-pro", "flux.1-krea",
    "flux.1-dev", "flux.1-schnell-free", "flux.1-schnell", "flux",
)


def _reason(body: str) -> str:
    """Together javobidan faqat xabar matnini ajratib oladi."""
    try:
        import json as _json

        data = _json.loads(body or "{}")
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or "")[:120]
        if error:
            return str(error)[:120]
    except Exception:
        pass
    return (body or "")[:120]


def _rank(model_id: str) -> int:
    name = model_id.lower()
    for index, marker in enumerate(_PREFERENCE):
        if marker in name:
            return index
    return len(_PREFERENCE)


def _catalogue() -> list:
    """Hisobda mavjud rasm modellarini Together katalogidan oladi.

    Bir marta so'raladi va eslab qolinadi. Katalog olinmasa bo'sh
    ro'yxat qaytadi — u holda faqat sozlamadagi nomlar sinaladi.
    """
    global _CATALOGUE, _CATALOGUE_TRIED
    if _CATALOGUE_TRIED:
        return _CATALOGUE
    _CATALOGUE_TRIED = True

    url = config.TOGETHER_IMAGE_URL.split("/images/")[0] + "/models"
    try:
        resp = requests.get(
            url, timeout=30,
            headers={"Authorization": f"Bearer {config.TOGETHER_API_KEY}"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("Together katalogini o'qib bo'lmadi: %s", e)
        return _CATALOGUE

    items = data.get("data") if isinstance(data, dict) else data
    found = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").lower() != "image":
            continue
        model_id = str(item.get("id") or "").strip()
        if model_id:
            found.append(model_id)
    _CATALOGUE = sorted(found, key=_rank)
    log.info("Together katalogida %s ta rasm modeli: %s",
             len(_CATALOGUE), ", ".join(_CATALOGUE[:6]))
    return _CATALOGUE


def _models() -> list:
    """Sinaladigan modellar: sozlamadagilar, so'ng katalogdan topilganlar."""
    chain = list(getattr(config, "TOGETHER_IMAGE_MODELS", None)
                 or [config.TOGETHER_IMAGE_MODEL])
    for model in _catalogue():
        if model not in chain:
            chain.append(model)
    if _WORKING_MODEL and _WORKING_MODEL in chain:
        return [_WORKING_MODEL] + [m for m in chain if m != _WORKING_MODEL]
    return chain


def _throttle() -> None:
    """Ketma-ket so'rovlar orasida minimal oraliqni ushlab turadi."""
    interval = float(getattr(config, "TOGETHER_MIN_INTERVAL", 0.0) or 0.0)
    if interval <= 0:
        return
    global _last_request_at
    with _RATE_LOCK:
        gap = time.monotonic() - _last_request_at
        if gap < interval:
            time.sleep(interval - gap)
        _last_request_at = time.monotonic()


def _retry_after(response) -> float | None:
    """Together bergan Retry-After sarlavhasini soniyaga aylantiradi."""
    if response is None:
        return None
    raw = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, min(float(raw.strip()), _MAX_RETRY_WAIT))
    except (TypeError, ValueError):
        return None


def generate_image(prompt: str, retries: int = 3) -> str | None:
    """Together AI orqali sifatli rasm generatsiya qiladi."""
    global LAST_ERROR
    if not config.TOGETHER_API_KEY:
        LAST_ERROR = "TOGETHER_API_KEY o'rnatilmagan"
        log.warning("TOGETHER_API_KEY yo'q, rasm generatsiyasi o'tkazib yuborildi")
        return None

    enhanced_prompt = _build_prompt(prompt)
    log.info("Rasm so'rovi: %s", enhanced_prompt[:160])

    for model in _models():
        path = _generate_with(model, enhanced_prompt, retries)
        if path:
            return path
    return None


def _generate_with(model_name: str, enhanced_prompt: str, retries: int) -> str | None:
    """Bitta model bilan urinadi. Sabab `LAST_ERROR` ga yoziladi."""
    global _WORKING_MODEL, LAST_ERROR

    headers = {
        "Authorization": f"Bearer {config.TOGETHER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "prompt": enhanced_prompt,
        "width": config.TOGETHER_IMAGE_WIDTH,
        "height": config.TOGETHER_IMAGE_HEIGHT,
        "n": 1,
        "seed": random.randint(1, 999999),
    }
    steps = _steps(model_name)
    if steps is not None:
        payload["steps"] = steps

    for attempt in range(1, retries + 1):
        try:
            _throttle()
            resp = requests.post(
                config.TOGETHER_IMAGE_URL,
                headers=headers,
                json=payload,
                timeout=150,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data") or []
            if not items:
                log.error("Together javobida 'data' bo'sh: %s", str(data)[:400])
                break

            item = items[0]
            os.makedirs(config.WORK_DIR, exist_ok=True)
            out_path = os.path.join(config.WORK_DIR, f"img_{uuid.uuid4().hex[:10]}.png")

            # b64_json ustuvor
            b64 = item.get("b64_json") or ""
            if b64:
                img_bytes = base64.b64decode(b64)
                with open(out_path, "wb") as f:
                    f.write(img_bytes)
                log.info("Rasm saqlandi (b64): %s | model %s", out_path, model_name)
                _WORKING_MODEL = model_name
                LAST_ERRORS.pop(model_name, None)
                return out_path

            # URL orqali yuklash
            url = item.get("url") or ""
            if url:
                img_resp = requests.get(
                    url, timeout=90, allow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                img_resp.raise_for_status()
                content = img_resp.content
                if not content:
                    log.error("URL orqali olingan rasm bo'sh: %s", url)
                    if attempt < retries:
                        time.sleep(2 * attempt)
                        continue
                    break
                with open(out_path, "wb") as f:
                    f.write(content)
                log.info("Rasm saqlandi (url): %s | %s bayt | model %s",
                         out_path, len(content), model_name)
                _WORKING_MODEL = model_name
                LAST_ERRORS.pop(model_name, None)
                return out_path

            log.error("Together javobida na b64_json na url: %s", item)
            break

        except requests.exceptions.HTTPError as e:
            response = e.response
            status = response.status_code if response is not None else "?"
            body = response.text[:300] if response is not None else ""
            LAST_ERROR = f"{model_name}: HTTP {status} {body[:160]}"
            LAST_ERRORS[model_name] = f"HTTP {status} {_reason(body)}"
            log.warning("Together HTTP %s (%s, urinish %s/%s): %s | %s",
                        status, model_name, attempt, retries, e, body)
            if status == 429:
                wait = _retry_after(response)
                if wait is None:
                    wait = min(5 * (2 ** (attempt - 1)), _MAX_RETRY_WAIT)
                log.info("Rate limit — %.1fs kutilmoqda", wait)
                time.sleep(wait)
                continue
            if isinstance(status, int) and status >= 500 and attempt < retries:
                time.sleep(2 * attempt)
                continue
            log.error("Qayta urinish bekor: HTTP %s | %s", status, body)
            break
        except Exception as e:
            LAST_ERROR = f"{model_name}: {e}"
            LAST_ERRORS[model_name] = str(e)[:120]
            log.warning("Together xato (%s, urinish %s/%s): %s",
                        model_name, attempt, retries, e)
            if attempt < retries:
                time.sleep(2 * attempt)

    log.error("Rasm chiqmadi (%s, %s urinish). Sabab: %s",
              model_name, retries, LAST_ERROR or "noma'lum")
    return None
