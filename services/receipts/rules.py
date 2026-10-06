"""Chek bo'yicha qaror qoidalari.

AI chekni faqat O'QIYDI; qaror shu yerda, aniq qoidalar bilan chiqariladi. Sabablar to'planadi
(birinchisida to'xtamaydi), shunda admin barcha muammoni bir karta ichida ko'radi.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

# O'zbekistonda yozgi vaqt yo'q: UTC+5.
TASHKENT = timezone(timedelta(hours=5))


def now_tashkent() -> datetime:
    """Hozirgi Toshkent vaqti (naive) — cheklardagi vaqt ham shu zonada."""
    return datetime.now(TASHKENT).replace(tzinfo=None)


# Verdictlar
AUTO = "auto"                    # avtomatik tasdiqlanadi
REVIEW = "review"                # admin tugmalar bilan hal qiladi
DUPLICATE = "duplicate"          # takroriy chek (admin ko'radi, mijoz ogohlantiriladi)
WRONG_RECEIVER = "wrong_receiver"
NOT_RECEIPT = "not_receipt"      # chek emas: qayta yuborish so'raladi
OWN_PENDING = "own_pending"      # o'zining tekshirilayotgan cheki qayta yuborildi

STRONG_KINDS = ("id", "cmp", "file", "scr")     # bularning mos kelishi — takroriy chek
WEAK_KINDS = ("wk", "scr2")                     # mos kelishi — shubha, lekin jazo emas

_PHOTO_EDITORS = re.compile(
    r"photoshop|gimp|snapseed|picsart|canva|lightroom|pixlr|photopea|facetune|remini|"
    r"fotor|polarr|vsco|afterlight|paint\.net|affinity", re.IGNORECASE)


@dataclass
class Receipt:
    """Claude o'qigan va kod normallashtirgan chek ma'lumoti."""
    doc_type: str = "other"                  # transfer | payment | tax_receipt | other
    status: str = "unknown"                  # success | failed | pending | unknown
    readable: bool = True
    amount: Optional[int] = None             # o'tkazma summasi (komissiyasiz), so'm
    fee: Optional[int] = None
    currency: str = "UZS"
    dt: Optional[datetime] = None            # chekdagi operatsiya vaqti (Toshkent)
    ids: List[str] = field(default_factory=list)
    sender_name: str = ""
    sender_tail: str = ""                    # karta oxirgi 4 raqam
    receiver_name: str = ""
    receiver_tail: str = ""
    app: str = ""
    status_time: Optional[str] = None        # skrinshotdagi telefon soati "HH:MM"
    battery: Optional[int] = None
    cropped: bool = False
    tamper: str = "none"                     # none | low | high
    tamper_reason: str = ""
    meta_flags: List[str] = field(default_factory=list)   # EXIF/PDF: tahrirlovchi dastur izi
    is_screenshot: bool = False
    confidence: float = 1.0                  # Claude o'qishga ishonchi (0..1)
    raw: Dict = field(default_factory=dict)


@dataclass
class Context:
    now: datetime
    claimed: int                              # mijoz ko'rsatgan summa
    cards: Tuple[str, ...]                    # bizning kartalar oxirgi 4 raqami
    owner_names: Tuple[str, ...] = ()         # karta egasi ismining qismlari (JAVLONBEK)
    started_at: Optional[datetime] = None     # mijoz to'lov summasini tanlagan payt
    user_tg: int = 0
    max_age_min: int = 45
    auto_max: int = 100_000
    auto_max_noid: int = 30_000
    auto_enabled: bool = True


@dataclass
class Prior:
    """Avval saqlangan chek (kalit mos kelganda)."""
    receipt_id: int
    user_tg: int
    verdict: str
    payment_id: Optional[int]
    payment_status: str                       # pending | approved | rejected | ""
    created_at: str
    kind: str = ""
    age_min: float = 1e9                       # saqlanganiga necha daqiqa bo'ldi


@dataclass
class Decision:
    verdict: str
    reasons: List[str] = field(default_factory=list)       # kodlar (texts.REASONS)
    fraud: bool = False
    credit: int = 0
    keys: List[Tuple[str, str]] = field(default_factory=list)   # (kind, key) — bazaga yoziladi
    priors: List[Prior] = field(default_factory=list)
    age_min: Optional[float] = None
    needs_verify: bool = False                # avto-tasdiq uchun ikkinchi o'qish kerak


# ───────────────────────────────────────────────────────────── normallashtirish

def norm_id(value: str) -> str:
    return re.sub(r"[^0-9a-z]", "", str(value or "").lower())


def norm_name(value: str) -> str:
    text = re.sub(r"[^A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ' ]", " ", str(value or "")).upper()
    return re.sub(r"\s+", " ", text).strip()


def card_tail(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-4:] if len(digits) >= 4 else ""


def _minute(dt: datetime, shift: int = 0) -> str:
    return (dt + timedelta(minutes=shift)).strftime("%Y%m%d%H%M")


def build_keys(r: Receipt, file_sha: str = "") -> List[Tuple[str, str]]:
    """Bazaga yoziladigan kalitlar (bir chekning barcha 'barmoq izlari')."""
    keys: List[Tuple[str, str]] = []
    for raw in r.ids:
        value = norm_id(raw)
        if len(value) >= 7:
            keys.append(("id", value))
    sender = r.sender_tail or norm_name(r.sender_name)
    if r.amount and r.dt and sender and r.receiver_tail:
        keys.append(("cmp", f"{r.amount}|{_minute(r.dt)}|{sender}|{r.receiver_tail}"))
    if r.amount and r.dt and r.receiver_tail:
        keys.append(("wk", f"{r.amount}|{_minute(r.dt)}|{r.receiver_tail}"))
    if file_sha:
        keys.append(("file", file_sha))
    if r.status_time and r.battery is not None and r.app and r.amount:
        keys.append(("scr", f"{r.status_time}|{r.battery}|{r.app}|{r.amount}"))
    if r.status_time and r.battery is not None and r.app and r.receiver_tail:
        keys.append(("scr2", f"{r.status_time}|{r.battery}|{r.app}|{r.receiver_tail}"))
    return list(dict.fromkeys(keys))


def lookup_keys(r: Receipt, file_sha: str = "") -> List[Tuple[str, str]]:
    """Bazadan qidiriladigan kalitlar: vaqt ±1 daqiqa (ilovalar soniyani turlicha yaxlitlaydi)."""
    keys = build_keys(r, file_sha)
    if r.amount and r.dt and r.receiver_tail:
        sender = r.sender_tail or norm_name(r.sender_name)
        for shift in (-1, 1):
            keys.append(("wk", f"{r.amount}|{_minute(r.dt, shift)}|{r.receiver_tail}"))
            if sender:
                keys.append(("cmp", f"{r.amount}|{_minute(r.dt, shift)}|{sender}|{r.receiver_tail}"))
    return list(dict.fromkeys(keys))


def _parse_clock(value: Optional[str]) -> Optional[Tuple[int, int]]:
    match = re.match(r"^\s*(\d{1,2})[:.](\d{2})", str(value or ""))
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    return (hour, minute) if hour < 24 and minute < 60 else None


def clock_age_min(clock: Optional[str], now: datetime) -> Optional[float]:
    """Telefon soati hozirdan necha daqiqa oldin (kecha bo'lishi ham hisobga olinadi)."""
    parsed = _parse_clock(clock)
    if not parsed:
        return None
    moment = now.replace(hour=parsed[0], minute=parsed[1], second=0, microsecond=0)
    if moment > now + timedelta(minutes=10):
        moment -= timedelta(days=1)
    return (now - moment).total_seconds() / 60


def fmt_age(minutes: Optional[float]) -> str:
    if minutes is None:
        return ""
    minutes = abs(minutes)
    if minutes < 90:
        return f"{int(minutes)} daqiqa"
    if minutes < 48 * 60:
        return f"{int(minutes // 60)} soat"
    return f"{int(minutes // 1440)} kun"


def editor_flag(software: str) -> bool:
    return bool(_PHOTO_EDITORS.search(str(software or "")))


# ───────────────────────────────────────────────────────────────── qaror

def evaluate(r: Receipt, ctx: Context, file_sha: str = "",
             found: Optional[Dict[Tuple[str, str], Prior]] = None) -> Decision:
    """Chek bo'yicha qaror. `found` — bazadan topilgan oldingi cheklar (kalit → Prior)."""
    found = found or {}
    d = Decision(verdict=AUTO)
    d.keys = build_keys(r, file_sha)

    # 1) Chek emas / o'qib bo'lmaydi / muvaffaqiyatsiz
    if r.doc_type == "tax_receipt":
        d.verdict, d.reasons = NOT_RECEIPT, ["tax_receipt"]
        return d
    if r.doc_type not in ("transfer", "payment") or not r.readable:
        d.verdict = NOT_RECEIPT
        d.reasons = ["unreadable" if r.doc_type in ("transfer", "payment") else "not_payment"]
        return d
    if r.status in ("failed", "pending"):
        d.verdict, d.reasons = NOT_RECEIPT, [f"status_{r.status}"]
        return d
    # Faqat summa va ilova nomi ko'rinadigan "chek" (qabul qiluvchi, yuboruvchi, sana va ID yo'q) hech narsani
    # isbotlamaydi — qabul qilinmaydi, mijozdan to'lov tarixidagi asl chek so'raladi.
    identified = bool(r.receiver_tail or norm_name(r.receiver_name) or r.sender_tail or norm_name(r.sender_name))
    if not identified and not [i for i in r.ids if len(norm_id(i)) >= 7] and r.dt is None:
        d.verdict, d.reasons = NOT_RECEIPT, ["too_little"]
        return d
    if r.currency and r.currency.upper() not in ("UZS", "SUM", "SO'M", "СУМ"):
        d.verdict, d.reasons = REVIEW, ["currency"]
        return d

    # 2) Takrorlanish
    strong = [(k, found[k]) for k in d.keys if k[0] in STRONG_KINDS and k in found]
    # ±1 daqiqadagi mos kelish (ilovalar vaqtni turlicha yaxlitlaydi) — faqat shubha, jazo emas:
    # bir mijoz ketma-ket ikki real to'lov qilgan bo'lishi mumkin.
    weak = [(k, found[k]) for k in lookup_keys(r, file_sha)
            if k in found and (k[0] in WEAK_KINDS or (k[0] == "cmp" and k not in d.keys))]
    if strong:
        priors = list({p.receipt_id: p for _, p in strong}.values())
        d.priors = priors
        # Mijozning o'zi shu chekni yaqinda yuborgan (ikki marta bosdi, sabrsizlik qildi): bu soxtalik
        # emas — jazosiz, faqat "allaqachon qabul qilingan" deyiladi.
        own = all(p.user_tg == ctx.user_tg and (
            p.payment_status == "pending" or (p.payment_status == "approved" and p.age_min <= 30))
            for p in priors)
        if own:
            done = all(p.payment_status == "approved" for p in priors)
            d.verdict, d.reasons = OWN_PENDING, ["own_done" if done else "own_pending"]
            return d
        d.verdict, d.fraud = DUPLICATE, True
        d.reasons.append("duplicate_" + strong[0][0][0])
    elif weak:
        d.priors = list({p.receipt_id: p for _, p in weak}.values())
        d.reasons.append("possible_duplicate")

    # 3) Qabul qiluvchi
    receiver_ok = False
    if r.receiver_tail:
        receiver_ok = r.receiver_tail in ctx.cards
        if not receiver_ok:
            d.reasons.append("wrong_receiver")
    else:
        name = norm_name(r.receiver_name)
        if name and ctx.owner_names and all(part in name for part in ctx.owner_names):
            d.reasons.append("receiver_by_name")
        else:
            d.reasons.append("no_receiver")

    # 4) Vaqt
    age = None
    if r.dt:
        age = (ctx.now - r.dt).total_seconds() / 60
    else:
        age = clock_age_min(r.status_time, ctx.now)
        d.reasons.append("no_date")
    d.age_min = age
    if age is None:
        d.reasons.append("no_time")
    else:
        if age > ctx.max_age_min:
            d.reasons.append("stale")
        elif age < -10:
            d.reasons.append("future")
    if r.dt and ctx.started_at and r.dt < ctx.started_at - timedelta(minutes=3):
        d.reasons.append("before_request")
    shot_age = clock_age_min(r.status_time, ctx.now)
    if shot_age is not None and abs(shot_age) > ctx.max_age_min and "stale" not in d.reasons:
        d.reasons.append("screenshot_old")
    if r.dt and r.status_time:
        parsed = _parse_clock(r.status_time)
        if parsed:
            shot = r.dt.replace(hour=parsed[0], minute=parsed[1], second=0, microsecond=0)
            if shot < r.dt - timedelta(hours=12):
                shot += timedelta(days=1)
            gap = (shot - r.dt).total_seconds() / 60
            if gap < -5 or gap > ctx.max_age_min:
                d.reasons.append("clock_mismatch")

    # 5) Soxtalik belgilari
    if r.tamper == "high":
        d.reasons.append("tamper_high")
    if r.meta_flags:
        d.reasons.append("tamper_meta")
    if r.cropped:
        d.reasons.append("cropped")

    # 6) Summa
    if not r.amount or r.amount <= 0:
        d.reasons.append("no_amount")
    else:
        if r.amount < 1000:
            d.reasons.append("tiny_amount")
        if r.amount > ctx.auto_max:
            d.reasons.append("over_limit")
        elif not any(k[0] == "id" for k in d.keys) and r.amount > ctx.auto_max_noid:
            d.reasons.append("over_limit_noid")
    # Takrorlanishni ushlay oladigan kalit: ID, to'liq kompozit yoki skrinshot belgisi (soat+batareya).
    has_strong_key = any(k[0] in ("id", "cmp", "scr") for k in d.keys)
    if not has_strong_key:
        d.reasons.append("no_unique_key")
    if r.confidence < 0.7:
        d.reasons.append("low_confidence")

    # Verdict
    if d.verdict == DUPLICATE:
        return d
    d.credit = r.amount or 0
    if "wrong_receiver" in d.reasons:
        d.verdict = WRONG_RECEIVER
        return d
    soft = {"receiver_by_name", "no_date"}        # o'zi to'siq emas
    blocking = [x for x in d.reasons if x not in soft]
    if blocking or not ctx.auto_enabled:
        d.verdict = REVIEW
        if not ctx.auto_enabled and not blocking:
            d.reasons.append("shadow_mode")
        return d
    if "receiver_by_name" in d.reasons:         # karta oxiri ko'rinmagan: faqat ism — admin
        d.verdict = REVIEW
        return d
    d.verdict = AUTO
    d.needs_verify = True
    if r.amount != ctx.claimed:
        d.reasons.append("amount_differs")
    return d
