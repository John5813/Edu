"""Huquqiy sahifalar: /oferta, /tolov-va-qaytarish, /xavfsizlik (ruschasi — /ru/... da).

To'lov tizimlari (Uzum Bank, Click, Payme) saytda ommaviy oferta, to'lov va qaytarish tartibi hamda
firibgarlik xavfini cheklash choralari ochiq turishini talab qiladi. Matn shu yerda, rekvizitlar `.env`
dan (`config.LEGAL_*`) olinadi — bo'sh qator sahifada ko'rsatilmaydi.

Bo'lim: (sarlavha, [blok, ...]); blok — paragraf (str) yoki ro'yxat (tuple). Matndagi {min}, {max},
{contact}, {site} va {date} sahifa chizilganda to'ldiriladi.
"""
import html
import json
import logging

from aiohttp import web

import config

logger = logging.getLogger(__name__)

OFERTA = {
    "title": "Ommaviy oferta — Edufayl",
    "h1": "Ommaviy oferta",
    "lead": "Edufayl sayti ({site}) va Telegram boti orqali xizmat ko'rsatish shartnomasi. "
            "Hisobni to'ldirish yoki xizmatga buyurtma berish ushbu shartlarga to'liq rozilik bildiradi.",
    "sections": (
        ("1. Umumiy qoidalar", (
            "1.1. Ushbu hujjat O'zbekiston Respublikasi Fuqarolik kodeksining 367–370-moddalariga muvofiq "
            "ommaviy oferta hisoblanadi. Unda Ijrochi (pastdagi rekvizitlarda ko'rsatilgan) bilan xizmatdan "
            "foydalanuvchi har qanday shaxs (Buyurtmachi) o'rtasidagi munosabatlar belgilanadi.",
            "1.2. Buyurtmachi hisobini to'ldirgan yoki xizmatga buyurtma bergan paytdan boshlab oferta qabul "
            "qilingan (aksept) hisoblanadi va shartnoma tuzilgan sanaladi.",
            "1.3. Ijrochi oferta matnini o'zgartirishi mumkin. Yangi tahrir saytga joylangan paytdan kuchga "
            "kiradi va undan keyingi to'lov va buyurtmalarga tatbiq etiladi.",
        )),
        ("2. Shartnoma predmeti", (
            "2.1. Ijrochi sun'iy intellekt yordamida o'quv va ilmiy ishlarni elektron fayl ko'rinishida "
            "tayyorlash xizmatini ko'rsatadi:",
            ("taqdimot (PPTX), mustaqil ish, referat, kurs ishi, maqola, tezis, diplom va bitiruv ishi (DOCX);",
             "hujjat tarjimasi, formatlash va boshqa yordamchi xizmatlar;",
             "saytdagi do'kondan tayyor ishlarni sotish."),
            "2.2. Xizmatlar raqamli ko'rinishda — saytda yuklab olish yoki Telegram bot orqali fayl yuborish "
            "yo'li bilan ko'rsatiladi. Moddiy tovar yetkazib berilmaydi.",
            "2.3. Tayyorlangan ish Buyurtmachining shaxsiy foydalanishi uchun namuna va yordamchi material "
            "hisoblanadi. Uni o'quv muassasasi talablariga moslashtirish va undan to'g'ri foydalanish "
            "Buyurtmachining zimmasida.",
        )),
        ("3. Xizmat narxi va hisob", (
            "3.1. Har bir xizmat narxi buyurtma berishdan oldin saytda yoki botda so'mda aniq ko'rsatiladi.",
            "3.2. Xizmatlar Buyurtmachining ichki hisobidagi (balansdagi) mablag'dan to'lanadi. Hisob "
            "Buyurtmachining Telegram ID'siga bog'langan.",
            "3.3. Hisobni to'ldirish usullari va tartibi «To'lov va qaytarish» sahifasida "
            "({site}/tolov-va-qaytarish) bayon etilgan. Bir martalik to'lov {min} so'mdan {max} so'mgacha.",
            "3.4. Hisobdagi mablag' faqat Ijrochi xizmatlari uchun ishlatiladi, uni boshqa foydalanuvchiga "
            "o'tkazib bo'lmaydi va unga foiz hisoblanmaydi.",
        )),
        ("4. Tomonlarning huquq va majburiyatlari", (
            "4.1. Ijrochi:",
            ("buyurtmani to'lov qabul qilingach, odatda bir necha daqiqa ichida bajaradi;",
             "texnik nosozlik tufayli xizmat ko'rsatilmasa, mablag'ni hisobga qaytaradi;",
             "Buyurtmachining shaxsiy ma'lumotlarini maxfiy saqlaydi;",
             "firibgarlikka shubha bo'lsa, hisobni vaqtincha cheklash va qo'shimcha tekshiruv o'tkazish huquqiga ega."),
            "4.2. Buyurtmachi:",
            ("buyurtma shartlarini (mavzu, til, hajm) to'g'ri kiritadi;",
             "faqat o'ziga tegishli bank kartasidan to'laydi;",
             "xizmatdan qonunga zid maqsadlarda foydalanmaydi;",
             "kamchilik aniqlansa, 3 kun ichida murojaat qilish huquqiga ega."),
        )),
        ("5. Qaytarish", (
            "5.1. Hisobdagi ishlatilmagan mablag' Buyurtmachining so'rovi bo'yicha qaytariladi. Ko'rsatilgan "
            "xizmat uchun yechilgan mablag' qaytarilmaydi, 5.2-bandda ko'rsatilgan holatlar bundan mustasno.",
            "5.2. Xizmat ko'rsatilmasa, texnik xato bilan bajarilsa yoki natija buyurtma shartlariga mos kelmasa, "
            "Buyurtmachi 3 kun ichida murojaat qilib, ishni bepul qayta tayyorlatishi yoki uning narxini hisobga "
            "qaytarishni tanlashi mumkin.",
            "5.3. Qaytarish muddati va tartibi «To'lov va qaytarish» sahifasida batafsil yozilgan.",
        )),
        ("6. Javobgarlik", (
            "6.1. Ijrochi to'lov tizimlari, bank, internet provayder yoki Telegram tomonidagi uzilishlar uchun "
            "javobgar emas, lekin ular tufayli ko'rsatilmagan xizmat uchun mablag'ni hisobga qaytaradi.",
            "6.2. Ijrochining javobgarligi Buyurtmachi tegishli xizmat uchun to'lagan summa bilan cheklanadi.",
            "6.3. Buyurtmachi tayyor ishni o'quv muassasasiga topshirish va undan foydalanish oqibatlari uchun "
            "o'zi javobgar.",
        )),
        ("7. Shaxsiy ma'lumotlar", (
            "7.1. Ijrochi xizmat ko'rsatish uchun zarur ma'lumotlarni — Telegram ID, ism, foydalanuvchi nomi, "
            "buyurtmalar va to'lovlar tarixini — qayta ishlaydi. Bank kartasi ma'lumotlari Ijrochiga "
            "berilmaydi va saqlanmaydi: to'lov bank va to'lov tizimi sahifasida amalga oshiriladi.",
            "7.2. Ma'lumotlar uchinchi shaxslarga faqat qonunda belgilangan hollarda beriladi.",
        )),
        ("8. Nizolarni hal qilish", (
            "8.1. Nizolar avvalo muzokara yo'li bilan hal qilinadi. Buyurtmachining yozma murojaatiga 10 ish kuni "
            "ichida javob beriladi.",
            "8.2. Kelishuvga erishilmasa, nizo O'zbekiston Respublikasi qonunchiligiga muvofiq sudda ko'riladi.",
        )),
        ("9. Amal qilish muddati", (
            "9.1. Oferta {date} dan kuchga kiradi va muddatsiz amal qiladi.",
        )),
    ),
}

