"""Classify a freelance task into a CP (commercial-proposal) type.

The proposal generator uses the type to pick a per-type structure/offer overlay
(prompts/cp_type_<type>.txt), so a partnership invite doesn't get an offer built
for a one-off task. Classification is a single cheap LLM call that must return
exactly one keyword; anything unexpected falls back to TASK (the safe default,
identical to the pre-typing behaviour).
"""
from __future__ import annotations

from enum import Enum

from utils.llm import chat_completion
from utils.logger import log_agent_action


class CPType(str, Enum):
    TASK = "task"        # разовая задача/разработка с результатом
    LEADS = "leads"      # массовый объём, оплата за единицу
    PARTNER = "partner"  # долгосрочное сотрудничество / % от выручки
    JOB = "job"          # вакансия / регулярный подряд за ставку


_CLASSIFY_SYS = (
    "Ты классифицируешь задание фрилансера по типу. Верни РОВНО одно слово из списка, без пояснений:\n"
    "task — конкретная разовая задача/разработка с понятным результатом и (обычно) бюджетом за работу;\n"
    "leads — массовый объём с оплатой за единицу (лиды, контакты, подписчики, рассылки, аутрич, обзвоны, парсинг, отметки);\n"
    "partner — предложение о долгосрочном сотрудничестве или партнёрстве, оплата процентом от выручки/продаж/прибыли, обычно без детального ТЗ;\n"
    "job — вакансия или регулярный подряд: ищут исполнителя в команду на постоянную/почасовую занятость за ставку.\n"
    "Ответ: одно слово — task, leads, partner или job."
)


async def classify(project: dict) -> CPType:
    """Return the CPType for a project. Never raises — falls back to TASK."""
    text = f"{project.get('title', '')}\n{project.get('description', '')}".strip()
    if not text:
        return CPType.TASK
    try:
        raw = await chat_completion(
            [
                {"role": "system", "content": _CLASSIFY_SYS},
                {"role": "user", "content": text[:2000]},
            ],
            timeout=20,
        )
    except Exception as e:
        log_agent_action("CPTypes", f"classify failed → task: {e}", level="WARNING")
        return CPType.TASK

    word = (raw or "").strip().strip(".").lower()
    # Model may echo a sentence; take the first token that is a valid type.
    for token in word.replace(",", " ").split():
        if token in CPType._value2member_map_:
            return CPType(token)
    log_agent_action("CPTypes", f"unrecognised classify output {raw!r} → task", level="WARNING")
    return CPType.TASK
