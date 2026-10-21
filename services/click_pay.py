"""Click SHOP API: balansni Click orqali to'ldirish.

Oqim:
    1. Mijoz summani tanlaydi → invoys (`database.click_invoices`) va `pay_url` havolasi.
    2. Mijoz my.click.uz sahifasida to'laydi.
    3. Click serveri bizga ikki POST yuboradi (form-urlencoded):
       Prepare (`action=0`) — invoys bor, summa to'g'ri, hali to'lanmagan → `merchant_prepare_id`;
       Complete (`action=1`) — pul yechildi → balans `credit_approved_payment` orqali to'ldiriladi
       (chek tasdig'i bilan bir xil: bonuslar, kutayotgan buyurtma eslatmasi, mijozga xabar).

Har so'rov `sign_string` (MD5) bilan tekshiriladi:
    Prepare:  md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id + amount + action + sign_time)
    Complete: md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id + merchant_prepare_id
                  + amount + action + sign_time)

Click kabinetida Prepare va Complete manzillari: https://<domen>/click/prepare, https://<domen>/click/complete.
"""
import hashlib
import hmac
import logging
from typing import Awaitable, Callable, Dict, Mapping, Optional
from urllib.parse import urlencode

import config
from database import click_invoices as invoices

log = logging.getLogger(__name__)

PAY_URL = "https://my.click.uz/services/pay"
PREPARE, COMPLETE = 0, 1
MIN_AMOUNT = 1000
MAX_AMOUNT = 5_000_000

# Click hujjatidagi javob kodlari.
OK = 0
SIGN_FAILED = -1
BAD_AMOUNT = -2
NO_ACTION = -3
ALREADY_PAID = -4
NO_ORDER = -5
NO_TRANSACTION = -6
UPDATE_FAILED = -7
BAD_REQUEST = -8
CANCELLED = -9

NOTES = {
    OK: "Success",
    SIGN_FAILED: "SIGN CHECK FAILED!",
    BAD_AMOUNT: "Incorrect parameter amount",
    NO_ACTION: "Action not found",
    ALREADY_PAID: "Already paid",
    NO_ORDER: "User does not exist",
    NO_TRANSACTION: "Transaction does not exist",
    UPDATE_FAILED: "Failed to update user",
    BAD_REQUEST: "Error in request from click",
    CANCELLED: "Transaction cancelled",
}

_FIELDS = ("click_trans_id", "service_id", "click_paydoc_id", "merchant_trans_id", "amount", "action",
           "error", "sign_time", "sign_string")


def enabled() -> bool:
    return bool(config.CLICK_SERVICE_ID and config.CLICK_MERCHANT_ID and config.CLICK_SECRET_KEY)


def valid_amount(amount) -> int:
    """Summa butun so'mda; noto'g'ri bo'lsa `ValueError` (xabari mijozga ko'rsatiladi)."""
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise ValueError("Summani raqam bilan kiriting.")
    if amount < MIN_AMOUNT:
        raise ValueError(f"Minimal to'lov miqdori {MIN_AMOUNT:,} so'm.".replace(",", " "))
    if amount > MAX_AMOUNT:
        raise ValueError(f"Bir martalik to'lov {MAX_AMOUNT:,} so'mdan oshmasin.".replace(",", " "))
    return amount


def pay_url(invoice_id: int, amount: int, return_url: str = "") -> str:
    """my.click.uz to'lov havolasi.

    `merchant_user_id` havolaga qo'yilmaydi: u faqat Merchant API ga murojaat uchun. Havolada
    bo'lsa Click ilovasi «Поставщик не найден» deb to'lovni ochmasdi (Click xodimi tasdiqlagan).
    `return_url` berilmasa — sozlamadagi, u ham bo'lmasa botning o'zi (to'lovdan keyin qaytish).
    """
    import webapp

    params = {"service_id": config.CLICK_SERVICE_ID, "merchant_id": config.CLICK_MERCHANT_ID,
              "amount": int(amount), "transaction_param": invoice_id}
    return_url = return_url or config.CLICK_RETURN_URL or (
        f"https://t.me/{webapp.BOT_USERNAME}" if webapp.BOT_USERNAME else "")
    if return_url:
        params["return_url"] = return_url
    return f"{PAY_URL}?{urlencode(params)}"


