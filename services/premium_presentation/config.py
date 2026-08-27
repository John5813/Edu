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
OPENROUTER_TEXT_MODEL = os.getenv("OPENROUTER_TEXT_MODEL", "openai/gpt-5.4")
OPENROUTER_VISION_MODEL = os.getenv(
    "OPENROUTER_VISION_MODEL",
    "openai/gpt-5.4",
)
MAX_QA_RETRIES = int(os.getenv("PREMIUM_MAX_QA_RETRIES", "1"))
MAX_CODE_RETRIES = int(os.getenv("PREMIUM_CODE_RETRIES", "1"))
WORK_DIR = os.getenv("PREMIUM_WORK_DIR", "temp")

# Premium oqim AI kontentini PPTX faylga render qiladi va mavjud bo'lsa visual QA ishlatadi.
