"""Mijoz va admin uchun xabarlar."""
from typing import Dict, List, Optional

from config import ADMIN_CONTACT

_USER: Dict[str, Dict[str, str]] = {
    "uz": {
        "checking": "⏳ Chek tekshirilmoqda...",
        "approved": "✅ To'lov tasdiqlandi! {amount} so'm hisobingizga qo'shildi.",
        "approved_differs": "\n\nℹ️ Siz {claimed} so'm deb ko'rsatgan edingiz, chekdagi summa ({amount} so'm) qo'shildi.",
        "tax_receipt": ("❌ Bu to'lov cheki emas (do'kon/soliq cheki). Iltimos, to'lov tasdig'ini yuboring: "
                        "kvitansiya, «Muvaffaqiyatli» ekrani skrinshoti yoki PDF. Summa, sana, qabul qiluvchi "
                        "karta va ID ko'rinib turishi kerak."),
        "not_payment": ("❌ Bu to'lov cheki emasga o'xshaydi. Iltimos, to'lov tasdig'ini (kvitansiya yoki "
                        "«Muvaffaqiyatli» ekrani skrinshoti) to'liq ko'rinishda yuboring."),
        "unreadable": ("❌ Chekni o'qib bo'lmadi. Iltimos, aniqroq va to'liq yuboring (rasmni «fayl» sifatida "
                       "yuborsangiz sifati saqlanadi): summa, sana, qabul qiluvchi karta va ID ko'rinsin."),
        "too_little": ("❌ Bu chekda faqat summa va ilova nomi ko'rinyapti — bu to'lovni tasdiqlamaydi. "
                       "To'lov tarixidan (Click, Payme yoki bank ilovasi → «To'lovlar tarixi/Hisobotlar» → "
                       "shu o'tkazma → «Kvitansiya/To'lov ma'lumotlari») asl chekni oching va qayta yuboring: "
                       "sana, qabul qiluvchi karta va ID ko'rinsin."),
        "resend_btn": "🔄 Chekni qayta yuborish",
        "resend_prompt": ("📤 Chekni yuboring: rasm (skrinshot), PDF yoki DOCX. Eng yaxshisi — to'lov tarixidagi "
                          "asl kvitansiya (sana, qabul qiluvchi karta va ID ko'rinsin)."),
        "status_failed": "❌ Chekda to'lov muvaffaqiyatsiz ko'rinmoqda. To'lov o'tgach, uning chekini yuboring.",
        "status_pending": "⏳ Chekda to'lov hali yakunlanmagan ko'rinmoqda. To'lov o'tgach, chekni qayta yuboring.",
        "unsupported": ("❌ Bu fayl turini o'qib bo'lmadi. Iltimos, chekni rasm (skrinshot), PDF yoki DOCX "
                        "ko'rinishida yuboring."),
        "own_pending": "ℹ️ Bu chek allaqachon yuborilgan va tekshirilmoqda. Qayta yuborish shart emas.",
        "own_done": "ℹ️ Bu chek allaqachon qabul qilingan va summa hisobingizga qo'shilgan.",
        "duplicate": ("⚠️ Bu chek avval ishlatilgan. Takroriy chek bilan to'lov qabul qilinmaydi.\n\n"
                      "Agar xato bo'lgan deb o'ylasangiz, adminga murojaat qiling: " + ADMIN_CONTACT),
        "stale": ("⏳ Chek eski ko'rinadi ({age} oldin). Agar bu hozirgi to'lovingiz bo'lsa, adminga murojaat "
                  "qiling: " + ADMIN_CONTACT + "\nChek unga yuborildi."),
        "wrong_receiver": ("❌ Chekdagi qabul qiluvchi bizning kartalar emas. To'lovni ko'rsatilgan karta "
                           "raqamlariga o'tkazing. Savol bo'lsa, adminga murojaat qiling: " + ADMIN_CONTACT),
        "fake": ("⚠️ Chek tahrirlangan ko'rinadi, shuning uchun qabul qilinmadi. Agar chek haqiqiy bo'lsa, "
                 "to'lov tarixidan asl chekni qayta yuboring yoki adminga murojaat qiling: " + ADMIN_CONTACT),
        "review": ("📨 Chek adminga tekshirish uchun yuborildi. Tasdiqlangach hisobingizga qo'shiladi.\n"
                   "Savol bo'lsa: " + ADMIN_CONTACT),
    },
    "ru": {
        "checking": "⏳ Проверяю чек...",
        "approved": "✅ Платёж подтверждён! {amount} сум зачислено на ваш счёт.",
        "approved_differs": "\n\nℹ️ Вы указали {claimed} сум, зачислена сумма из чека ({amount} сум).",
        "tax_receipt": ("❌ Это не чек об оплате (кассовый/налоговый чек). Отправьте подтверждение перевода: "
                        "квитанцию, скриншот экрана «Успешно» или PDF. Должны быть видны сумма, дата, карта "
                        "получателя и ID."),
        "not_payment": ("❌ Это не похоже на чек об оплате. Отправьте подтверждение перевода (квитанцию или "
                        "скриншот экрана «Успешно») целиком."),
        "unreadable": ("❌ Не удалось прочитать чек. Отправьте чётче и полностью (картинку лучше отправить как "
                       "«файл»): сумма, дата, карта получателя и ID должны быть видны."),
        "too_little": ("❌ В этом чеке видны только сумма и название приложения — это не подтверждает платёж. "
                       "Откройте исходный чек в истории платежей (Click, Payme или банковское приложение → "
                       "«История платежей/Отчёты» → этот перевод → «Квитанция/Детали платежа») и отправьте заново: "
                       "должны быть видны дата, карта получателя и ID."),
        "resend_btn": "🔄 Отправить чек заново",
        "resend_prompt": ("📤 Отправьте чек: фото (скриншот), PDF или DOCX. Лучше всего — исходная квитанция из "
                          "истории платежей (видны дата, карта получателя и ID)."),
        "status_failed": "❌ В чеке платёж выглядит неуспешным. Отправьте чек после успешного перевода.",
        "status_pending": "⏳ В чеке платёж ещё не завершён. Отправьте чек после завершения перевода.",
        "unsupported": "❌ Не удалось прочитать этот тип файла. Отправьте чек как фото (скриншот), PDF или DOCX.",
        "own_pending": "ℹ️ Этот чек уже отправлен и проверяется. Повторно отправлять не нужно.",
        "own_done": "ℹ️ Этот чек уже принят, сумма зачислена на ваш счёт.",
        "duplicate": ("⚠️ Этот чек уже использовался. Повторный чек не принимается.\n\n"
                      "Если считаете, что это ошибка, обратитесь к админу: " + ADMIN_CONTACT),
        "stale": ("⏳ Чек выглядит старым ({age} назад). Если это ваш текущий платёж, обратитесь к админу: "
                  + ADMIN_CONTACT + "\nЧек ему отправлен."),
        "wrong_receiver": ("❌ Получатель в чеке — не наша карта. Переведите деньги на указанные номера карт. "
                           "Вопросы: " + ADMIN_CONTACT),
        "fake": ("⚠️ Чек выглядит изменённым, поэтому не принят. Если чек настоящий, отправьте исходный чек из "
                 "истории платежей или обратитесь к админу: " + ADMIN_CONTACT),
        "review": ("📨 Чек отправлен админу на проверку. После подтверждения сумма будет зачислена.\n"
                   "Вопросы: " + ADMIN_CONTACT),
    },
    "en": {
        "checking": "⏳ Checking the receipt...",
        "approved": "✅ Payment confirmed! {amount} som added to your balance.",
        "approved_differs": "\n\nℹ️ You entered {claimed} som; the receipt amount ({amount} som) was added.",
        "tax_receipt": ("❌ This is not a payment receipt (store/tax receipt). Please send the transfer "
                        "confirmation: a receipt, a «Success» screen screenshot or a PDF showing the amount, "
                        "date, receiver card and ID."),
        "not_payment": ("❌ This does not look like a payment receipt. Please send the full transfer "
                        "confirmation (receipt or «Success» screen screenshot)."),
        "unreadable": ("❌ The receipt could not be read. Please send a clearer, complete one (sending the "
                       "image as a «file» keeps quality): amount, date, receiver card and ID must be visible."),
        "too_little": ("❌ This receipt only shows the amount and the app name — that does not confirm the payment. "
                       "Open the original receipt in your payment history (Click, Payme or your bank app → "
                       "«Payment history/Reports» → this transfer → «Receipt/Payment details») and send it again: "
                       "the date, receiver card and ID must be visible."),
        "resend_btn": "🔄 Resend receipt",
        "resend_prompt": ("📤 Send the receipt: a photo (screenshot), PDF or DOCX. Best of all — the original "
                          "receipt from your payment history (date, receiver card and ID visible)."),
        "status_failed": "❌ The payment looks unsuccessful in this receipt. Send the receipt after a successful transfer.",
        "status_pending": "⏳ The payment looks unfinished in this receipt. Send it again once it completes.",
        "unsupported": "❌ This file type cannot be read. Please send the receipt as a photo (screenshot), PDF or DOCX.",
        "own_pending": "ℹ️ This receipt has already been sent and is being checked. No need to resend.",
        "own_done": "ℹ️ This receipt was already accepted and the amount is on your balance.",
        "duplicate": ("⚠️ This receipt was already used. Repeated receipts are not accepted.\n\n"
                      "If you think this is a mistake, contact the admin: " + ADMIN_CONTACT),
        "stale": ("⏳ The receipt looks old ({age} ago). If this is your current payment, contact the admin: "
                  + ADMIN_CONTACT + "\nThe receipt was forwarded to them."),
        "wrong_receiver": ("❌ The receiver in the receipt is not our card. Please transfer to the card numbers "
                           "shown. Questions: " + ADMIN_CONTACT),
        "fake": ("⚠️ The receipt looks edited, so it was not accepted. If it is genuine, send the original "
                 "receipt from your payment history or contact the admin: " + ADMIN_CONTACT),
        "review": ("📨 The receipt was sent to the admin for review. The amount will be added once approved.\n"
                   "Questions: " + ADMIN_CONTACT),
    },
}


