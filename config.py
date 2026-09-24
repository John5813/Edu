import os

# Bot configuration - no default values for security
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
FAL_API_KEY = os.getenv("FAL_API_KEY")

# Telegram Stars conversion rate: 1 Star ≈ 165 so'm (bot developer receive rate)
STARS_RATE = 165

# Media generation prices (in so'm)
IMAGE_PRICE = 2000
IMAGE_EDIT_PRICE = 2000

# Legacy single-model video prices (kept for backward compat)
VIDEO_PRICES = {5: 5000, 10: 10000}

# Per-model video prices (in so'm) — always max duration:
# Grok Video:   $0.10/s × 10s = $1.00 → 12,500 som → charge 18,000
# Veo 3.1:      $0.15/s × 10s = $1.50 → 18,750 som → charge 26,000
# Kling v3 Pro: $0.14/s × 10s = $1.40 → 17,500 som → charge 24,000
VIDEO_MODEL_PRICES = {
    "grok":  18_000,
    "veo":   26_000,
    "kling": 24_000,
}
IMG2VIDEO_PRICE = 13_000
VID2VID_PRICE = 5000

def som_to_stars(price_som: int) -> int:
    """Convert som price to equivalent Telegram Stars (ceiling)"""
    import math
    return math.ceil(price_som / STARS_RATE)

# Validate required environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
# TOGETHER_API_KEY is optional - images won't be generated if not provided

# Admin configuration
ADMIN_IDS = list(map(int, filter(None, os.getenv("ADMIN_IDS", "5304482470").split(",")))) if os.getenv("ADMIN_IDS") else [5304482470]

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot.db")

# Payment configuration
PAYMENT_CARD = os.getenv("PAYMENT_CARD", "9860160606136655")
PAYMENT_CARD_2 = os.getenv("PAYMENT_CARD_2", "9860160104562378")
PAYMENT_CARD_OWNER = os.getenv("PAYMENT_CARD_OWNER", "Moʻydinov Javlonbek")

# Payment amounts with descriptions (for reference - actual values in keyboards.py)
PAYMENT_OPTIONS_REFERENCE = [
    (10000, "10,000 so'm"),
    (15000, "15,000 so'm"),
    (20000, "20,000 so'm"),
    (25000, "25,000 so'm")
]

# PDF to DOCX conversion prices (in som) based on page count
PDF_CONVERT_PRICES = {
    "1_30": 5000,
    "31_100": 10000,
    "101_plus": 20000,
}

# Book translation prices (in som) based on word count
BOOK_TRANSLATE_PRICES = {
    5000: 15_000,
    15000: 30_000,
    40000: 60_000,
    999999999: 100_000,
}

# ── Telegram fayl cheklovlari
#
# Oddiy Bot API bot'ga 20 MB dan katta faylni bermaydi va 50 MB dan katta
# fayl yuborishga ruxsat bermaydi. Serverda mahalliy Bot API server
# (telegram-bot-api) ishga tushirilsa, ikkala chegara 2000 MB ga ko'tariladi:
#   TELEGRAM_API_SERVER=http://127.0.0.1:8081
# Server Docker ichida bo'lsa va fayllari boshqa papkada ko'rinsa:
#   TELEGRAM_API_FILES_SERVER_DIR=/var/lib/telegram-bot-api
#   TELEGRAM_API_FILES_LOCAL_DIR=/srv/telegram-bot-api
TELEGRAM_API_SERVER = os.getenv("TELEGRAM_API_SERVER", "").strip().rstrip("/")
TELEGRAM_API_FILES_SERVER_DIR = os.getenv("TELEGRAM_API_FILES_SERVER_DIR", "").strip()
TELEGRAM_API_FILES_LOCAL_DIR = os.getenv("TELEGRAM_API_FILES_LOCAL_DIR", "").strip()
_MB = 1024 * 1024
TELEGRAM_DOWNLOAD_LIMIT = (2000 if TELEGRAM_API_SERVER else 20) * _MB
TELEGRAM_UPLOAD_LIMIT = (2000 if TELEGRAM_API_SERVER else 50) * _MB

