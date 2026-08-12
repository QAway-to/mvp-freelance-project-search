import os
from typing import Optional, List
from dotenv import load_dotenv

# Try to load .env file, but don't fail if it doesn't exist
try:
    load_dotenv()
except Exception:
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
    KWORK_FAVORITES_URL: str = f"{KWORK_PROJECTS_URL}?type=favourite"
    KWORK_LOGIN_URL: str = f"{KWORK_BASE_URL}/login"
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
    # Session cookies JSON (alternative to login — paste from browser DevTools)
    KWORK_COOKIES: Optional[str] = os.getenv('KWORK_COOKIES')

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHANNEL_ID: Optional[str] = os.getenv('TELEGRAM_CHANNEL_ID')
    TELEGRAM_BOT_ENABLED: bool = os.getenv('TELEGRAM_BOT_ENABLED', 'true').strip().lower() in ('1', 'true', 'yes', 'on')
    # Private channel used as the video library (-100... form). Posts there are
    # indexed and served to users via copy_message.
    CONTENT_CHANNEL_ID: Optional[str] = os.getenv('CONTENT_CHANNEL_ID')
    # Who may run /reindex. Also receives the throwaway forwards it uses to read
    # captions, so it must be a private chat with the bot.
    ADMIN_CHAT_ID: Optional[str] = os.getenv('ADMIN_CHAT_ID')
    # Касса внутри бота (Telegram Stars). Выключена: продажа закрывается вне
    # бота, воронка только доводит до неё. Обработчики /buy, /testpay и
    # платёжные апдейты не регистрируются, пока флаг не поднят.
    PAYMENTS_ENABLED: bool = os.getenv('PAYMENTS_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
    # Внешняя страница оплаты. К ней добавляется ?uid=<chat_id>, чтобы платёж
    # можно было связать с диалогом.
    PURCHASE_URL: Optional[str] = os.getenv('PURCHASE_URL')
    # После скольких сообщений показывать оффер. На демо удобно 2.
    FUNNEL_CTA_AT: int = int(os.getenv('FUNNEL_CTA_AT', '5'))
    # Цена в Telegram Stars (XTR). 1 звезда ≈ $0.02, то есть 2500 ≈ $50.
    STARS_PRICE: int = int(os.getenv('STARS_PRICE', '1000'))
    # Публичный адрес сервиса. На Render подставляется автоматически.
    # Если задан — бот работает через webhook, а не поллинг: спящий контейнер
    # будит сам входящий запрос Telegram, поэтому сообщения не теряются.
    PUBLIC_URL: Optional[str] = os.getenv('PUBLIC_URL') or os.getenv('RENDER_EXTERNAL_URL')
    # Секрет вебхука. Telegram присылает его в заголовке, чужие POST отсекаем.
    TELEGRAM_WEBHOOK_SECRET: str = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')


    # n8n Integration
    N8N_WEBHOOK_URL: Optional[str] = os.getenv('N8N_WEBHOOK_URL')
    
    # Gemini AI — embeddings for semantic evaluation (optional)
    GEMINI_API_KEY: Optional[str] = os.getenv('GEMINI_API_KEY')
    # DeepSeek — chat completions and КП generation (direct paid API, OpenAI-compatible).
    # DEEPSEEK_MODEL: deepseek-v4-flash (default, non-thinking) or deepseek-v4-pro.
    DEEPSEEK_API_KEY: Optional[str] = os.getenv('DEEPSEEK_API_KEY')
    DEEPSEEK_MODEL: str = os.getenv('DEEPSEEK_MODEL', 'deepseek-v4-flash')
    SEMANTIC_SIMILARITY_THRESHOLD: float = float(os.getenv('SEMANTIC_SIMILARITY_THRESHOLD', '0.50'))  # Lowered from 0.75 to 0.50 for better matching

    # Search limits
    MAX_PROJECTS_PER_SESSION: int = int(os.getenv('MAX_PROJECTS_PER_SESSION', '5'))
    EVALUATION_THRESHOLD: float = float(os.getenv('EVALUATION_THRESHOLD', '0.4'))
    MAX_URGENCY_HOURS: int = int(os.getenv('MAX_URGENCY_HOURS', '24'))

    # Timing (seconds)
    SESSION_DURATION_MAX: int = int(os.getenv('SESSION_DURATION_MAX', '300'))
    PAUSE_BETWEEN_CHECKS: int = int(os.getenv('PAUSE_BETWEEN_CHECKS', '3600'))
    READING_TIME_MIN: int = int(os.getenv('READING_TIME_MIN', '10'))
    READING_TIME_MAX: int = int(os.getenv('READING_TIME_MAX', '30'))

    # Gemini CP Prompt Template
    GEMINI_CP_PROMPT: str = os.getenv('GEMINI_CP_PROMPT', """
Вы — эксперт по продажам на фриланс-бирже Kwork. 
Ваша задача: написать профессиональное коммерческое предложение (КП) для проекта.

Описание проекта:
{description}

Бюджет клиента: {budget}

Требования к КП:
1. Тон: Профессиональный, уверенный, но дружелюбный.
2. Структура: Приветствие, понимание задачи, краткое описание решения, почему выбрать именно нас, призыв к действию.
3. Язык: Только русский.
4. Длина: Около 100-150 слов.
5. Не используйте шаблоны, пишите конкретно по задаче.

Напишите только текст отклика.
""")

    # Budget filters (indices 0-4 as discovered by browser subagent)
    # 0: up to 1k, 1: 1k-3k, 2: 3k-10k, 3: 10k-30k, 4: 30k+
    BUDGET_FILTERS: List[int] = []

    # Human behavior
    DELAY_BETWEEN_ACTIONS_MIN: float = 1.0
    DELAY_BETWEEN_ACTIONS_MAX: float = 4.0
    MOUSE_MOVEMENT_STEPS: int = 10

config = Config()
