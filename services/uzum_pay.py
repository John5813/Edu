"""Uzum Bank Merchant API: balansni Uzum Bank ilovasi orqali to'ldirish.

Oqim:
    1. Mijoz botda/saytda summani tanlaydi → deeplink `uzumbank.uz/open-service?serviceId=..&user_id=<Telegram ID>
       &amount=<tiyin>` Uzum ilovasini ochadi (yoki mijoz ilovada xizmatni topib, ID va summani o'zi yozadi).
    2. Uzum serveri `<sayt>/uzum/webhook/...` ga so'rov yuboradi:
       /check   — hisob bormi (mijoz topildimi);
       /create  — tranzaksiya ochildi (`CREATED`);
       /confirm — pul yechildi → balans `credit_approved_payment` orqali (chek tasdig'i bilan bir xil);
       /reverse — bekor qilish (tasdiqlangan bo'lsa summa balansdan yechiladi);
       /status  — tranzaksiya holati.

Har so'rov `Authorization: Basic base64("<UZUM_LOGIN>:<UZUM_PASSWORD>")` bilan keladi, tanasida `serviceId`.
Summalar tiyinda (so'm × 100). Muvaffaqiyat — HTTP 200, xato — HTTP 400 va `errorCode` (satr).
Takroriy /create, /confirm, /reverse xato qaytaradi (10010, 10016, 10018) — Uzum hujjati shunday talab qiladi.
`data` (hisob va mijoz ismi) faqat /check va /status'da, ikkalasida bir xil — Uzum xodimi talabi.
"""
import base64
import binascii
import hmac
import logging
from typing import Awaitable, Callable, Dict, Mapping, Optional, Tuple

import config
from database import uzum_orders as orders

log = logging.getLogger(__name__)

DEEPLINK_URL = "https://uzumbank.uz/open-service"
FEATURE = "uzum_pay"                 # admin «Funksiyalar boshqaruvi»dagi kalit (sukut — yoqilgan)
MIN_AMOUNT = 1000                    # so'm
MAX_AMOUNT = 5_000_000
TIMEOUT_MS = 30 * 60 * 1000          # tasdiqlanmagan tranzaksiya 30 daqiqadan keyin bekor

# Uzum hujjatidagi xato kodlari.
ACCESS_DENIED = "10001"
JSON_ERROR = "10002"
BAD_OPERATION = "10003"
MISSING_PARAM = "10005"
BAD_SERVICE = "10006"
NO_ACCOUNT = "10007"
ALREADY_PAID = "10008"
PAYMENT_CANCELLED = "10009"
TX_EXISTS = "10010"
BAD_AMOUNT = "10011"
AMOUNT_LOW = "10012"
AMOUNT_HIGH = "10013"
NO_TRANSACTION = "10014"
TX_CANCELLED = "10015"
TX_CONFIRMED = "10016"
CANT_REVERSE = "10017"
TX_REVERSED = "10018"
SYSTEM_ERROR = "99999"


class UzumError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def enabled() -> bool:
    """ServiceId, login va parol sozlanganmi. Bo'lmasa har so'rovga 10001."""
    return bool(config.UZUM_SERVICE_ID and config.UZUM_LOGIN and config.UZUM_PASSWORD)


async def available() -> bool:
    """Mijozga Uzum tugmasini ko'rsatish mumkinmi: sozlangan, sinov rejimida emas va admin o'chirmagan.

    Sinov ServiceId'si Uzum ilovasida yo'q — deeplink ishlamaydi, shuning uchun sinovda tugma chiqmaydi.
    """
    if not enabled() or config.UZUM_TEST:
        return False
    try:
        from database.database import Database
        return bool(await Database().get_feature_status(FEATURE))
    except Exception as exc:                      # holatni o'qib bo'lmasa — sozlamalar bo'yicha
        log.warning("Uzum tugmasi holati o'qilmadi: %s", exc)
        return True


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