TOLOV = {
    "title": "To'lov va qaytarish tartibi — Edufayl",
    "h1": "To'lov va qaytarish tartibi",
    "lead": "Hisobni qanday to'ldirish, pul qachon tushishi va qanday holatlarda qaytarilishi haqida.",
    "sections": (
        ("To'lov qanday ishlaydi", (
            "Edufayl'da xizmatlar ichki hisob (balans) orqali to'lanadi. Avval hisobni to'ldirasiz, keyin "
            "buyurtma berasiz — xizmat narxi balansdan yechiladi. Narx buyurtma berishdan oldin ko'rsatiladi.",
            "Hisob Telegram ID'ingizga bog'langan. Uni botda yoki saytdagi «Hamyon» bo'limida ko'rasiz.",
            "Bir martalik to'lov: kamida {min} so'm, ko'pi bilan {max} so'm.",
        )),
        ("To'lov usullari", (
            ("Uzum Bank — botdagi yoki saytdagi «Uzum Bank orqali» tugmasi Uzum ilovasini ochadi, Telegram ID va "
             "summa avtomatik to'ldiriladi. Ilovada to'lovni tasdiqlaysiz — summa darhol hisobga tushadi. "
             "Uzum ilovasida xizmatni qidirib, Telegram ID'ingizni qo'lda kiritib ham to'lash mumkin.",
             "Click — «Click orqali» tugmasi my.click.uz to'lov sahifasini ochadi. To'lov o'tishi bilan summa "
             "avtomatik hisobga tushadi.",
             "Payme — «Payme orqali» tugmasi Payme to'lov sahifasini ochadi. To'lov o'tishi bilan summa "
             "avtomatik hisobga tushadi.",
             "Kartaga o'tkazma — ko'rsatilgan kartaga pul o'tkazib, to'lov chekini botga yoki saytga yuklaysiz. "
             "Chek tekshirilgach summa hisobga qo'shiladi; admin tasdig'i kerak bo'lsa, natija Telegramga keladi."),
            "Karta ma'lumotlari faqat bank va to'lov tizimi sahifasida kiritiladi. Edufayl karta raqami, "
            "amal qilish muddati yoki SMS-kodni so'ramaydi va saqlamaydi.",
        )),
        ("Pul qachon tushadi", (
            ("Uzum Bank, Click, Payme — to'lov tasdiqlangach darhol (odatda bir necha soniyada). Botdan "
             "«to'lov qabul qilindi» xabari keladi.",
             "Kartaga o'tkazma — chek tekshirilgach. Odatda bir necha daqiqada, ish vaqtidan tashqari biroz "
             "kechroq."),
            "Pul kartadan yechilgan, lekin 30 daqiqa ichida hisobga tushmagan bo'lsa, {contact} ga to'lov cheki "
             "bilan yozing — tekshirib, hisobga qo'shamiz yoki pulni qaytaramiz.",
        )),
        ("Qaytarish tartibi", (
            ("Ishlatilmagan mablag'. Hisobdagi ishlatilmagan summani istalgan vaqtda qaytarishni so'rashingiz "
             "mumkin. Pul 10 ish kuni ichida to'lov qilingan kartaga yoki o'sha to'lov tizimi orqali qaytariladi.",
             "Ishlatilgan mablag'. Ko'rsatilgan xizmat (tayyorlangan va berilgan fayl) uchun yechilgan summa "
             "qaytarilmaydi — quyidagi holatlar bundan mustasno.",
             "Sifatsiz natija. Fayl ochilmasa, buyurtma shartlariga (mavzu, til, hajm) mos kelmasa yoki texnik xato "
             "bilan tayyorlangan bo'lsa, 3 kun ichida murojaat qiling — ish bepul qayta tayyorlanadi yoki uning "
             "narxi hisobingizga qaytariladi (tanlov sizda).",
             "Xizmat ko'rsatilmagan. Texnik nosozlik tufayli buyurtma bajarilmasa, summa hisobga avtomatik "
             "qaytariladi.",
             "Ikki marta yechilgan yoki xato to'lov. Summa to'liq qaytariladi."),
        )),
        ("Qaytarishni qanday so'rash mumkin", (
            ("{contact} ga Telegram orqali yozing yoki pastdagi aloqa ma'lumotlaridan foydalaning;",
             "Telegram ID'ingizni, summani, to'lov sanasi va usulini ko'rsating, iloji bo'lsa to'lov chekini ilova qiling;",
             "so'rov 1–3 ish kunida ko'rib chiqiladi, pul 10 ish kuni ichida qaytariladi."),
            "Bank yoki to'lov tizimi tomonidan qaytarish muddati ularning qoidalariga bog'liq bo'lishi mumkin.",
        )),
    ),
}

