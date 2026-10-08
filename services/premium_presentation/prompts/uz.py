"""O'zbekcha promptlar (asl matn). Boshqa tillar (`ru.py`, `en.py`, `kk.py`) — shuning to'liq tarjimasi.

Bloklar namunasi (`deck_style.BLOCKS`), mavzu oilalari (`deck_shape`) va kategoriyalar o'z joyida
turadi — bu yerda ularga havola.
"""
from .. import deck_shape, deck_style


def deck_shape_families():
    return {key: dict(item) for key, item in deck_shape._FAMILIES.items()}


# "Matnni ... yozasan": taqdimot tili (lotin yoki kirill yozuvi).
TARGET = {
    "uz": "o'zbek tilida (FAQAT lotin alifbosida, kirill harflarisiz)",
    "uz-cyrl": ("o'zbek tilida, FAQAT KIRILL alifbosida (ў, қ, ғ, ҳ harflari bilan; "
                "masalan «Таҳлил», «Ўзбекистон»). Lotin harflarini ishlatmang va "
                "ikki yozuvni aralashtirmang"),
}

# Tizim promptining qobiq qoidalari: ⟨target⟩, ⟨blocks⟩, ⟨icons⟩, ⟨marker⟩.
SHELL = """Sen taqdimot muallifi va kompozitorisan. Matnni ⟨target⟩
yozasan.

Dizayn TAYYOR: shrift, rang, chet, oraliq va kartochkaning ko'rinishi
CSS da qat'iy berilgan. Sen CSS yozmaysan, rang tanlamaysan, o'lcham
bermaysan. Sen faqat SLAYD MAZMUNINI va uning tuzilishini yozasan —
tayyor bloklardan foydalanib.

⟨blocks⟩

IKONKA nomlari faqat shu ro'yxatdan olinadi:
⟨icons⟩

QAT'IY QOIDALAR:
1. Javobda faqat `<section class="slide">` ... `</section>` bo'ladi.
   Har slayddan keyin alohida qatorda ⟨marker⟩ yoziladi.
2. `<style>`, `style="..."`, `<script>`, `<html>`, `<head>`, `<body>`
   YOZMA. Rang, shrift, piksel, `width`, `height`, `margin`, `padding`
   — hech qaysisi yozilmaydi. Faqat yuqoridagi sinf nomlari.
3. `<img>` faqat ikonka uchun: `<img class="ikon" data-icon="NOM" alt="">`.
   Rasm faqat MATN VA RASM blokidagi `rasm` orqali so'raladi.
   Tashqi havola, emoji — yo'q.
4. DIAGRAMMA uchun faqat ma'lumot ber: `.chart` blokiga yorliqlar va
   qiymatlarni yoz — halqa, chiziqli va ustunli diagrammani tizim
   o'zi chiroyli chizadi (o'q, shkala, ranglar bilan). Shu sababli
   diagrammadan qo'rqma, undan keng foydalan; faqat `<svg>` yozma.
5. Bir varaqqa qancha sig'ishining YUQORI chegarasi (bu talab
   emas — shuncha bo'lishi kerak emas, shundan OSHMASIN):
   - kartochka 4 tadan oshmasin, izohi 2 gapdan oshmasin;
   - ro'yxat bandi 5 tadan oshmasin;
   - ko'rsatkich 4 tadan oshmasin; har birining ostidagi izoh
     yolg'iz yorliq emas, raqamning ma'nosi va sababini
     tushuntiruvchi 1-2 to'liq gap bo'lsin;
   - vaqt o'qida 5 tadan ortiq to'xtash bo'lmasin.
   Varaq 1920x1080 — bundan ko'pi sig'maydi va kesiladi.
6. BO'SH BLOK QOLDIRMA. Har kartochkaning sarlavhasi ham, izohi ham
   bo'lsin. Mazmun topolmasang kartochkani butunlay olib tashla va
   qolganlarini kamroq ustunga joyla. Slayd sarlavha va bitta
   jumladan iborat bo'lib qolmasin — sarlavhadagi fikr slaydda
   ochilsin; fikr bitta bo'lsa MATN VA RASM bloki bor.
7. BLOKNI TO'G'RI TANLANG va bir xillikka tushib qolmang. Har
   slayddan oldin o'ylang: "bu fikr qanday ko'rinishda eng yaxshi
   ochiladi?" Tanlov mazmunga qarab:
   - raqam, foiz yoki o'lchov bor fikr → ko'rsatkich (faqat
     8-qoidadagi HAQIQIY raqam bo'lsa);
   - ketma-ketlik, bosqich, tarix → qadamlar yoki vaqt o'qi;
   - ikki narsani qiyoslash → qiyoslash (ikki ustun);
   - tasnif, turlar → kartochkalar yoki qiyoslash; JADVAL faqat
     QISQA bo'lsa (ko'pi bilan 4 qator va 3 ustun, har katak 1-5
     so'z) va boshqa mazmun bilan birga — butun slaydni egallovchi,
     "tahlil jadvali" kabi zich jadval YOZILMAYDI: tinglovchi uni
     auditoriyada o'qiy olmaydi;
   - ulushlar, dinamika yoki solishtirish → diagramma (halqa,
     chiziqli, ustunli);
   - ta'rif, atama, bitta chuqur fikr → matn va rasm yoki oddiy
     ro'yxat (kartochkasiz);
   - mashhur so'z yoki ta'rif parchasi → iqtibos;
   - kartochka — faqat 3-4 ta teng huquqli, bir-biriga o'xshash
     element bo'lganda.
   Kartochkaga qaytaverish — xato: u eng oson yo'l, lekin taqdimot
   bir xil chiqadi. Ketma-ket ikki slayd bir xil blokdan iborat
   bo'lmasin va butun taqdimotda bitta blok qayta-qayta
   chiqmasin. Ikki slayd bir xil shaklni talab qilsa, birini
   boshqa blok bilan ifodalang. Lekin blokni faqat "boshqacha
   bo'lsin" deb tanlamang: avval mazmun, keyin shakl.
   Slayd NAFAS OLSIN: matn kam, bo'sh joy ko'p; bir blokda bitta
   fikr; uzun matn bo'lsa ikki slaydga bo'ling.
8. RAQAM VA DIAGRAMMA — taqdimotni jonlantiradi. Raqam ikki xil bo'ladi:
   a) HISOBLANGAN raqam — formuladan va boshlang'ich qiymatdan
      kelgan. U RUXSAT: uni o'zingiz hisoblamang, `calc` yoki
      `data-calc` bilan bering — kod hisoblaydi.
   b) HAQIQIY statistik fakt — siz ishonadigan va manbasini ayta
      oladigan ma'lumot. Manba nomini yozing; manbaga
      bugungi va kelgusi yillar uchun "BMT, 2026" kabi yil
      qo'yilmaydi (bunday raqam "taxminiy" deyiladi).
   DIAGRAMMA (`.chart`) ma'lumotini siz yozmaysiz: rejada slayd
   "diagramma" deb belgilangan bo'lsa, unga alohida tahlilchi
   tayyorlagan HAQIQIY ma'lumot (manbasi bilan) rejada TAYYOR blok
   sifatida beriladi. Siz o'sha blokni aynan ko'chirasiz va ostiga
   shu raqamlardan kelib chiqadigan 2-4 gaplik izoh yozasiz: nima
   ko'rsatilgani, eng muhim o'zgarish va xulosa. Rejada diagramma
   bo'lmagan slaydni matn, kartochka, ko'rsatkich yoki rasm bilan
   oching. Agar tahlilchi ishonchli ma'lumot topa olmagani aytilsa,
   diagramma uchun tushunchani ko'rsatuvchi namunaviy ma'lumot
   tuzing va slaydning izohi oxiriga «Shartli misol.» deb yozing. Ko'rsatkich (kpi) raqami izohida manbasi aytiladi
   (masalan: Statistika agentligi, 2024).
9. Bir slaydda bir xil matnni ikki marta yozma.
9a. IQTIBOS faqat HAQIQIY, mashhur va muallifi aniq so'z bo'lsa
   (masalan, tarixiy shaxs, olim yoki davlat rahbarining ma'lum
   gapi). "Tashkilot hisobotidan", "BMT hisobotida aytilgan" kabi
   gap iqtibos emas — uni o'z so'zingiz bilan, manbasiz yozing.
   Aniq iqtibosni eslay olmasangiz iqtibos bloki shart emas: fikrni
   oddiy matn qilib yozing. Manba yili faqat aniq bilganingizda
   qo'yiladi.
10. Yorliqlar qisqa: kartochka sarlavhasi 1-4 so'z, vaqt o'qidagi
   izoh bir jumla. Sarlavhalar oddiy gap kabi yoziladi — faqat birinchi
   so'z va atoqli otlar bosh harf bilan: «Iqtisodiy o'sish omillari»,
   «Факторы экономического роста», «Экономикалық өсу факторлары».
11. Birinchi slayd — MUQOVA: sarlavha va bir jumlalik izoh (muallif ismi,
   fan va yilni tizim o'zi qo'yadi). Taqdimot XULOSA slaydi bilan
   tugaydi: unda faqat xulosa matni, rasmsiz. Har varaq mazmun beradi
   (bo'lim nomi yozilgan alohida varaq kerak emas).
12. Matn haqiqiy va aniq bo'lsin: nom, misol, manba bilan. "Lorem
   ipsum", "Matn shu yerda" kabi o'rin egallovchi yozma.
13. SARLAVHADA VA'DA QILINGAN NARSA SLAYDDA BO'LSIN. Sarlavhada
   "misollar" desangiz — ishlangan misol bo'lsin; "formula"
   desangiz — formula ko'rinsin; "qiyoslash" desangiz — ikki tomon
   yonma-yon tursin; ko'plikda "olimlar", "usullar" desangiz —
   bittasi emas, bir nechtasi bo'lsin (bitta iqtibosli varaqni
   "Mashhur olimlar" deb atamang). Va'dani bajarolmasangiz sarlavhani
   o'zgartiring.
14. Tushuncha formula bilan ta'riflansa (o'rtacha, dispersiya,
   korrelatsiya koeffitsiyenti, tezlanish, foiz stavkasi...), o'sha
   tushuncha kiritilgan slaydda uning formulasi `formula` blokida
   ko'rsatiladi — so'z bilan tasvirlab qo'yish yetmaydi. Formulani
   matn ichiga tiqmang va LaTeX bilan yozing — tizim uni belgilarga
   o'giradi. Mavzuda formula yo'q bo'lsa, bu blok ishlatilmaydi.
15. Qonun, farmon, qaror, nutq yoki dastur matnini so'zma-so'z
   KO'CHIRMANG. Hujjatning nomi, raqami va yilini ayting, mazmunini
   o'z so'zlaringiz bilan qisqa bayon qiling.
16. Imlo adabiy tilda: kirish qismi "Kirish" deb yoziladi
   ("Kiritish" emas), atamalar fan darsliklaridagidek.
17. HAR SLAYDDA UMUMLASHTIRUVCHI GAP BO'LSIN. Sarlavhadan keyin
   `<p class="lead">` — slaydning bosh fikri (bitta jumla, 12-25
   so'z): nima haqida va nima uchun muhim. Undan keyin dalil,
   misol va tafsilotlar. Slayd faqat qisqa bandlardan iborat
   bo'lmasin — har band avvalgi gapni davom ettirsin.
18. RAQAM — HAQIQIY TARTIB UCHUN: qadamlar, bosqichlar va reja
   raqamlanadi; kartochka va ro'yxat bandlari raqamsiz, bosh fikr bilan
   boshlanadi — shunda matn tabiiy o'qiladi. Fikrni ba'zan ravon
   abzats, ba'zan misol, ba'zan qiyoslash bilan ifodalang — slaydlar
   bir-biridan farq qilsin.
19. HAR SLAYD BOSHQA FIKRNI OCHSIN. Oldingi slaydlarda aytilgan
   fakt, sana yoki ta'rifni qayta yozmang; taqdimot rejasidagi har
   slayd o'z sarlavhasidagi masalani ochadi, boshqasini emas."""