# Kitob tarjimasi uchun eng katta fayl. Telegram orqali sig'magani sayt
# orqali yuklanadi (bot bir martalik havola beradi).
BOOK_MAX_UPLOAD_MB = int(os.getenv("BOOK_MAX_UPLOAD_MB", "150"))

# Katta PDF kitob tarjimasi uchun modellar zanjiri: birinchisi ishlamasa
# keyingisi. `BOOK_TRANSLATE_MODEL` muhit o'zgaruvchisi bilan boshqasini
# birinchi qo'yish mumkin. Gemini 2.5 Flash — sifat/narx bo'yicha eng mosi:
# 200 betlik kitob taxminan $0.5-1 turadi.
BOOK_TRANSLATE_MODELS = [
    "google/gemini-2.5-flash",
    "google/gemini-2.0-flash-001",
    "openai/gpt-4.1-mini",
]

# Article prices (in som)
ARTICLE_PRICES = {
    "4_5": 5000,
    "5_7": 7000,
    "7_10": 10000,
}

# Dynamic pricing based on slide/page count (in som)
PRESENTATION_PRICES = {
    10: 5000,
    15: 7000,
    20: 10000
}

DOCUMENT_PRICES = {
    "10_15": 5000,
    "15_20": 7000,
    "20_25": 10000,
    "25_30": 12000,
    "tezis": 5000
}

# Course work prices (with chapters)
COURSE_WORK_PRICES = {
    "15_20_3": 10000,
    "20_25_3": 15000,
    "25_30_3": 20000,
    "30_35_3": 25000,
    # Kurs ishi qaysi hajmda bo'lmasin uch bobdan iborat: shunday
    # yoziladi. Katta hajmda bob qo'shilmaydi, har bobga qo'shimcha
    # kichik bo'lim qo'shiladi — aks holda bitta kichik bo'limga 1400
    # so'zdan tushib, matn suyulib ketardi.
    #
    # Narx zinapoyaning +5 000 ritmini davom ettiradi. Ilgari u varoq soniga
    # to'g'ri proporsional edi va varog'iga tushadigan narx hajm oshgani sari
    # ko'tarilib borardi (500 → 833) — ya'ni ko'p buyurtma qilgan mijoz
    # qimmatroq to'lardi. Endi aksincha: 40-50 da 600, 50-60 da 583 so'm.
    "40_50_3": 30000,
    "50_60_3": 35000,
}

# Diploma work prices (same structure as course work)
DIPLOMA_WORK_PRICES = {
    "15_20_2": 10000,
    "20_25_2": 15000,
    "25_30_3": 20000,
    "30_35_3": 25000
}

# Graduation qualifying work prices (bitiruv malakaviy ishi)
GRADUATION_WORK_PRICES = {
    "30_40_3": 35000,
    "40_50_3": 50000,
    "50_60_3": 65000,
    "60_70_3": 80000,
}

# Master's dissertation prices (Magistrlik dissertatsiyasi)
DISSERTATION_PRICES = {
    "60_70_3":  90000,
    "70_80_3":  110000,
    "80_90_4":  140000,
    "90_100_4": 170000,
}

# Loyiha ishi — hajmi bo'yicha ikki daraja
# Loyiha ishi hajmi. Ilgari ikkita variant bor edi ("standart" va
# "kengaytirilgan") va ular faqat bo'lim matnini cho'zardi — bo'limlar soniga
# ta'sir qilmasdi. Shu sababli "~15-20 bet" deb yozilgan tugma 40 varoqli
# hujjat berardi. Endi varoq soni haqiqiy chegara: unga qarab mijoz nechta
# mazmun bloki tanlay olishi ham, matn uzunligi ham belgilanadi
# (`services/project_work/layout.py`).
PROJECT_WORK_SIZES = {
    "10_15": {"pages": (10, 15), "price": 10_000},
    "15_20": {"pages": (15, 20), "price": 15_000},
    "20_25": {"pages": (20, 25), "price": 20_000},
    "25_30": {"pages": (25, 30), "price": 25_000},
    "30_40": {"pages": (30, 40), "price": 35_000},
}

