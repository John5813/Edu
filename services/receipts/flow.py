"""To'lov chekini tekshirish oqimi: o'qish → qoidalar → mijoz, admin va bloklash.

Muhim tamoyillar:
- har chek (soxtasi, takrorisi, chek emasi ham) adminda o'qilgan ma'lumoti bilan qoladi;
- pul faqat hamma qoidadan o'tgan va ikki marta bir xil o'qilgan chek uchun avtomatik qo'shiladi;
- AI yoki tarmoq ishlamasa `process` None qaytaradi — chaqiruvchi avvalgi qo'lda tekshiruvga o'tadi.
"""
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

def resend_keyboard(lang: str, claimed: int, started: Optional[datetime]):
    """«Chekni qayta yuborish» tugmasi: summa va boshlanish vaqti tugma ichida, holat yo'qolsa ham tiklanadi."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    moment = started or rules.now_tashkent()
    epoch = int(moment.replace(tzinfo=rules.TASHKENT).timestamp())
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=texts.user_text(lang, "resend_btn"), callback_data=f"rcpt_resend:{int(claimed)}:{epoch}")]])


# ───────────────────────────────────────────────────────────── admin kartasi

def card_text(user, verdict: str, receipt: rules.Receipt, decision: rules.Decision, claimed: int,
              receipt_id: int, payment_id: Optional[int], extra: str = "") -> str:
    link = f"@{user.username}" if getattr(user, "username", None) else f"tg://user?id={user.telegram_id}"
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
    if decision.reasons:
        lines.append("⚠️ Sabablar:")
        lines += [f" • {texts.REASONS.get(code, code)}" for code in decision.reasons]
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
                     buttons: bool = False, silent: bool = False, copy: bool = True) -> None:
    from bot.keyboards import get_payment_review_keyboard
    for admin_id in config.ADMIN_IDS:
        try:
            if copy:
                await bot.copy_message(chat_id=admin_id, from_chat_id=message.chat.id,
                                       message_id=message.message_id, disable_notification=silent)
            sent = await bot.send_message(
                admin_id, text, disable_notification=silent,
                reply_markup=get_payment_review_keyboard(payment_id) if buttons and payment_id else None)
            if buttons and payment_id:
                await Database.add_payment_admin_message(payment_id, sent.chat.id, sent.message_id, text=text)
        except Exception as exc:
            log.error("Admin %s ga chek yuborilmadi: %s", admin_id, exc)


# ────────────────────────────────────────────────────────────── yordamchilar

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
            "meta_flags": receipt.meta_flags, "confidence": receipt.confidence, "file_sha": file_sha}


async def _block(bot, db, user, lang: str, strikes: int) -> None:
    admin = config.ADMIN_IDS[0] if config.ADMIN_IDS else 0
    await db.block_user(user.telegram_id, getattr(user, "username", "") or "", admin,
                        f"Takroriy/soxta cheklar ({strikes})")
    try:
        await bot.send_message(user.telegram_id, texts.user_text(lang, "blocked"))
    except Exception:
        pass
    link = f"@{user.username}" if getattr(user, "username", None) else f"tg://user?id={user.telegram_id}"
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"🚫 {link} (id {user.telegram_id}) avtomatik bloklandi: "
                                             f"{strikes} ta takroriy/soxta chek.\nBloklanganlar ro'yxatidan ochish mumkin.")
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────── asosiy oqim

async def process(message, state_data: dict, db, user, lang: str, source: str = "",
                  keyboard=None) -> Optional[Outcome]:
    """Chekni tekshiradi. None — AI/tarmoq ishlamadi (avvalgi qo'lda tekshiruvga o'tiladi)."""
    if not config.RECEIPT_AI:
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


async def _process(message, state_data: dict, db, user, lang: str, source: str,
                   keyboard=None) -> Optional[Outcome]:
    bot = message.bot
    claimed = int(state_data.get("payment_amount") or 0)
    file_id, filename, mime, size = _file_of(message)
    started = None
    try:
        started = datetime.fromisoformat(state_data["payment_started_at"]) if state_data.get("payment_started_at") else None
    except (TypeError, ValueError):
        started = None

    data = await _download(bot, file_id)
    file_sha = hashlib.sha256(data).hexdigest()
    now = rules.now_tashkent()
    loop = asyncio.get_running_loop()
    try:
        receipt, prepared = await loop.run_in_executor(None, partial(reader.read, data, filename, mime, now))
    except reader.Unsupported:
        await message.answer(texts.user_text(lang, "unsupported"),
                             reply_markup=resend_keyboard(lang, claimed, started))
        return Outcome(rules.NOT_RECEIPT, clear_state=False)

    ctx = rules.Context(now=now, claimed=claimed, cards=card_tails(), owner_names=owner_keys(),
                        started_at=started, user_tg=user.telegram_id,
                        max_age_min=config.RECEIPT_MAX_AGE_MIN, auto_max=config.RECEIPT_AUTO_MAX,
                        auto_max_noid=config.RECEIPT_AUTO_MAX_NOID, auto_enabled=config.RECEIPT_AUTO)
    priors = await store.find_priors(rules.lookup_keys(receipt, file_sha))
    decision = rules.evaluate(receipt, ctx, file_sha, priors)

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

    snapshot = _snapshot(receipt, file_sha)
    verdict = decision.verdict
    amount_for_payment = receipt.amount if receipt.amount and receipt.amount >= 1000 else claimed

    # ── chek emas: qayta so'raladi, admin jim xabar oladi
    if verdict == rules.NOT_RECEIPT:
        rid, _ = await store.save_receipt(user.telegram_id, verdict, False, receipt.amount, claimed,
                                          decision.reasons, snapshot, [])
        key = decision.reasons[0] if decision.reasons[0] in (
            "tax_receipt", "too_little", "not_payment", "unreadable", "status_failed", "status_pending") else "not_payment"
        # Qayta yuborish so'ralgan har xabar «Chekni qayta yuborish» tugmasi bilan boradi.
        await message.answer(texts.user_text(lang, key), reply_markup=resend_keyboard(lang, claimed, started))
        await _to_admins(bot, user, message, card_text(user, verdict, receipt, decision, claimed, rid, None),
                         silent=True)
        return Outcome(verdict, clear_state=False, receipt_id=rid)

    # ── o'zining kutilayotgan cheki qayta yuborildi
    if verdict == rules.OWN_PENDING:
        rid, _ = await store.save_receipt(user.telegram_id, verdict, False, receipt.amount, claimed,
                                          decision.reasons, snapshot, [])
        await message.answer(texts.user_text(lang, "own_done" if "own_done" in decision.reasons else "own_pending"),
                             reply_markup=keyboard)
        await _to_admins(bot, user, message, card_text(user, verdict, receipt, decision, claimed, rid, None),
                         silent=True, copy=False)
        return Outcome(verdict, receipt_id=rid)

    # ── avtomatik tasdiq
    if verdict == rules.AUTO:
        rid, taken = await store.save_receipt(user.telegram_id, verdict, False, receipt.amount, claimed,
                                              decision.reasons, snapshot, decision.keys)
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
        verdict = rules.DUPLICATE
        await store.mark(rid, verdict, True)
        payment_id = await db.create_payment(user.id, amount_for_payment, file_id, source)
        await store.attach_payment(rid, payment_id)
        return await _flagged(message, bot, db, user, lang, receipt, decision, claimed, rid, payment_id, keyboard)

    # ── admin hal qiladigan holatlar (takroriy, boshqa karta, shubhali, eski ...)
    rid, _ = await store.save_receipt(user.telegram_id, verdict, decision.fraud, receipt.amount, claimed,
                                      decision.reasons, snapshot, decision.keys)
    payment_id = await db.create_payment(user.id, amount_for_payment, file_id, source)
    await store.attach_payment(rid, payment_id)
    return await _flagged(message, bot, db, user, lang, receipt, decision, claimed, rid, payment_id, keyboard)


async def _flagged(message, bot, db, user, lang, receipt, decision, claimed, rid, payment_id,
                   keyboard=None) -> Outcome:
    verdict = decision.verdict
    strikes = 0
    is_admin = user.telegram_id in config.ADMIN_IDS
    if verdict == rules.DUPLICATE and decision.fraud and not is_admin:
        strikes = await store.fraud_strikes(user.telegram_id)

    if verdict == rules.DUPLICATE:
        text = texts.user_text(lang, "duplicate")
        if strikes and strikes >= config.RECEIPT_FRAUD_STRIKES - 1:
            text += texts.user_text(lang, "duplicate_warn")
    elif verdict == rules.WRONG_RECEIVER:
        text = texts.user_text(lang, "wrong_receiver")
    elif any(code in decision.reasons for code in ("stale", "before_request", "screenshot_old")):
        text = texts.user_text(lang, "stale", age=rules.fmt_age(decision.age_min) or "—")
    else:
        text = texts.user_text(lang, "review")
    try:
        await message.answer(text, reply_markup=keyboard)
    except Exception:
        pass

    extra = f"⚠️ Soxta/takroriy urinishlar: {strikes}" if strikes else ""
    await _to_admins(bot, user, message,
                     card_text(user, verdict, receipt, decision, claimed, rid, payment_id, extra=extra),
                     payment_id, buttons=True)
    if strikes >= config.RECEIPT_FRAUD_STRIKES:
        await _block(bot, db, user, lang, strikes)
    return Outcome(verdict, payment_id=payment_id, receipt_id=rid)
