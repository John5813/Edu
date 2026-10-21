"""To'lov chekini tekshirish oqimi: o'qish → qoidalar → mijoz va admin.

Muhim tamoyillar:
- har chek (soxtasi, takrorisi, chek emasi ham) bazada o'qilgan ma'lumoti bilan qoladi;
- pul faqat hamma qoidadan o'tgan va ikki marta bir xil o'qilgan chek uchun avtomatik qo'shiladi;
- to'liq avtomatik rejimda kamchiligi bor chek RAD ETILADI: mijozga chek tagida kamchiliklar ro'yxati,
  «qayta yuborish» va «adminga murojaat» tugmalari boradi; mijoz hech qachon bloklanmaydi;
- AI yoki tarmoq ishlamasa `process` None qaytaradi — chaqiruvchi avvalgi qo'lda tekshiruvga o'tadi.
"""
from database import web_accounts as _web_accounts
import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Dict, List, Optional

import config
from database.database import Database
from . import reader, rules, store, texts

log = logging.getLogger(__name__)

_locks: Dict[int, asyncio.Lock] = {}


@dataclass
class Outcome:
    verdict: str
    clear_state: bool = True            # False — mijoz chekni qayta yuboradi (holat saqlanadi)
    payment_id: Optional[int] = None
    receipt_id: Optional[int] = None


def card_tails() -> tuple:
    return tuple(c[-4:] for c in (config.PAYMENT_CARD, config.PAYMENT_CARD_2) if c)


def owner_keys() -> tuple:
    raw = os.getenv("RECEIPT_RECEIVER_NAMES", "JAVLONBEK")
    return tuple(x.strip().upper() for x in raw.split(",") if x.strip())


def _lang(lang: str) -> str:
    return lang if lang in ("uz", "ru", "en") else "ru"


def _money(value) -> str:
    return f"{int(value):,}".replace(",", " ") if value is not None else "—"


# ─────────────────────────────────────────────────────── qayta yuborish tugmasi

def resend_keyboard(lang: str, claimed: int, started: Optional[datetime], admin: bool = False):
    """«Chekni qayta yuborish» tugmasi: summa va boshlanish vaqti tugma ichida, holat yo'qolsa ham tiklanadi.

    `admin=True` — ostida «Adminga murojaat» havolasi ham bo'ladi (rad javobi uchun).
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    moment = started or rules.now_tashkent()
    epoch = int(moment.replace(tzinfo=rules.TASHKENT).timestamp())
    rows = [[InlineKeyboardButton(text=texts.user_text(lang, "resend_btn"),
                                  callback_data=f"rcpt_resend:{int(claimed)}:{epoch}")]]
    url = texts.admin_url() if admin else None
    if url:
        rows.append([InlineKeyboardButton(text=texts.admin_button_text(lang), url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def override_keyboard(payment_id: int):
    """Admin kartasidagi tugma: AI rad etgan to'lovni baribir tasdiqlash (mijoz adminga murojaat qilganda)."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="✅ Baribir tasdiqlash", callback_data=f"rcpt_force_{int(payment_id)}")]])


# ───────────────────────────────────────────────────────────── admin kartasi

