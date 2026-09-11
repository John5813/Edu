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
# Brief — qat'iy JSON sxema; uni pydantic tekshiradi va noto'g'ri slaydni
# alohida qayta so'raydi, shuning uchun bu yerda eng qimmat model shart emas.
OPENROUTER_TEXT_MODEL = os.getenv("OPENROUTER_TEXT_MODEL", "google/gemini-2.5-flash")
OPENROUTER_VISION_MODEL = os.getenv(
    "OPENROUTER_VISION_MODEL",
    "openai/gpt-4o-mini",
)

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
TOGETHER_IMAGE_MODEL = os.getenv(
    "PREMIUM_TOGETHER_IMAGE_MODEL", "black-forest-labs/FLUX.2-pro"
)
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