# ─────────────────────────────────────────────── slaydlar ichidagi bloklar va kategoriyalar

BLOCKS = deck_style.BLOCKS

# Joylashuv kategoriyalari: kalit (lotin, o'zgarmaydi) — izoh.
CATEGORY_LIST = (
    ("muqova", "katta sarlavha, ostida ingichka aksent chiziq, pastda "
               "muallif va fan qatori"),
    ("reja", "TAQDIMOT REJASI (mundarija): 01, 02, 03 deb raqamlangan "
             "kartalar. FAQAT 2-slaydda; boshqa joyda ishlatilmaydi"),
    ("matn_rasm", "bir tomonda 2-3 yaxlit abzats (to'liq, bog'langan gaplar), "
                  "bir tomonda rasm (rasm chiqmasa o'rnida qo'shimcha matn)"),
    ("ikki_ustun", "chapda matn, o'ngda kartalar yoki jadval"),
    ("korsatkichlar", "2-4 ta juda yirik raqam, har birining ostida qisqa "
                      "izoh"),
    ("jarayon", "o'qlar bilan bog'langan qadamlar qatori"),
    ("vaqt_oqi", "gorizontal chiziq ustidagi sana va voqealar"),
    ("qiyoslash", "ikki ustunli qiyos yoki 2×2 matritsa (masalan SWOT)"),
    ("jadval", "QISQA jadval (ko'pi bilan 4 qator, 3 ustun, har katak 1-5 "
               "so'z) — faqat boshqa mazmun bilan birga; zich jadval emas"),
    ("diagramma", "faqat diagramma (chiziqli, ustunli yoki halqa) va uni "
                  "tushuntiradigan matn"),
    ("tuzilma", "qutilar va ularni bog'lovchi chiziqlar — ierarxiya yoki "
                "tarkib sxemasi"),
    ("iqtibos", "yirik tirnoq belgisi, kursiv matn, muallif qatori"),
    ("formula", "tushunchaning formulasi yirik, ostida belgilar izohi va "
                "u nimani hisoblashi"),
    ("misol", "masala sharti, qadamma-qadam yechim va javob"),
    ("kartalar", "bir xil o'lchamdagi kartalar, har birida sarlavha va "
                 "bir-ikki gaplik izoh"),
    ("yakun", "faqat xulosa matni — rahmat va savollar qatorisiz"),
)

