"""Brave Search API kalitlari: bir nechta kalit navbat bilan ishlaydi.

Har kalit `LIMIT` (sukut — 900) so'rovdan keyin navbatdagisiga almashadi. Kalit rad etilsa (401/403 — noto'g'ri,
429 — limit tugagan) darhol keyingisiga o'tiladi — shuning uchun hisobi yuritilmagan eski kalit 900 ga yetmay
tugasa ham ish to'xtamaydi. Admin istalgan kalitga qo'lda o'tishi yoki joriysini o'tkazib yuborishi mumkin. Hamma kalit limitga yetsa — hisob boshidan boshlanadi (yangi
davr), har oy boshida hisoblagichlar o'zi nollanadi. Kalitlar admin panel orqali qo'shiladi va
`data/brave_keys.json` da saqlanadi; `.env` dagi `BRAVE_API_KEY` ham ro'yxatga birinchi bo'lib kiradi.
"""
import json
import os
import threading
import time
from typing import List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.getenv("BRAVE_KEYS_FILE") or os.path.join(ROOT, "data", "brave_keys.json")
LIMIT = int(os.getenv("BRAVE_KEY_LIMIT") or 900)

_lock = threading.Lock()


def _env_key() -> str:
    return (os.getenv("BRAVE_API_KEY") or os.getenv("BRAVE_SEARCH_API_KEY") or "").strip()


def _month() -> str:
    return time.strftime("%Y-%m")


