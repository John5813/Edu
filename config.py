import os

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Admin configuration
ADMIN_IDS = list(map(int, filter(None, os.getenv("ADMIN_IDS", "5304482470").split(",")))) if os.getenv("ADMIN_IDS") else [5304482470]

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot.db")

# Payment configuration
PAYMENT_CARD = os.getenv("PAYMENT_CARD", "9860 1234 5678 9012")
PAYMENT_AMOUNTS = [5000, 10000, 15000, 20000]

# Document pricing (in som)
PRESENTATION_PRICE = 3000
INDEPENDENT_WORK_PRICE = 5000
REFERAT_PRICE = 4000

# AI configuration
MAX_TOKENS = 4000
TEMPERATURE = 0.7

# File paths
DOCUMENTS_DIR = "generated_documents"
TEMP_DIR = "temp"

# Ensure directories exist
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