def card_text(user, verdict: str, receipt: rules.Receipt, decision: rules.Decision, claimed: int,
              receipt_id: int, payment_id: Optional[int], extra: str = "") -> str:
    link = _web_accounts.label(user)
    lines = [texts.VERDICT_LABEL.get(verdict, verdict.upper()),
             f"🧾 Chek #{receipt_id}" + (f" · To'lov #{payment_id}" if payment_id else ""),
             f"👤 {link} (id {user.telegram_id})",
             f"💵 Chekda: {_money(receipt.amount)} so'm | mijoz ko'rsatgan: {_money(claimed)} so'm"
             + (f" | komissiya {_money(receipt.fee)}" if receipt.fee else "")]
    when = receipt.dt.strftime("%d.%m.%Y %H:%M") if receipt.dt else "yo'q"
    age = f" ({rules.fmt_age(decision.age_min)} {'oldin' if (decision.age_min or 0) >= 0 else 'keyin'})" \
        if decision.age_min is not None else ""
    shot = ""
    if receipt.status_time or receipt.battery is not None:
        shot = f" · skrinshot soati {receipt.status_time or '?'}" + (
            f" 🔋{receipt.battery}%" if receipt.battery is not None else "")
    lines.append(f"🕒 Chek vaqti: {when}{age}{shot}")
    lines.append(f"🏦 {receipt.app or '?'} · {receipt.doc_type} · {receipt.status}")
    if receipt.ids:
        lines.append("🆔 ID: " + ", ".join(receipt.ids[:4]))
    if receipt.sender_name or receipt.sender_tail:
        lines.append(f"📤 {receipt.sender_name or '?'} ••{receipt.sender_tail or '????'}")
    if receipt.receiver_name or receipt.receiver_tail:
        lines.append(f"📥 {receipt.receiver_name or '?'} ••{receipt.receiver_tail or '????'}")
    # Qo'lda tasdiqlash rejimida avto-tasdiq chegaralari haqidagi sabablar admin uchun shovqin.
    hidden = set() if config.RECEIPT_AUTO else {"over_limit", "over_limit_noid", "no_unique_key", "receiver_by_name"}
    shown = [code for code in decision.reasons if code not in hidden]
    if shown:
        lines.append("⚠️ Diqqat:")
        lines += [f" • {texts.REASONS.get(code, code)}" for code in shown]
    for prior in decision.priors[:3]:
        status = {"approved": "✅ tasdiqlangan", "rejected": "❌ rad etilgan",
                  "pending": "⏳ kutilmoqda"}.get(prior.payment_status, prior.verdict)
        lines.append(f"🔁 Avval: chek #{prior.receipt_id}"
                     + (f" / to'lov #{prior.payment_id}" if prior.payment_id else "")
                     + f" · {status} · id {prior.user_tg} · {prior.created_at[:16]}")
    if receipt.tamper != "none" or receipt.meta_flags:
        lines.append(f"🔎 Tahrir belgisi: {receipt.tamper}"
                     + (f" ({receipt.tamper_reason})" if receipt.tamper_reason else "")
                     + (f"; fayl: {', '.join(receipt.meta_flags)}" if receipt.meta_flags else ""))
    if extra:
        lines.append(extra)
    return "\n".join(lines)


async def _to_admins(bot, user, message, text: str, payment_id: Optional[int] = None,
                     buttons: bool = False, silent: bool = False, copy: bool = True, markup=None) -> None:
    from bot.keyboards import get_payment_review_keyboard
    for admin_id in config.ADMIN_IDS:
        try:
            if copy and hasattr(message, "send_copy"):
                # Sayt orqali kelgan chek: fayl bevosita yuboriladi (Telegramda asl xabar yo'q).
                file_id = await message.send_copy(bot, admin_id, silent)
                if file_id and payment_id:
                    await Database.set_payment_screenshot(payment_id, file_id)
            elif copy:
                await bot.copy_message(chat_id=admin_id, from_chat_id=message.chat.id,
                                       message_id=message.message_id, disable_notification=silent)
            sent = await bot.send_message(
                admin_id, text, disable_notification=silent,
                reply_markup=get_payment_review_keyboard(payment_id) if buttons and payment_id else markup)
            if (buttons or markup is not None) and payment_id:
                await Database.add_payment_admin_message(payment_id, sent.chat.id, sent.message_id, text=text)
        except Exception as exc:
            log.error("Admin %s ga chek yuborilmadi: %s", admin_id, exc)


# ────────────────────────────────────────────────────────────── yordamchilar

def _uid_of(message) -> str:
    """Telegram fayl raqami (file_unique_id): bir fayl uchun doimiy, qayta yuborilsa/uzatilsa ham o'zgarmaydi."""
    try:
        if getattr(message, "photo", None):
            return str(getattr(message.photo[-1], "file_unique_id", "") or "")
        doc = getattr(message, "document", None)
        return str(getattr(doc, "file_unique_id", "") or "") if doc else ""
    except Exception:
        return ""