def _load() -> dict:
    try:
        with open(PATH, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    doc.setdefault("keys", [])
    doc.setdefault("current", 0)
    env = _env_key()
    if env and all(k["key"] != env for k in doc["keys"]):
        doc["keys"].insert(0, {"key": env, "used": 0, "failed": False, "added": "env"})
    if doc.get("month") != _month():            # yangi oy — Brave limitlari ham yangilanadi
        doc["month"] = _month()
        for k in doc["keys"]:
            k["used"], k["failed"] = 0, False
            k.pop("error", None)
    return doc


def _save(doc: dict) -> None:
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def _usable(k: dict) -> bool:
    return not k.get("failed") and int(k.get("used", 0)) < LIMIT


def _pick(doc: dict) -> Optional[int]:
    """Joriy kalit (limitga yetgan bo'lsa — navbatdagisi). Hammasi limitda — yangi davr."""
    keys = doc["keys"]
    if not keys:
        return None
    n = len(keys)
    start = int(doc.get("current", 0)) % n
    for step in range(n):
        i = (start + step) % n
        if _usable(keys[i]):
            return i
    if all(k.get("failed") for k in keys):
        return None
    for k in keys:                               # hammasi 900 ga yetdi — hisob boshidan
        k["used"] = 0
    return next((i for i, k in enumerate(keys) if not k.get("failed")), None)


def current() -> str:
    """Hozir ishlatiladigan kalit (hisoblagich oshmaydi) — "Brave yoqilganmi" tekshiruvi uchun."""
    with _lock:
        doc = _load()
        i = _pick(doc)
        return doc["keys"][i]["key"] if i is not None else ""


def take() -> str:
    """So'rov uchun kalit: hisoblagich bittaga oshadi, limitga yetsa keyingisiga o'tiladi."""
    with _lock:
        doc = _load()
        i = _pick(doc)
        if i is None:
            _save(doc)
            return ""
        doc["keys"][i]["used"] = int(doc["keys"][i].get("used", 0)) + 1
        doc["current"] = i
        _save(doc)
        return doc["keys"][i]["key"]


ALERT_EVERY = 6 * 3600          # bir kalit haqidagi bir xil ogohlantirish shundan tez takrorlanmaydi
ALL_DOWN_EVERY = 3 * 3600       # «hamma kalit tugadi» — har 3 soatda eslatiladi (muammo hal bo'lmaguncha)
LOW_LEFT = 0.1                  # oylik limitli kalitda shuncha ulush (10%) qolganda ogohlantiriladi


def _windows(headers, name: str) -> List[int]:
    """`X-RateLimit-Remaining: 49, 0` → [49, 0] (soniyalik, oylik). Yo'q bo'lsa — []."""
    raw = ""
    try:
        raw = headers.get(name) or headers.get(name.lower()) or ""
    except Exception:
        pass
    out = []
    for part in str(raw).split(","):
        try:
            out.append(int(part.strip()))
        except ValueError:
            pass
    return out


def _alert(key: str, text: str, cooldown: float = ALERT_EVERY) -> None:
    try:
        from services import admin_alerts
        admin_alerts.alert(key, text, cooldown)
    except Exception:
        pass


def _where(doc: dict, key: str) -> str:
    for i, k in enumerate(doc["keys"]):
        if k["key"] == key:
            return f"№{i + 1} ({mask(key)})"
    return mask(key)


def _after_change(doc: dict) -> None:
    """Ishlaydigan kalit qolmagan bo'lsa — adminga qattiq ogohlantirish."""
    alive = [k for k in doc["keys"] if _usable(k)]
    if doc["keys"] and not alive:
        _alert("brave_all_down",
               "🚨 Brave: HAMMA kalitlarning limiti tugadi yoki yaroqsiz.\n"
               "Taqdimotlarda internetdan rasm va yangi faktlar topilmayapti (rasmlar faqat AI bilan chiziladi, "
               "statistik mavzularda raqamlar eskirishi mumkin).\n"
               "Yechim: search.brave.com/api da kredit to'ldiring yoki admin panel → 🔑 Brave kalitlari → "
               "«➕ Kalit qo'shish». To'ldirgandan keyin «▶️ ...-kalitga o'tish» ni bosing.", ALL_DOWN_EVERY)


def note_response(key: str, headers) -> None:
    """Muvaffaqiyatli javob sarlavhalaridan oylik qoldiqni yozadi (oylik limitli tariflarda) va kam qolsa ogohlantiradi.

    Kredit bo'yicha (oylik limit «0») tariflarda Brave qoldiqni bermaydi — u holda kredit tugaganini 402 bildiradi."""
    limits, left = _windows(headers, "X-RateLimit-Limit"), _windows(headers, "X-RateLimit-Remaining")
    with _lock:
        doc = _load()
        k = next((k for k in doc["keys"] if k["key"] == key), None)
        if k is not None and k.get("error"):          # kredit to'ldirildi — kalit yana ishlayapti
            k.pop("error", None)
            _save(doc)
    if len(limits) < 2 or len(left) < 2 or limits[1] <= 0:
        return
    quota, remaining = limits[1], left[1]
    with _lock:
        doc = _load()
        for k in doc["keys"]:
            if k["key"] == key:
                k["quota"], k["left"] = quota, remaining
        where = _where(doc, key)
        _save(doc)
    if remaining <= max(1, int(quota * LOW_LEFT)):
        _alert(f"brave_low:{key[-6:]}", f"⚠️ Brave kaliti {where}: shu oyga {remaining} ta so'rov qoldi "
                                         f"({quota} tadan). Tugasa keyingi kalitga o'tiladi — zaxira kalit qo'shib qo'ying.")


def report_failure(key: str, status: int, headers=None) -> None:
    """Brave kalitni rad etdi: 402 (kredit tugagan) yoki oylik 429 — shu oy limiti tugagan, 401/403 — kalit yaroqsiz.

    Soniyalik cheklov (429, oylik qoldiq hali bor) kalitni «tugagan» qilmaydi. Har holatda adminga xabar boriladi."""
    if status == 429 and headers is not None:
        limits, left = _windows(headers, "X-RateLimit-Limit"), _windows(headers, "X-RateLimit-Remaining")
        if len(left) >= 2 and (len(limits) < 2 or limits[1] <= 0 or left[1] > 0):
            return                       # faqat soniyalik chegara — kalit ishlayveradi
    with _lock:
        doc = _load()
        for k in doc["keys"]:
            if k["key"] == key:
                k["error"] = f"HTTP {status} · {time.strftime('%d.%m %H:%M')}"
                if status in (429, 402):
                    k["used"] = LIMIT
                else:
                    k["failed"] = True
        where = _where(doc, key)
        alive = sum(1 for k in doc["keys"] if _usable(k))
        _save(doc)
        if status == 402:
            why = "krediti tugadi (HTTP 402)"
        elif status == 429:
            why = "oylik limiti tugadi (HTTP 429)"
        else:
            why = f"rad etildi — kalit yaroqsiz yoki o'chirilgan (HTTP {status})"
        _alert(f"brave_fail:{key[-6:]}:{status}",
               f"⚠️ Brave kaliti {where} {why}.\n"
               + (f"Keyingi kalitga o'tildi, ishlaydigan kalitlar: {alive} ta." if alive else "Boshqa ishlaydigan kalit yo'q."))
        _after_change(doc)


def add(key: str) -> bool:
    key = key.strip()
    with _lock:
        doc = _load()
        if not key or any(k["key"] == key for k in doc["keys"]):
            return False
        doc["keys"].append({"key": key, "used": 0, "failed": False, "added": time.strftime("%Y-%m-%d")})
        _save(doc)
        return True


def remove(index: int) -> bool:
    with _lock:
        doc = _load()
        if not 0 <= index < len(doc["keys"]):
            return False
        doc["keys"].pop(index)
        doc["current"] = 0
        _save(doc)
        return True


def activate(index: int) -> bool:
    """Admin tanlovi: shu kalitga qo'lda o'tish (yaroqsiz yoki limitda deb belgilangan bo'lsa ham — qayta sinaladi)."""
    with _lock:
        doc = _load()
        if not 0 <= index < len(doc["keys"]):
            return False
        k = doc["keys"][index]
        k["failed"] = False
        k.pop("error", None)
        if int(k.get("used", 0)) >= LIMIT:
            k["used"] = 0
        doc["current"] = index
        _save(doc)
        return True


def skip() -> int:
    """Hozirgi kalitni shu davrga "tugagan" deb belgilab, keyingisiga o'tish. Qaytaradi: yangi faol kalit raqami
    (0 dan), kalit qolmasa -1."""
    with _lock:
        doc = _load()
        i = _pick(doc)
        if i is None:
            return -1
        doc["keys"][i]["used"] = LIMIT
        doc["current"] = (i + 1) % len(doc["keys"])
        j = _pick(doc)
        if j is not None:
            doc["current"] = j
        _save(doc)
        return -1 if j is None else j


def reset() -> None:
    """Hamma hisoblagich va "yaroqsiz" belgisini nollash (masalan, tarif yangilangach)."""
    with _lock:
        doc = _load()
        for k in doc["keys"]:
            k["used"], k["failed"] = 0, False
            k.pop("error", None)
        doc["current"] = 0
        _save(doc)


def mask(key: str) -> str:
    return key[:4] + "…" + key[-4:] if len(key) > 10 else "…"


def status() -> List[dict]:
    """Admin panel uchun: [{n, mask, used, failed, active, added}]."""
    with _lock:
        doc = _load()
        active = _pick(doc)
        return [{"n": i + 1, "mask": mask(k["key"]), "used": int(k.get("used", 0)), "failed": bool(k.get("failed")),
                 "active": i == active, "added": k.get("added", ""), "error": k.get("error", ""),
                 "left": k.get("left"), "quota": k.get("quota"), "spent": int(k.get("used", 0)) >= LIMIT}
                for i, k in enumerate(doc["keys"])]