XAVFSIZLIK = {
    "title": "To'lov xavfsizligi va firibgarlikka qarshi choralar — Edufayl",
    "h1": "To'lov xavfsizligi va firibgarlikka qarshi choralar",
    "lead": "Firibgarlik operatsiyalari xavfini cheklash va nazorat qilish uchun Edufayl va hamkor banklar "
            "qo'llaydigan choralar.",
    "sections": (
        ("To'lov bank tomonida amalga oshiriladi", (
            "Barcha onlayn to'lovlar (Uzum Bank, Click, Payme) shu tizimlarning o'z ilovasi yoki sahifasida "
            "amalga oshiriladi. Karta ma'lumotlari Edufayl serverlariga kelmaydi va saqlanmaydi.",
            "To'lov bank va to'lov tizimining himoya vositalari bilan tasdiqlanadi: SMS-kod, ilovadagi "
            "tasdiqlash va bankning firibgarlikka qarshi monitoring tizimi. Bank shubhali operatsiyani "
            "rad etishi yoki to'xtatib turishi mumkin.",
        )),
        ("Edufayl tomonidagi cheklovlar", (
            ("Bir martalik to'lov summasi cheklangan: kamida {min} so'm, ko'pi bilan {max} so'm.",
             "Har bir to'lov aniq foydalanuvchi hisobiga (Telegram ID) bog'lanadi; hisob topilmasa, to'lov qabul "
             "qilinmaydi.",
             "To'lov tizimlarining har bir so'rovi login-parol yoki elektron imzo bilan tekshiriladi; "
             "tekshiruvdan o'tmagan so'rov rad etiladi.",
             "Bir to'lov ikki marta hisobga tushmaydi: takroriy so'rovlar aniqlanadi, summa qayta qo'shilmaydi.",
             "Tasdiqlanmagan to'lov avtomatik bekor qilinadi: Uzum Bank'da 30 daqiqadan, Payme'da 12 soatdan keyin.",
             "Uzum Bank yoki Payme to'lovni bekor qilsa (qaytarsa), summa hisobdan avtomatik yechiladi.",
             "Saytda to'lov tugmalarini juda tez-tez bosish cheklangan (daqiqasiga 10 marta).",
             "Kartaga o'tkazma cheklari tekshiriladi: sana, summa, qabul qiluvchi karta va operatsiya raqami. "
             "Eski, takroriy yoki tahrirlangan cheklar qabul qilinmaydi; katta summalar admin tomonidan "
             "qo'lda tasdiqlanadi."),
        )),
        ("Nazorat", (
            ("Har bir onlayn to'lov haqida administratorga darhol xabar boradi.",
             "To'lovlar va qaytarishlar tarixi saqlanadi va muntazam tekshiriladi.",
             "Firibgarlikka shubha bo'lsa, hisob vaqtincha cheklanadi, to'lov bank bilan birga tekshiriladi va "
             "kerak bo'lsa bankka ma'lumot beriladi. Bankning shubhali operatsiyalar bo'yicha so'rovlariga "
             "shartnomada belgilangan muddatda javob beriladi."),
        )),
        ("Foydalanuvchi uchun maslahatlar", (
            ("Edufayl hech qachon karta raqami, amal qilish muddati, CVV yoki SMS-kodni so'ramaydi. Bunday "
             "so'rov kelsa — bu firibgarlar.",
             "Faqat o'zingizga tegishli kartadan to'lang.",
             "To'lovni faqat rasmiy bot (@Edufayl_bot) yoki {site} saytidagi tugmalar orqali qiling.",
             "Kartangizdan siz qilmagan to'lov o'tgan bo'lsa, darhol bankingizga va {contact} ga xabar bering."),
        )),
    ),
}