def pay_url(telegram_id: int, amount: int) -> str:
    """Uzum ilovasini ochadigan deeplink: hisob maydoni (`user_id`) — Telegram ID, summa tiyinda.

    Namuna (Uzum xodimi bergan): `open-service?serviceId=973627&user_id=5304482470&amount=100000`.
    """
    from urllib.parse import urlencode

    query = urlencode({"serviceId": config.UZUM_SERVICE_ID, config.UZUM_ACCOUNT: int(telegram_id),
                       "amount": int(amount) * 100})
    return f"{DEEPLINK_URL}?{query}"


async def new_payment(telegram_id: int, amount, source: str = "", **_) -> str:
    """Deeplink (buyurtma yaratilmaydi — tranzaksiyani Uzum /create bilan ochadi)."""
    amount = valid_amount(amount)
    log.info("Uzum havolasi: %s so'm → %s (%s)", amount, telegram_id, source)
    return pay_url(telegram_id, amount)


def authorized(header: str) -> bool:
    """`Authorization: Basic base64("login:parol")`."""
    if not enabled() or not header or not header.startswith("Basic "):
        return False
    try:
        login, _, password = base64.b64decode(header[6:].strip()).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    return (hmac.compare_digest(login.encode(), config.UZUM_LOGIN.encode())
            and hmac.compare_digest(password.encode(), config.UZUM_PASSWORD.encode()))


def _require(body: Mapping, key: str):
    value = body.get(key)
    if value is None or value == "":
        raise UzumError(MISSING_PARAM)
    return value


def _service(body: Mapping) -> None:
    if str(_require(body, "serviceId")).strip() != config.UZUM_SERVICE_ID:
        raise UzumError(BAD_SERVICE)


def _account_value(params) -> str:
    """`params.user_id` — oddiy qiymat yoki `{"value": ...}` ko'rinishida kelishi mumkin."""
    if not isinstance(params, Mapping):
        raise UzumError(MISSING_PARAM)
    value = params.get(config.UZUM_ACCOUNT)
    if isinstance(value, Mapping):
        value = value.get("value")
    if value is None or str(value).strip() == "":
        raise UzumError(MISSING_PARAM)
    return str(value).strip()


async def _user(params):
    """Hisob maydonidagi Telegram ID bo'yicha mijoz; topilmasa 10007."""
    from database.database import Database

    value = _account_value(params)
    if not value.isdigit():
        raise UzumError(NO_ACCOUNT)
    user = await Database.get_user(int(value))
    if user is None:
        raise UzumError(NO_ACCOUNT)
    return user


async def _data(telegram_id) -> Dict:
    """/check va /status uchun bir xil `data`: asosiy parametr (hisob) va mijoz ismi."""
    from database.database import Database

    data = {"account": {"value": str(telegram_id)}}
    user = await Database.get_user(int(telegram_id))
    if user is not None and user.first_name:
        data["fio"] = {"value": user.first_name}
    return data


def _amount(body: Mapping) -> int:
    """Summa tiyinda; balans butun so'mda yuritiladi."""
    amount = _require(body, "amount")
    if isinstance(amount, bool):
        raise UzumError(BAD_AMOUNT)
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise UzumError(BAD_AMOUNT)
    if amount <= 0 or amount % 100:
        raise UzumError(BAD_AMOUNT)
    if amount < MIN_AMOUNT * 100:
        raise UzumError(AMOUNT_LOW)
    if amount > MAX_AMOUNT * 100:
        raise UzumError(AMOUNT_HIGH)
    return amount


def _base(body: Mapping) -> Dict:
    return {"serviceId": body.get("serviceId"), "timestamp": orders.now_ms()}


async def _expire(tx: Dict) -> bool:
    """30 daqiqadan oshgan tasdiqlanmagan tranzaksiyani bekor qiladi. True — muddati o'tgan."""
    if tx["state"] != orders.CREATED or orders.now_ms() - tx["create_time"] <= TIMEOUT_MS:
        return False
    await orders.reverse_tx(tx["trans_id"], orders.CREATED)
    return True