async def new_payment(telegram_id: int, amount, source: str, return_url: str = "") -> str:
    """Invoys yaratib, Click to'lov havolasini qaytaradi."""
    amount = valid_amount(amount)
    invoice_id = await invoices.create(telegram_id, amount, source)
    log.info("Click invoys %s: %s so'm (%s, %s)", invoice_id, amount, telegram_id, source)
    return pay_url(invoice_id, amount, return_url)


def _sign(p: Mapping[str, str], with_prepare_id: bool) -> str:
    parts = [p["click_trans_id"], p["service_id"], config.CLICK_SECRET_KEY, p["merchant_trans_id"]]
    if with_prepare_id:
        parts.append(p.get("merchant_prepare_id", ""))
    parts += [p["amount"], p["action"], p["sign_time"]]
    return hashlib.md5("".join(str(x) for x in parts).encode()).hexdigest()


def _answer(p: Mapping[str, str], error: int, **extra) -> Dict:
    out = {"click_trans_id": p.get("click_trans_id", ""), "merchant_trans_id": p.get("merchant_trans_id", ""),
           "error": error, "error_note": NOTES[error]}
    out.update(extra)
    return out


def _same_amount(raw: str, amount: int) -> bool:
    try:
        return abs(float(raw) - float(amount)) < 0.01
    except (TypeError, ValueError):
        return False


def _check(p: Mapping[str, str], action: int) -> Optional[int]:
    """Umumiy tekshiruvlar: maydonlar, xizmat raqami, imzo, amal turi. Xato kodi yoki None."""
    if any(not str(p.get(name, "")).strip() for name in _FIELDS if name not in ("error", "click_paydoc_id")):
        return BAD_REQUEST
    if str(p.get("action")) != str(action):
        return NO_ACTION
    if action == COMPLETE and not str(p.get("merchant_prepare_id", "")).strip():
        return BAD_REQUEST
    expected = _sign(p, with_prepare_id=action == COMPLETE)
    if not hmac.compare_digest(expected, str(p.get("sign_string", "")).lower()):
        return SIGN_FAILED
    if str(p.get("service_id")) != str(config.CLICK_SERVICE_ID):
        return BAD_REQUEST
    return None


async def _invoice(p: Mapping[str, str]) -> Optional[Dict]:
    try:
        return await invoices.get(int(p.get("merchant_trans_id", "")))
    except (TypeError, ValueError):
        return None


async def prepare(p: Mapping[str, str]) -> Dict:
    error = _check(p, PREPARE)
    if error is not None:
        return _answer(p, error)
    invoice = await _invoice(p)
    if invoice is None:
        return _answer(p, NO_ORDER)
    if invoice["status"] == invoices.PAID:
        return _answer(p, ALREADY_PAID)
    if invoice["status"] == invoices.CANCELLED:
        return _answer(p, CANCELLED)
    if not _same_amount(p["amount"], invoice["amount"]):
        return _answer(p, BAD_AMOUNT)
    if not await invoices.prepare(invoice["id"], p["click_trans_id"], p.get("click_paydoc_id", "")):
        return _answer(p, ALREADY_PAID)
    return _answer(p, OK, merchant_prepare_id=invoice["id"])


CreditFn = Callable[[Dict], Awaitable[int]]


