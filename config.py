import os

# Bot configuration - no default values for security
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

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
PAYMENT_CARD_OWNER = os.getenv("PAYMENT_CARD_OWNER", "Moʻydinov Javlonbek")

# Payment amounts with descriptions (for reference - actual values in keyboards.py)
PAYMENT_OPTIONS_REFERENCE = [
    (10000, "10,000 so'm"),
    (15000, "15,000 so'm"),
    (20000, "20,000 so'm"),
    (25000, "25,000 so'm")
]

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
    "25_30": 12000
}

# AI configuration (DeepSeek via OpenRouter)
MAX_TOKENS = 4000
TEMPERATURE = 0.7

# File paths
DOCUMENTS_DIR = "generated_documents"
TEMP_DIR = "temp"

# Ensure directories exist
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
