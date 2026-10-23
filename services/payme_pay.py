"""Payme Merchant API: balansni Payme orqali to'ldirish.

Oqim:
    1. Mijoz summani tanlaydi → buyurtma (`database.payme_orders`) va checkout havolasi
       (`https://checkout.paycom.uz/<base64("m=ID;ac.order_id=N;a=TIYIN;c=QAYTISH")>`).
    2. Mijoz Payme sahifasida to'laydi.
    3. Payme serveri bizning `/payme` manzilimizga JSON-RPC so'rovlar yuboradi:
       CheckPerformTransaction → CreateTransaction → PerformTransaction (pul yechildi → balans
       `credit_approved_payment` orqali, chek tasdig'i bilan bir xil), kerak bo'lsa CancelTransaction;
       shuningdek CheckTransaction va GetStatement.

Har so'rov `Authorization: Basic base64("Paycom:<KALIT>")` bilan keladi. Test rejimida (`PAYME_TEST=1`)
test kaliti va test.paycom.uz ishlatiladi — Payme kabinetidagi «Песочница» shu bilan o'tkaziladi;
test kaliti ishlab chiqarishda qabul qilinmaydi (sinov tranzaksiyalari haqiqiy balansga tushmasin).

Summalar Payme'da tiyinda (so'm × 100). Javob doim HTTP 200, xatolar JSON-RPC `error` maydonida.
"""
import base64
import binascii
import hmac
import logging
from typing import Awaitable, Callable, Dict, Mapping, Optional

import config
from database import payme_orders as orders

log = logging.getLogger(__name__)

CHECKOUT_URL = "https://checkout.paycom.uz"
TEST_CHECKOUT_URL = "https://test.paycom.uz"
MIN_AMOUNT = 1000
MAX_AMOUNT = 5_000_000
TIMEOUT_MS = 12 * 60 * 60 * 1000          # yakunlanmagan tranzaksiya 12 soatdan keyin bekor qilinadi
TIMEOUT_REASON = 4

FEATURE = "payme_pay"           # admin «Funksiyalar boshqaruvi»dagi kalit (sukut — yoqilgan)

# Payme hujjatidagi xato kodlari.
AUTH_FAILED = -32504
PARSE_ERROR = -32700
BAD_REQUEST = -32600
NO_METHOD = -32601
SYSTEM_ERROR = -32400
BAD_AMOUNT = -31001
NO_TRANSACTION = -31003
CANT_CANCEL = -31007
CANT_PERFORM = -31008
NO_ORDER = -31050
ORDER_BUSY = -31051
ORDER_CLOSED = -31052

MESSAGES = {
    AUTH_FAILED: ("Недостаточно привилегий", "Ruxsat yo'q", "Insufficient privilege"),
    PARSE_ERROR: ("Ошибка разбора JSON", "JSON xato", "Parse error"),
    BAD_REQUEST: ("Неверный запрос", "Noto'g'ri so'rov", "Invalid request"),
    NO_METHOD: ("Метод не найден", "Usul topilmadi", "Method not found"),
    SYSTEM_ERROR: ("Системная ошибка", "Tizim xatosi", "System error"),
    BAD_AMOUNT: ("Неверная сумма", "Noto'g'ri summa", "Incorrect amount"),
    NO_TRANSACTION: ("Транзакция не найдена", "Tranzaksiya topilmadi", "Transaction not found"),
    CANT_CANCEL: ("Невозможно отменить транзакцию", "Tranzaksiyani bekor qilib bo'lmaydi",
                  "Unable to cancel transaction"),
    CANT_PERFORM: ("Невозможно выполнить операцию", "Amalni bajarib bo'lmaydi", "Unable to perform operation"),
    NO_ORDER: ("Заказ не найден", "Buyurtma topilmadi", "Order not found"),
    ORDER_BUSY: ("Заказ ожидает оплаты", "Buyurtma to'lov kutmoqda", "Order is awaiting payment"),
    ORDER_CLOSED: ("Заказ уже оплачен или отменён", "Buyurtma to'langan yoki bekor qilingan",
                   "Order already paid or cancelled"),
}


