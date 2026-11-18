"""«Sayt rejimi»: bot pullik xizmatlarni o'zi sotmaydi — xizmat tugmasi saytda ochiladi.

Admin «🎛 Funksiyalar boshqaruvi»dagi bitta tugma bilan yoqiladi/o'chiriladi (`FEATURE`). Sukut bo'yicha
O'CHIQ: bot hozirgidek ishlaydi — buyurtma, to'lov (karta, Click, Payme, Uzum, Stars) hammasi botda.
Yoqilganda bot kodi o'chirilmaydi: faqat kirish nuqtalari (asosiy menyu va «Boshqa xizmatlar» tugmalari)
saytga yo'naltiriladi; tugma o'chirilsa hammasi darhol avvalgi holiga qaytadi.

Holat bazada saqlanadi va xotirada (`ON`) ham turadi: menyu klaviaturasi sinxron yasaladi, har bosishda
bazaga murojaat qilinmasin. Ishga tushishda `load()`, admin tugmasida `set()` chaqiriladi.
"""
import logging
import os

log = logging.getLogger(__name__)

FEATURE = "bot_site_mode"
ON = False

# Asosiy menyu tugmasi → saytdagi xizmat (None — saytda hali yo'q).
MENU = {
    "main_menu.presentation": "premium_presentation",
    "main_menu.premium_presentation": "premium_presentation",
    "main_menu.independent_work": "independent_work",
    "main_menu.referat": "referat",
    "main_menu.course_work": "course_work",
    "main_menu.presentation_3d": "presentation_3d",
    "main_menu.project_work": None,
    "main_menu.mahsus_ishlanma": None,
}
# «Boshqa xizmatlar» (`os:<kalit>`) → saytdagi xizmat; ro'yxatda yo'q kalitlar (bepul: PPTX→PDF, faylni
# tahrirlash) botda o'zgarishsiz ishlayveradi.
OTHER = {
    "dissertatsiya": "dissertatsiya",
    "bitiruv_ishi": "bitiruv_ishi",
    "diploma_work": "diploma_work",
    "tezis": "thesis",
    "maqola": "article",
    "pdf_convert": None,
    "book_translate": None,
    "test": None,
}
# «💳 To'lov qilish» va «💎 Mening hisobim» o'rniga — saytdagi kabinet.
ACCOUNT_KEYS = ("main_menu.payment", "main_menu.my_account")


def login_url_buttons() -> bool:
    """`SITE_LOGIN_URL=1` — Telegramning «Login URL» tugmasi (BotFather'da /setdomain qilingandan keyin)."""
    return os.getenv("SITE_LOGIN_URL", "0").lower() in {"1", "true", "yes"}


async def load(db) -> bool:
    global ON
    try:
        ON = bool(await db.get_feature_status(FEATURE, default=False))
    except Exception as exc:
        log.warning("Sayt rejimi holati o'qilmadi (o'chiq deb olinadi): %s", exc)
        ON = False
    return ON


async def set(db, enabled: bool) -> None:
    global ON
    await db.set_feature_status(FEATURE, bool(enabled))
    ON = bool(enabled)
