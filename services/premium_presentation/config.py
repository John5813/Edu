import os

# Premium presentation OpenAI-compatible OpenRouter API orqali ishlaydi.
#
# Kalit ikki nom bilan saqlanishi mumkin: Replit integratsiyasi uni
# `AI_INTEGRATIONS_OPENROUTER_API_KEY` deb qo'yadi, qo'lda sozlanganda esa
# odatda `OPENROUTER_API_KEY` bo'ladi. Ildizdagi `config.py` ikkalasini ham
# qabul qiladi, bu modul esa faqat ikkinchisini bilardi — shu sababli bir
# serverda oddiy taqdimot ishlab, premium "OPENROUTER_API_KEY topilmadi"
# deb to'xtardi. Endi ro'yxat bir xil.
OPENROUTER_API_KEY = (
    os.getenv("AI_INTEGRATIONS_OPENROUTER_API_KEY")
    or os.getenv("OPENROUTER_API_KEY")
    or ""
)
OPENROUTER_BASE_URL = (
    os.getenv("AI_INTEGRATIONS_OPENROUTER_BASE_URL")
    or os.getenv("OPENROUTER_BASE_URL")
    or "https://openrouter.ai/api/v1"
).rstrip("/")
OPENROUTER_URL = os.getenv(
    "OPENROUTER_URL",
    f"{OPENROUTER_BASE_URL}/chat/completions",
)

# Model nomlari OpenRouter katalogidagi aniq model ID'lari bo'lishi kerak.
#
# Ular RO'YXAT bo'lib sinaladi: birinchisi ishlamasa (hisobda mavjud emas,
# nomi o'zgargan, vaqtincha o'chirilgan) keyingisiga o'tiladi. Shu sababli
# bitta noto'g'ri nom xizmatni to'xtatib qo'ymaydi va ishlagan model
# jarayon davomida eslab qolinadi — har so'rovda qayta sinalmaydi.
#
# Tartib sifat bo'yicha: avval kuchli modellar, oxirida — avvalgi arzon
# model, ya'ni eng yomon holatda xizmat bugungidek ishlaydi.
_DEFAULT_TEXT_CHAIN = (
    "anthropic/claude-sonnet-5,"
    "anthropic/claude-sonnet-4.5,"
    "openai/gpt-4.1,"
    "google/gemini-2.5-pro,"
    "google/gemini-2.5-flash"
)
# Slayd rasmini ko'z bilan tekshiradigan model. U har slayd uchun
# chaqiriladi, shuning uchun o'rta darajali model yetarli.
_DEFAULT_VISION_CHAIN = (
    "anthropic/claude-haiku-4.5,"
    "openai/gpt-4.1-mini,"
    "openai/gpt-4o-mini"
)


def _chain(value: str) -> list:
    """Vergul bilan ajratilgan model ro'yxatini tozalab beradi."""
    return [item.strip() for item in (value or "").split(",") if item.strip()]


# `OPENROUTER_TEXT_MODEL` berilsa — u ro'yxat boshiga qo'yiladi, ya'ni
# serverda bitta o'zgaruvchi bilan modelni almashtirib bo'ladi.
OPENROUTER_TEXT_MODELS = _chain(
    os.getenv("OPENROUTER_TEXT_MODEL", "") + "," +
    os.getenv("OPENROUTER_TEXT_FALLBACKS", _DEFAULT_TEXT_CHAIN)
)
OPENROUTER_VISION_MODELS = _chain(
    os.getenv("OPENROUTER_VISION_MODEL", "") + "," +
    os.getenv("OPENROUTER_VISION_FALLBACKS", _DEFAULT_VISION_CHAIN)
)

# Eski nom bilan foydalanadigan joylar uchun — ro'yxatning birinchisi.
OPENROUTER_TEXT_MODEL = OPENROUTER_TEXT_MODELS[0]
OPENROUTER_VISION_MODEL = OPENROUTER_VISION_MODELS[0]

# Vizual QA har slaydni rasmga aylantirib vision modelga yuboradi. Ilgari u
# sukut bo'yicha o'chiq edi, shuning uchun tekshiruv umuman ishlamasdi.
# Endi yoqiq: dasturiy tekshiruvlar ustma-ustlikning kattasini bepul topadi,
# lekin matn rasm ustiga tushgan yoki kontrast yetmagan holatni faqat ko'z
# ko'radi. PREMIUM_VISUAL_QA=0 bilan o'chiriladi.
VISUAL_QA_ENABLED = os.getenv("PREMIUM_VISUAL_QA", "1").lower() in {"1", "true", "yes"}
# Ikki raund: birinchisida arzon tuzatish (surish), yordam bermasa
# ikkinchisida daraja ko'tariladi.
MAX_QA_RETRIES = int(os.getenv("PREMIUM_MAX_QA_RETRIES", "2"))
WORK_DIR = os.getenv("PREMIUM_WORK_DIR", "temp")

# Slayd rasmlari — asosiy bot bilan bir xil Together AI kaliti va FLUX modeli.
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")
# FLUX.1-schnell hisobimizning model ro'yxatida yo'q edi — birinchi so'rov
# HTTP 400 bilan yiqilib, keyingi urinishlar 429 ga tushardi. FLUX.2-pro
# mavjud va premium slaydlar uchun mos.
# Rasm modeli ham ro'yxat: yetkazilgan taqdimotlarda hamma rasm so'rovi
# muvaffaqiyatsiz tugagan va taqdimot faqat ikonka bilan chiqqan. Bitta
# model ishlamasa (hisobda ochiq emas, nomi o'zgargan, limit) keyingisiga
# o'tiladi — mijoz pul to'lagan ishda rasmsiz qolmaslik muhimroq.
_DEFAULT_IMAGE_CHAIN = (
    "black-forest-labs/FLUX.2-pro,"
    "black-forest-labs/FLUX.1.1-pro,"
    "black-forest-labs/FLUX.1-schnell-Free,"
    "black-forest-labs/FLUX.1-schnell"
)
TOGETHER_IMAGE_MODELS = _chain(
    os.getenv("PREMIUM_TOGETHER_IMAGE_MODEL", "") + "," +
    os.getenv("PREMIUM_TOGETHER_IMAGE_FALLBACKS", _DEFAULT_IMAGE_CHAIN)
)
TOGETHER_IMAGE_MODEL = TOGETHER_IMAGE_MODELS[0]
TOGETHER_IMAGE_URL = os.getenv(
    "PREMIUM_TOGETHER_IMAGE_URL", "https://api.together.ai/v1/images/generations"
)
# `steps` faqat uni qabul qiladigan modellarga yuboriladi (pastdagi ro'yxat).
# Schnell uchun chegara 4 ta: undan yuqorisi HTTP 400 beradi.
TOGETHER_IMAGE_STEPS = int(os.getenv("PREMIUM_TOGETHER_IMAGE_STEPS", "4"))
# Slayd nisbati 16:9 — o'lchamlar 16 ga karrali bo'lishi shart.
TOGETHER_IMAGE_WIDTH = int(os.getenv("PREMIUM_TOGETHER_IMAGE_WIDTH", "1344"))
TOGETHER_IMAGE_HEIGHT = int(os.getenv("PREMIUM_TOGETHER_IMAGE_HEIGHT", "768"))
# Bepul/arzon tariflarda soniyasiga bir nechta so'rov 429 beradi.
TOGETHER_MIN_INTERVAL = float(os.getenv("PREMIUM_TOGETHER_MIN_INTERVAL", "2.0"))

# Premium oqim AI kontentini PPTX faylga render qiladi va mavjud bo'lsa visual QA ishlatadi.