# To'lovgacha yetib kelgan eski buyurtmalar holatida hali eski kalit turishi
# mumkin — ular yangi hajmga o'giriladi, aks holda KeyError bilan yiqilardi.
_LEGACY_SIZE_KEYS = {"standart": "15_20", "keng": "25_30"}


def project_work_size(key: str) -> dict:
    """Hajm kaliti bo'yicha varoq oralig'i va narxi."""
    key = _LEGACY_SIZE_KEYS.get(key, key)
    return PROJECT_WORK_SIZES.get(key, PROJECT_WORK_SIZES["15_20"])

# Extras prices (in so'm) added on top of base document price
EXTRAS_PRICES = {
    "formulas":   1000,
    "images":     2000,
    "scheme":     1000,
    "tables":     1000,
    "glossary":   1000,
    "statistics": 1000,
}

# AI configuration (OpenRouter)
# Support both Replit AI Integrations and a user-provided OpenRouter key.
AI_INTEGRATIONS_OPENROUTER_API_KEY = (
    os.getenv("AI_INTEGRATIONS_OPENROUTER_API_KEY")
    or os.getenv("OPENROUTER_API_KEY")
)
AI_INTEGRATIONS_OPENROUTER_BASE_URL = (
    os.getenv("AI_INTEGRATIONS_OPENROUTER_BASE_URL")
    or os.getenv("OPENROUTER_BASE_URL")
    or "https://openrouter.ai/api/v1"
)

MAX_TOKENS = 4000
TEMPERATURE = 0.7

# Available AI Models for OpenRouter (samarali modellar)
#
# Tartib muhim: ro'yxat admin panelda shu ketma-ketlikda ko'rinadi va
# birinchilari eng kuchli modellar. Narxlar taxminiy (OpenRouter'da vaqt
# o'tishi bilan o'zgaradi), shuning uchun "~" bilan yozilgan.
AI_MODELS = {
    "claude_sonnet_5": {
        "id": "anthropic/claude-sonnet-5",
        "name": "Claude Sonnet 5",
        "price": "~$3/1M",
        "description": "Eng kuchli — chuqur, tabiiy va ishonchli matn"
    },
    "claude_sonnet_45": {
        "id": "anthropic/claude-sonnet-4.5",
        "name": "Claude Sonnet 4.5",
        "price": "~$3/1M",
        "description": "Kuchli, uzun matnlarda barqaror"
    },
    "gpt_41": {
        "id": "openai/gpt-4.1",
        "name": "GPT-4.1",
        "price": "~$2/1M",
        "description": "OpenAI, ko'rsatmalarga qat'iy amal qiladi"
    },
    "gemini_25_pro": {
        "id": "google/gemini-2.5-pro",
        "name": "Gemini 2.5 Pro",
        "price": "~$1.25/1M",
        "description": "Google'ning kuchli modeli, arzonroq"
    },
    "gemini_25_flash": {
        "id": "google/gemini-2.5-flash",
        "name": "Gemini 2.5 Flash",
        "price": "$0.30/1M",
        "description": "Tez va yuqori sifatli"
    },
    "gemini_25_flash_lite": {
        "id": "google/gemini-2.5-flash-lite",
        "name": "Gemini 2.5 Flash Lite",
        "price": "$0.10/1M",
        "description": "Eng tez, arzon"
    },
    "gemini_20_flash": {
        "id": "google/gemini-2.0-flash-001",
        "name": "Gemini 2.0 Flash",
        "price": "$0.10/1M",
        "description": "Tez, ishonchli"
    },
    "gpt_4o_mini": {
        "id": "openai/gpt-4o-mini",
        "name": "GPT-4o Mini",
        "price": "$0.15/1M",
        "description": "OpenAI, tez va aqlli"
    },
    "claude_haiku": {
        "id": "anthropic/claude-3.5-haiku",
        "name": "Claude 3.5 Haiku",
        "price": "$0.80/1M",
        "description": "Sifatli, aniq javoblar"
    },
    "qwen3_14b": {
        "id": "qwen/qwen3-14b",
        "name": "Qwen3 14B",
        "price": "$0.06/1M",
        "description": "Eng arzon, yaxshi sifat"
    },
    "llama_33_70b": {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "name": "Llama 3.3 70B",
        "price": "$0.10/1M",
        "description": "Open-source, kuchli"
    }
}