class PaymeError(Exception):
    def __init__(self, code: int, data: Optional[str] = None):
        super().__init__(code)
        self.code, self.data = code, data


def _env_key() -> str:
    return config.PAYME_TEST_KEY if config.PAYME_TEST else config.PAYME_KEY


def _mode() -> str:
    return "test" if config.PAYME_TEST else "prod"


async def _key() -> str:
    """Amaldagi kalit: Payme ChangePassword bilan yuborgani, aks holda .env dagi.

    Saqlangan kalit faqat .env o'sha paytdagidek tursa ishlaydi — .env qo'lda yangilansa, o'shanisi olinadi.
    """
    env_key = _env_key()
    try:
        saved = await orders.get_key(_mode())
    except Exception as exc:
        log.warning("Payme kaliti bazadan o'qilmadi: %s", exc)
        saved = None
    return saved["key"] if saved and saved["env_key"] == env_key else env_key


def enabled() -> bool:
    """Kalitlar sozlanganmi. `/payme` manzili shunga qaraydi — admin o'chirsa ham boshlangan to'lovlar yakunlanadi."""
    return bool(config.PAYME_MERCHANT_ID and _env_key())


async def available() -> bool:
    """Mijozga Payme tugmasini ko'rsatish mumkinmi: kalitlar bor va admin paneldan o'chirilmagan."""
    if not enabled():
        return False
    try:
        from database.database import Database
        return bool(await Database().get_feature_status(FEATURE))
    except Exception as exc:                      # holatni o'qib bo'lmasa — kalitlar bo'yicha
        log.warning("Payme tugmasi holati o'qilmadi: %s", exc)
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


def pay_url(order_id: int, amount: int, return_url: str = "", lang: str = "uz") -> str:
    """Payme checkout havolasi (summa tiyinda). `return_url` bo'lmasa — sozlamadagi yoki bot."""
    import webapp

    return_url = return_url or config.PAYME_RETURN_URL or (
        f"https://t.me/{webapp.BOT_USERNAME}" if webapp.BOT_USERNAME else "")
    parts = [f"m={config.PAYME_MERCHANT_ID}", f"ac.{config.PAYME_ACCOUNT}={order_id}", f"a={int(amount) * 100}",
             f"l={lang if lang in ('uz', 'ru', 'en') else 'uz'}"]
    if return_url:
        parts.append(f"c={return_url}")
    raw = base64.b64encode(";".join(parts).encode()).decode()
    return f"{TEST_CHECKOUT_URL if config.PAYME_TEST else CHECKOUT_URL}/{raw}"


async def new_payment(telegram_id: int, amount, source: str, return_url: str = "", lang: str = "uz") -> str:
    """Buyurtma yaratib, Payme to'lov havolasini qaytaradi."""
    amount = valid_amount(amount)
    order_id = await orders.create_order(telegram_id, amount, source)
    log.info("Payme buyurtma %s: %s so'm (%s, %s)", order_id, amount, telegram_id, source)
    return pay_url(order_id, amount, return_url, lang)


async def authorized(header: str) -> bool:
    """`Authorization: Basic base64("Paycom:<kalit>")`."""
    key = await _key()
    if not key or not header or not header.startswith("Basic "):
        return False
    try:
        login, _, password = base64.b64decode(header[6:].strip()).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    return login == "Paycom" and hmac.compare_digest(password.encode(), key.encode())


# ─────────────────────────────────────────────────────────────── usullar