OFERTA_RU = {
    "title": "Публичная оферта — Edufayl",
    "h1": "Публичная оферта",
    "lead": "Договор оказания услуг через сайт Edufayl ({site}) и Telegram-бот. "
            "Пополнение счёта или оформление заказа означает полное согласие с настоящими условиями.",
    "sections": (
        ("1. Общие положения", (
            "1.1. Настоящий документ в соответствии со статьями 367–370 Гражданского кодекса Республики Узбекистан "
            "является публичной офертой. Он определяет отношения между Исполнителем (указан в реквизитах ниже) и "
            "любым лицом, пользующимся услугами (Заказчиком).",
            "1.2. Оферта считается принятой (акцептованной), а договор заключённым с момента пополнения "
            "Заказчиком счёта или оформления заказа.",
            "1.3. Исполнитель вправе изменять текст оферты. Новая редакция вступает в силу с момента размещения "
            "на сайте и применяется к последующим платежам и заказам.",
        )),
        ("2. Предмет договора", (
            "2.1. Исполнитель оказывает услуги по подготовке учебных и научных работ в электронном виде "
            "с помощью искусственного интеллекта:",
            ("презентации (PPTX), самостоятельные работы, рефераты, курсовые, статьи, тезисы, дипломные и "
             "выпускные работы (DOCX);",
             "перевод документов, оформление и другие вспомогательные услуги;",
             "продажа готовых работ в магазине на сайте."),
            "2.2. Услуги оказываются в цифровом виде — загрузкой файла на сайте или отправкой через Telegram-бот. "
            "Материальные товары не поставляются.",
            "2.3. Подготовленная работа является образцом и вспомогательным материалом для личного использования "
            "Заказчиком. Адаптация её к требованиям учебного заведения и правомерное использование лежат на "
            "Заказчике.",
        )),
        ("3. Стоимость услуг и счёт", (
            "3.1. Стоимость каждой услуги указывается в сумах на сайте или в боте до оформления заказа.",
            "3.2. Услуги оплачиваются со внутреннего счёта (баланса) Заказчика. Счёт привязан к Telegram ID "
            "Заказчика.",
            "3.3. Способы и порядок пополнения счёта описаны на странице «Оплата и возврат» "
            "({site}/ru/tolov-va-qaytarish). Разовый платёж — от {min} до {max} сум.",
            "3.4. Средства на счёте используются только для оплаты услуг Исполнителя, не передаются другим "
            "пользователям, проценты на них не начисляются.",
        )),
        ("4. Права и обязанности сторон", (
            "4.1. Исполнитель:",
            ("выполняет заказ после поступления оплаты, как правило в течение нескольких минут;",
             "возвращает средства на счёт, если услуга не оказана из-за технического сбоя;",
             "сохраняет конфиденциальность персональных данных Заказчика;",
             "вправе временно ограничить счёт и провести дополнительную проверку при подозрении на мошенничество."),
            "4.2. Заказчик:",
            ("корректно указывает условия заказа (тема, язык, объём);",
             "оплачивает только с принадлежащей ему банковской карты;",
             "не использует услуги в противоправных целях;",
             "вправе обратиться в течение 3 дней при обнаружении недостатков."),
        )),
        ("5. Возврат", (
            "5.1. Неиспользованные средства на счёте возвращаются по запросу Заказчика. Средства, списанные за "
            "оказанную услугу, не возвращаются, за исключением случаев, указанных в п. 5.2.",
            "5.2. Если услуга не оказана, выполнена с технической ошибкой или результат не соответствует условиям "
            "заказа, Заказчик в течение 3 дней может обратиться и выбрать бесплатную повторную подготовку работы "
            "либо возврат её стоимости на счёт.",
            "5.3. Сроки и порядок возврата подробно описаны на странице «Оплата и возврат».",
        )),
        ("6. Ответственность", (
            "6.1. Исполнитель не отвечает за сбои на стороне платёжных систем, банка, интернет-провайдера или "
            "Telegram, но возвращает на счёт средства за не оказанную по этой причине услугу.",
            "6.2. Ответственность Исполнителя ограничена суммой, уплаченной Заказчиком за соответствующую услугу.",
            "6.3. Заказчик самостоятельно отвечает за сдачу готовой работы в учебное заведение и последствия её "
            "использования.",
        )),
        ("7. Персональные данные", (
            "7.1. Исполнитель обрабатывает данные, необходимые для оказания услуг: Telegram ID, имя, имя "
            "пользователя, история заказов и платежей. Данные банковской карты Исполнителю не передаются и не "
            "хранятся: оплата производится на странице банка и платёжной системы.",
            "7.2. Данные передаются третьим лицам только в случаях, предусмотренных законом.",
        )),
        ("8. Разрешение споров", (
            "8.1. Споры решаются прежде всего путём переговоров. Письменное обращение Заказчика рассматривается в "
            "течение 10 рабочих дней.",
            "8.2. При недостижении согласия спор рассматривается в суде в соответствии с законодательством "
            "Республики Узбекистан.",
        )),
        ("9. Срок действия", (
            "9.1. Оферта вступает в силу с {date} и действует бессрочно.",
        )),
    ),
}

