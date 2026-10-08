"""Xizmat sahifalari: /taqdimot, /mustaqil-ish, /referat, /kurs-ishi ...

Odamlar Google'da "taqdimot", "mustaqil ish", "referat yozib berish" deb izlaydi. Bosh sahifa bitta —
har xizmat uchun alohida, serverda chiziladigan, o'zbekcha matnli sahifa bo'lsa, Google har birini
o'z so'zi bo'yicha ko'rsata oladi. Sahifada: nima qilinadi, qanday ishlaydi, nimalar kiradi, savol-javob,
shu turdagi tayyor ishlar va «Hoziroq yaratish» tugmasi (bosh sahifadagi yaratish oynasi shu xizmat bilan ochiladi).
"""
import html
import json
import logging
from pathlib import Path

from aiohttp import web

logger = logging.getLogger(__name__)

LANDING_HTML = Path(__file__).parent / "landing.html"

COMMON_STEPS = (
    ("Mavzuni yozing", "Til, hajm va kerakli sozlamalarni tanlang. Xohlasangiz, o'z talablaringizni yozing "
                       "yoki manba (PDF, DOCX, sayt havolasi) bering."),
    ("AI tayyorlaydi", "Reja, matn, jadval va rasmlar bir necha daqiqada tayyorlanadi. Jarayon sahifada ko'rinib turadi."),
    ("Yuklab oling", "Tayyor faylni yuklab oling va xohlagancha tahrirlang. Nusxasi Telegram botga ham yuboriladi."),
)

COMMON_FAQ = (
    ("Ro'yxatdan o'tish kerakmi?", "Ha, Google akkaunt yoki Telegram orqali bir bosishda kiriladi. Parol kerak emas, "
                                   "hisob birinchi kirishda o'zi ochiladi."),
    ("To'lov qanday qilinadi?", "Hamyonni to'ldirib, chekni saytga yuklaysiz. Admin tasdiqlagach, summa hisobingizga "
                                "tushadi. Narx buyurtma berishdan oldin aniq ko'rsatiladi."),
    ("Faylni tahrirlash mumkinmi?", "Ha. Fayl oddiy Word (DOCX) yoki PowerPoint (PPTX) ko'rinishida beriladi — matnini, "
                                    "rasmlarini va tartibini o'zingiz o'zgartira olasiz."),
)

