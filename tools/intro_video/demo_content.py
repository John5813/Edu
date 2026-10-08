"""Tanishtiruv videosi uchun namoyish mazmuni: taqdimot slaydlari va do'kondagi namunaviy ishlar."""

TOPIC = "Raqamli iqtisodiyot: O‘zbekiston tajribasi"


def head(title):
    return f'<section class="slide"><div class="head"><h2 class="title">{title}</h2><div class="rule"></div></div>'


DECK = [
    ("muqova", "Raqamli iqtisodiyot: O‘zbekiston tajribasi",
     '<section class="slide dark"><div class="body"><h1 class="title big">Raqamli iqtisodiyot: O‘zbekiston tajribasi</h1>'
     '<div class="rule"></div><p class="lead">Elektron xizmatlar, IT-park va onlayn to‘lovlarning iqtisodiy o‘sishga ta’siri</p></div></section>'),
    ("reja", "Taqdimot rejasi", None),
    ("ikki_ustun", "Raqamli iqtisodiyot nima?",
     head("Raqamli iqtisodiyot nima?") + '<div class="body"><p class="lead">Iqtisodiy faoliyatning raqamli texnologiyalar asosida yuritilishi.</p><div class="list">'
     '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Elektron xizmatlar.</b> Davlat va bank xizmatlari onlayn ko‘rsatiladi.</div></div>'
     '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Onlayn savdo.</b> Xarid va to‘lovlar smartfon orqali amalga oshadi.</div></div>'
     '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Ma’lumotlar.</b> Qarorlar raqamlar tahlili asosida qabul qilinadi.</div></div>'
     '</div></div></section>'),
    ("korsatkichlar", "Raqamlarda: so‘nggi besh yil",
     head("Raqamlarda: so‘nggi besh yil") + '<div class="body"><p class="lead">Raqamli xizmatlar iqtisodiyotning eng tez o‘sayotgan qismiga aylandi.</p><div class="cols cols-3">'
     '<div class="kpi"><div class="kpi-value">3,2×</div><div class="kpi-label">IT xizmatlar eksporti</div><div class="kpi-note">2019-yilga nisbatan o‘sish.</div></div>'
     '<div class="kpi"><div class="kpi-value">78%</div><div class="kpi-label">Internet foydalanuvchilari</div><div class="kpi-note">Aholining katta qismi mobil internetda.</div></div>'
     '<div class="kpi"><div class="kpi-value">400+</div><div class="kpi-label">Davlat e-xizmatlari</div><div class="kpi-note">Arizalar navbatsiz, onlayn.</div></div>'
     '</div></div></section>'),
    ("diagramma", "Onlayn to‘lovlar hajmi",
     head("Onlayn to‘lovlar hajmi") + '<div class="body"><div class="split wide-left">'
     '<div class="chart" data-kind="bar" data-labels="2020,2021,2022,2023,2024" data-series="Trln so‘m: 38,61,94,142,198" data-unit="trln so‘m"></div>'
     '<div class="list">'
     '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Besh baravar.</b> To‘lovlar hajmi to‘rt yilda keskin oshdi.</div></div>'
     '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Mobil ilovalar.</b> Asosiy o‘sish smartfon orqali bo‘ldi.</div></div>'
     '</div></div></div></section>'),
    ("kartalar", "O‘sishning uch omili",
     head("O‘sishning uch omili") + '<div class="body"><p class="lead">Raqamli iqtisodiyot infratuzilma, kadrlar va qonunchilik ustida turadi.</p><div class="cols cols-3">'
     '<div class="card line"><div class="ikon-dot"><img class="ikon" data-icon="network" alt=""></div><div class="card-title">Infratuzilma</div><div class="card-note">Optik tola va 4G qishloqlargacha yetdi.</div></div>'
     '<div class="card line"><div class="ikon-dot"><img class="ikon" data-icon="education" alt=""></div><div class="card-title">Kadrlar</div><div class="card-note">IT akademiyalar dasturchilar tayyorlaydi.</div></div>'
     '<div class="card line"><div class="ikon-dot"><img class="ikon" data-icon="law" alt=""></div><div class="card-title">Qonunchilik</div><div class="card-note">IT-park rezidentlariga imtiyozlar.</div></div>'
     '</div></div></section>'),
    ("diagramma", "To‘lovlar qanday amalga oshiriladi",
     head("To‘lovlar qanday amalga oshiriladi") + '<div class="body"><div class="split">'
     '<div class="chart" data-kind="donut" data-labels="Mobil ilova,Bank kartasi,Internet-bank,Boshqa" data-series="Ulush: 52,27,14,7" data-unit="%"></div>'
     '<div class="list">'
     '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Mobil ilova</b> — har ikki to‘lovdan biri.</div></div>'
     '<div class="item"><span class="item-dot"></span><div class="item-text"><b>Karta</b> — do‘konlarda hali keng tarqalgan.</div></div>'
     '</div></div></div></section>'),
    ("vaqt_oqi", "Raqamlashtirish bosqichlari",
     head("Raqamlashtirish bosqichlari") + '<div class="body"><p class="lead">Davlat dasturlari raqamli xizmatlarni bosqichma-bosqich kengaytirdi.</p><div class="timeline">'
     '<div class="stop"><span class="bead"></span><div class="when">2017</div><div class="what">Yagona davlat xizmatlari portali.</div></div>'
     '<div class="stop"><span class="bead"></span><div class="when">2019</div><div class="what">IT-park imtiyozlari.</div></div>'
     '<div class="stop"><span class="bead"></span><div class="when">2020</div><div class="what">«Raqamli O‘zbekiston — 2030».</div></div>'
     '<div class="stop"><span class="bead"></span><div class="when">2024</div><div class="what">400 dan ortiq onlayn xizmat.</div></div>'
     '</div></div></section>'),
    ("qiyoslash", "Imkoniyat va xavflar",
     head("Imkoniyat va xavflar") + '<div class="body"><div class="cols cols-2">'
     '<div class="card"><div class="card-title">Imkoniyatlar</div><div class="list">'
     '<div class="item"><span class="item-dot"></span><div class="item-text">Yangi ish o‘rinlari</div></div>'
     '<div class="item"><span class="item-dot"></span><div class="item-text">Eksport hajmi o‘sishi</div></div></div></div>'
     '<div class="card solid"><div class="card-title">Xavflar</div><div class="list">'
     '<div class="item"><span class="item-dot"></span><div class="item-text">Kiberxavfsizlik tahdidlari</div></div>'
     '<div class="item"><span class="item-dot"></span><div class="item-text">Raqamli tengsizlik</div></div></div></div>'
     '</div></div></section>'),
    ("yakun", "Xulosa",
     head("Xulosa") + '<div class="body"><p class="lead">Raqamli iqtisodiyot O‘zbekiston taraqqiyotining asosiy drayveriga aylanmoqda.</p><div class="list">'
     '<div class="item"><span class="item-dot"></span><div class="item-text">Infratuzilmani qishloqlarga yanada kengaytirish.</div></div>'
     '<div class="item"><span class="item-dot"></span><div class="item-text">Raqamli savodxonlikni oshirish.</div></div>'
     '<div class="item"><span class="item-dot"></span><div class="item-text">Kiberxavfsizlikka alohida e’tibor.</div></div>'
     '</div></div></section>'),
]