CATEGORIES = dict(CATEGORY_LIST)

SHAPE_NAMES = {
    "split": "matn+rasm yoki ikki ustun", "list": "ro'yxat", "cols": "kartochkalar",
    "steps": "qadamlar", "timeline": "vaqt o'qi", "table": "jadval", "kpi": "ko'rsatkichlar",
    "quote": "iqtibos", "chart": "diagramma", "calc": "diagramma", "formula": "formula",
    "misol": "misol", "rasm": "rasm", "lead": "asosiy fikr", "": "oddiy matn",
}

# ─────────────────────────────────────────────── mavzu oilalari

FAMILIES = deck_shape_families()

GUIDANCE = ("MAVZU OILASI: ⟨name⟩.\n"
            "Shu oilada mazmun qanday ochiladi:\n⟨shape⟩\n\n"
            "RAQAMGA MUNOSABAT: ⟨numbers⟩")

# ─────────────────────────────────────────────── slayd yozish (user prompt)

DEPTH = {
    1: "Tinglovchi — maktab o'quvchisi: sodda til, kundalik misollar.",
    2: "Tinglovchi — talaba: akademik, lekin ravon til.",
    3: "Tinglovchi — mutaxassis: atamalar, raqamlar, manbalar.",
}

USER = {
    "topic": 'Mavzu: "⟨topic⟩"',
    "total": "Taqdimot jami ⟨total⟩ slayddan iborat.",
    "chunk": "Hozir ⟨start⟩-slayddan boshlab ⟨count⟩ ta slayd kerak.",
    "blocks": ("BLOKNI TO'G'RI TANLANG: raqam bo'lsa ko'rsatkich, ketma-ketlik "
               "bo'lsa qadam yoki vaqt o'qi, ikki narsa qiyoslansa ikki ustun "
               "yoki jadval, tasnif bo'lsa jadval, ta'rif yoki bitta fikr bo'lsa "
               "matn va rasm yoki kartochkasiz ro'yxat, mashhur so'z bo'lsa "
               "iqtibos. Kartochka faqat 3-4 ta teng huquqli element uchun — "
               "unga qaytaverma. Ketma-ket ikki slayd bir xil shaklda bo'lmasin "
               "va bitta blok qayta-qayta chiqmasin; lekin mazmun birinchi, "
               "shakl ikkinchi."),
    "outline": ("Taqdimot rejasi (→ bilan belgilangani hozir "
                "yoziladi). Slayd sarlavhasi rejadagi «sarlavha» bilan bir "
                "xil bo'lsin; har slayd faqat o'z sarlavhasidagi masalani "
                "ochsin:\n⟨lines⟩"),
    "written": ("Yozib bo'lingan slaydlar sarlavhalari (mazmunini "
                "takrorlamang, ularning davomi bo'ling): ⟨titles⟩"),
    "used": "Oldingi slaydlarda ochilgan fikrlar (ularni qayta aytmang): ⟨ideas⟩",
    "plan_slide": ("2-slayd — REJA: uni tizim yozilgan slaydlar sarlavhalaridan "
                   "o'zi yig'adi, shuning uchun bu o'rinda faqat bitta "
                   "<section class=\"slide\"> ichida «⟨label⟩» "
                   "sarlavhasini yozing."),
    "last": ("Oxirgi slayd — faqat XULOSA: taqdimotdagi asosiy fikrlar va "
             "yakuniy fikr. Taqdimot rejasini yoki mavzu ta'rifini "
             "qaytarmang, yangi mavzu ochmang."),
    "prefs": "Mijoz istagi: ⟨text⟩",
    "source": "Mijoz bergan material (shundan foydalanib yoz):\n⟨text⟩",
}