def _file_of(message):
    """(file_id, filename, mime, size) — rasm yoki hujjat."""
    if getattr(message, "photo", None):
        photo = message.photo[-1]
        return photo.file_id, "photo.jpg", "image/jpeg", getattr(photo, "file_size", 0) or 0
    doc = message.document
    return doc.file_id, doc.file_name or "", doc.mime_type or "", getattr(doc, "file_size", 0) or 0


async def _download(bot, file_id: str) -> bytes:
    file = await bot.get_file(file_id)
    buffer = await bot.download_file(file.file_path)
    return buffer.read()


def _snapshot(receipt: rules.Receipt, file_sha: str) -> dict:
    return {"doc_type": receipt.doc_type, "status": receipt.status, "amount": receipt.amount,
            "fee": receipt.fee, "dt": receipt.dt.isoformat() if receipt.dt else None, "ids": receipt.ids,
            "sender": [receipt.sender_name, receipt.sender_tail],
            "receiver": [receipt.receiver_name, receipt.receiver_tail], "app": receipt.app,
            "status_time": receipt.status_time, "battery": receipt.battery, "cropped": receipt.cropped,
            "tamper": receipt.tamper, "tamper_reason": receipt.tamper_reason,
            "meta_flags": receipt.meta_flags, "confidence": receipt.confidence, "file_sha": file_sha,
            "file_time": receipt.file_time.isoformat() if receipt.file_time else None,
            "file_time_src": receipt.file_time_src}


# ──────────────────────────────────────────────────────────────── asosiy oqim

FEATURE = "receipt_ai"          # admin «Funksiyalar boshqaruvi»dagi kalit (sukut — yoqilgan)


async def ai_enabled() -> bool:
    """AI tekshiruv yoqilganmi: muhit (`RECEIPT_AI`) va admin paneldagi tugma ikkalasi ham ruxsat berishi kerak.

    Tugma har chekda o'qiladi, shuning uchun admin o'chirgach qayta ishga tushirish shart emas.
    O'chiq bo'lsa barcha cheklar avvalgidek to'g'ridan-to'g'ri adminga boradi.
    """
    if not config.RECEIPT_AI:
        return False
    try:
        return bool(await Database().get_feature_status(FEATURE))
    except Exception as exc:                      # tugma holatini o'qib bo'lmasa muhit qiymati ishlaydi
        log.warning("Chek AI tugmasi o'qilmadi: %s", exc)
        return True

FULL_FEATURE = "receipt_full_auto"    # «Funksiyalar boshqaruvi»: AI o'zi tasdiqlaydi yoki rad etadi


async def full_auto_enabled() -> bool:
    """To'liq avtomatik rejim: muhit (`RECEIPT_FULL_AUTO`) va admin paneldagi tugma ikkalasi ham yoqilgan bo'lsin."""
    if not config.RECEIPT_FULL_AUTO:
        return False
    try:
        return bool(await Database().get_feature_status(FULL_FEATURE))
    except Exception as exc:
        log.warning("To'liq avto tugmasi o'qilmadi: %s", exc)
        return True


async def process(message, state_data: dict, db, user, lang: str, source: str = "",
                  keyboard=None) -> Optional[Outcome]:
    """Chekni tekshiradi. None — AI/tarmoq ishlamadi (avvalgi qo'lda tekshiruvga o'tiladi)."""
    if not await ai_enabled():
        return None
    lang = _lang(lang)
    lock = _locks.setdefault(user.telegram_id, asyncio.Lock())
    async with lock:
        notice = None
        try:
            notice = await message.answer(texts.user_text(lang, "checking"))
        except Exception:
            pass
        try:
            return await _process(message, state_data, db, user, lang, source, keyboard)
        except Exception as exc:
            log.error("Chekni AI bilan tekshirib bo'lmadi, qo'lda tekshiruvga o'tildi: %s", exc, exc_info=True)
            return None
        finally:
            if notice:
                try:
                    await notice.delete()
                except Exception:
                    pass