# Do'kondagi namunaviy ishlar: (kod, sarlavha, ish turi, narx, uslub, rang, sahifalar soni)
SHOP = [
    ("TQ100001", "Sun’iy intellektning ta’limdagi o‘rni", "premium_taqdimot", 4000, "qorongu", "binafsha", 12),
    ("TQ100002", "Amir Temur davlatchiligi", "premium_taqdimot", 3500, "jurnal", "qizil", 10),
    ("TQ100003", "Ekologiya va barqaror rivojlanish", "premium_taqdimot", 3500, "toza", "yashil", 10),
    ("TQ100004", "Marketing strategiyalari", "premium_taqdimot", 4000, "blok", "to'q ko'k", 12),
    ("TQ100005", "Kiberxavfsizlik asoslari", "premium_taqdimot", 4000, "kontur", "ko'k", 12),
    ("TQ100006", "Bank tizimi va moliya bozori", "premium_taqdimot", 3500, "blok", "zumrad", 10),
    ("TQ100007", "O‘zbekistonda turizmni rivojlantirish", "premium_taqdimot", 3500, "toza", "to'q sariq", 10),
    ("TQ100008", "Inson huquqlari va erkinliklari", "premium_taqdimot", 3000, "jurnal", "to'q ko'k", 8),
]


def shop_slides(title):
    """Do'kondagi ish uchun 3 ta oldindan ko'rish sahifasi."""
    cover = (f'<section class="slide dark"><div class="body"><h1 class="title big">{title}</h1><div class="rule"></div>'
             f'<p class="lead">Taqdimot · tahrirlanadigan PPTX</p></div></section>')
    plan = head("Taqdimot rejasi") + ('<div class="body"><div class="cols cols-3">'
                                     + "".join(f'<div class="card line"><div class="card-num">0{i}</div><div class="card-title">{t}</div>'
                                               f'<div class="card-note">{n}</div></div>'
                                               for i, (t, n) in enumerate([("Kirish", "Mavzuning dolzarbligi"), ("Asosiy qism", "Tahlil va misollar"),
                                                                            ("Xulosa", "Natija va takliflar")], 1))
                                     + '</div></div></section>')
    kpi = head("Asosiy ko‘rsatkichlar") + ('<div class="body"><div class="cols cols-3">'
                                          '<div class="kpi"><div class="kpi-value">64%</div><div class="kpi-label">O‘sish</div><div class="kpi-note">So‘nggi besh yilda.</div></div>'
                                          '<div class="kpi"><div class="kpi-value">12</div><div class="kpi-label">Yo‘nalish</div><div class="kpi-note">Asosiy sohalar.</div></div>'
                                          '<div class="kpi"><div class="kpi-value">2030</div><div class="kpi-label">Strategiya</div><div class="kpi-note">Maqsadli yil.</div></div>'
                                          '</div></div></section>')
    return [cover, plan, kpi]
