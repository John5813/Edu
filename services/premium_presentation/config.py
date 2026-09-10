import os

# Premium presentation OpenAI-compatible OpenRouter API orqali ishlaydi.
# Kalit Replit Secrets'da OPENROUTER_API_KEY sifatida saqlanadi.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv(
    "OPENROUTER_BASE_URL",
    "https://openrouter.ai/api/v1",
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

# Vizual QA har slaydni rasmga aylantirib vision modelga yuboradi — oqimdagi
# eng qimmat qadam. Dasturiy tekshiruvlar (ustma-ustlik, minimal shrift,
# grounding) ishning kattasini bepul bajaradi, shuning uchun QA ixtiyoriy.
VISUAL_QA_ENABLED = os.getenv("PREMIUM_VISUAL_QA", "0").lower() in {"1", "true", "yes"}
MAX_QA_RETRIES = int(os.getenv("PREMIUM_MAX_QA_RETRIES", "1"))
WORK_DIR = os.getenv("PREMIUM_WORK_DIR", "temp")

# Slayd rasmlari — asosiy bot bilan bir xil Together AI kaliti va FLUX modeli.
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")
TOGETHER_IMAGE_MODEL = os.getenv(
    "PREMIUM_TOGETHER_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell"
)
TOGETHER_IMAGE_URL = os.getenv(
    "PREMIUM_TOGETHER_IMAGE_URL", "https://api.together.xyz/v1/images/generations"
)

# Premium oqim AI kontentini PPTX faylga render qiladi va mavjud bo'lsa visual QA ishlatadi.