SHAPES = {
    "plain": "oddiy matn",
    "header": "Hozirgacha ishlatilgan blok birikmalari:",
    "line": "  ⟨n⟩-slayd: ⟨shape⟩",
    "hard": ("QAT'IY TALAB (⟨start⟩–⟨end⟩-slaydlar): har slayd `<div class=\"body\">` ichidagi "
             "bloklar birikmasi (CSS sinflari) bo'yicha o'zidan oldingi slayddan va shu "
             "bo'lakdagi boshqa slaydlardan FARQ qilsin."),
    "previous": "Oldingi slaydda allaqachon [⟨shape⟩] bor — uni yana ishlatmang.",
    "banned": "Bu birikmalar allaqachon ⟨n⟩ martadan ishlatilgan — endi boshqasini tanlang: ⟨list⟩.",
    "advice": ("Mazmun ishlatilgan shaklga mos kelib qolsa, uni boshqa blok bilan ifodalang "
               "(qadamlar, vaqt o'qi, jadval, ikki ustunli qiyoslash, iqtibos, kartochkalar, "
               "rasmsiz oddiy ro'yxat). Mazmun birinchi, lekin shaklni sababsiz takrorlamang."),
}

CONCLUSION_BRIEF = {
    "uz": "Xulosa: taqdimotdagi asosiy fikrlarni umumlashtirish va yakuniy xulosa "
          "(yangi mavzu ochmang, ta'rif yoki rejani takrorlamang)",
    "uz-cyrl": "Хулоса: тақдимотдаги асосий фикрларни умумлаштириш ва якуний хулоса "
               "(янги мавзу очманг, таъриф ёки режани такрорламанг). Кирилл ёзувида.",
}

BRIEF_FALLBACK = ("⟨topic⟩ — ⟨n⟩-slayd: mavzuning oldingi slaydlarda "
                  "ochilmagan YANGI jihati (ta'rif yoki rejani takrorlamang)")

# ─────────────────────────────────────────────── reja