async def process_web(message, state_data: dict, db, user, lang: str) -> Optional[Outcome]:
    """Sayt orqali yuklangan chek (`services.receipts.web.WebMessage`): `process` bilan bir xil qoidalar."""
    if not await ai_enabled():
        return None
    lang = _lang(lang)
    lock = _locks.setdefault(user.telegram_id, asyncio.Lock())
    async with lock:
        try:
            return await _process(message, state_data, db, user, lang, "web", None)
        except Exception as exc:
            log.error("Sayt chekini AI bilan tekshirib bo'lmadi, qo'lda tekshiruvga o'tildi: %s", exc, exc_info=True)
            return None


async def _process(message, state_data: dict, db, user, lang: str, source: str,
                   keyboard=None) -> Optional[Outcome]:
    bot = message.bot
    claimed = int(state_data.get("payment_amount") or 0)
    web_data = getattr(message, "web_data", None)
    if web_data is not None:
        file_id, filename, mime, size = "", message.web_name, message.web_mime, len(web_data)
    else:
        file_id, filename, mime, size = _file_of(message)
    started = None
    try:
        started = datetime.fromisoformat(state_data["payment_started_at"]) if state_data.get("payment_started_at") else None
    except (TypeError, ValueError):
        started = None

    data = web_data if web_data is not None else await _download(bot, file_id)
    file_sha = hashlib.sha256(data).hexdigest()
    file_uid = "" if web_data is not None else _uid_of(message)
    now = rules.now_tashkent()
    loop = asyncio.get_running_loop()
    full = await full_auto_enabled()
    reject = _Reject(message, user, lang, claimed, started) if full else None

    # Faylning o'z izi (baytlar hash'i va Telegram fayl raqami) avval kelgan bo'lsa AI'siz, bepul aniqlanadi.
    fkeys = rules.file_keys(file_sha, file_uid)
    same_file = await store.find_priors(fkeys)
    if same_file:
        priors = list({p.receipt_id: p for p in same_file.values()}.values())
        # O'zining AI rad etgan cheki aynan o'zi qayta yuborildi: natija o'zgarmaydi — o'sha kamchiliklar aytiladi.
        if all(p.user_tg == user.telegram_id and p.verdict == rules.REJECTED for p in priors):
            reasons = await store.reasons_of(priors[0].receipt_id)
            await _say(message, texts.rejection_text(lang, reasons or ["unreadable"]),
                       resend_keyboard(lang, claimed, started, admin=True))
            return Outcome(rules.REJECTED, clear_state=False, receipt_id=priors[0].receipt_id)
        verdict, reason, fraud = rules.classify_priors(priors, user.telegram_id)
        dup = "duplicate_file" if ("file", file_sha) in same_file else "duplicate_fuid"
        decision = rules.Decision(verdict=verdict, fraud=fraud, priors=priors,
                                  reasons=[reason if verdict == rules.OWN_PENDING else dup])
        rid, _ = await store.save_receipt(user.telegram_id, verdict, fraud, None, claimed, decision.reasons,
                                          {"file_sha": file_sha, "file_uid": file_uid, "ai_skipped": True}, fkeys)
        if verdict == rules.OWN_PENDING:
            await message.answer(texts.user_text(lang, "own_done" if reason == "own_done" else "own_pending"),
                                 reply_markup=keyboard)
            return Outcome(verdict, receipt_id=rid)
        if reject:
            return await reject.say(decision, rid)
        return await _rejected(message, bot, db, user, lang, decision, rid, keyboard)
    try:
        receipt, prepared = await loop.run_in_executor(None, partial(reader.read, data, filename, mime, now))
    except reader.Unsupported:
        if reject:
            return await reject.say(rules.Decision(verdict=rules.NOT_RECEIPT, reasons=["unsupported"]), None)
        await message.answer(texts.user_text(lang, "unsupported"),
                             reply_markup=resend_keyboard(lang, claimed, started))
        return Outcome(rules.NOT_RECEIPT, clear_state=False)

    ctx = rules.Context(now=now, claimed=claimed, cards=card_tails(), owner_names=owner_keys(),
                        started_at=started, user_tg=user.telegram_id,
                        max_age_min=config.RECEIPT_MAX_AGE_MIN, auto_max=config.RECEIPT_AUTO_MAX,
                        auto_max_noid=config.RECEIPT_AUTO_MAX_NOID, auto_enabled=config.RECEIPT_AUTO or full)
    found = await store.find_priors(rules.lookup_keys(receipt, file_sha, file_uid))
    # Shu mijozning AI rad etgan cheki (o'sha to'lov) tuzatilib qayta yuborildi: takroriy emas, yangidan baholanadi
    # va kalitlar yangi chekka o'tadi. Boshqa mijozniki yoki admin qaror qilgani — takroriy bo'lib qoladi.
    retry = {p.receipt_id for p in found.values()
             if p.user_tg == user.telegram_id and p.verdict == rules.REJECTED and p.payment_status != "approved"}
    priors = {k: p for k, p in found.items() if p.receipt_id not in retry}
    decision = rules.evaluate(receipt, ctx, file_sha, priors, file_uid)

    # Avtomatik tasdiq uchun muhim maydonlar ikkinchi (kuchliroq) modelda qayta o'qiladi.
    if decision.verdict == rules.AUTO and decision.needs_verify:
        try:
            bad = await loop.run_in_executor(None, partial(reader.verify, prepared, receipt, now))
        except Exception as exc:
            log.warning("Tasdiqlovchi o'qish ishlamadi: %s", exc)
            decision.verdict = rules.REVIEW
            decision.reasons.append("verify_failed")
        else:
            if bad:
                decision.verdict = rules.REVIEW
                decision.reasons.append("verify_mismatch")
                log.info("Ikki o'qish mos kelmadi: %s", bad)

    if full:
        rules.full_auto(decision)

    snapshot = _snapshot(receipt, file_sha)
    verdict = decision.verdict
    # Tashxis uchun jurnal (ism va karta raqamlarisiz): nega chek shu qarorga keldi.
    log.info("Chek hukmi: %s | sabablar=%s | hujjat=%s holat=%s ilova=%s summa=%s o'qildi=%s fayl_belgisi=%s",
             verdict, decision.reasons, receipt.doc_type, receipt.status, receipt.app, receipt.amount,
             receipt.raw.get("readable"), receipt.meta_flags)
    amount_for_payment = receipt.amount if receipt.amount and receipt.amount >= 1000 else claimed

    # ── chek emas: qayta so'raladi, admin jim xabar oladi
    if verdict == rules.NOT_RECEIPT:
        rid, _ = await store.save_receipt(user.telegram_id, verdict, False, receipt.amount, claimed,
                                          decision.reasons, snapshot, [])
        if reject:
            return await reject.say(decision, rid)
        key = decision.reasons[0] if decision.reasons[0] in (
            "tax_receipt", "too_little", "not_payment", "unreadable", "status_failed", "status_pending") else "not_payment"
        # Qayta yuborish so'ralgan har xabar «Chekni qayta yuborish» tugmasi bilan boradi.
        await message.answer(texts.user_text(lang, key) + _debug(user, decision),
                             reply_markup=resend_keyboard(lang, claimed, started))
        return Outcome(verdict, clear_state=False, receipt_id=rid)

    # ── o'zining kutilayotgan cheki qayta yuborildi
    if verdict == rules.OWN_PENDING:
        rid, _ = await store.save_receipt(user.telegram_id, verdict, False, receipt.amount, claimed,
                                          decision.reasons, snapshot, [])
        await message.answer(texts.user_text(lang, "own_done" if "own_done" in decision.reasons else "own_pending"),
                             reply_markup=keyboard)
        return Outcome(verdict, receipt_id=rid)

    # ── avtomatik tasdiq
    if verdict == rules.AUTO:
        rid, taken = await store.save_receipt(user.telegram_id, verdict, False, receipt.amount, claimed,
                                              decision.reasons, snapshot, decision.keys, takeover=retry)
        if not taken:
            payment_id = await db.create_payment(user.id, decision.credit, file_id, source)
            await store.attach_payment(rid, payment_id)
            payment = await db.get_payment_by_id(payment_id)
            text = texts.user_text(lang, "approved", amount=_money(decision.credit))
            if "amount_differs" in decision.reasons:
                text += texts.user_text(lang, "approved_differs", claimed=_money(claimed),
                                        amount=_money(decision.credit))
            try:
                from bot.handlers.admin import credit_approved_payment
                await credit_approved_payment(bot, db, payment, user_message=text, reply_markup=keyboard)
            except Exception as exc:
                log.error("Avto-tasdiqda pul qo'shilmadi (to'lov %s): %s", payment_id, exc, exc_info=True)
                decision.reasons.append("ai_error")
                await store.mark(rid, rules.REVIEW)
                await message.answer(texts.user_text(lang, "review"), reply_markup=keyboard)
                await _to_admins(bot, user, message,
                                 card_text(user, rules.REVIEW, receipt, decision, claimed, rid, payment_id),
                                 payment_id, buttons=True)
                return Outcome(rules.REVIEW, payment_id=payment_id, receipt_id=rid)
            await _to_admins(bot, user, message,
                             card_text(user, verdict, receipt, decision, claimed, rid, payment_id,
                                       extra=f"💰 {_money(decision.credit)} so'm mijoz hisobiga qo'shildi"),
                             silent=True)
            return Outcome(verdict, payment_id=payment_id, receipt_id=rid)
        # Poyga: shu kalit bir lahza oldin boshqa chek bilan band qilindi.
        decision.verdict, decision.fraud = rules.DUPLICATE, True
        decision.reasons.append("race")
        await store.mark(rid, rules.DUPLICATE, True)
        if reject:
            return await reject.say(decision, rid)
        return await _rejected(message, bot, db, user, lang, decision, rid, keyboard)

    # ── takroriy yoki tahrirlangan (fayl izida Photoshop): mijozga rad javobi; ADMINGA BORMAYDI.
    # Boshqa karta, ID/qabul qiluvchi ko'rinmaydigan chek kabi noaniq hollar adminga boradi: yakuniy qaror odamda.
    if verdict in (rules.DUPLICATE, rules.FAKE):
        rid, _ = await store.save_receipt(user.telegram_id, verdict, decision.fraud, receipt.amount, claimed,
                                          decision.reasons, snapshot, decision.keys)
        if reject:
            return await reject.say(decision, rid)
        return await _rejected(message, bot, db, user, lang, decision, rid, keyboard)

    # ── to'liq avto rejim: haqiqiy chek, lekin kamchiligi bor — rad etiladi, mijozga sabablar aytiladi.
    # To'lov yozuvi «rejected» holatida qoladi: mijoz adminga murojaat qilsa, admin bir tugma bilan tasdiqlaydi.
    if verdict == rules.REJECTED:
        rid, _ = await store.save_receipt(user.telegram_id, verdict, False, receipt.amount, claimed,
                                          decision.reasons, snapshot, decision.keys, takeover=retry)
        payment_id = await db.create_payment(user.id, amount_for_payment, file_id, source)
        await db.update_payment_status(payment_id, "rejected")
        await store.attach_payment(rid, payment_id)
        outcome = await reject.say(decision, rid, payment_id)
        await _to_admins(bot, user, message,
                         card_text(user, verdict, receipt, decision, claimed, rid, payment_id,
                                   extra="👤 Mijozga kamchiliklar aytildi. Murojaat qilsa — «Baribir tasdiqlash»."),
                         payment_id, silent=True, markup=override_keyboard(payment_id))
        return outcome

    # ── haqiqiy chek, lekin odam qarori kerak (eski, katta summa, shubhali tafsilot ...): adminga
    rid, _ = await store.save_receipt(user.telegram_id, verdict, False, receipt.amount, claimed,
                                      decision.reasons, snapshot, decision.keys, takeover=retry)
    payment_id = await db.create_payment(user.id, amount_for_payment, file_id, source)
    await store.attach_payment(rid, payment_id)
    return await _flagged(message, bot, db, user, lang, receipt, decision, claimed, rid, payment_id, keyboard)