async def _order_for(params: Mapping, amount_required: bool = True) -> Dict:
    """Buyurtma va summa tekshiruvi (CheckPerformTransaction / CreateTransaction uchun umumiy)."""
    amount = params.get("amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        raise PaymeError(BAD_AMOUNT, "amount")
    account = params.get("account")
    if not isinstance(account, dict):
        raise PaymeError(NO_ORDER, config.PAYME_ACCOUNT)
    try:
        order = await orders.get_order(int(str(account.get(config.PAYME_ACCOUNT, "")).strip()))
    except (TypeError, ValueError):
        order = None
    if order is None:
        raise PaymeError(NO_ORDER, config.PAYME_ACCOUNT)
    if int(amount) != amount or int(amount) != order["amount"] * 100:
        raise PaymeError(BAD_AMOUNT, "amount")
    if order["status"] != orders.NEW:
        raise PaymeError(ORDER_CLOSED, config.PAYME_ACCOUNT)
    return order


async def check_perform(params: Mapping) -> Dict:
    order = await _order_for(params)
    if await orders.active_tx(order["id"]):
        raise PaymeError(ORDER_BUSY, config.PAYME_ACCOUNT)
    result = {"allow": True}
    if config.PAYME_IKPU:
        result["detail"] = receipt_detail(order)
    return result


def receipt_detail(order: Dict) -> Dict:
    """Fiskal chek ma'lumoti (chekni Payme chiqaradi): bitta xizmat — hisobni to'ldirish."""
    item = {"title": config.PAYME_ITEM_TITLE, "price": order["amount"] * 100, "count": 1,
            "code": config.PAYME_IKPU, "vat_percent": config.PAYME_VAT_PERCENT}
    if config.PAYME_PACKAGE_CODE:
        item["package_code"] = config.PAYME_PACKAGE_CODE
    return {"receipt_type": 0, "items": [item]}


def _tx_id(params: Mapping) -> str:
    tx_id = params.get("id")
    if not isinstance(tx_id, str) or not tx_id.strip():
        raise PaymeError(BAD_REQUEST, "id")
    return tx_id


async def _expire(tx: Dict) -> bool:
    """12 soatdan oshgan yakunlanmagan tranzaksiyani bekor qiladi. True — muddati o'tgan."""
    if tx["state"] != orders.CREATED or orders.now_ms() - tx["create_time"] <= TIMEOUT_MS:
        return False
    await orders.cancel_tx(tx["payme_id"], orders.CREATED, TIMEOUT_REASON)
    await orders.set_order_status(tx["order_id"], orders.CANCELLED)
    return True


def _created(tx: Dict) -> Dict:
    return {"create_time": tx["create_time"], "transaction": str(tx["id"]), "state": tx["state"]}


async def create(params: Mapping) -> Dict:
    tx_id = _tx_id(params)
    tx = await orders.get_tx(tx_id)
    if tx is not None:
        if tx["state"] != orders.CREATED or await _expire(tx):
            raise PaymeError(CANT_PERFORM, "id")
        return _created(tx)
    payme_time = params.get("time")
    if not isinstance(payme_time, int) or isinstance(payme_time, bool):
        raise PaymeError(BAD_REQUEST, "time")
    order = await _order_for(params)
    tx = await orders.create_tx(tx_id, order["id"], int(params["amount"]), payme_time)
    if tx is None:                                # buyurtmada boshqa faol tranzaksiya bor
        raise PaymeError(ORDER_BUSY, config.PAYME_ACCOUNT)
    log.info("Payme tranzaksiya %s: buyurtma %s", tx_id, order["id"])
    return _created(tx)


CreditFn = Callable[[Dict], Awaitable[int]]


async def perform(params: Mapping, credit: Optional[CreditFn] = None) -> Dict:
    """`credit(order) -> payment_id` — balansni to'ldiradi (testlarda almashtiriladi)."""
    tx_id = _tx_id(params)
    tx = await orders.get_tx(tx_id)
    if tx is None:
        raise PaymeError(NO_TRANSACTION, "id")
    if tx["state"] == orders.CREATED:
        if await _expire(tx):
            raise PaymeError(CANT_PERFORM, "id")
        if await orders.claim_perform(tx_id):
            order = await orders.get_order(tx["order_id"])
            try:
                payment_id = await (credit or _credit)(order)
            except Exception as exc:
                # Balans qo'shilmadi: tranzaksiya qaytariladi, Payme PerformTransaction'ni qayta yuboradi.
                log.exception("Payme to'lovi %s balansga qo'shilmadi: %s", tx_id, exc)
                await orders.unclaim_perform(tx_id)
                raise PaymeError(CANT_PERFORM, "id")
            await orders.set_payment(tx_id, payment_id)
            await orders.set_order_status(order["id"], orders.PAID)
            log.info("Payme to'lovi %s: %s so'm → %s (payment %s)", tx_id, order["amount"], order["telegram_id"],
                     payment_id)
        tx = await orders.get_tx(tx_id)
    if tx["state"] != orders.PERFORMED:
        raise PaymeError(CANT_PERFORM, "id")
    return {"transaction": str(tx["id"]), "perform_time": tx["perform_time"], "state": tx["state"]}


async def cancel(params: Mapping) -> Dict:
    tx_id = _tx_id(params)
    reason = params.get("reason")
    reason = reason if isinstance(reason, int) and not isinstance(reason, bool) else None
    tx = await orders.get_tx(tx_id)
    if tx is None:
        raise PaymeError(NO_TRANSACTION, "id")
    if tx["state"] == orders.CREATED:
        if await orders.cancel_tx(tx_id, orders.CREATED, reason):
            await orders.set_order_status(tx["order_id"], orders.CANCELLED)
            log.info("Payme tranzaksiya %s bekor qilindi (sabab %s)", tx_id, reason)
    elif tx["state"] == orders.PERFORMED:
        # Yakunlangan to'lov qaytarilmoqda: Payme pulni mijozga baribir qaytaradi, shuning uchun rad etilmaydi.
        # Summa balansdan yechiladi; mijoz sarflab bo'lgan bo'lsa balans manfiyga tushadi va adminga xabar boradi.
        if await orders.cancel_tx(tx_id, orders.PERFORMED, reason):
            await _refund(await orders.get_order(tx["order_id"]), tx, reason)
    tx = await orders.get_tx(tx_id)
    return {"transaction": str(tx["id"]), "cancel_time": tx["cancel_time"], "state": tx["state"]}


async def check(params: Mapping) -> Dict:
    tx = await orders.get_tx(_tx_id(params))
    if tx is None:
        raise PaymeError(NO_TRANSACTION, "id")
    return {"create_time": tx["create_time"], "perform_time": tx["perform_time"], "cancel_time": tx["cancel_time"],
            "transaction": str(tx["id"]), "state": tx["state"], "reason": tx["reason"]}


async def get_statement(params: Mapping) -> Dict:
    start, end = params.get("from"), params.get("to")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (start, end)):
        raise PaymeError(BAD_REQUEST, "from")
    return {"transactions": [
        {"id": tx["payme_id"], "time": tx["payme_time"], "amount": tx["amount"],
         "account": {config.PAYME_ACCOUNT: str(tx["order_id"])}, "create_time": tx["create_time"],
         "perform_time": tx["perform_time"], "cancel_time": tx["cancel_time"], "transaction": str(tx["id"]),
         "state": tx["state"], "reason": tx["reason"]}
        for tx in await orders.statement(start, end)]}