TOLOV_RU = {
    "title": "Порядок оплаты и возврата — Edufayl",
    "h1": "Порядок оплаты и возврата",
    "lead": "Как пополнить счёт, когда поступают деньги и в каких случаях они возвращаются.",
    "sections": (
        ("Как работает оплата", (
            "В Edufayl услуги оплачиваются через внутренний счёт (баланс). Сначала вы пополняете счёт, затем "
            "оформляете заказ — стоимость услуги списывается с баланса. Цена показывается до оформления заказа.",
            "Счёт привязан к вашему Telegram ID. Его можно увидеть в боте или в разделе «Кошелёк» на сайте.",
            "Разовый платёж: не менее {min} сум и не более {max} сум.",
        )),
        ("Способы оплаты", (
            ("Uzum Bank — кнопка «Через Uzum Bank» в боте или на сайте открывает приложение Uzum, Telegram ID и "
             "сумма заполняются автоматически. Вы подтверждаете платёж в приложении — сумма сразу зачисляется на "
             "счёт. Можно также найти сервис в приложении Uzum и ввести Telegram ID вручную.",
             "Click — кнопка «Через Click» открывает страницу оплаты my.click.uz. После оплаты сумма "
             "автоматически зачисляется на счёт.",
             "Payme — кнопка «Через Payme» открывает страницу оплаты Payme. После оплаты сумма автоматически "
             "зачисляется на счёт.",
             "Перевод на карту — вы переводите деньги на указанную карту и загружаете чек в бот или на сайт. "
             "После проверки чека сумма зачисляется на счёт; если требуется подтверждение администратора, "
             "результат придёт в Telegram."),
            "Данные карты вводятся только на странице банка и платёжной системы. Edufayl не запрашивает и не "
            "хранит номер карты, срок действия или SMS-код.",
        )),
        ("Когда поступают деньги", (
            ("Uzum Bank, Click, Payme — сразу после подтверждения платежа (обычно за несколько секунд). Бот "
             "пришлёт сообщение «оплата принята».",
             "Перевод на карту — после проверки чека. Обычно за несколько минут, в нерабочее время немного дольше."),
            "Если деньги списаны с карты, но не поступили на счёт в течение 30 минут, напишите {contact} и "
            "приложите чек — мы проверим и зачислим сумму или вернём деньги.",
        )),
        ("Порядок возврата", (
            ("Неиспользованные средства. Неиспользованную сумму на счёте можно вернуть в любое время. Деньги "
             "возвращаются в течение 10 рабочих дней на карту, с которой была оплата, или через ту же платёжную "
             "систему.",
             "Использованные средства. Сумма, списанная за оказанную услугу (подготовленный и выданный файл), "
             "не возвращается — за исключением случаев ниже.",
             "Некачественный результат. Если файл не открывается, не соответствует условиям заказа (тема, язык, "
             "объём) или подготовлен с технической ошибкой, обратитесь в течение 3 дней — работа будет бесплатно "
             "подготовлена заново или её стоимость вернётся на счёт (на ваш выбор).",
             "Услуга не оказана. Если заказ не выполнен из-за технического сбоя, сумма автоматически "
             "возвращается на счёт.",
             "Двойное списание или ошибочный платёж. Сумма возвращается полностью."),
        )),
        ("Как запросить возврат", (
            ("напишите {contact} в Telegram или воспользуйтесь контактами ниже;",
             "укажите Telegram ID, сумму, дату и способ оплаты, по возможности приложите чек;",
             "запрос рассматривается 1–3 рабочих дня, деньги возвращаются в течение 10 рабочих дней."),
            "Сроки возврата на стороне банка или платёжной системы могут зависеть от их правил.",
        )),
    ),
}

