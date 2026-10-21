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
FAKE = "fake"                    # tahrirlangan ko'rinadi: qabul qilinmaydi (adminga bormaydi)
OWN_PENDING = "own_pending"      # o'zining tekshirilayotgan cheki qayta yuborildi
REJECTED = "rejected"            # to'liq avto rejim: haqiqiy chek, lekin kamchiligi bor — mijozga sabablar aytiladi

# Fayl kalitlari: "file" — fayl baytlarining SHA-256 izi, "fuid" — Telegram fayl raqami (file_unique_id).
# Telegram bir faylga bitta doimiy raqam beradi: chek boshqa chatdan uzatilsa yoki qayta yuborilsa ham raqam
# o'zgarmaydi, shuning uchun AI chaqirilmasdan (bepul) takroriy chek ushlanadi.
STRONG_KINDS = ("id", "cmp", "file", "fuid", "scr")     # bularning mos kelishi — takroriy chek
WEAK_KINDS = ("wk", "scr2")                     # mos kelishi — shubha, lekin jazo emas

_PHOTO_EDITORS = re.compile(
    r"photoshop|gimp|snapseed|picsart|canva|lightroom|pixlr|photopea|facetune|remini|"
    r"fotor|polarr|vsco|afterlight|paint\.net|affinity", re.IGNORECASE)


@dataclass
class Receipt:
    """AI o'qigan va kod normallashtirgan chek ma'lumoti."""
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
    file_time: Optional[datetime] = None     # faylning o'z vaqti: nomidagi raqamlar (Screenshot_20261006_200412) yoki EXIF
    file_time_src: str = ""                  # name | exif | pdf
    confidence: float = 1.0                  # AI o'qishga ishonchi (0..1)
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
    """Karta raqamining oxirgi 4 raqami. Telefon raqami ("99890*****58", "998901234567") karta emas.

    Karta oxiri satr OXIRIDAGI ketma-ket 4+ raqam: "**** 6655", "986016****6655", "•6655".
    Yulduzchadan keyin 2 raqam qolgan niqoblangan telefon yoki 998 bilan boshlanuvchi 12 xonali raqam —
    kartaga o'xshamaydi, shuning uchun bo'sh qaytadi.
    """
    text = str(value or "").strip()
    digits = re.sub(r"\D", "", text)
    if re.fullmatch(r"998\d{9}", digits):
        return ""                                   # to'liq telefon raqami
    match = re.search(r"(\d{4,})\s*$", text)
    return match.group(1)[-4:] if match else ""


def _minute(dt: datetime, shift: int = 0) -> str:
    return (dt + timedelta(minutes=shift)).strftime("%Y%m%d%H%M")


def file_keys(file_sha: str = "", file_uid: str = "") -> List[Tuple[str, str]]:
    """Faylning o'z izlari: baytlar hash'i va Telegram fayl raqami (AI'siz tekshiriladi)."""
    keys: List[Tuple[str, str]] = []
    if file_sha:
        keys.append(("file", file_sha))
    if file_uid:
        keys.append(("fuid", str(file_uid)))
    return keys


def build_keys(r: Receipt, file_sha: str = "", file_uid: str = "") -> List[Tuple[str, str]]:
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
    keys += file_keys(file_sha, file_uid)
    if r.status_time and r.battery is not None and r.app and r.amount:
        keys.append(("scr", f"{r.status_time}|{r.battery}|{r.app}|{r.amount}"))
    if r.status_time and r.battery is not None and r.app and r.receiver_tail:
        keys.append(("scr2", f"{r.status_time}|{r.battery}|{r.app}|{r.receiver_tail}"))
    return list(dict.fromkeys(keys))


def lookup_keys(r: Receipt, file_sha: str = "", file_uid: str = "") -> List[Tuple[str, str]]:
    """Bazadan qidiriladigan kalitlar: vaqt ±1 daqiqa (ilovalar soniyani turlicha yaxlitlaydi)."""
    keys = build_keys(r, file_sha, file_uid)
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


def classify_priors(priors: List[Prior], user_tg: int) -> Tuple[str, str, bool]:
    """Avval ishlatilgan chek: (verdict, sabab, jazo bormi).

    Mijozning o'zi shu chekni yaqinda yuborgan (ikki marta bosdi, sabrsizlik qildi): soxtalik emas —
    jazosiz, faqat "allaqachon qabul qilingan/tekshirilmoqda" deyiladi.
    """
    own = all(p.user_tg == user_tg and (
        p.payment_status == "pending" or (p.payment_status == "approved" and p.age_min <= 30))
        for p in priors)
    if own:
        done = all(p.payment_status == "approved" for p in priors)
        return OWN_PENDING, "own_done" if done else "own_pending", False
    return DUPLICATE, "duplicate", True