async def complete(p: Mapping[str, str], credit: Optional[CreditFn] = None) -> Dict:
    """`credit(invoice) -> payment_id` — balansni to'ldiradi (testlarda almashtiriladi)."""
    error = _check(p, COMPLETE)
    if error is not None:
        return _answer(p, error)
    invoice = await _invoice(p)
    if invoice is None:
        return _answer(p, NO_ORDER)
    if str(p.get("merchant_prepare_id")) != str(invoice["id"]) or str(p["click_trans_id"]) != invoice["click_trans_id"]:
        return _answer(p, NO_TRANSACTION)
    if invoice["status"] == invoices.PAID:
        return _answer(p, ALREADY_PAID, merchant_confirm_id=invoice["payment_id"] or invoice["id"])
    if invoice["status"] == invoices.CANCELLED:
        return _answer(p, CANCELLED)
    if not _same_amount(p["amount"], invoice["amount"]):
        return _answer(p, BAD_AMOUNT)
    # Click to'lovni o'z tomonida bekor qilgan (pul yechilmagan) — invoys yopiladi.
    try:
        click_error = int(str(p.get("error") or "0"))
    except ValueError:
        click_error = 0
    if click_error < 0:
        await invoices.set_status(invoice["id"], invoices.CANCELLED, only_from=(invoices.NEW, invoices.PREPARED))
        log.info("Click invoys %s bekor qilindi (Click xatosi %s)", invoice["id"], click_error)
        return _answer(p, CANCELLED)
    if not await invoices.claim_paid(invoice["id"], p["click_trans_id"]):
        fresh = await invoices.get(invoice["id"]) or {}
        return _answer(p, ALREADY_PAID if fresh.get("status") == invoices.PAID else NO_TRANSACTION)
    try:
        payment_id = await (credit or _credit)(invoice)
    except Exception as exc:
        # Balans qo'shilmadi: invoys qaytariladi, Click Complete'ni qayta yuborishi mumkin.
        log.exception("Click to'lovi %s balansga qo'shilmadi: %s", invoice["id"], exc)
        await invoices.set_status(invoice["id"], invoices.PREPARED, only_from=(invoices.PAID,))
        return _answer(p, UPDATE_FAILED)
    await invoices.set_payment(invoice["id"], payment_id)
    log.info("Click to'lovi %s: %s so'm → %s (payment %s)", invoice["id"], invoice["amount"],
             invoice["telegram_id"], payment_id)
    return _answer(p, OK, merchant_confirm_id=payment_id)


async def handle(p: Mapping[str, str], action: Optional[int] = None) -> Dict:
    """Bitta kirish: `action` berilmasa so'rovdagisi olinadi."""
    try:
        action = int(p.get("action", "")) if action is None else action
    except (TypeError, ValueError):
        return _answer(p, NO_ACTION)
    if action == PREPARE:
        return await prepare(p)
    if action == COMPLETE:
        return await complete(p)
    return _answer(p, NO_ACTION)


async def _credit(invoice: Dict) -> int:
    """To'lov yozuvi (`source='click'`) va chek tasdig'i bilan bir xil balans oqimi."""
    import webapp
    from bot.handlers.admin import credit_approved_payment
    from database.database import Database

    user = await Database.get_user(invoice["telegram_id"])
    if user is None:
        raise RuntimeError(f"mijoz topilmadi: {invoice['telegram_id']}")
    payment_id = await Database.create_payment(user.id, invoice["amount"], "", "click")
    payment = await Database.get_payment_by_id(payment_id)
    bot = webapp.BOT
    text = f"✅ Click orqali to'lov qabul qilindi! {invoice['amount']:,} so'm hisobingizga qo'shildi."
    try:
        await credit_approved_payment(bot, Database, payment, user_message=text)
    except Exception:
        # Balans qo'shilgandan keyingi xato (bonus, xabar) to'lovni bekor qilmasin: Click Complete'ni
        # qayta yuborsa, pul ikki marta qo'shilardi. Faqat to'lov hali tasdiqlanmagan bo'lsa — qaytariladi.
        fresh = await Database.get_payment_by_id(payment_id)
        if getattr(fresh, "status", "") != "approved":
            await Database.update_payment_status(payment_id, "rejected")
            raise
        log.exception("Click to'lovi %s: balans qo'shildi, keyingi qadamda xato", invoice["id"])
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"⚡ Click to'lovi: {invoice['amount']:,} so'm · "
                                             f"mijoz {invoice['telegram_id']} · to'lov ID {payment_id}",
                                   disable_notification=True)
        except Exception as exc:
            log.debug("Adminga Click xabari yuborilmadi: %s", exc)
    return payment_id