# Default AI model.
#
# Gemini Flash arzon, lekin u cheklovlarni ko'rganda eng kam ish qilishni
# tanlaydi: yetkazilgan taqdimotlarda "kamida 80 so'z" talab qilingan
# slaydlarda 34-38 so'z chiqqan va matnda markdown belgilar qolib ketgan.
# Shuning uchun sukut bo'yicha model kuchlirog'iga almashtirildi.
DEFAULT_AI_MODEL = "claude_sonnet_5"

# Premium taqdimot uchun alohida sukut. Bu eng qimmat xizmat va undagi
# matn sifati mijozga eng ko'p ko'rinadi, shuning uchun u boshqa
# xizmatlardan mustaqil tanlanadi.
PREMIUM_DEFAULT_AI_MODEL = "claude_sonnet_5"

# Tanlangan model ishlamasa (hisobda yo'q, nomi o'zgargan, provayder javob
# bermayapti) shu ro'yxat bo'yicha keyingisiga o'tiladi. Oxirgisi — eski
# arzon model, ya'ni eng yomon holatda xizmat avvalgidek ishlaydi.
AI_MODEL_FALLBACKS = [
    "anthropic/claude-sonnet-5",
    "anthropic/claude-sonnet-4.5",
    "openai/gpt-4.1",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "meta-llama/llama-3.3-70b-instruct",
]

# Eski sukut modeli. Admin panelda hech narsa tanlanmagan bo'lsa,
# ma'lumotlar bazasida shu qiymat turibdi va u yangi sukutni bosib
# ketardi — `main.py` uni bir marta yangilaydi.
PREVIOUS_DEFAULT_AI_MODEL = "gemini_25_flash"

