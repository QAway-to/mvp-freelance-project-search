import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Config:
    # App settings
    MODE: str = os.getenv('MODE', 'demo')
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')

    # Kwork settings
    KWORK_BASE_URL: str = "https://kwork.ru"
    KWORK_PROJECTS_URL: str = f"{KWORK_BASE_URL}/projects"
    SEARCH_KEYWORD: str = os.getenv('SEARCH_KEYWORD', 'бот')

    # Credentials
    KWORK_EMAIL: Optional[str] = os.getenv('KWORK_EMAIL')
    KWORK_PASSWORD: Optional[str] = os.getenv('KWORK_PASSWORD')

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHANNEL_ID: Optional[str] = os.getenv('TELEGRAM_CHANNEL_ID')

    # Search limits
    MAX_PROJECTS_PER_SESSION: int = int(os.getenv('MAX_PROJECTS_PER_SESSION', '5'))
    EVALUATION_THRESHOLD: float = float(os.getenv('EVALUATION_THRESHOLD', '0.7'))

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