XAVFSIZLIK_RU = {
    "title": "Безопасность платежей и меры против мошенничества — Edufayl",
    "h1": "Безопасность платежей и меры против мошенничества",
    "lead": "Меры, применяемые Edufayl и банками-партнёрами для ограничения и контроля рисков мошеннических "
            "операций.",
    "sections": (
        ("Оплата проводится на стороне банка", (
            "Все онлайн-платежи (Uzum Bank, Click, Payme) проводятся в приложении или на странице этих систем. "
            "Данные карты не поступают на серверы Edufayl и не хранятся.",
            "Платёж подтверждается средствами защиты банка и платёжной системы: SMS-код, подтверждение в "
            "приложении и система мониторинга мошенничества банка. Банк может отклонить или приостановить "
            "подозрительную операцию.",
        )),
        ("Ограничения на стороне Edufayl", (
            ("Сумма разового платежа ограничена: не менее {min} сум и не более {max} сум.",
             "Каждый платёж привязывается к конкретному счёту пользователя (Telegram ID); если счёт не найден, "
             "платёж не принимается.",
             "Каждый запрос платёжной системы проверяется логином и паролем или электронной подписью; запрос, "
             "не прошедший проверку, отклоняется.",
             "Один платёж не зачисляется дважды: повторные запросы распознаются, сумма повторно не начисляется.",
             "Неподтверждённый платёж отменяется автоматически: в Uzum Bank через 30 минут, в Payme через 12 часов.",
             "Если Uzum Bank или Payme отменяет (возвращает) платёж, сумма автоматически списывается со счёта.",
             "На сайте ограничена частота нажатия кнопок оплаты (не более 10 раз в минуту).",
             "Чеки переводов на карту проверяются: дата, сумма, карта получателя и номер операции. Старые, "
             "повторные или отредактированные чеки не принимаются; крупные суммы подтверждаются администратором "
             "вручную."),
        )),
        ("Контроль", (
            ("О каждом онлайн-платеже администратору сразу приходит уведомление.",
             "История платежей и возвратов хранится и регулярно проверяется.",
             "При подозрении на мошенничество счёт временно ограничивается, платёж проверяется совместно с банком "
             "и при необходимости информация передаётся банку. На запросы банка по подозрительным операциям "
             "ответ даётся в сроки, установленные договором."),
        )),
        ("Советы пользователю", (
            ("Edufayl никогда не запрашивает номер карты, срок действия, CVV или SMS-код. Если вас об этом "
             "просят — это мошенники.",
             "Оплачивайте только со своей карты.",
             "Оплачивайте только через официальный бот (@Edufayl_bot) или кнопки на сайте {site}.",
             "Если с вашей карты прошёл платёж, который вы не совершали, сразу сообщите в свой банк и {contact}."),
        )),
    ),
}