async def change_password(params: Mapping) -> Dict:
    """Payme kabinetida kalit almashtirildi: yangisi saqlanadi, eskisi endi qabul qilinmaydi."""
    password = params.get("password")
    if not isinstance(password, str) or not password.strip():
        raise PaymeError(BAD_REQUEST, "password")
    await orders.set_key(_mode(), _env_key(), password.strip())
    log.warning("Payme kaliti almashtirildi (%s rejim) — .env dagi %s ni ham yangilang",
                _mode(), "PAYME_TEST_KEY" if config.PAYME_TEST else "PAYME_KEY")
    return {"success": True}


METHODS = {
    "CheckPerformTransaction": check_perform,
    "CreateTransaction": create,
    "PerformTransaction": perform,
    "CancelTransaction": cancel,
    "CheckTransaction": check,
    "GetStatement": get_statement,
    "ChangePassword": change_password,
}


def _error(request_id, code: int, data: Optional[str] = None) -> Dict:
    ru, uz, en = MESSAGES[code]
    error = {"code": code, "message": {"ru": ru, "uz": uz, "en": en}}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


async def handle(body, auth_header: str) -> Dict:
    """Bitta kirish: JSON-RPC so'rov (allaqachon o'qilgan `body`; None — JSON xato)."""
    request_id = body.get("id") if isinstance(body, dict) else None
    if not await authorized(auth_header):
        return _error(request_id, AUTH_FAILED)
    if body is None:
        return _error(None, PARSE_ERROR)
    if not isinstance(body, dict) or not isinstance(body.get("method"), str):
        return _error(request_id, BAD_REQUEST)
    method = METHODS.get(body["method"])
    if method is None:
        return _error(request_id, NO_METHOD, body["method"])
    params = body.get("params")
    if not isinstance(params, dict):
        return _error(request_id, BAD_REQUEST, "params")
    try:
        return {"jsonrpc": "2.0", "id": request_id, "result": await method(params)}
    except PaymeError as exc:
        return _error(request_id, exc.code, exc.data)
    except Exception as exc:
        log.exception("Payme %s bajarilmadi: %s", body["method"], exc)
        return _error(request_id, SYSTEM_ERROR)


