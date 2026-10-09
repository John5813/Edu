"""Qayta jalb xabarlari matni (uz/ru/en/kk) va har xabar ostidagi tugmalar.

Har xabarda kamida bitta tugma bor: mijoz o'qib bo'lgach bir bosishda kerakli joyga tushadi. Tugma maqsadi:
  * "gift" — 5 slaydli bepul taqdimot (sovg'a) oqimi;
  * boshqa kalitlar — botning bo'limi (`bot.ad_buttons.TARGETS`: taqdimot, mustaqil, referat, tolov, pul ...).

Matnlardagi o'rinlar: {hello} — ism bilan (yoki ismsiz) salom, {name} — ism yoki bo'sh, {balance} — balans,
{date} — muddat sanasi va soati (O'zbekiston vaqti), {bonus} — bonus foizi.
"""

LANGS = ("uz", "ru", "en", "kk")

HELLO = {
    "uz": ("{name}, assalomu alaykum!", "Assalomu alaykum!"),
    "ru": ("{name}, здравствуйте!", "Здравствуйте!"),
    "en": ("Hi {name}!", "Hi there!"),
    "kk": ("{name}, сәлеметсіз бе!", "Сәлеметсіз бе!"),
}

# Ism bo'lmasa matn boshidagi "{name}, " olib tashlanadi (reengage._fill).
STEPS = {
    # A — yangi kelgan, hech narsadan foydalanmagan; "old" — eski bazadagi shunday mijozlar (matnlar bir xil).
    "inactive": [
        {
            "uz": ("👋 {hello}\n\nSiz Edufayl'ga kirgansiz, lekin hali birorta ish tayyorlamadingiz. Sizga sovg'a: "
                   "<b>5 slaydli zamonaviy taqdimot — bepul</b>.\n\nMavzuni yozasiz — 3–5 daqiqada tayyor PowerPoint "
                   "fayl qo'lingizda."),
            "ru": ("👋 {hello}\n\nВы зашли в Edufayl, но ещё ничего не подготовили. Вам подарок: <b>современная "
                   "презентация на 5 слайдов — бесплатно</b>.\n\nНапишите тему — через 3–5 минут готовый файл "
                   "PowerPoint у вас."),
            "en": ("👋 {hello}\n\nYou joined Edufayl but haven't made anything yet. Here's a gift: <b>a modern "
                   "5-slide presentation — free</b>.\n\nType your topic and get a ready PowerPoint file in 3–5 minutes."),
            "kk": ("👋 {hello}\n\nСіз Edufayl-ға кірдіңіз, бірақ әлі ештеңе дайындаған жоқсыз. Сізге сыйлық: "
                   "<b>5 слайдты заманауи презентация — тегін</b>.\n\nТақырыпты жазыңыз — 3–5 минутта дайын "
                   "PowerPoint файлы қолыңызда."),
            # Eski bazada: oldingi foydalanish to'liq yozilmagan bo'lishi mumkin — "hech narsa qilmadingiz" demaymiz.
            "old": {
                "uz": ("👋 {hello}\n\nEdufayl'dan sizga sovg'a: <b>5 slaydli zamonaviy taqdimot — bepul</b>.\n\n"
                       "Mavzuni yozasiz — 3–5 daqiqada tayyor PowerPoint fayl qo'lingizda."),
                "ru": ("👋 {hello}\n\nПодарок от Edufayl: <b>современная презентация на 5 слайдов — бесплатно</b>.\n\n"
                       "Напишите тему — через 3–5 минут готовый файл PowerPoint у вас."),
                "en": ("👋 {hello}\n\nA gift from Edufayl: <b>a modern 5-slide presentation — free</b>.\n\n"
                       "Type your topic and get a ready PowerPoint file in 3–5 minutes."),
                "kk": ("👋 {hello}\n\nEdufayl-дан сізге сыйлық: <b>5 слайдты заманауи презентация — тегін</b>.\n\n"
                       "Тақырыпты жазыңыз — 3–5 минутта дайын PowerPoint файлы қолыңызда."),
            },
            "buttons": [("gift", {"uz": "🎁 Bepul taqdimot olish", "ru": "🎁 Получить бесплатно",
                                  "en": "🎁 Get it free", "kk": "🎁 Тегін алу"})],
        },
        {
            "uz": ("{name}, mana Edufayl'da tayyorlangan taqdimotlardan biri. Sizniki ham shunday bo'lishi mumkin — "
                   "birinchi taqdimotingiz (5 slayd) biz tomondan sovg'a."),
            "ru": ("{name}, вот одна из презентаций, сделанных в Edufayl. Ваша может быть такой же — первая "
                   "презентация (5 слайдов) в подарок от нас."),
            "en": ("{name}, here is one of the presentations made with Edufayl. Yours can look like this too — your "
                   "first presentation (5 slides) is our gift."),
            "kk": ("{name}, міне Edufayl-да жасалған презентациялардың бірі. Сіздікі де осындай болуы мүмкін — "
                   "алғашқы презентацияңыз (5 слайд) бізден сыйлық."),
            "buttons": [("gift", {"uz": "🎁 Sinab ko'rish", "ru": "🎁 Попробовать", "en": "🎁 Try it",
                                  "kk": "🎁 Байқап көру"}),
                        ("namunalar", {"uz": "📁 Namunalar", "ru": "📁 Образцы", "en": "📁 Samples",
                                       "kk": "📁 Үлгілер"})],
            "sample": True,
        },
        {
            "uz": ("{name}, Edufayl faqat taqdimot emas: mustaqil ish, referat, kurs ishi va testlar ham bir necha "
                   "daqiqada Word faylda tayyor bo'ladi.\n\nBoshlash uchun sovg'angizdan foydalaning: 5 slaydli "
                   "taqdimot bepul."),
            "ru": ("{name}, Edufayl — это не только презентации: самостоятельная работа, реферат, курсовая и тесты "
                   "тоже готовы за несколько минут в файле Word.\n\nНачните с подарка: презентация на 5 слайдов "
                   "бесплатно."),
            "en": ("{name}, Edufayl isn't only presentations: independent work, essays, course papers and tests are "
                   "ready as Word files in a few minutes too.\n\nStart with your gift: a 5-slide presentation for free."),
            "kk": ("{name}, Edufayl тек презентация емес: өзіндік жұмыс, реферат, курстық жұмыс пен тесттер де бірнеше "
                   "минутта Word файлында дайын болады.\n\nСыйлығыңыздан бастаңыз: 5 слайдты презентация тегін."),
            "buttons": [("gift", {"uz": "🎁 Bepul taqdimot", "ru": "🎁 Бесплатная презентация",
                                  "en": "🎁 Free presentation", "kk": "🎁 Тегін презентация"}),
                        ("mustaqil", {"uz": "📝 Mustaqil ish", "ru": "📝 Самостоятельная работа",
                                      "en": "📝 Independent work", "kk": "📝 Өзіндік жұмыс"}),
                        ("referat", {"uz": "📄 Referat", "ru": "📄 Реферат", "en": "📄 Essay", "kk": "📄 Реферат"})],
        },
        {
            "uz": ("{name}, do'stlaringizni Edufayl'ga taklif qiling: har bir yangi do'stingiz uchun hisobingizga "
                   "<b>2 500 so'm</b>, u birinchi to'lov qilganda yana <b>1 000 so'm</b> tushadi. Shu pulga taqdimot "
                   "va mustaqil ishlar tayyorlaysiz."),
            "ru": ("{name}, приглашайте друзей в Edufayl: за каждого нового друга на ваш счёт поступает "
                   "<b>2 500 сум</b>, а когда он сделает первый платёж — ещё <b>1 000 сум</b>. На эти деньги вы "
                   "готовите презентации и самостоятельные работы."),
            "en": ("{name}, invite your friends to Edufayl: every new friend adds <b>2,500 soʻm</b> to your balance, "
                   "and their first payment adds another <b>1,000 soʻm</b>. Spend it on presentations and papers."),
            "kk": ("{name}, достарыңызды Edufayl-ға шақырыңыз: әр жаңа досыңыз үшін шотыңызға <b>2 500 сум</b>, ол "
                   "алғашқы төлемін жасағанда тағы <b>1 000 сум</b> түседі. Осы ақшаға презентация мен өзіндік "
                   "жұмыстар дайындайсыз."),
            "buttons": [("pul", {"uz": "💰 Pul ishlab topish", "ru": "💰 Заработать", "en": "💰 Earn money",
                                 "kk": "💰 Ақша табу"}),
                        ("gift", {"uz": "🎁 Bepul taqdimot", "ru": "🎁 Бесплатная презентация",
                                  "en": "🎁 Free presentation", "kk": "🎁 Тегін презентация"})],
        },
        {
            "uz": ("{name}, oxirgi eslatma: 5 slaydli bepul taqdimot sovg'angiz <b>48 soatdan keyin</b> ({date} "
                   "gacha) yopiladi. Mavzuni yozing — taqdimot bir necha daqiqada tayyor."),
            "ru": ("{name}, последнее напоминание: ваш подарок — бесплатная презентация на 5 слайдов — закроется "
                   "<b>через 48 часов</b> (до {date}). Напишите тему — презентация будет готова за несколько минут."),
            "en": ("{name}, last reminder: your free 5-slide presentation gift closes <b>in 48 hours</b> (until "
                   "{date}). Type a topic — the presentation is ready in a few minutes."),
            "kk": ("{name}, соңғы еске салу: 5 слайдты тегін презентация сыйлығыңыз <b>48 сағаттан кейін</b> ({date} "
                   "дейін) жабылады. Тақырыпты жазыңыз — презентация бірнеше минутта дайын."),
            "buttons": [("gift", {"uz": "🎁 Sovg'ani olish", "ru": "🎁 Забрать подарок", "en": "🎁 Claim the gift",
                                  "kk": "🎁 Сыйлықты алу"})],
            "deadline": True,
        },
    ],
    # B — to'lagan, lekin hali foydalanmagan.
    "paid_unused": [
        {
            "uz": ("{name}, hisobingizda <b>{balance} so'm</b> turibdi, lekin hali undan foydalanmadingiz. Taqdimot, "
                   "mustaqil ish yoki referat — bir necha daqiqada tayyor."),
            "ru": ("{name}, на вашем счёте <b>{balance} сум</b>, но вы ещё ими не воспользовались. Презентация, "
                   "самостоятельная работа или реферат — готовы за несколько минут."),
            "en": ("{name}, you have <b>{balance} soʻm</b> on your balance that you haven't used yet. A presentation, "
                   "independent work or essay is ready in a few minutes."),
            "kk": ("{name}, шотыңызда <b>{balance} сум</b> тұр, бірақ сіз оны әлі пайдаланбадыңыз. Презентация, "
                   "өзіндік жұмыс немесе реферат — бірнеше минутта дайын."),
            "buttons": [("taqdimot", {"uz": "📊 Taqdimot", "ru": "📊 Презентация", "en": "📊 Presentation",
                                      "kk": "📊 Презентация"}),
                        ("mustaqil", {"uz": "📝 Mustaqil ish", "ru": "📝 Самостоятельная работа",
                                      "en": "📝 Independent work", "kk": "📝 Өзіндік жұмыс"})],
        },
        {
            "uz": "{name}, {balance} so'm hisobingizda sizni kutmoqda. Mavzuni yozing — qolganini Edufayl qiladi.",
            "ru": "{name}, {balance} сум ждут вас на счёте. Напишите тему — остальное сделает Edufayl.",
            "en": "{name}, {balance} soʻm is waiting on your balance. Type a topic — Edufayl does the rest.",
            "kk": "{name}, {balance} сум шотыңызда сізді күтуде. Тақырыпты жазыңыз — қалғанын Edufayl жасайды.",
            "buttons": [("taqdimot", {"uz": "📊 Taqdimot", "ru": "📊 Презентация", "en": "📊 Presentation",
                                      "kk": "📊 Презентация"}),
                        ("referat", {"uz": "📄 Referat", "ru": "📄 Реферат", "en": "📄 Essay", "kk": "📄 Реферат"})],
        },
        {
            "uz": ("{name}, eslatib qo'yamiz: hisobingizdagi {balance} so'm saqlanib turibdi. Kerak bo'lganda bir "
                   "tugma bilan ish buyurtma qiling."),
            "ru": ("{name}, напоминаем: {balance} сум на вашем счёте сохранены. Когда понадобится — закажите работу "
                   "одной кнопкой."),
            "en": ("{name}, a reminder: the {balance} soʻm on your balance is kept for you. Order a paper with one "
                   "tap whenever you need it."),
            "kk": ("{name}, еске саламыз: шотыңыздағы {balance} сум сақтаулы тұр. Қажет болғанда бір батырмамен "
                   "жұмыс тапсырыс беріңіз."),
            "buttons": [("hisob", {"uz": "👤 Hisobim", "ru": "👤 Мой счёт", "en": "👤 My account",
                                   "kk": "👤 Менің шотым"}),
                        ("taqdimot", {"uz": "📊 Taqdimot", "ru": "📊 Презентация", "en": "📊 Presentation",
                                      "kk": "📊 Презентация"})],
        },
    ],
    # C — bepul taqdimotni olgan, hali to'lov qilmagan: birinchi to'lovga bonus.
    "trial": [
        {
            "uz": ("{name}, bepul taqdimotingiz yoqdimi? To'liq taqdimotda rasmlar, diagrammalar va istalgan slayd "
                   "soni bor.\n\n🎁 Siz uchun: birinchi to'lovingizga <b>+{bonus}% bonus</b> — {date} gacha."),
            "ru": ("{name}, понравилась бесплатная презентация? В полной версии — изображения, диаграммы и любое "
                   "число слайдов.\n\n🎁 Для вас: <b>+{bonus}% бонус</b> к первому пополнению — до {date}."),
            "en": ("{name}, did you like your free presentation? The full version has images, charts and any number "
                   "of slides.\n\n🎁 For you: <b>+{bonus}% bonus</b> on your first top-up — until {date}."),
            "kk": ("{name}, тегін презентацияңыз ұнады ма? Толық нұсқада суреттер, диаграммалар және кез келген "
                   "слайд саны бар.\n\n🎁 Сіз үшін: алғашқы төлеміңізге <b>+{bonus}% бонус</b> — {date} дейін."),
            "buttons": [("tolov", {"uz": "💳 Hisobni to'ldirish", "ru": "💳 Пополнить счёт", "en": "💳 Top up",
                                   "kk": "💳 Шотты толтыру"}),
                        ("taqdimot", {"uz": "📊 To'liq taqdimot", "ru": "📊 Полная презентация",
                                      "en": "📊 Full presentation", "kk": "📊 Толық презентация"})],
            "bonus": True,
        },
        {
            "uz": ("{name}, +{bonus}% bonus hali amal qilmoqda ({date} gacha): masalan, 20 000 so'm to'lasangiz, "
                   "hisobingizga 24 000 so'm tushadi."),
            "ru": ("{name}, бонус +{bonus}% ещё действует (до {date}): например, пополните на 20 000 сум — на счёт "
                   "поступит 24 000 сум."),
            "en": ("{name}, the +{bonus}% bonus is still on (until {date}): top up 20,000 soʻm and get 24,000 soʻm "
                   "on your balance."),
            "kk": ("{name}, +{bonus}% бонус әлі күшінде ({date} дейін): мысалы, 20 000 сум төлесеңіз, шотыңызға "
                   "24 000 сум түседі."),
            "buttons": [("tolov", {"uz": "💳 Hisobni to'ldirish", "ru": "💳 Пополнить счёт", "en": "💳 Top up",
                                   "kk": "💳 Шотты толтыру"})],
        },
        {
            "uz": ("{name}, +{bonus}% bonus muddati {date} da tugaydi. Hisobni to'ldiring — bonus avtomatik "
                   "qo'shiladi."),
            "ru": "{name}, срок бонуса +{bonus}% истекает {date}. Пополните счёт — бонус начислится автоматически.",
            "en": "{name}, the +{bonus}% bonus ends on {date}. Top up — the bonus is added automatically.",
            "kk": "{name}, +{bonus}% бонус мерзімі {date} аяқталады. Шотты толтырыңыз — бонус автоматты қосылады.",
            "buttons": [("tolov", {"uz": "💳 Hisobni to'ldirish", "ru": "💳 Пополнить счёт", "en": "💳 Top up",
                                   "kk": "💳 Шотты толтыру"}),
                        ("taqdimot", {"uz": "📊 Taqdimot", "ru": "📊 Презентация", "en": "📊 Presentation",
                                      "kk": "📊 Презентация"})],
        },
    ],
    # D — ilgari to'lab foydalangan, 14+ kun kelmagan.
    "lapsed": [
        {
            "uz": ("{name}, Edufayl sizni kutmoqda! Taqdimot, mustaqil ish yoki referat kerak bo'lsa — hammasi bir "
                   "necha daqiqada tayyor."),
            "ru": ("{name}, Edufayl ждёт вас! Нужна презентация, самостоятельная работа или реферат — всё готово за "
                   "несколько минут."),
            "en": ("{name}, Edufayl is waiting for you! Need a presentation, independent work or an essay — it's "
                   "ready in a few minutes."),
            "kk": ("{name}, Edufayl сізді күтуде! Презентация, өзіндік жұмыс немесе реферат керек болса — бәрі "
                   "бірнеше минутта дайын."),
            "buttons": [("taqdimot", {"uz": "📊 Taqdimot", "ru": "📊 Презентация", "en": "📊 Presentation",
                                      "kk": "📊 Презентация"}),
                        ("mustaqil", {"uz": "📝 Mustaqil ish", "ru": "📝 Самостоятельная работа",
                                      "en": "📝 Independent work", "kk": "📝 Өзіндік жұмыс"})],
        },
        {
            "uz": ("{name}, Edufayl'da yangiliklar: matni ko'p yoki kam taqdimotlar, rasmlar va diagrammalar bilan. "
                   "Navbatdagi ishingizni bizga topshiring."),
            "ru": ("{name}, новое в Edufayl: презентации с большим или малым объёмом текста, с изображениями и "
                   "диаграммами. Доверьте нам следующую работу."),
            "en": ("{name}, new in Edufayl: presentations with more or less text, with images and charts. Let us "
                   "handle your next paper."),
            "kk": ("{name}, Edufayl-дағы жаңалықтар: мәтіні көп немесе аз презентациялар, суреттер мен "
                   "диаграммалармен. Келесі жұмысыңызды бізге тапсырыңыз."),
            "buttons": [("taqdimot", {"uz": "📊 Taqdimot", "ru": "📊 Презентация", "en": "📊 Presentation",
                                      "kk": "📊 Презентация"}),
                        ("referat", {"uz": "📄 Referat", "ru": "📄 Реферат", "en": "📄 Essay", "kk": "📄 Реферат"})],
        },
    ],
}