FILE_TIME_SLACK_MIN = 3          # telefon soati va bank vaqti orasidagi odatiy farq


def file_time_reasons(r: Receipt, ctx: Context) -> List[str]:
    """Faylning o'z vaqti (nomidagi raqamlar yoki EXIF) bo'yicha belgilar.

    - fayl to'lovdan OLDIN yaratilgan bo'lsa — bu mumkin emas: eski skrinshot ustiga yangi sana yozilgan;
    - fayl ancha oldin yaratilgan bo'lsa — eski skrinshot qayta yuborilmoqda.
    Fayl vaqti kelajakda bo'lsa (telefon soati noto'g'ri) hech narsa deyilmaydi.
    """
    if not r.file_time:
        return []
    out: List[str] = []
    if r.dt and r.file_time < r.dt - timedelta(minutes=FILE_TIME_SLACK_MIN):
        out.append("file_before_payment")
    age = (ctx.now - r.file_time).total_seconds() / 60
    if age > ctx.max_age_min + 15:
        out.append("file_old")
    return out


# ───────────────────────────────────────────────── to'liq avtomatik rejim

# Mijoz chekni qayta yuborib tuzata olmaydigan holatlar: bular rad etilmaydi, admin hal qiladi.
ADMIN_ONLY = {
    "over_limit",            # egasi belgilagan xavfsizlik chegarasi (RECEIPT_AUTO_MAX)
    "verify_failed",         # ikkinchi o'qish tarmoq sabab bajarilmadi
    "ai_error",
    "possible_duplicate",    # boshqa odamning shu daqiqadagi shu summadagi to'lovi bo'lishi mumkin
    "receiver_by_name",      # karta ko'rinmaydi, lekin qabul qiluvchi ismi bizniki
    "currency",
}
INFO_ONLY = {"no_date", "amount_differs"}      # o'zi kamchilik emas


def full_auto(d: Decision) -> Decision:
    """To'liq avtomatik rejim: odam qarori kutiladigan chekni iloji boricha AI o'zi hal qiladi.

    Kamchiligi bor har chek (eski, qirqilgan, ID yo'q, boshqa karta, tahrirlangan, takroriy ...) RAD ETILADI —
    mijozga sabablari ro'yxati bilan. Adminga faqat mijoz tuzata olmaydigan holatlar boradi (`ADMIN_ONLY`).
    Mijoz bloklanmaydi.
    """
    if d.verdict in (DUPLICATE, WRONG_RECEIVER, FAKE):
        if d.verdict != DUPLICATE:
            d.verdict = REJECTED
        return d
    if d.verdict != REVIEW:
        return d
    user_fixable = [code for code in d.reasons if code not in ADMIN_ONLY and code not in INFO_ONLY]
    if user_fixable:
        d.verdict = REJECTED
    return d


# ───────────────────────────────────────────────────────────────── qaror

def evaluate(r: Receipt, ctx: Context, file_sha: str = "",
             found: Optional[Dict[Tuple[str, str], Prior]] = None, file_uid: str = "") -> Decision:
    """Chek bo'yicha qaror. `found` — bazadan topilgan oldingi cheklar (kalit → Prior)."""
    found = found or {}
    d = Decision(verdict=AUTO)
    d.keys = build_keys(r, file_sha, file_uid)

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
    weak = [(k, found[k]) for k in lookup_keys(r, file_sha, file_uid)
            if k in found and (k[0] in WEAK_KINDS or (k[0] == "cmp" and k not in d.keys))]
    if strong:
        priors = list({p.receipt_id: p for _, p in strong}.values())
        d.priors = priors
        verdict, reason, fraud = classify_priors(priors, ctx.user_tg)
        if verdict == OWN_PENDING:
            d.verdict, d.reasons = OWN_PENDING, [reason]
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
    d.reasons += file_time_reasons(r, ctx)

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
    # Fayl metama'lumotida tahrirlovchi dastur izi: ogohlantirish, lekin RAD ETISH EMAS. Ilgari bunday chek
    # mijozga «tahrirlangan» deb qaytarilib, adminga bormasdi; haqiqiy cheklar ham shunday rad etilgan
    # (belgi tasodifan topilishi yoki PDF yaratuvchi dastur nomi). Yakuniy qaror adminda — kartochkada
    # belgi ko'rsatiladi.
    soft = {"receiver_by_name", "no_date"}        # o'zi to'siq emas
    blocking = [x for x in d.reasons if x not in soft]
    if blocking or not ctx.auto_enabled:
        d.verdict = REVIEW
        return d
    if "receiver_by_name" in d.reasons:         # karta oxiri ko'rinmagan: faqat ism — admin
        d.verdict = REVIEW
        return d
    d.verdict = AUTO
    d.needs_verify = True
    if r.amount != ctx.claimed:
        d.reasons.append("amount_differs")
    return d