async def _say(message, text: str, markup) -> None:
    """Javobni mijoz yuborgan chek TAGIGA (reply) yozadi; reply bo'lmasa oddiy xabar."""
    kwargs = {}
    message_id = getattr(message, "message_id", 0)
    if message_id and not hasattr(message, "web_data"):
        try:
            from aiogram.types import ReplyParameters
            kwargs["reply_parameters"] = ReplyParameters(message_id=message_id, allow_sending_without_reply=True)
        except Exception:
            pass
    try:
        await message.answer(text, reply_markup=markup, **kwargs)
    except Exception as exc:
        log.warning("Rad javobi chek tagiga yozilmadi: %s", exc)
        try:
            await message.answer(text, reply_markup=markup)
        except Exception:
            pass


class _Reject:
    """To'liq avto rejimdagi rad javobi: «To'lov rad etildi» + kamchiliklar + qayta yuborish/admin tugmalari."""

    def __init__(self, message, user, lang: str, claimed: int, started: Optional[datetime]):
        self.message, self.user, self.lang, self.claimed, self.started = message, user, lang, claimed, started

    async def say(self, decision: rules.Decision, rid: Optional[int], payment_id: Optional[int] = None) -> Outcome:
        reasons = list(decision.reasons)
        if decision.verdict == rules.DUPLICATE and not any(r.startswith("duplicate") or r == "race" for r in reasons):
            reasons.insert(0, "duplicate")
        text = texts.rejection_text(self.lang, reasons, rules.fmt_age(decision.age_min)) + _debug(self.user, decision)
        await _say(self.message, text, resend_keyboard(self.lang, self.claimed, self.started, admin=True))
        # Holat saqlanadi: mijoz tugmasiz ham to'g'ri chekni darhol yubora oladi.
        return Outcome(decision.verdict, clear_state=False, payment_id=payment_id, receipt_id=rid)