async def _tx(body: Mapping) -> Dict:
    tx = await orders.get_tx(str(_require(body, "transId")))
    if tx is None:
        raise UzumError(NO_TRANSACTION)
    return tx


# ─────────────────────────────────────────────────────────────── usullar

async def check(body: Mapping) -> Dict:
    user = await _user(_require(body, "params"))
    return {**_base(body), "status": "OK", "data": await _data(user.telegram_id)}


async def create(body: Mapping) -> Dict:
    trans_id = str(_require(body, "transId"))
    params = _require(body, "params")
    if await orders.get_tx(trans_id) is not None:
        raise UzumError(TX_EXISTS)
    user = await _user(params)
    amount = _amount(body)
    tx = await orders.create_tx(trans_id, user.telegram_id, amount, config.UZUM_TEST)
    if tx is None:                                 # parallel so'rov bizdan oldin yaratdi
        raise UzumError(TX_EXISTS)
    log.info("Uzum tranzaksiya %s: %s so'm → %s", trans_id, amount // 100, user.telegram_id)
    return {**_base(body), "transId": trans_id, "status": orders.CREATED, "transTime": tx["create_time"],
            "amount": amount}


CreditFn = Callable[[Dict], Awaitable[Optional[int]]]


async def confirm(body: Mapping, credit: Optional[CreditFn] = None) -> Dict:
    """`credit(tx) -> payment_id` — balansni to'ldiradi (testlarda almashtiriladi)."""
    tx = await _tx(body)
    trans_id = tx["trans_id"]
    if tx["state"] == orders.REVERSED or await _expire(tx):
        raise UzumError(TX_CANCELLED)
    if tx["state"] == orders.CONFIRMED:
        raise UzumError(TX_CONFIRMED)
    if not await orders.claim_confirm(trans_id, str(body.get("paymentSource") or ""), str(body.get("phone") or "")):
        raise UzumError(TX_CONFIRMED)
    if tx["test"]:
        log.info("Uzum sinov to'lovi %s tasdiqlandi (balansga qo'shilmadi)", trans_id)
    else:
        try:
            payment_id = await (credit or _credit)(tx)
        except Exception as exc:
            log.exception("Uzum to'lovi %s balansga qo'shilmadi: %s", trans_id, exc)
            await orders.unclaim_confirm(trans_id)
            raise UzumError(SYSTEM_ERROR)
        if payment_id:
            await orders.set_payment(trans_id, payment_id)
        log.info("Uzum to'lovi %s: %s so'm → %s (payment %s)", trans_id, tx["amount"] // 100, tx["telegram_id"],
                 payment_id)
    tx = await orders.get_tx(trans_id)
    return {**_base(body), "transId": trans_id, "status": orders.CONFIRMED, "confirmTime": tx["confirm_time"],
            "amount": tx["amount"]}


async def reverse(body: Mapping) -> Dict:
    tx = await _tx(body)
    trans_id = tx["trans_id"]
    if tx["state"] == orders.REVERSED:
        raise UzumError(TX_REVERSED)
    if not await orders.reverse_tx(trans_id, tx["state"]):
        raise UzumError(TX_REVERSED)
    if tx["state"] == orders.CONFIRMED and not tx["test"]:
        await _refund(tx)
    log.info("Uzum tranzaksiya %s bekor qilindi (%s edi)", trans_id, tx["state"])
    tx = await orders.get_tx(trans_id)
    return {**_base(body), "transId": trans_id, "status": orders.REVERSED, "reverseTime": tx["reverse_time"],
            "amount": tx["amount"]}


async def status(body: Mapping) -> Dict:
    tx = await _tx(body)
    if await _expire(tx):
        tx = await orders.get_tx(tx["trans_id"])
    return {**_base(body), "transId": tx["trans_id"], "status": tx["state"], "transTime": tx["create_time"],
            "confirmTime": tx["confirm_time"] or None, "reverseTime": tx["reverse_time"] or None,
            "data": await _data(tx["telegram_id"]), "amount": tx["amount"]}


METHODS = {"check": check, "create": create, "confirm": confirm, "reverse": reverse, "status": status}


def _error(body, code: str) -> Dict:
    body = body if isinstance(body, Mapping) else {}
    answer = {"serviceId": body.get("serviceId"), "timestamp": orders.now_ms(), "status": "FAILED",
              "errorCode": code}
    if body.get("transId"):
        answer["transId"] = body["transId"]
    return answer


async def handle(action: str, body, auth_header: str) -> Tuple[int, Dict]:
    """Bitta kirish: (HTTP holat, javob). `body` — o'qilgan JSON (None — JSON xato)."""
    method = METHODS.get(action)
    if method is None:
        return 400, _error(body, BAD_OPERATION)
    if not authorized(auth_header):
        return 400, _error(body, ACCESS_DENIED)
    if not isinstance(body, dict):
        return 400, _error(None, JSON_ERROR)
    try:
        _service(body)
        _require(body, "timestamp")
        return 200, await method(body)
    except UzumError as exc:
        return 400, _error(body, exc.code)
    except Exception as exc:
        log.exception("Uzum /%s bajarilmadi: %s", action, exc)
        return 400, _error(body, SYSTEM_ERROR)


async def _notify_admins(text: str) -> None:
    import webapp

    for admin_id in config.ADMIN_IDS:
        try:
            await webapp.BOT.send_message(admin_id, text, disable_notification=True)
        except Exception as exc:
            log.debug("Adminga Uzum xabari yuborilmadi: %s", exc)


async def _refund(tx: Dict) -> None:
    """Uzum qaytargan to'lov: balansdan yechish (yetmasa — manfiyga), to'lov yozuvi rad etilgan."""
    from database.database import Database

    amount = tx["amount"] // 100
    if not await Database.charge_balance(tx["telegram_id"], amount):
        await Database.update_user_balance(tx["telegram_id"], -amount)
        note = " · balans yetmadi, manfiyga tushdi"
    else:
        note = ""
    if tx.get("payment_id"):
        await Database.update_payment_status(tx["payment_id"], "rejected")
    log.info("Uzum to'lovi %s qaytarildi%s", tx["trans_id"], note)
    await _notify_admins(f"↩️ Uzum to'lovi qaytarildi: {amount:,} so'm · mijoz {tx['telegram_id']}{note}")


async def _credit(tx: Dict) -> int:
    """To'lov yozuvi (`source='uzum'`) va chek tasdig'i bilan bir xil balans oqimi."""
    import webapp
    from bot.handlers.admin import credit_approved_payment
    from database.database import Database

    amount = tx["amount"] // 100
    user = await Database.get_user(tx["telegram_id"])
    if user is None:
        raise RuntimeError(f"mijoz topilmadi: {tx['telegram_id']}")
    payment_id = await Database.create_payment(user.id, amount, "", "uzum")
    payment = await Database.get_payment_by_id(payment_id)
    text = f"✅ Uzum Bank orqali to'lov qabul qilindi! {amount:,} so'm hisobingizga qo'shildi."
    try:
        await credit_approved_payment(webapp.BOT, Database, payment, user_message=text)
    except Exception:
        # Balans qo'shilgandan keyingi xato (bonus, xabar) to'lovni bekor qilmasin — aks holda
        # Uzum qayta yuborganda pul ikki marta qo'shilardi.
        fresh = await Database.get_payment_by_id(payment_id)
        if getattr(fresh, "status", "") != "approved":
            await Database.update_payment_status(payment_id, "rejected")
            raise
        log.exception("Uzum to'lovi %s: balans qo'shildi, keyingi qadamda xato", tx["trans_id"])
    await _notify_admins(f"🟣 Uzum to'lovi: {amount:,} so'm · mijoz {tx['telegram_id']} · to'lov ID {payment_id}")
    return payment_id