# Sovg'a (bepul taqdimot) oqimi matnlari.
GIFT = {
    "ask": {
        "uz": ("🎁 <b>5 slaydli bepul taqdimot</b>\n\nTaqdimot mavzusini yozing (masalan: «Amir Temur davlati» yoki "
               "«Suv aylanishi»). Taqdimot mavzu yozilgan tilda tayyorlanadi."),
        "ru": ("🎁 <b>Бесплатная презентация на 5 слайдов</b>\n\nНапишите тему презентации (например: «Государство "
               "Амира Тимура» или «Круговорот воды»). Презентация будет на языке темы."),
        "en": ("🎁 <b>Free 5-slide presentation</b>\n\nType the presentation topic (for example: «The water cycle»). "
               "The presentation is made in the language of the topic."),
        "kk": ("🎁 <b>5 слайдты тегін презентация</b>\n\nПрезентация тақырыбын жазыңыз (мысалы: «Су айналымы»). "
               "Презентация тақырып жазылған тілде дайындалады."),
    },
    "short": {"uz": "Mavzu juda qisqa — kamida 3 ta belgi yozing.", "ru": "Тема слишком короткая — минимум 3 символа.",
              "en": "The topic is too short — at least 3 characters.", "kk": "Тақырып тым қысқа — кемінде 3 таңба."},
    "used": {
        "uz": "Bepul taqdimot sovg'asidan avval foydalangansiz yoki uning muddati tugagan. To'liq taqdimot buyurtma qiling:",
        "ru": "Подарок — бесплатная презентация — уже использован или его срок истёк. Закажите полную презентацию:",
        "en": "The free presentation gift has already been used or has expired. Order a full presentation:",
        "kk": "Тегін презентация сыйлығы бұрын пайдаланылған немесе мерзімі өткен. Толық презентация тапсырыс беріңіз:",
    },
    "busy": {"uz": "⏳ Taqdimotingiz tayyorlanmoqda, biroz kuting.", "ru": "⏳ Ваша презентация готовится, подождите.",
             "en": "⏳ Your presentation is being prepared, please wait.",
             "kk": "⏳ Презентацияңыз дайындалуда, күте тұрыңыз."},
    "working": {"uz": "⏳ <b>{topic}</b>\n5 slaydli taqdimot tayyorlanmoqda (3–5 daqiqa)...",
                "ru": "⏳ <b>{topic}</b>\nГотовим презентацию на 5 слайдов (3–5 минут)...",
                "en": "⏳ <b>{topic}</b>\nPreparing your 5-slide presentation (3–5 minutes)...",
                "kk": "⏳ <b>{topic}</b>\n5 слайдты презентация дайындалуда (3–5 минут)..."},
    "failed": {"uz": "❌ Taqdimot tayyorlanmadi. Sovg'angiz saqlandi — qayta urinib ko'ring.",
               "ru": "❌ Презентация не подготовлена. Подарок сохранён — попробуйте ещё раз.",
               "en": "❌ The presentation could not be prepared. Your gift is kept — please try again.",
               "kk": "❌ Презентация дайындалмады. Сыйлығыңыз сақталды — қайта көріңіз."},
    "done": {
        "uz": ("✅ Bepul taqdimotingiz tayyor!\n\nTo'liq zamonaviy taqdimotda: <b>rasmlar, diagrammalar, 5 xil uslub "
               "va istalgan slayd soni</b> (30 tagacha). Navbatdagi taqdimotingizni shunday buyurtma qiling:"),
        "ru": ("✅ Ваша бесплатная презентация готова!\n\nВ полной современной презентации: <b>изображения, "
               "диаграммы, 5 стилей и любое число слайдов</b> (до 30). Закажите следующую так:"),
        "en": ("✅ Your free presentation is ready!\n\nThe full modern presentation has <b>images, charts, 5 styles "
               "and any number of slides</b> (up to 30). Order your next one here:"),
        "kk": ("✅ Тегін презентацияңыз дайын!\n\nТолық заманауи презентацияда: <b>суреттер, диаграммалар, 5 стиль "
               "және кез келген слайд саны</b> (30-ға дейін). Келесі презентацияңызды осылай тапсырыс беріңіз:"),
    },
    "retry": {"uz": "🔄 Qayta urinish", "ru": "🔄 Попробовать снова", "en": "🔄 Try again", "kk": "🔄 Қайта көру"},
    "cancel": {"uz": "⬅️ Bekor qilish", "ru": "⬅️ Отмена", "en": "⬅️ Cancel", "kk": "⬅️ Болдырмау"},
    "full": {"uz": "📊 To'liq taqdimot", "ru": "📊 Полная презентация", "en": "📊 Full presentation",
             "kk": "📊 Толық презентация"},
    "topup": {"uz": "💳 Hisobni to'ldirish", "ru": "💳 Пополнить счёт", "en": "💳 Top up", "kk": "💳 Шотты толтыру"},
}

# Birinchi to'lovga qo'shilgan bonus haqida mijozga xabar.
BONUS_PAID = {
    "uz": "🎁 Birinchi to'lovingiz uchun bonus: +{amount} so'm hisobingizga qo'shildi.",
    "ru": "🎁 Бонус за первое пополнение: +{amount} сум добавлено на ваш счёт.",
    "en": "🎁 First top-up bonus: +{amount} soʻm added to your balance.",
    "kk": "🎁 Алғашқы төлем бонусы: +{amount} сум шотыңызға қосылды.",
}
