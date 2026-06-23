import json
from utils.llm import chat_completion
from utils.logger import log_agent_action

_SYSTEM = """Ты категоризатор заказов с биржи фриланса (русскоязычный рынок).

Правила:
1. Присваивай категорию из ~15-20 широких групп, не создавай узкие.
2. Похожие задачи → одна категория ("парсинг сайта", "сбор данных", "скрапинг" → "Парсинг").
3. Если не уверен — бери ближайшую широкую категорию.
4. Теги — конкретные технологии или детали задачи (2-4 штуки).

Примеры широких категорий (не исчерпывающий список — можешь добавить новую если ничего не подходит):
- Парсинг / сбор данных
- Telegram-бот
- Автоматизация / скрипты
- Интеграция API
- Google Sheets / Excel
- Рассылки (email, WhatsApp, Viber)
- CRM (Bitrix24, amoCRM)
- Веб-разработка
- Мобильное приложение
- Дизайн / верстка
- SEO / продвижение
- Копирайтинг / тексты
- Администрирование / DevOps
- Прочее

Верни ТОЛЬКО валидный JSON без пояснений и markdown:
{"category": "...", "tags": ["...", "..."], "complexity": "low|medium|high"}"""


async def categorize(title: str, description: str) -> dict:
    user_msg = f"Название: {title}\nОписание: {(description or '').strip()[:800] or '(нет описания)'}"
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    raw = await chat_completion(messages, timeout=30)
    try:
        # Strip possible markdown fences
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(cleaned)
        return {
            "category": str(result.get("category", "Прочее")),
            "tags": list(result.get("tags", [])),
            "complexity": str(result.get("complexity", "medium")),
        }
    except Exception as e:
        log_agent_action("Categorizer", f"⚠️ JSON parse error: {e} | raw={raw[:100]}", level="WARNING")
        return {"category": "Прочее", "tags": [], "complexity": "medium"}