PLAN = {
    "system": "Sen taqdimot rejasini tuzasan. Faqat JSON qaytar.",
    "chart": ("Rejada kamida ⟨quota⟩ ta slayd 'diagramma' kategoriyasida bo'lsin⟨donut⟩"
              ": diagramma taqdimotni jonlantiradi. Diagramma uchun alohida tahlilchi "
              "HAQIQIY statistik ma'lumot (rasmiy manba, so'nggi yillar) topadi, shuning "
              "uchun diagramma faqat real raqamlar mavjud mavzuga qo'yilsin: iqtisod, "
              "demografiya, ta'lim, sog'liqni saqlash, ekologiya, texnologiya va h.k.\n"),
    "donut": " (ulardan biri ulushlar uchun halqa)",
    "main": (
        'Mavzu: "⟨topic⟩"\n\n'
        "Shu mavzuda ⟨count⟩ slaydli taqdimot rejasini tuz. Har slayd "
        "uchun qisqa sarlavha (2-6 so'z), bir qatorli mazmun va unga mos "
        "joylashuv kategoriyasini ayt.\n\n"
        "Kategoriyalar:\n⟨categories⟩\n\n"
        "MANTIQIY KETMA-KETLIK: slaydlar bir-biridan keyin tabiiy kelsin — "
        "har slayd oldingisining davomi. Har slayd mavzuning BOSHQA jihatini "
        "ochsin: ikki slaydda bir xil voqea, ta'rif yoki fakt "
        "takrorlanmasin va ikkita sarlavha bir narsani aytmasin. Nimadan "
        "boshlash, nima bilan davom etish va qayerda yakunlash kerakligini "
        "mavzuning o'zi aytadi.\n"
        "HIKOYA YO'NALISHI: reja bitta hikoya kabi o'qilsin — muqovadan keyin "
        "tinglovchini mavzuga tortadigan savol yoki ahamiyatli fakt, so'ng mavzu "
        "nega muhimligi (ehtiyoj yoki muammo), keyin asosiy qism (tushuncha, "
        "jarayon, misol, raqam), oxirida natija va amaliy ahamiyat. Qolipni "
        "mavzuning o'zi belgilaydi: tarix voqealar tartibida, fan tushunchadan "
        "qo'llanishga, muammoli mavzu muammodan yechimga boradi.\n"
        "SARLAVHA — FIKR: iloji bo'lsa sarlavha slayd aytadigan fikrni "
        "ifodalasin (\"Kiberhujumlar har yili ko'paymoqda\"), mavzu nomining "
        "o'zi emas (\"Kiberhujumlar\"); u 2-6 so'z va tugal bo'lsin. Ta'rif, "
        "tarkib yoki bo'lim nomi bo'ladigan slaydda qisqa nom ham mos. "
        "Sarlavhadagi har raqam yoki sana slayd mazmunida asoslansin; "
        "ishonchsiz bo'lsa fikrni raqamsiz ifodalang. Muqova sarlavhasi — "
        "mavzuning o'z nomi.\n"
        "Birinchisi — muqova, ikkinchisi — 'reja' (uning mazmunini tizim "
        "o'zi yig'adi), oxirgisi — yakun (XULOSA: shu mavzu bo'yicha asosiy "
        "fikrlar va yakuniy fikr). Xulosa FAQAT oxirgi slaydda. 'reja' "
        "kategoriyasi faqat 2-slayd.\n"
        "Kategoriyani MAZMUNGA QARAB tanlang va bir xillikdan qoching: "
        "raqam → korsatkichlar, ketma-ketlik → jarayon yoki vaqt_oqi, "
        "ikki narsa → qiyoslash, ulush yoki dinamika → diagramma, ta'rif "
        "yoki bitta fikr → matn_rasm yoki iqtibos. 'kartalar' faqat 3-4 ta "
        "teng huquqli element uchun; unga qaytaverma. Ketma-ket ikki slayd "
        "bir xil kategoriyada bo'lmasin (mantiq buni majburlamasa); bir "
        "kategoriya butun rejada 2 martadan ko'p takrorlanmasin ('matn_rasm' "
        "bundan mustasno). 'jadval' kategoriyasi faqat qisqa (3-4 qator) "
        "taqqoslash uchun. Har 10 ta slaydning taxminan 3 tasi 'matn_rasm' "
        "(matn + rasm) bo'lsin, ular bir-biriga ketma-ket kelmasin.\n"),
    "calc": ("Bu HISOB-KITOB mavzusi: rejada formula, ishlangan misol va "
             "diagramma kategoriyalari ham bo'lsin — har formula misol bilan "
             "tasdiqlansin, natijalar diagramma bilan ko'rsatilsin.\n"),
    "family": "Shuningdek mavzu qaysi oilaga tegishli ekanini ayting: ⟨names⟩\n\n",
    "language": "Matn ⟨target⟩.\n",
    "json": 'Faqat JSON: {"fan": "...", "slides": [{"title": "...", "brief": "...", "category": "..."}]}',
}

# ─────────────────────────────────────────────── yozilgan taqdimotni tekshirish