# ── Rasm modellari (Together AI)
#
# Uchta xizmat uchun alohida tanlanadi: hujjatlar (mustaqil ish, referat,
# kurs ishi va h.k.), oddiy taqdimot va zamonaviy taqdimot. Narx — bitta
# ~1 megapikselli rasm uchun taxminiy qiymat (Together narxlari o'zgarib
# turadi). Admin modelni tanlaganda u Together hisobidagi ro'yxatdan
# tekshiriladi; ishlab chiqarishda tanlangani ishlamasa
# IMAGE_MODEL_FALLBACKS bo'yicha keyingisiga o'tiladi.
#
# `steps` faqat uni qabul qiladigan modellarga yoziladi: FLUX.2-pro va
# boshqa "pro" modellar uni noma'lum parametr deb rad etadi, Schnell esa
# 4 dan ortig'ini rad etadi. Yozilmagan modelda sukut qiymati ishlaydi.
IMAGE_MODELS = {
    "flux2_pro": {
        "id": "black-forest-labs/FLUX.2-pro",
        "name": "FLUX.2 Pro",
        "price": "~$0.03",
        "description": "Eng aniq va realistik FLUX, hozirgi sukut",
    },
    "flux2_flex": {
        "id": "black-forest-labs/FLUX.2-flex",
        "name": "FLUX.2 Flex",
        "price": "~$0.03",
        "description": "FLUX.2 — mayda detallar va matnsiz kompozitsiyada yaxshi",
    },
    "flux2_dev": {
        "id": "black-forest-labs/FLUX.2-dev",
        "name": "FLUX.2 Dev",
        "price": "~$0.015",
        "description": "FLUX.2 ning arzonroq ochiq versiyasi",
    },
    "flux11_pro": {
        "id": "black-forest-labs/FLUX.1.1-pro",
        "name": "FLUX 1.1 Pro",
        "price": "~$0.04",
        "description": "Barqaror, yuqori sifatli fotosurat",
    },
    "flux1_kontext_max": {
        "id": "black-forest-labs/FLUX.1-kontext-max",
        "name": "FLUX Kontext Max",
        "price": "~$0.08",
        "description": "FLUX 1 oilasining eng kuchlisi, qimmat",
    },
    "flux1_kontext_pro": {
        "id": "black-forest-labs/FLUX.1-kontext-pro",
        "name": "FLUX Kontext Pro",
        "price": "~$0.04",
        "description": "Kuchli, kompozitsiyani yaxshi ushlaydi",
    },
    "flux1_krea_dev": {
        "id": "black-forest-labs/FLUX.1-krea-dev",
        "name": "FLUX Krea Dev",
        "price": "~$0.025",
        "description": "Tabiiy, \"AI ko'rinishisiz\" fotosurat uslubi",
    },
    "flux1_dev": {
        "id": "black-forest-labs/FLUX.1-dev",
        "name": "FLUX.1 Dev",
        "price": "~$0.025",
        "description": "O'rtacha sifat va narx",
    },
    "flux1_schnell": {
        "id": "black-forest-labs/FLUX.1-schnell",
        "name": "FLUX.1 Schnell",
        "price": "~$0.003",
        "description": "Juda arzon va tez, sifati oddiyroq",
        "steps": 4,
    },
    "imagen4_ultra": {
        "id": "google/imagen-4.0-ultra",
        "name": "Google Imagen 4 Ultra",
        "price": "~$0.06",
        "description": "Google'ning eng sifatli rasm modeli",
    },
    "imagen4": {
        "id": "google/imagen-4.0-preview",
        "name": "Google Imagen 4",
        "price": "~$0.04",
        "description": "Realistik, ranglari tabiiy",
    },
    "imagen4_fast": {
        "id": "google/imagen-4.0-fast",
        "name": "Google Imagen 4 Fast",
        "price": "~$0.02",
        "description": "Imagen 4 ning tez va arzon varianti",
    },
    "nano_banana": {
        "id": "google/flash-image-2.5",
        "name": "Gemini 2.5 Flash Image (Nano Banana)",
        "price": "~$0.04",
        "description": "Mavzuni yaxshi tushunadi, infografikaga ham mos",
    },
    "seedream4": {
        "id": "ByteDance-Seed/Seedream-4.0",
        "name": "ByteDance Seedream 4.0",
        "price": "~$0.03",
        "description": "Kuchli, yuqori aniqlikdagi rasm",
    },
    "seedream3": {
        "id": "ByteDance-Seed/Seedream-3.0",
        "name": "ByteDance Seedream 3.0",
        "price": "~$0.018",
        "description": "Yaxshi sifat, arzonroq",
    },
    "ideogram3": {
        "id": "ideogram/ideogram-3.0",
        "name": "Ideogram 3.0",
        "price": "~$0.06",
        "description": "Dizaynli, plakat uslubidagi rasmlar",
    },
    "qwen_image": {
        "id": "Qwen/Qwen-Image",
        "name": "Qwen Image",
        "price": "~$0.006",
        "description": "Arzon, sifati yaxshi",
    },
    "hidream_full": {
        "id": "HiDream-ai/HiDream-I1-Full",
        "name": "HiDream I1 Full",
        "price": "~$0.009",
        "description": "Arzon va sifatli ochiq model",
    },
    "hidream_dev": {
        "id": "HiDream-ai/HiDream-I1-Dev",
        "name": "HiDream I1 Dev",
        "price": "~$0.005",
        "description": "Juda arzon, sifati o'rtacha",
    },
    "juggernaut_pro": {
        "id": "RunDiffusion/Juggernaut-pro-flux",
        "name": "Juggernaut Pro Flux",
        "price": "~$0.005",
        "description": "Arzon fotorealistik FLUX varianti",
    },
}

DEFAULT_IMAGE_MODEL = "flux2_pro"

# Tanlangan model ishlamasa shu tartibda keyingisi sinaladi.
IMAGE_MODEL_FALLBACKS = [
    "black-forest-labs/FLUX.2-pro",
    "black-forest-labs/FLUX.1.1-pro",
    "black-forest-labs/FLUX.1-schnell",
]