PAGES = {"oferta": OFERTA, "tolov-va-qaytarish": TOLOV, "xavfsizlik": XAVFSIZLIK}
PAGES_RU = {"oferta": OFERTA_RU, "tolov-va-qaytarish": TOLOV_RU, "xavfsizlik": XAVFSIZLIK_RU}
LINKS = (("oferta", "Ommaviy oferta"), ("tolov-va-qaytarish", "To'lov va qaytarish"),
         ("xavfsizlik", "To'lov xavfsizligi"))
LINKS_RU = (("oferta", "Публичная оферта"), ("tolov-va-qaytarish", "Оплата и возврат"),
            ("xavfsizlik", "Безопасность платежей"))

# Til bo'yicha sahifa matnlari: sahifalar, havolalar, sahifa qolipidagi yozuvlar.
LANGS = {
    "uz": {"pages": PAGES, "links": LINKS, "prefix": "", "home": "Bosh sahifa", "nav": "Huquqiy ma'lumotlar",
           "req_title": "Ijrochi rekvizitlari va aloqa", "switch": ("ru", "Русский"),
           "req": ("Ijrochi", "JShShIR (STIR)", "Davlat ro'yxatidan o'tgan", "Manzil", "Bank rekvizitlari", "Telefon",
                   "E-pochta", "Telegram", "Sayt")},
    "ru": {"pages": PAGES_RU, "links": LINKS_RU, "prefix": "/ru", "home": "Главная", "nav": "Правовая информация",
           "req_title": "Реквизиты исполнителя и контакты", "switch": ("uz", "O'zbekcha"),
           "req": ("Исполнитель", "ПИНФЛ (ИНН)", "Государственная регистрация", "Адрес", "Банковские реквизиты",
                   "Телефон", "E-mail", "Telegram", "Сайт")},
}

TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{canonical}">
<link rel="alternate" hreflang="uz" href="{href_uz}">
<link rel="alternate" hreflang="ru" href="{href_ru}">
<link rel="icon" href="/static/logo.jpg">
<link rel="stylesheet" href="/shop/style.css">
<script type="application/ld+json">{ld}</script>
<style>
.legal .about{{margin-top:16px}}
.legal .about p{{margin:8px 0;line-height:1.6}}
.legal .about ul{{margin:8px 0 8px 20px;font-size:15px;line-height:1.6;max-width:80ch}}
.legal .about li{{margin:4px 0}}
.legal .req dt{{color:var(--muted);font-size:13px;margin-top:8px}}
.legal .req dd{{font-size:15px;margin:2px 0 0}}
.legal .tabs{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 4px}}
.legal .tabs a{{padding:6px 12px;border:1px solid var(--line);border-radius:999px;text-decoration:none;
  color:var(--ink,inherit);font-size:14px}}
.legal .tabs a[aria-current]{{border-color:var(--accent);color:var(--accent);font-weight:600}}
.legal .tabs .lang{{margin-left:auto}}
</style>
</head>
<body>
<header>
  <div class="wrap head-in">
    <a class="logo" href="/" aria-label="Edufayl"><img src="/static/logo.jpg" alt="Edufayl" width="44" height="44"></a>
    <a class="create" href="/">{home}</a>
  </div>
