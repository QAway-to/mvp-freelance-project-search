import os
from utils.openrouter import chat_completion
from utils.logger import log_agent_action

_PROMPT_FILE = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'cp_system.txt')


def _load_system_prompt() -> str:
    try:
        with open(_PROMPT_FILE, encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        log_agent_action("CPGenerator", f"⚠️ Could not load cp_system.txt: {e}", level="WARNING")
        return "Ты — Александр, фрилансер. Пишешь коммерческие предложения на русском."


SYSTEM_PROMPT = _load_system_prompt()


async def generate_proposal(project: dict) -> str:
    task = (
        f"Напиши КП для следующего заказа с Kwork:\n\n"
        f"Название: {project.get('title', '?')}\n"
        f"Бюджет: {project.get('budget') or 'не указан'}\n"
        f"Описание:\n{project.get('description') or '(нет описания)'}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    result = await chat_completion(messages)
    log_agent_action("CPGenerator", f"✅ КП сгенерировано ({len(result)} символов)")
    return result