# slug → sahifa ma'lumoti. `kind` — bosh sahifadagi yaratish oynasining xizmati, `types` — do'kondagi ish turlari.
LANDINGS = {
    "taqdimot": {
        "kind": "premium_presentation",
        "types": ("taqdimot", "premium_taqdimot"),
        "title": "Taqdimot tayyorlash onlayn — AI bilan prezentatsiya (PPTX) | Edufayl",
        "h1": "Taqdimot tayyorlash — AI bilan bir necha daqiqada",
        "lead": "Mavzuni yozing — Edufayl reja, slayd matni, diagramma, jadval va rasmlari bilan to'liq taqdimot "
                "(prezentatsiya) tayyorlaydi. Natija tahrirlanadigan PowerPoint (PPTX) fayl: uni darsda, seminarda "
                "yoki himoyada bemalol ishlatasiz.",
        "includes": ("5 dan 30 tagacha slayd — sonini o'zingiz tanlaysiz",
                     "Muqova, reja, asosiy qism, xulosa va foydalanilgan adabiyotlar",
                     "Diagramma, jadval, infografika va mavzuga mos rasmlar",
                     "5 xil uslub va rang tanlash, o'zbek (lotin va kirill), rus, ingliz, qozoq tillari",
                     "Har bir slaydni saytning o'zida varaqlab ko'rish va AI ga qayta yozdirish"),
        "faq": (("Taqdimot qancha vaqtda tayyor bo'ladi?", "Odatda 2–5 daqiqada. Slayd soni ko'p bo'lsa, biroz ko'proq."),
                ("Qaysi formatda beriladi?", "PowerPoint (PPTX). Uni PowerPoint, Google Slides yoki WPS'da ochish mumkin.")),
    },
    "mustaqil-ish": {
        "kind": "independent_work",
        "types": ("mustaqil_ish",),
        "title": "Mustaqil ish tayyorlash onlayn — AI bilan (Word, DOCX) | Edufayl",
        "h1": "Mustaqil ish tayyorlash — AI bilan, Word faylida",
        "lead": "Mavzuni yozing — Edufayl titul varag'i, reja, kirish, asosiy qism, xulosa va adabiyotlar ro'yxati bilan "
                "to'liq mustaqil ish (SRS) tayyorlaydi. Hajmini o'zingiz tanlaysiz, fayl Word (DOCX) ko'rinishida beriladi.",
        "includes": ("Titul varag'i, reja (mundarija) va varaq raqamlari",
                     "Kirish, asosiy qism bo'limlari, xulosa",
                     "Foydalanilgan adabiyotlar ro'yxati",
                     "Hajm: 10–15 dan 25–30 varaqqacha",
                     "O'zbek (lotin va kirill), rus, ingliz, qozoq tillarida"),
        "faq": (("Mustaqil ish necha varaq bo'ladi?", "Buyurtma berishda hajmni tanlaysiz: 10–15, 15–20, 20–25 yoki 25–30 varaq."),
                ("Rejani o'zim bersam bo'ladimi?", "Ha, o'z rejangizni yozsangiz, ish aynan shu reja bo'yicha yoziladi.")),
    },
    "referat": {
        "kind": "referat",
        "types": ("referat",),
        "title": "Referat tayyorlash onlayn — AI bilan referat yozish (DOCX) | Edufayl",
        "h1": "Referat tayyorlash — AI bilan, tayyor Word fayl",
        "lead": "Mavzuni yozing — Edufayl titul varag'i, reja, kirish, asosiy qism, xulosa va adabiyotlar ro'yxati bilan "
                "referat tayyorlaydi. Natija tahrirlanadigan Word (DOCX) fayl.",
        "includes": ("Titul varag'i va reja (mundarija)",
                     "Mavzu bo'yicha izchil yozilgan asosiy qism",
                     "Xulosa va foydalanilgan adabiyotlar",
                     "Hajmni o'zingiz tanlaysiz",
                     "O'zbek (lotin va kirill), rus, ingliz, qozoq tillarida"),
        "faq": (("Referat bilan mustaqil ishning farqi nima?", "Tuzilishi o'xshash; referat odatda mavzuni qisqaroq yoritadi. "
                                                            "Ikkalasini ham hajmini tanlab buyurtma qilish mumkin."),),
    },
    "kurs-ishi": {
        "kind": "course_work",
        "types": ("kurs_ishi",),
        "title": "Kurs ishi tayyorlash onlayn — AI bilan kurs ishi yozish | Edufayl",
        "h1": "Kurs ishi tayyorlash — boblar, mundarija va adabiyotlar bilan",
        "lead": "Mavzuni yozing — Edufayl uch bobli kurs ishini titul varag'i, mundarija (varaq raqamlari bilan), kirish, "
                "boblar, xulosa va adabiyotlar ro'yxati bilan tayyorlaydi. Fayl Word (DOCX) ko'rinishida.",
        "includes": ("Titul varag'i, mundarija va varaq raqamlari",
                     "Kirish: dolzarblik, maqsad, vazifalar, obyekt va predmet",
                     "Uch bob va ularning bandlari (o'z rejangiz ham bo'lishi mumkin)",
                     "Xulosa va takliflar, foydalanilgan adabiyotlar",
                     "Jadval va diagrammalar (mavzuga mos bo'lsa)"),
        "faq": (("Kurs ishining rejasini o'zim bersam bo'ladimi?", "Ha, rejangizni yozsangiz, AI uni tekshirib, aynan shu "
                                                                  "reja bo'yicha yozadi."),),
    },
    "maqola": {
        "kind": "article",
        "types": ("maqola",),
        "title": "Ilmiy maqola tayyorlash — AI bilan maqola yozish (IMRAD) | Edufayl",
        "h1": "Ilmiy maqola tayyorlash — IMRAD tuzilmasida",
        "lead": "Mavzuni yozing — Edufayl annotatsiya, kalit so'zlar, kirish, usullar, natijalar, muhokama, xulosa va "
                "adabiyotlar bilan ilmiy maqola tayyorlaydi. Fayl Word (DOCX) ko'rinishida.",
        "includes": ("Annotatsiya va kalit so'zlar", "IMRAD: kirish, usullar, natijalar, muhokama",
                     "Xulosa va adabiyotlar ro'yxati", "Bir necha tilda annotatsiya"),
        "faq": (),
    },
    "tezis": {
        "kind": "thesis",
        "types": ("tezis",),
        "title": "Tezis tayyorlash — konferensiya tezisi AI bilan | Edufayl",
        "h1": "Konferensiya tezisi tayyorlash",
        "lead": "Mavzuni yozing — Edufayl konferensiya talablariga mos qisqa va aniq tezis tayyorlaydi: dolzarblik, "
                "maqsad, asosiy natijalar va xulosa. Fayl Word (DOCX) ko'rinishida.",
        "includes": ("Dolzarblik va maqsad", "Asosiy fikrlar va natijalar", "Xulosa va adabiyotlar"),
        "faq": (),
    },
    "diplom-ishi": {
        "kind": "diploma_work",
        "types": ("diplom_ishi",),
        "title": "Diplom ishi tayyorlash — AI bilan diplom ishi | Edufayl",
        "h1": "Diplom ishi tayyorlash — boblar va qo'shimchalar bilan",
        "lead": "Mavzuni yozing — Edufayl boblarga bo'lingan katta hajmli diplom ishini mundarija, kirish, boblar, "
                "xulosa, adabiyotlar va qo'shimchalar bilan tayyorlaydi. Fayl Word (DOCX) ko'rinishida.",
        "includes": ("Titul varag'i va mundarija", "Kirish va bir necha bob", "Xulosa, takliflar va adabiyotlar",
                     "Jadval va diagrammalar"),
        "faq": (),
    },
    "bitiruv-ishi": {
        "kind": "bitiruv_ishi",
        "types": ("bitiruv_ishi",),
        "title": "Bitiruv malakaviy ishi (BMI) tayyorlash — AI bilan | Edufayl",
        "h1": "Bitiruv malakaviy ishi (BMI) tayyorlash",
        "lead": "Mavzuni yozing — Edufayl bitiruv malakaviy ishini mundarija, kirish, boblar, xulosa va adabiyotlar "
                "ro'yxati bilan tayyorlaydi. Fayl Word (DOCX) ko'rinishida.",
        "includes": ("Titul varag'i va mundarija", "Kirish, boblar va bandlar", "Xulosa va adabiyotlar"),
        "faq": (),
    },
    "dissertatsiya": {
        "kind": "dissertatsiya",
        "types": ("dissertatsiya",),
        "title": "Magistrlik dissertatsiyasi tayyorlash — AI bilan | Edufayl",
        "h1": "Magistrlik dissertatsiyasi tayyorlash",
        "lead": "Mavzuni yozing — Edufayl 60–100 varaqli magistrlik dissertatsiyasini mundarija, kirish, boblar, "
                "xulosa va adabiyotlar bilan tayyorlaydi. Fayl Word (DOCX) ko'rinishida.",
        "includes": ("Mundarija va kirish (dolzarblik, maqsad, vazifalar, ilmiy yangilik)",
                     "Nazariy, tahliliy va amaliy boblar", "Xulosa, takliflar va adabiyotlar"),
        "faq": (),
    },
}