</header>
<main class="wrap landing legal">
  <nav class="crumbs"><a href="/">Edufayl</a> / {h1}</nav>
  <nav class="tabs" aria-label="{nav}">{tabs}</nav>
  <section class="hero-l"><h1>{h1}</h1><p class="lead">{lead}</p></section>
  {sections}
  <section class="about"><h2>{req_title}</h2><dl class="req">{requisites}</dl></section>
</main>
<footer class="wrap">{footer}</footer>
</body>
</html>
"""


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _values(origin: str) -> dict:
    from services import uzum_pay

    contact = config.ADMIN_CONTACT or "@Edufayl_bot"
    return {"min": f"{uzum_pay.MIN_AMOUNT:,}".replace(",", " "), "max": f"{uzum_pay.MAX_AMOUNT:,}".replace(",", " "),
            "contact": contact, "site": origin.split("://", 1)[-1] or "edufayl.org", "date": config.LEGAL_DATE}


def requisites(lang: str = "uz") -> list:
    """(nomi, qiymati) — faqat to'ldirilganlari."""
    values = (config.LEGAL_NAME, config.LEGAL_STIR, config.LEGAL_REG, config.LEGAL_ADDRESS, config.LEGAL_BANK,
              config.LEGAL_PHONE, config.LEGAL_EMAIL, config.ADMIN_CONTACT, "edufayl.org")
    return [(name, value) for name, value in zip(LANGS[lang]["req"], values) if value]


def footer_links(lang: str = "uz") -> str:
    """Boshqa sahifalar pastiga qo'yiladigan havolalar."""
    conf = LANGS[lang]
    return " · ".join(f'<a href="{conf["prefix"]}/{slug}">{_esc(name)}</a>' for slug, name in conf["links"])


def _block(block, values: dict) -> str:
    if isinstance(block, tuple):
        return "<ul>" + "".join(f"<li>{_esc(item.format(**values))}</li>" for item in block) + "</ul>"
    return f"<p>{_esc(block.format(**values))}</p>"


def render(slug: str, origin: str, lang: str = "uz") -> str:
    conf = LANGS[lang]
    page = conf["pages"][slug]
    values = _values(origin)
    canonical = f"{origin}{conf['prefix']}/{slug}"
    lead = page["lead"].format(**values)
    sections = "".join(
        f'<section class="about"><h2>{_esc(heading)}</h2>{"".join(_block(b, values) for b in blocks)}</section>'
        for heading, blocks in page["sections"])
    other, other_name = conf["switch"]
    tabs = "".join(f'<a href="{conf["prefix"]}/{s}"{" aria-current=\"page\"" if s == slug else ""}>{_esc(name)}</a>'
                   for s, name in conf["links"])
    tabs += f'<a class="lang" href="{LANGS[other]["prefix"]}/{slug}" hreflang="{other}">{_esc(other_name)}</a>'
    reqs = "".join(f"<dt>{_esc(name)}</dt><dd>{_esc(value)}</dd>" for name, value in requisites(lang))
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": page["h1"], "url": canonical,
          "inLanguage": lang, "description": lead,
          "publisher": {"@type": "Organization", "name": "Edufayl", "url": origin + "/"}}
    return TEMPLATE.format(
        lang=lang, title=_esc(page["title"]), desc=_esc(lead[:300]), canonical=_esc(canonical),
        href_uz=_esc(f"{origin}/{slug}"), href_ru=_esc(f"{origin}/ru/{slug}"),
        ld=json.dumps(ld, ensure_ascii=False).replace("</", "<\\/"), home=_esc(conf["home"]), nav=_esc(conf["nav"]),
        h1=_esc(page["h1"]), lead=_esc(lead), tabs=tabs, sections=sections, req_title=_esc(conf["req_title"]),
        requisites=reqs, footer=f"Edufayl — edufayl.org · {footer_links(lang)}")


def _handler(slug: str, lang: str):
    async def handle(request: web.Request) -> web.Response:
        from webapp import store

        text = render(slug, store._origin(request), lang)
        return web.Response(text=store._with_style_version(text), content_type="text/html")
    return handle


def setup_legal_routes(app: web.Application) -> None:
    for lang, conf in LANGS.items():
        for slug in conf["pages"]:
            app.router.add_get(f"{conf['prefix']}/{slug}", _handler(slug, lang))
