"""Huquqiy sahifalar: /oferta, /tolov-va-qaytarish, /xavfsizlik.

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

PAGES = {"oferta": OFERTA, "tolov-va-qaytarish": TOLOV, "xavfsizlik": XAVFSIZLIK}
LINKS = (("oferta", "Ommaviy oferta"), ("tolov-va-qaytarish", "To'lov va qaytarish"),
         ("xavfsizlik", "To'lov xavfsizligi"))

TEMPLATE = """<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{canonical}">
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
</style>
</head>
<body>
<header>
  <div class="wrap head-in">
    <a class="logo" href="/" aria-label="Edufayl"><img src="/static/logo.jpg" alt="Edufayl" width="44" height="44"></a>
    <a class="create" href="/">Bosh sahifa</a>
  </div>
</header>
<main class="wrap landing legal">
  <nav class="crumbs"><a href="/">Edufayl</a> / {h1}</nav>
  <nav class="tabs" aria-label="Huquqiy ma'lumotlar">{tabs}</nav>
  <section class="hero-l"><h1>{h1}</h1><p class="lead">{lead}</p></section>
  {sections}
  <section class="about"><h2>Ijrochi rekvizitlari va aloqa</h2><dl class="req">{requisites}</dl></section>
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


def requisites() -> list:
    """(nomi, qiymati) — faqat to'ldirilganlari."""
    contact = config.ADMIN_CONTACT
    rows = (("Ijrochi", config.LEGAL_NAME), ("STIR (INN)", config.LEGAL_STIR), ("Manzil", config.LEGAL_ADDRESS),
            ("Bank rekvizitlari", config.LEGAL_BANK), ("Telefon", config.LEGAL_PHONE), ("E-pochta", config.LEGAL_EMAIL),
            ("Telegram", contact), ("Sayt", "edufayl.org"))
    return [(name, value) for name, value in rows if value]


def footer_links() -> str:
    """Boshqa sahifalar pastiga qo'yiladigan havolalar."""
    return " · ".join(f'<a href="/{slug}">{_esc(name)}</a>' for slug, name in LINKS)


def _block(block, values: dict) -> str:
    if isinstance(block, tuple):
        return "<ul>" + "".join(f"<li>{_esc(item.format(**values))}</li>" for item in block) + "</ul>"
    return f"<p>{_esc(block.format(**values))}</p>"


def render(slug: str, origin: str) -> str:
    page = PAGES[slug]
    values = _values(origin)
    canonical = f"{origin}/{slug}"
    lead = page["lead"].format(**values)
    sections = "".join(
        f'<section class="about"><h2>{_esc(heading)}</h2>{"".join(_block(b, values) for b in blocks)}</section>'
        for heading, blocks in page["sections"])
    tabs = "".join(f'<a href="/{s}"{" aria-current=\"page\"" if s == slug else ""}>{_esc(name)}</a>'
                   for s, name in LINKS)
    reqs = "".join(f"<dt>{_esc(name)}</dt><dd>{_esc(value)}</dd>" for name, value in requisites())
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": page["h1"], "url": canonical,
          "description": lead, "publisher": {"@type": "Organization", "name": "Edufayl", "url": origin + "/"}}
    return TEMPLATE.format(
        title=_esc(page["title"]), desc=_esc(lead[:300]), canonical=_esc(canonical),
        ld=json.dumps(ld, ensure_ascii=False).replace("</", "<\\/"), h1=_esc(page["h1"]), lead=_esc(lead),
        tabs=tabs, sections=sections, requisites=reqs, footer=f"Edufayl — edufayl.org · {footer_links()}")


def _handler(slug: str):
    async def handle(request: web.Request) -> web.Response:
        from webapp import store

        text = render(slug, store._origin(request))
        return web.Response(text=store._with_style_version(text), content_type="text/html")
    return handle


def setup_legal_routes(app: web.Application) -> None:
    for slug in PAGES:
        app.router.add_get(f"/{slug}", _handler(slug))
