import os

from utils.cp_types import CPType, classify
from utils.llm import chat_completion
from utils.logger import log_agent_action

_PROMPT_DIR = os.path.join(os.path.dirname(__file__), '..', 'prompts')

_FALLBACK_BASE = "Ты — Александр, фрилансер. Пишешь коммерческие предложения на русском."

_TYPE_FILES = {
    CPType.TASK: 'cp_type_task.txt',
    CPType.LEADS: 'cp_type_leads.txt',
    CPType.PARTNER: 'cp_type_partner.txt',
    CPType.JOB: 'cp_type_job.txt',
}


def _read(name: str) -> str:
    with open(os.path.join(_PROMPT_DIR, name), encoding='utf-8') as f:
        return f.read().strip()


def _load(name: str, fallback: str = "") -> str:
    try:
        return _read(name)
    except Exception as e:
        log_agent_action("CPGenerator", f"⚠️ Could not load {name}: {e}", level="WARNING")
        return fallback


# Loaded once at import. Base = type-independent (style, ОБО МНЕ, tone);
# per-type overlays carry the structure + offer rules that must differ.
_BASE_PROMPT = _load('cp_base.txt', _FALLBACK_BASE)
_TYPE_PROMPTS = {t: _load(f) for t, f in _TYPE_FILES.items()}


def _system_prompt(cp_type: CPType) -> str:
    overlay = _TYPE_PROMPTS.get(cp_type) or _TYPE_PROMPTS.get(CPType.TASK) or ""
    return f"{_BASE_PROMPT}\n\n{overlay}".strip() if overlay else _BASE_PROMPT


async def build_system_prompt(project: dict) -> tuple[str, CPType]:
    """Classify the project and return its typed CP system prompt + type.

    Exposed so alternate CP paths (e.g. the Telegram bot's own message loop with
    its rewrite branch) share the exact same typing as generate_proposal."""
    cp_type = await classify(project)
    return _system_prompt(cp_type), cp_type


async def generate_proposal(project: dict, attachments_text: str = "") -> str:
    system_prompt, cp_type = await build_system_prompt(project)

    att = (attachments_text or "").strip()
    attachments_block = (
        f"СОДЕРЖИМОЕ ВЛОЖЕНИЙ К ЗАДАНИЮ (распознано автоматически — учти при составлении КП):\n{att}"
        if att else "Вложения / детали: нет."
    )
    task = (
        "ЗАДАЧА КЛИЕНТА:\n"
        f"{project.get('description') or '(описание не указано)'}\n\n"
        f"Название заказа: {project.get('title', '?')}\n"
        f"Бюджет клиента: {project.get('budget') or 'не указан'}\n\n"
        f"{attachments_block}\n\n"
        "Напиши КП строго по системному промпту."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    result = await chat_completion(messages)
    log_agent_action("CPGenerator", f"✅ КП сгенерировано (тип: {cp_type.value}, {len(result)} символов)")
    return result
