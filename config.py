import os
from typing import Optional, List
from dotenv import load_dotenv

# Try to load .env file, but don't fail if it doesn't exist
try:
    load_dotenv()
except:
    pass

class Config:
    # App settings
    _mode = os.getenv('MODE', 'demo').lower().strip()  # Normalize to lowercase (full, FULL, Full -> full)
    # Validate MODE value
    if _mode not in ['demo', 'full']:
        # If invalid, default to demo and log warning
        import warnings
        warnings.warn(f"Invalid MODE value: {os.getenv('MODE')}. Using 'demo' instead. Valid values: 'demo', 'full'")
        _mode = 'demo'
    MODE: str = _mode
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')

    # Kwork settings
    KWORK_BASE_URL: str = "https://kwork.ru"
    KWORK_PROJECTS_URL: str = f"{KWORK_BASE_URL}/projects"
    # Search keywords - can be comma-separated list or single keyword
    SEARCH_KEYWORDS: str = os.getenv('SEARCH_KEYWORDS', 'бот, данные, скрипт, скрипты, сканер, парсер')
    # Legacy support: if SEARCH_KEYWORD is set, use it
    _legacy_keyword = os.getenv('SEARCH_KEYWORD')
    if _legacy_keyword:
        SEARCH_KEYWORDS = _legacy_keyword
    # Parse keywords into list (split by comma, strip whitespace)
    SEARCH_KEYWORDS_LIST: List[str] = [kw.strip() for kw in SEARCH_KEYWORDS.split(',') if kw.strip()]
    # Primary keyword for logging (first one)
    SEARCH_KEYWORD: str = SEARCH_KEYWORDS_LIST[0] if SEARCH_KEYWORDS_LIST else 'бот'

    # Credentials
    KWORK_EMAIL: Optional[str] = os.getenv('KWORK_EMAIL')
    KWORK_PASSWORD: Optional[str] = os.getenv('KWORK_PASSWORD')

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHANNEL_ID: Optional[str] = os.getenv('TELEGRAM_CHANNEL_ID')
    
    # n8n Integration
    N8N_WEBHOOK_URL: Optional[str] = os.getenv('N8N_WEBHOOK_URL')
    
    # Gemini AI (for semantic evaluation)
    GEMINI_API_KEY: Optional[str] = os.getenv('GEMINI_API_KEY')
    SEMANTIC_SIMILARITY_THRESHOLD: float = float(os.getenv('SEMANTIC_SIMILARITY_THRESHOLD', '0.50'))  # Lowered from 0.75 to 0.50 for better matching

    # Search limits
    MAX_PROJECTS_PER_SESSION: int = int(os.getenv('MAX_PROJECTS_PER_SESSION', '5'))
    EVALUATION_THRESHOLD: float = float(os.getenv('EVALUATION_THRESHOLD', '0.4'))

    # Timing (seconds)
    SESSION_DURATION_MAX: int = int(os.getenv('SESSION_DURATION_MAX', '300'))
    PAUSE_BETWEEN_CHECKS: int = int(os.getenv('PAUSE_BETWEEN_CHECKS', '3600'))
    READING_TIME_MIN: int = int(os.getenv('READING_TIME_MIN', '10'))
    READING_TIME_MAX: int = int(os.getenv('READING_TIME_MAX', '30'))

    # Human behavior
    DELAY_BETWEEN_ACTIONS_MIN: float = 2.0
    DELAY_BETWEEN_ACTIONS_MAX: float = 8.0
    MOUSE_MOVEMENT_STEPS: int = 10

config = Config()
