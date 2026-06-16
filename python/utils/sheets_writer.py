import os
import aiohttp
from utils.logger import log_agent_action

_URL    = os.getenv("SHEETS_SCRIPT_URL", "")
_SECRET = os.getenv("SHEETS_SECRET", "")


async def write_order(project: dict, category: str, tags: list, complexity: str) -> bool:
    if not _URL:
        return False
    payload = {
        "platform":    project.get("platform", "kwork"),
        "category":    category,
        "tags":        tags,
        "complexity":  complexity,
        "title":       project.get("title", ""),
        "budget":      project.get("budget", ""),
        "url":         project.get("url", ""),
        "description": (project.get("description") or "")[:500],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_URL}?secret={_SECRET}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                text = await resp.text()
                if text.strip() in ("ok", "duplicate"):
                    log_agent_action("Sheets", f"{'✅' if text=='ok' else '⏭️'} {text}: {project.get('title','')[:50]}")
                    return text == "ok"
                log_agent_action("Sheets", f"⚠️ Unexpected response: {text[:100]}", level="WARNING")
                return False
    except Exception as e:
        log_agent_action("Sheets", f"❌ Write error: {e}", level="ERROR")
        return False
