from pydantic_settings import BaseSettings

VALID_CATEGORY_IDS = {41, 15, 11, 13, 12, 14, 17}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://kwork.ru/",
}


class Settings(BaseSettings):
    kwork_base_url: str = "https://kwork.ru"
    kwork_rate_limit_rps: float = 1.0
    request_timeout: int = 15
    log_level: str = "INFO"
    kwork_cookie: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
