"""Saytda mijoz 3D modellarni o'zi tanlaydi: fanlar, bo'limlar, qidiruv va sahifalab ko'rish.

Faqat taklif qilsa bo'ladigan modellar chiqadi (diskda bor yoki avtomatik yuklanadi, hajmi taqdimotga sig'adi).
Mavzu tekshiruvi topgan modellar («mavzuga mos») har doim boshida turadi. Tanlangan ro'yxat buyurtmada qayta
tekshiriladi (`toza`): katalogda va serverda yo'q, takror yoki ortiqcha model o'tmaydi."""
import re
from typing import Dict, List, Optional, Sequence

MAX_MODELS = 12            # bitta taqdimotga (taxminan har slaydga bittadan)
MIN_MODELS = 2
PAGE = 40

FANLAR: Dict[str, str] = {
    "biologiya": "🧬 Biologiya", "tibbiyot": "🩺 Tibbiyot", "kimyo": "⚗️ Kimyo", "fizika": "🧲 Fizika",
    "matematika": "📐 Matematika", "geografiya": "🌍 Geografiya", "astronomiya": "🪐 Astronomiya",
    "tarix": "🏺 Tarix", "arxitektura": "🏛 Arxitektura", "san'at": "🎨 San'at", "texnika": "⚙️ Texnika",
    "transport": "🚗 Transport", "informatika": "💻 Informatika", "chizmachilik": "📏 Chizmachilik",
    "statistika": "📊 Statistika", "sport": "⚽ Sport", "musiqa": "🎵 Musiqa", "oshxona": "🍲 Oshxona",
    "adabiyot": "📚 Adabiyot", "bolalar": "🧸 Bolalar",
}


def _norm(s: str) -> str:
    return re.sub(r"[ʻʼ'`‘’]", "", (s or "").lower())


def _offerable() -> List[dict]:
    from services import katalog3d

    from . import qidiruv, yukla

    have = yukla.mumkin()
    return [m for i, m in katalog3d.katalog().items()
            if i in have and m.get("hajm", 0) <= qidiruv.MAX_MB * 1e6]


def card(m: dict) -> dict:
    return {"id": m["id"], "name": m.get("nom_uz") or m.get("nom") or "", "fan": m.get("fan", ""),
            "kat": m.get("kategoriya", "")}


def fanlar(models: Optional[List[dict]] = None) -> List[dict]:
    counts: Dict[str, int] = {}
    for m in models if models is not None else _offerable():
        counts[m.get("fan", "")] = counts.get(m.get("fan", ""), 0) + 1
    keys = [k for k in FANLAR if counts.get(k)] + sorted(k for k in counts if k and k not in FANLAR)
    return [{"key": k, "label": FANLAR.get(k, k.capitalize()), "count": counts[k]} for k in keys]


def mavzu_fanlari(ids: Sequence[str]) -> List[str]:
    """Mavzuga topilgan modellarning fanlari — ko'pi birinchi (tugmada «Biologiya modellarini tanlash»)."""
    from services import katalog3d

    cat = katalog3d.katalog()
    score: Dict[str, float] = {}
    for rank, mid in enumerate(ids):
        fan = cat.get(mid, {}).get("fan")
        if fan:
            score[fan] = score.get(fan, 0) + 1.0 / (1 + rank * 0.15)
    return sorted(score, key=lambda f: -score[f])


def royxat(fan: str = "", kat: str = "", q: str = "", offset: int = 0, suggested: Sequence[str] = (),
           limit: int = PAGE, topic: str = "") -> dict:
    """Bir sahifa: {items, total, offset, next, kats, fans}. `suggested` (mavzuga mos) — boshida, «mos» belgisi bilan;
    keyin mavzuga o'xshash modellar (nom va kalit so'zlar bo'yicha), keyin qolganlari."""
    models = _offerable()
    by_id = {m["id"]: m for m in models}
    fans = fanlar(models)
    pool = [m for m in models if not fan or m.get("fan") == fan]
    if fan != "bolalar":
        pool = [m for m in pool if m.get("tur") != "bolalar"]
    kats: Dict[str, int] = {}
    for m in pool:
        if m.get("kategoriya"):
            kats[m["kategoriya"]] = kats.get(m["kategoriya"], 0) + 1
    if kat:
        pool = [m for m in pool if m.get("kategoriya") == kat]
    words = [w for w in _norm(q).split() if len(w) > 1]
    if words:
        scored = []
        for m in pool:
            name = _norm(m.get("nom_uz", "") + " " + m.get("nom", ""))
            tags = _norm(" ".join(m.get("kalit") or []) + " " + m.get("kategoriya", ""))
            sc = sum(3 if w in name else 1 if w in tags else 0 for w in words)
            if sc:
                scored.append((-sc, -m.get("sifat", 0), m.get("nom_uz", ""), m["id"]))
        scored.sort()
        order = [x[-1] for x in scored]
    else:
        order = [m["id"] for m in sorted(pool, key=lambda m: (-m.get("sifat", 0), _norm(m.get("nom_uz", ""))))]
    allowed = set(order)
    top = [i for i in suggested if i in allowed]
    near: List[str] = []
    if topic and not words:
        from . import qidiruv

        near = [i for _, i in qidiruv.score(topic, [], available=frozenset(allowed), limit=300) if i not in top]
    head = top + near
    order = head + [i for i in order if i not in set(head)]
    offset = max(0, int(offset or 0))
    page = order[offset:offset + limit]
    items = []
    for i in page:
        c = card(by_id[i])
        c["mos"] = i in top
        items.append(c)
    return {"items": items, "total": len(order), "offset": offset,
            "next": offset + limit if offset + limit < len(order) else None,
            "kats": [{"key": k, "count": n} for k, n in sorted(kats.items(), key=lambda kv: -kv[1])],
            "fans": fans}


def toza(raw) -> List[str]:
    """Buyurtmadagi tanlov: faqat taklif qilsa bo'ladigan, takrorsiz, ko'pi bilan MAX_MODELS ta; kami — bo'sh."""
    if not isinstance(raw, (list, tuple)):
        return []
    ok = {m["id"] for m in _offerable()}
    out: List[str] = []
    for x in raw:
        x = str(x or "").strip()
        if x in ok and x not in out:
            out.append(x)
        if len(out) >= MAX_MODELS:
            break
    return out if len(out) >= MIN_MODELS else []


def kartalar(ids: Sequence[str]) -> List[dict]:
    from services import katalog3d

    cat = katalog3d.katalog()
    return [card(cat[i]) for i in ids if i in cat]