def user_text(lang: str, key: str, **kw) -> str:
    table = _USER.get(lang) or _USER["ru"]          # qozoq tili ham rus matnidan foydalanadi
    return table[key].format(**kw) if kw else table[key]


# Admin kartasi uchun sabablar (adminga o'zbekcha)
REASONS: Dict[str, str] = {
    "tax_receipt": "Soliq/do'kon cheki — to'lov isboti emas",
    "too_little": "Chekda faqat summa va ilova nomi — qabul qiluvchi, sana, ID yo'q",
    "not_payment": "To'lov cheki emas",
    "unreadable": "Chekni o'qib bo'lmadi",
    "status_failed": "Chekda to'lov muvaffaqiyatsiz",
    "status_pending": "Chekda to'lov yakunlanmagan",
    "currency": "Valyuta so'm emas",
    "duplicate_id": "❗ ID avval ishlatilgan (takroriy chek)",
    "duplicate_cmp": "❗ Summa+vaqt+yuboruvchi+qabul qiluvchi avval ishlatilgan (ID o'zgartirilgan bo'lishi mumkin)",
    "duplicate_file": "❗ Aynan shu fayl avval yuborilgan",
    "duplicate_scr": "❗ Skrinshot belgisi (soat+batareya+ilova+summa) avval ishlatilgan — ID tahrirlangan bo'lishi mumkin",
    "possible_duplicate": "Shunga o'xshash chek avval bor (summa va vaqt mos) — tekshiring",
    "wrong_receiver": "Qabul qiluvchi karta bizniki emas",
    "receiver_by_name": "Karta oxiri ko'rinmaydi, faqat ism mos",
    "no_receiver": "Qabul qiluvchi aniqlanmadi",
    "no_date": "Chekda sana yo'q (faqat telefon soati)",
    "no_time": "Chek vaqtini aniqlab bo'lmadi",
    "stale": "Chek eski",
    "future": "Chek vaqti kelajakda",
    "screenshot_old": "Skrinshot soati hozirgi vaqtdan juda farq qiladi",
    "clock_mismatch": "Skrinshot soati chek vaqtiga mos emas",
    "tamper_high": "Tahrirlanganga o'xshaydi (AI)",
    "tamper_meta": "Fayl metama'lumotida tahrirlovchi dastur izi",
    "cropped": "Chek qirqilgan",
    "no_amount": "Summa o'qilmadi",
    "tiny_amount": "Summa juda kichik",
    "over_limit": "Summa avto-tasdiq chegarasidan katta",
    "over_limit_noid": "ID'siz chek uchun summa katta",
    "no_unique_key": "Chekni takrorlanishdan tekshirib bo'lmaydi (ID ham, to'liq ma'lumot ham yo'q)",
    "low_confidence": "AI o'qishga ishonchi past",
    "verify_mismatch": "Ikkinchi o'qish natijasi mos kelmadi",
    "verify_failed": "Ikkinchi o'qish bajarilmadi",
    "shadow_mode": "Soya rejimi: avto-tasdiq o'chiq",
    "amount_differs": "Chek summasi mijoz ko'rsatganidan farq qiladi",
    "own_pending": "Mijoz o'zining tekshirilayotgan chekini qayta yubordi",
    "own_done": "Mijoz o'zining allaqachon qabul qilingan chekini qayta yubordi",
    "race": "Bir vaqtda kelgan takroriy chek",
    "ai_error": "AI ishlamadi — qo'lda tekshiring",
}

VERDICT_LABEL = {
    "auto": "✅ AVTOMATIK TASDIQLANDI",
    "review": "🟡 TEKSHIRISH KERAK",
    "duplicate": "🔴 TAKRORIY CHEK",
    "wrong_receiver": "🟠 QABUL QILUVCHI BOSHQA",
    "fake": "🔴 TAHRIRLANGAN CHEK",
    "not_receipt": "ℹ️ CHEK EMAS (qayta so'raldi)",
    "own_pending": "ℹ️ Qayta yuborilgan chek",
    "ai_error": "⚪ AI ishlamadi",
}