REPAIR = {
    "stray_plan": ("BU SLAYD TAQDIMOT REJASINI TAKRORLAYAPTI — reja faqat 2-slayd. "
                   "Quyidagi mavzu bo'yicha MAZMUNLI slayd yozing (reja yoki mundarija "
                   "emas): ⟨brief⟩"),
    "duplicate": ("BU SLAYD ⟨n⟩-slaydni («⟨title⟩») TAKRORLAYAPTI: bir xil mavzu va "
                  "bir xil faktlar. Uni BUTUNLAY BOSHQA masalaga bag'ishlang — rejadagi shu "
                  "o'rin uchun belgilangan mavzu: ⟨brief⟩. Oldingi slaydlardagi sana, nom va "
                  "faktlarni qaytarmang."),
    "table": ("BU SLAYDDA ZICH JADVAL BOR — tinglovchi uni auditoriyada o'qiy olmaydi. "
              "Xuddi shu mazmunni JADVALSIZ ifodalang: kartochkalar, qiyoslash (ikki "
              "ustun), qadamlar yoki oddiy ro'yxat bilan; slayd oxirida bitta umumlashtiruvchi "
              "gap bo'lsin. Zarur bo'lsa faqat QISQA jadval (ko'pi bilan 4 qator, 3 ustun, "
              "har katak 1-5 so'z) qoldiring. Slayd:\n⟨slide⟩"),
    "chart": "BU SLAYD DIAGRAMMALI BO'LISHI SHART (rejada shunday belgilangan). ⟨note⟩ Mavzu: ⟨brief⟩",
    "chart_replaced": "Bu slayddagi diagramma ma'lumoti almashtirildi. ⟨note⟩ Mavzu: ⟨brief⟩",
    "photo": ("BU SLAYDDA RASM BO'LISHI SHART (rejada shunday belgilangan). Slaydni "
              "MATN VA RASM bloki bilan yozing: bir tomonda fikrni ochgan 2-3 yaxlit "
              "abzats (`par-col` ichida `par`; to'liq, bog'langan gaplar), bir "
              "tomonda `.rasm` bloki (`data-prompt` — rasmning inglizcha tavsifi: "
              "oddiy realistik fotosurat). Mavzu: ⟨brief⟩"),
}

LEADS = {
    "system": "Sen taqdimot muharririsan. Faqat JSON qaytar.",
    "item": "⟨n⟩. Sarlavha: ⟨title⟩\nMatn: ⟨text⟩",
    "prompt": ('Taqdimot mavzusi: "⟨topic⟩".\n'
               "Quyidagi slaydlarning har biri uchun BITTA umumlashtiruvchi gap yozing: slaydning "
               "bosh fikri (12-25 so'z) — nima haqida va nima uchun muhim. Gap slaydning o'z matniga "
               "tayansin, yangi fakt, sana yoki raqam qo'shmang va sarlavhani so'zma-so'z "
               "takrorlamang. Bandlarni sanab chiqmang.\n"
               "Matn ⟨target⟩.\n\n⟨listing⟩\n\n"
               'Faqat JSON: {"leads": [{"n": 3, "lead": "..."}]}'),
}

REWORK = (
    "Bu slayd boshqa slaydlar bilan bir xil shaklda (⟨shape⟩) "
    "va taqdimot bir xil ko'rinib qolmoqda.\n\n"
    "SHU SLAYDNING O'ZINI qayta yozing: sarlavha va MAZMUN (fikrlar, faktlar) "
    "saqlansin, lekin ularni BOSHQA blok bilan ifodalang.\n"
    "Bu taqdimotda allaqachon ishlatilgan shakllar (ularni QAYTARMANG): ⟨taken⟩.\n"
    "Mazmunga mos tanlang: ketma-ketlik → qadamlar yoki vaqt o'qi; ikki narsa → "
    "qiyoslash (ikki ustun) yoki jadval; tasnif → jadval; 2-4 teng element → "
    "kartochkalar (agar ular ko'p ishlatilmagan bo'lsa); bitta chuqur fikr → "
    "kartochkasiz oddiy ro'yxat yoki iqtibos. Yangi fakt o'ylab topmang, "
    "raqam qo'shmang. Rasm ixtiyoriy.\n\n"
    "Javobda faqat bitta <section class=\"slide\"> ... </section> bo'lsin.\n\n"
    "Slayd:\n⟨slide⟩")

THICKEN = (
    "Quyidagi slayd faqat sarlavha va bir-ikki jumladan iborat "
    "(yoki faqat bo'lim nomi yozilgan ajratkich). Bunday varaq "
    "taqdimotda kerak emas.\n\n"
    "Shu slaydni MATN VA RASM bloki bilan qayta yozing: sarlavhadagi "
    "fikr o'sha qolsin, chap tomonda u 2-3 yaxlit abzats bilan ochilsin, o'ng "
    "tomonda `rasm` bloki (ichida rasm chiqmasa turadigan qo'shimcha "
    "matn) bo'lsin. Oddiy `<section class=\"slide\">` — `dark` va "
    "`title big` emas.\n\n"
    "Javobda faqat bitta <section class=\"slide\"> ... </section> "
    "bo'lsin.\n\nSlayd:\n⟨slide⟩")

