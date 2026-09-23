import os

# Premium presentation faqat OpenAI'dan Python source code oladi.
# Kalit Replit Secrets orqali OPENAI_API_KEY sifatida beriladi.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")

# Bu modul endi PPTX render, image generation yoki visual QA ishlatmaydi.