# File paths
DOCUMENTS_DIR = "generated_documents"
TEMP_DIR = "temp"

# Do'kon (qayta sotuv sayti)
# Tayyor ishlarning o'zi yopiq Telegram kanalida saqlanadi — bazada faqat
# file_id turadi. Kanal ID'si "-100..." ko'rinishida bo'ladi va bot o'sha
# kanalda administrator bo'lishi shart.
STORE_VAULT_CHAT_ID = os.getenv("STORE_VAULT_CHAT_ID", "")
# Ko'rgazma rasmlari — yagona ommaviy ko'rinadigan qism. Bu katalog
# `temp/` dan tashqarida, chunki davriy tozalash uni o'chirib yuborardi.
STORE_PREVIEW_DIR = os.getenv("STORE_PREVIEW_DIR", "store_previews")
# Saytda ishning faqat boshlanishi ko'rsatiladi: dastlabki shuncha varaq
# rasmga aylantirilib saqlanadi, qolganlari umuman chizilmaydi — ular
# hostda joy egallamasin. Sahifada "yana X ta varaq bor" deb yoziladi,
# to'liq ish esa to'lovdan keyin fayl ko'rinishida beriladi.
STORE_PREVIEW_MAX = int(os.getenv("STORE_PREVIEW_MAX", "8"))
# Rasm ustidagi shaffof shtamp — ko'rgazma xaridning o'rnini bosmasligi uchun.
STORE_WATERMARK = os.getenv("STORE_WATERMARK", "NAMUNA")

# Tayyor ish mijozga yuborilgach o'zi katalogga tushadimi.
STORE_AUTO_PUBLISH = os.getenv("STORE_AUTO_PUBLISH", "1") not in ("0", "false", "no")

# Qayta sotuv narxlari (so'm). Bular yaratish narxidan ancha past: ish
# allaqachon tayyor, har xarid uchun yangi generatsiya ketmaydi. Zinapoya
# ish hajmi va murakkabligiga qarab ko'tariladi.
STORE_PRICES = {
    "taqdimot":         3000,
    "referat":          3000,
    "tezis":            3000,
    "mustaqil_ish":     4000,
    "maqola":           4000,
    "mahsus_ishlanma":  4000,
    "premium_taqdimot": 5000,
    "kurs_ishi":        5000,
    "loyiha_ishi":      5000,
    "bitiruv_ishi":     7000,
    "diplom_ishi":      7000,
    "dissertatsiya":    9000,
}
STORE_DEFAULT_PRICE = int(os.getenv("STORE_DEFAULT_PRICE", "4000"))

# Saytda ko'rinadigan nomlar. Tartib muhim: filtrlar shu ketma-ketlikda
# chiqadi, shuning uchun eng ko'p so'raladigani boshida turadi.
STORE_WORK_LABELS = {
    "taqdimot":         "Taqdimot",
    "premium_taqdimot": "Zamonaviy taqdimot",
    "referat":          "Referat",
    "mustaqil_ish":     "Mustaqil ish",
    "kurs_ishi":        "Kurs ishi",
    "loyiha_ishi":      "Loyiha ishi",
    "maqola":           "Maqola",
    "tezis":            "Tezis",
    "mahsus_ishlanma":  "Mahsus ishlanma",
    "bitiruv_ishi":     "Bitiruv ishi",
    "diplom_ishi":      "Diplom ishi",
    "dissertatsiya":    "Dissertatsiya",
}


def store_price(work_type: str) -> int:
    """Ish turiga ko'ra katalog narxi."""
    return STORE_PRICES.get(work_type, STORE_DEFAULT_PRICE)


def work_label(work_type: str) -> str:
    """Ish turining saytda ko'rinadigan nomi."""
    if not work_type:
        return ""
    return (STORE_WORK_LABELS.get(work_type)
            or work_type.replace("_", " ").capitalize())

# Ensure directories exist
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(STORE_PREVIEW_DIR, exist_ok=True)