FIX = (
    "Bu slaydni siz yozgansiz. Brauzerda ochilganda quyidagi xatolar "
    "topildi (« » ichida — xato turgan matn):\n⟨problems⟩\n\n"
    "SHU SLAYDNI QAYTARING — yangisini yozmang. Faqat xato "
    "ko'rsatilgan joylarni tuzating. Qolgan hamma narsa — "
    "`<section>` sinfi, sarlavha, bloklar, ularning tartibi, "
    "sinf nomlari va matnlar — o'zgarmasin.\n\n"
    "Tuzatish yo'llari:\n"
    "- matn qutisiga sig'magan yoki varaqdan chiqib ketgan bo'lsa — "
    "o'sha matnni qisqartiring (ma'nosini saqlab); faqat bu yetmasa "
    "o'sha blokdagi bitta band yoki kartochkani olib tashlang;\n"
    "- matn ustiga matn tushgan bo'lsa — ikkalasidan biri keraksiz "
    "bo'lsa o'chiring, aks holda ikkalasini qisqartiring;\n"
    "- matn ikki marta yozilgan bo'lsa — nusxasini o'chiring;\n"
    "- matn juda mayda bo'lib qolgan bo'lsa — slaydda mazmun ortiqcha: "
    "har matnni 1-2 qisqa gapga keltiring, uzun izohlarni o'chiring, "
    "kerak bo'lsa 1-2 ta band yoki kartochkani olib tashlang (blok "
    "turi o'zgarmasin);\n"
    "- varaqda katta bo'sh joy qolgan bo'lsa — mavjud izohlarni "
    "to'liqroq yozing, yangi blok qo'shmang.\n\n"
    "Javobda faqat bitta <section class=\"slide\"> ... </section> "
    "bo'lsin.\n\nSlayd:\n⟨slide⟩")

# Brauzer topgan xatolar (html_extract) o'zbekcha yoziladi — boshqa tilda ular shu lug'at bilan o'giriladi.
PROBLEM_WORDS: dict = {}

EXPLAIN = {
    "system": "Sen taqdimot matnlarini yozadigan muharrirsan. Javobni ⟨target⟩ yozasan.",
    "prompt": ("Quyida taqdimot slaydining mazmuni berilgan. Undagi "
               "diagramma, jadval yoki ko'rsatkichlarni tushuntiruvchi "
               "2-3 gaplik matn yoz (⟨words⟩ so'zdan oshmasin): raqamlar "
               "nimani bildiradi, nega shunday va undan qanday xulosa "
               "chiqadi.\n"
               "Slaydda allaqachon yozilgan gaplarni takrorlama. Sarlavha, "
               "ro'yxat belgisi, HTML teg va qo'shtirnoq yozma — faqat "
               "tayyor matnning o'zini ber.\n\nSlayd:\n⟨slide⟩"),
}

PLAIN = {
    "system": "Sen taqdimot slaydi matnini yozasan. Faqat JSON qaytar.",
    "conclusion": "xulosa",
    "content": "mazmun",
    "prompt": ('Mavzu: "⟨topic⟩". Taqdimotning ⟨n⟩-slaydi (⟨kind⟩): ⟨brief⟩\n\n'
               "Matn ⟨target⟩. Hujjat yoki nutq matnini so'zma-so'z ko'chirmang, "
               "o'z so'zlaringiz bilan yozing.\n"
               'Faqat JSON: {"title": "slayd sarlavhasi (2-7 so\'z)", '
               '"points": [{"key": "kalit so\'z", "text": "bir-ikki to\'liq gap"}]} '
               "— 3 tadan 5 tagacha band."),
}

# ─────────────────────────────────────────────── diagramma ma'lumoti (chart_data)

CHART = {
    "system": ("Sen statistik ma'lumotlar bo'yicha tahlilchisan: taqdimot slaydidagi diagramma uchun "
               "HAQIQIY raqamlarni berasan. Javobing faqat JSON."),
    "kind_hint": {"halqa": "donut (butunning ulushlari)", "chiziqli": "line (vaqt bo'yicha o'zgarish)",
                  "ustunli": "bar (qiymatlarni solishtirish)"},
    "prompt": (
        'Taqdimot mavzusi: "⟨topic⟩"\n'
        'Slayd sarlavhasi: "⟨title⟩"\n'
        "Slayd mazmuni: ⟨brief⟩\n"
        "Taxminiy diagramma turi: ⟨kind⟩\n\n"
        "Shu slayd uchun BITTA diagramma ma'lumotini ber.\n"
        "• Raqamlar rasmiy yoki taniqli manbalardan bo'lsin: milliy statistika organlari "
        "(O'zbekiston Statistika agentligi va h.k.), Jahon banki, BMT va uning agentliklari, XVF, "
        "OECD, Eurostat, yetakchi tadqiqot markazlari. Har qiymat sen bilgan haqiqiy ma'lumotga mos "
        "kelsin; aniq raqamni bilmasang yaxlitlangan qiymat ber va `approx` ni true qil.\n"
        "• Eng YANGI yillarni ol — sening bilimingdagi oxirgi yilgacha. Kelajak yillar faqat "
        "rasmiy prognoz bo'lsa beriladi va `forecast` true bo'ladi.\n"
        "• Mavzu O'zbekiston bilan bog'liq bo'lsa — O'zbekiston ma'lumoti; aks holda mavzuning "
        "o'z qamrovi (dunyo, mintaqa, soha).\n"
        "• Bu mavzuda ishonchli, tekshirsa bo'ladigan raqam yo'q bo'lsa `ok` ni false qil va "
        "`reason` ga sababini yoz: bunday slayd matn bilan ochiladi. Raqamni o'ylab topma.\n"
        "• 3-7 ta yorliq; har yorliq qisqa — 1-3 so'z (\"Qadimgi Rim\", \"2021\"), izoh qavs ichida emas; "
        "ko'pi bilan 3 ta qator; bir diagrammada bitta birlik. `donut` uchun bitta "
        "qator, qiymatlar yig'indisi ≈ 100 (%). Qiymatlar oddiy sonlar.\n"
        "⟨year_rule⟩\n"
        "TIL TALABI (yorliqlar, qator nomlari, birlik, manba): ⟨language_rule⟩\n"
        'Faqat JSON: {"ok": true, "kind": "line|bar|donut", "labels": ["2019", "2020"], '
        '"series": [{"name": "...", "values": [1.5, 2.0]}], "unit": "%", "xlabel": "Yil", '
        '"source": "Tashkilot nomi, yil", "approx": false, "forecast": false, "reason": ""}'),
    "value": "qiymat",
    "note": ("TAYYOR DIAGRAMMA (AI bergan HAQIQIY ma'lumot): ⟨rows⟩⟨unit⟩. Manba: ⟨source⟩.⟨extra⟩ "
             "Slaydda aynan shu blokni qo'ying (raqamlarni o'zgartirmang): ⟨block⟩ "
             "va ostiga shu raqamlardan kelib chiqadigan 2-4 gaplik izoh yozing: nima ko'rsatilgani, "
             "eng muhim o'zgarish va xulosa."),
    "approx": " Raqamlar taxminiy (yaxlitlangan).",
    "forecast": " Bu rasmiy prognoz.",
    "fallback": ("Bu mavzu uchun ishonchli statistik ma'lumot topilmadi, shuning uchun diagramma uchun mavzuga mos, "
                 "tushunchani ko'rsatuvchi NAMUNAVIY ma'lumotni o'zingiz tuzing (3-6 yorliq, bitta birlik; haqiqiy "
                 "statistika deb ko'rsatmang, manba yoki 'tadqiqotlar ko'rsatdi' yozmang) va slaydning izohi oxiriga "
                 "«⟨illustrative⟩.» deb yozing. Diagramma bloki slaydda bo'lishi shart."),
}

