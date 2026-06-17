import aiohttp
from config import config
from utils.logger import log_agent_action

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "meta-llama/llama-3.1-8b-instruct:free"


async def chat_completion(messages: list[dict], timeout: int = 60) -> str:
    if not config.OPENROUTER_API_KEY:
        log_agent_action("OpenRouter", "API key not configured", level="WARNING")
        return "OpenRouter API key not configured."

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": MODEL, "messages": messages},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log_agent_action("OpenRouter", f"❌ HTTP {resp.status}: {body[:300]}", level="ERROR")
                    raise RuntimeError(f"OpenRouter HTTP {resp.status}: {body[:200]}")
                data = await resp.json()
                if "choices" not in data:
                    log_agent_action("OpenRouter", f"❌ No choices in response: {str(data)[:300]}", level="ERROR")
                    raise RuntimeError(f"No choices: {data}")
                content = data["choices"][0]["message"]["content"]
                return (content or "").strip()
    except Exception as e:
        log_agent_action("OpenRouter", f"❌ API error: {e}", level="ERROR")
        raise