# Bosh sahifa pastidagi «Xizmatlar» ro'yxati shu tartibda (nomlari sayt lug'atida bor).
NAV = (("taqdimot", "Taqdimot"), ("mustaqil-ish", "Mustaqil ish"), ("referat", "Referat"), ("kurs-ishi", "Kurs ishi"),
       ("maqola", "Maqola"), ("tezis", "Tezis"), ("diplom-ishi", "Diplom ishi"), ("bitiruv-ishi", "Bitiruv ishi"),
       ("dissertatsiya", "Dissertatsiya"))


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


async def _ready_items(types, limit: int = 8):
    from database.database import Database

    found, total = [], 0
    for work_type in types:
        result = await Database.list_store_items(work_type=work_type, sort="popular", limit=limit)
        found += result["items"]
        total += result["total"]
    found.sort(key=lambda r: (r.get("sale_count") or 0), reverse=True)
    return found[:limit], total


def _handler(slug: str):
    async def handle(request: web.Request) -> web.Response:
        from webapp import store
        from services.store_seo import plural

        page = LANDINGS[slug]
        origin = store._origin(request)
        canonical = f"{origin}/{slug}"
        create = f"/#yaratish?kind={page['kind']}"
        items, total = await _ready_items(page["types"])
        main_type = page["types"][0]

        steps = "".join(f"<li><b>{_esc(t)}</b><span>{_esc(d)}</span></li>" for t, d in COMMON_STEPS)
        includes = "".join(f"<li>{_esc(line)}</li>" for line in page["includes"])
        faq = list(page["faq"]) + list(COMMON_FAQ)
        faq_html = "".join(f"<details><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>" for q, a in faq)
        ready = ""
        if items:
            ready = (f'<section class="related"><h2>Tayyor {_esc(plural(main_type))}</h2>'
                     f'<p class="cat-intro">Kerakli mavzu tayyor bo\'lsa — ko\'rib, darhol oling ({total} ta).</p>'
                     f'<div class="grid">{"".join(store._card(r) for r in items)}</div>'
                     f'<p><a class="more-link" href="{_esc(store._catalog_path(main_type))}">Hammasini ko\'rish →</a>'
                     f'</p></section>')
        others = " · ".join(f'<a href="/{s}">{_esc(name)}</a>' for s, name in NAV if s != slug)

        ld = {"@context": "https://schema.org", "@graph": [
            {"@type": "Service", "name": page["h1"], "description": page["lead"], "url": canonical,
             "provider": {"@type": "Organization", "name": "Edufayl", "url": origin + "/"},
             "areaServed": "UZ", "availableLanguage": ["uz", "ru", "en", "kk"]},
            {"@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Edufayl", "item": origin + "/"},
                {"@type": "ListItem", "position": 2, "name": page["h1"], "item": canonical}]},
        ]}

        try:
            text = LANDING_HTML.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("Xizmat sahifasi o'qilmadi: %s", exc)
            return web.Response(text="Sahifa vaqtincha ishlamayapti", status=503)
        values = {
            "{{PAGE_TITLE}}": _esc(page["title"]),
            "{{META_DESC}}": _esc(page["lead"][:300]),
            "{{CANONICAL}}": _esc(canonical),
            "{{OG_IMAGE}}": _esc(origin + "/static/logo.jpg"),
            "{{JSONLD}}": json.dumps(ld, ensure_ascii=False).replace("</", "<\\/"),
            "{{H1}}": _esc(page["h1"]),
            "{{LEAD}}": _esc(page["lead"]),
            "{{CREATE}}": _esc(create),
            "{{STEPS}}": steps,
            "{{INCLUDES}}": includes,
            "{{FAQ}}": faq_html,
            "{{READY}}": ready,
            "{{OTHERS}}": others,
            "__BOT_URL__": _esc(store._bot_url() or "__nobot__"),
        }
        for token, value in values.items():
            text = text.replace(token, value)
        return web.Response(text=store._with_style_version(text), content_type="text/html")
    return handle


def setup_landing_routes(app: web.Application) -> None:
    for slug in LANDINGS:
        app.router.add_get(f"/{slug}", _handler(slug))