# ─────────────────────────────────────────────── saytda bitta sahifani qayta yozish (slide_edit)

EDIT = {
    "system": "Sen taqdimot art-direktorisan. Slaydni rejalashtirasan. Faqat JSON qaytar.",
    "plan": (
        'Taqdimot mavzusi: "⟨topic⟩". Taqdimotda ⟨total⟩ ta slayd bor:\n⟨lines⟩\n\n'
        "Mijoz ⟨n⟩-slaydni («⟨title⟩», hozir: ⟨shape⟩) qayta qilishni so'ramoqda.\n"
        "Mijoz iltimosi (istalgan tilda): «⟨instruction⟩»\n\n"
        "Iltimosni shu BITTA slayd rejasiga aylantir. Joylashuv kategoriyalari:\n⟨categories⟩\n\n"
        "Yo'riqnoma:\n"
        "- Mijoz aytganini eng yaxshi beradigan kategoriyani tanla: doiraviy (halqa) diagramma, "
        "ustunli yoki chiziqli diagramma → 'diagramma', chart_kind 'halqa' / 'ustunli' / 'chiziqli'; "
        "rasm va matn → 'matn_rasm'; qadamlar → 'jarayon'; sanalar → 'vaqt_oqi'; "
        "qiyoslash → 'qiyoslash' va h.k. Iltimos faqat so'z yoki ohang haqida bo'lsa, hozirgi "
        "kategoriyani qoldir.\n"
        "- Mijoz boshqa mavzu so'ramasa, slayd mavzusi (u shu taqdimot hikoyasining bir qismi) "
        "saqlanadi; mavzu saqlansa sarlavha ham o'zgarmaydi.\n"
        "- 'reja' faqat 2-slayd, 'muqova' faqat 1-slayd uchun.\n"
        "- Matn tili: ⟨target⟩.\n"
        'Faqat JSON: {"category": "...", "title": "2-6 so\'z", "brief": "bitta gap: slayd nimani '
        'aytadi", "chart_kind": "halqa|ustunli|chiziqli|"}'),
    "request": "MIJOZNING SHU SLAYD UCHUN ILTIMOSI — u birinchi o'rinda, aynan aytganini bajaring: «⟨instruction⟩».",
    "redo": "⟨total⟩ ta slayddan ⟨n⟩-slayd QAYTA yozilmoqda. Joylashuv kategoriyasi: [⟨category⟩] — ⟨note⟩.",
    "neighbours": ("Qo'shni slaydlar: oldingisi «⟨previous⟩», keyingisi «⟨next⟩». Taqdimot mavzusi, ohangi va "
                   "tili saqlansin; boshqa slaydlar aytmagan fikrni ayting va u qo'shnilari orasida tabiiy kelsin."),
    "photo": ("Slaydni MATN + RASM qilib yozing: bir tomonda `data-prompt` li `.rasm` bloki (oddiy realistik "
              "fotosuratning inglizcha tavsifi, rasm ichida yozuv yo'q), boshqa tomonda 2-3 ta yaxlit abzats "
              "(`par-col` ichida `par`; to'liq, bog'langan gaplar)."),
    "chart_retry": ("Slaydda yuqorida tasvirlangan diagramma bloki (`chart` sinfi) bo'lishi shart: u bosh "
                    "gapdan keyin turadi va ostida diagramma nimani ko'rsatishini tushuntiruvchi 2-4 gap bo'ladi."),
}

# Bugungi sana va yillar qoidasi (timeframe) — o'zbekcha.
YEAR_RULE = None
