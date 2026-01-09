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

# Course work prices (with chapters)
COURSE_WORK_PRICES = {
    "15_20_2": 15000,
    "20_25_2": 20000,
    "25_30_3": 25000,
    "30_35_3": 30000
}

# AI configuration (DeepSeek via OpenRouter)
AI_INTEGRATIONS_OPENROUTER_API_KEY = os.getenv("AI_INTEGRATIONS_OPENROUTER_API_KEY")
AI_INTEGRATIONS_OPENROUTER_BASE_URL = os.getenv("AI_INTEGRATIONS_OPENROUTER_BASE_URL")

MAX_TOKENS = 4000
TEMPERATURE = 0.7

# Available AI Models for OpenRouter (samarali modellar)
AI_MODELS = {
    "deepseek_r1": {
        "id": "deepseek/deepseek-r1",
        "name": "DeepSeek R1",
        "price": "$0.55/1M",
        "description": "Eng kuchli, reasoning"
    },
    "gemini_25_flash": {
        "id": "google/gemini-2.5-flash",
        "name": "Gemini 2.5 Flash",
        "price": "$0.30/1M",
        "description": "Tez va samarali"
    },
    "claude_haiku": {
        "id": "anthropic/claude-3.5-haiku",
        "name": "Claude 3.5 Haiku",
        "price": "$0.25/1M",
        "description": "Tez, sifatli"
    },
    "gemini_25_flash_lite": {
        "id": "google/gemini-2.5-flash-lite-preview-09-2025",
        "name": "Gemini 2.5 Flash Lite",
        "price": "$0.40/1M",
        "description": "Yozuvda zo'r, tez"
    },
    "gemini_20_flash": {
        "id": "google/gemini-2.0-flash-001",
        "name": "Gemini 2.0 Flash",
        "price": "$0.10/1M",
        "description": "Eng arzon"
    }
}

# Default AI model
DEFAULT_AI_MODEL = "gemini_25_flash"

# File paths
DOCUMENTS_DIR = "generated_documents"
TEMP_DIR = "temp"

# Ensure directories exist
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