async def _refund(order: Dict, tx: Dict, reason) -> None:
    """Payme qaytargan to'lov: balansdan yechish (yetmasa — manfiyga), to'lov yozuvi rad etilgan."""
    import webapp
    from database.database import Database

    if not await Database.charge_balance(order["telegram_id"], order["amount"]):
        await Database.update_user_balance(order["telegram_id"], -order["amount"])
        note = " · balans yetmadi, manfiyga tushdi"
    else:
        note = ""
    if tx.get("payment_id"):
        await Database.update_payment_status(tx["payment_id"], "rejected")
    await orders.set_order_status(order["id"], orders.CANCELLED)
    log.info("Payme to'lovi %s qaytarildi (sabab %s)%s", tx["payme_id"], reason, note)
    for admin_id in config.ADMIN_IDS:
        try:
            await webapp.BOT.send_message(admin_id, f"↩️ Payme to'lovi qaytarildi: {order['amount']:,} so'm · "
                                                    f"mijoz {order['telegram_id']}{note}", disable_notification=True)
        except Exception as exc:
            log.debug("Adminga Payme qaytarish xabari yuborilmadi: %s", exc)


async def _credit(order: Dict) -> int:
    """To'lov yozuvi (`source='payme'`) va chek tasdig'i bilan bir xil balans oqimi."""
    import webapp
    from bot.handlers.admin import credit_approved_payment
    from database.database import Database

    user = await Database.get_user(order["telegram_id"])
    if user is None:
        raise RuntimeError(f"mijoz topilmadi: {order['telegram_id']}")
    payment_id = await Database.create_payment(user.id, order["amount"], "", "payme")
    payment = await Database.get_payment_by_id(payment_id)
    bot = webapp.BOT
    text = f"✅ Payme orqali to'lov qabul qilindi! {order['amount']:,} so'm hisobingizga qo'shildi."
    try:
        await credit_approved_payment(bot, Database, payment, user_message=text)
    except Exception:
        # Balans qo'shilgandan keyingi xato (bonus, xabar) to'lovni bekor qilmasin — aks holda
        # Payme qayta yuborganda pul ikki marta qo'shilardi.
        fresh = await Database.get_payment_by_id(payment_id)
        if getattr(fresh, "status", "") != "approved":
            await Database.update_payment_status(payment_id, "rejected")
            raise
        log.exception("Payme to'lovi buyurtma %s: balans qo'shildi, keyingi qadamda xato", order["id"])
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"💠 Payme to'lovi: {order['amount']:,} so'm · "
                                             f"mijoz {order['telegram_id']} · to'lov ID {payment_id}",
                                   disable_notification=True)
        except Exception as exc:
            log.debug("Adminga Payme xabari yuborilmadi: %s", exc)
    return payment_id