def _sent_to_admin_text(lang: str) -> str:
    """Avvalgi qo'lda tekshiruvdagi xabar: «adminga yuborildi» + kunduzgi/kechki eslatma."""
    try:
        from translations import get_text
        text = get_text(lang, "payment_sent_to_admin")
        hour = datetime.now().hour
        return text + "\n\n" + get_text(lang, "payment_reminder_daytime" if 7 <= hour < 22
                                          else "payment_reminder_nighttime")
    except Exception:
        return texts.user_text(lang, "review")


def _debug(user, decision) -> str:
    """Admin o'zi sinab ko'rayotganda sabablar mijoz xabariga qo'shiladi (oddiy mijozda ko'rinmaydi)."""
    if user.telegram_id not in config.ADMIN_IDS:
        return ""
    return "\n\n🛠 (admin ko'rinishi) " + "; ".join(texts.REASONS.get(c, c) for c in decision.reasons)


async def _rejected(message, bot, db, user, lang, decision, rid, keyboard=None) -> Outcome:
    """Takroriy yoki tahrirlangan chek: faqat mijozga javob. Adminga xabar yo'q, mijoz bloklanmaydi."""
    key = {rules.DUPLICATE: "duplicate", rules.WRONG_RECEIVER: "wrong_receiver", rules.FAKE: "fake"}[decision.verdict]
    try:
        await message.answer(texts.user_text(lang, key) + _debug(user, decision), reply_markup=keyboard)
    except Exception:
        pass
    return Outcome(decision.verdict, receipt_id=rid)


async def _flagged(message, bot, db, user, lang, receipt, decision, claimed, rid, payment_id,
                   keyboard=None) -> Outcome:
    """Haqiqiy chek, lekin admin qarori kerak: kartochka tugmalar bilan boradi."""
    legacy = not any(code in decision.reasons for code in ("stale", "screenshot_old"))
    text = _sent_to_admin_text(lang) if legacy else texts.user_text(
        lang, "stale", age=rules.fmt_age(decision.age_min) or "—")
    try:
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown" if legacy else None)
    except Exception:
        try:
            await message.answer(text.replace("*", ""), reply_markup=keyboard)
        except Exception:
            pass
    await _to_admins(bot, user, message,
                     card_text(user, decision.verdict, receipt, decision, claimed, rid, payment_id),
                     payment_id, buttons=True)
    return Outcome(decision.verdict, payment_id=payment_id, receipt_id=rid)
