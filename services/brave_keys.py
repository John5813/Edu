"""Brave Search API kalitlari: bir nechta kalit navbat bilan ishlaydi.

Har kalit `LIMIT` (sukut — 900) so'rovdan keyin navbatdagisiga almashadi. Kalit rad etilsa (401/403 — noto'g'ri,
429 — limit tugagan) darhol keyingisiga o'tiladi. Hamma kalit limitga yetsa — hisob boshidan boshlanadi (yangi
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


def report_failure(key: str, status: int) -> None:
    """Brave kalitni rad etdi: 429 — shu oy limiti tugagan, 401/403 — kalit yaroqsiz."""
    with _lock:
        doc = _load()
        for k in doc["keys"]:
            if k["key"] == key:
                if status == 429:
                    k["used"] = LIMIT
                else:
                    k["failed"] = True
        _save(doc)


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


def reset() -> None:
    """Hamma hisoblagich va "yaroqsiz" belgisini nollash (masalan, tarif yangilangach)."""
    with _lock:
        doc = _load()
        for k in doc["keys"]:
            k["used"], k["failed"] = 0, False
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
                 "active": i == active, "added": k.get("added", "")} for i, k in enumerate(doc["keys"])]
