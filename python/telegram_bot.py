import os
from typing import Any

from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from telegram.error import TelegramError

from config import config
from utils.logger import log_agent_action
from utils.openrouter import chat_completion

_PROMPT_FILE = os.path.join(os.path.dirname(__file__), 'prompts', 'cp_system.txt')


def _load_system_prompt() -> str:
    try:
        with open(_PROMPT_FILE, encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        log_agent_action("Telegram", f"⚠️ Could not load cp_system.txt: {e}", level="WARNING")
        return "Ты — Александр, фрилансер. Помогаешь с анализом проектов и написанием КП на русском."


_SYSTEM_PROMPT = _load_system_prompt()

# Max conversation turns to keep (system prompt + last N messages)
_MAX_HISTORY = 20


class TelegramBot:
    def __init__(self):
        self._app: Application | None = None
        # chat_id -> found projects from last search
        self._projects: dict[str, list[dict[str, Any]]] = {}
        # chat_id -> OpenRouter messages history (system + user/assistant turns)
        self._conversations: dict[str, list[dict[str, str]]] = {}

    async def start(self) -> None:
        if not config.TELEGRAM_BOT_TOKEN:
            log_agent_action("Telegram", "Bot token not configured — disabled")
            return
        try:
            self._app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
            self._app.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
            )
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(drop_pending_updates=True)
            log_agent_action("Telegram", "Bot started (polling)")
        except Exception as e:
            log_agent_action("Telegram", f"Bot startup failed: {e} — running without Telegram", level="WARNING")
            self._app = None

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            log_agent_action("Telegram", "Bot stopped")

    async def send_projects_for_confirmation(self, projects: list[dict[str, Any]]) -> None:
        """Send found projects to Telegram and initialise conversation context."""
        if not self._app or not config.TELEGRAM_CHANNEL_ID:
            return
        if not projects:
            return

        chat_id = str(config.TELEGRAM_CHANNEL_ID)
        self._projects[chat_id] = projects

        # Build display message + LLM context
        msg_lines = ["🎯 <b>Найдено проектов:</b>\n"]
        ctx_lines = []
        for i, p in enumerate(projects, 1):
            title = (p.get("title") or "?")[:70]
            budget = p.get("budget") or "?"
            url = p.get("url") or ""
            desc = (p.get("description") or "")[:300]
            msg_lines.append(
                f"{i}. <b>{title}</b>\n"
                f"   💰 {budget}\n"
                f"   🔗 {url}\n"
            )
            ctx_lines.append(
                f"Проект {i}: {title}\n"
                f"Бюджет: {budget}\n"
                f"Ссылка: {url}\n"
                f"Описание: {desc or '(нет)'}"
            )

        msg_lines.append("💬 Напиши что думаешь — обсудим или попроси написать КП для любого.")

        system_with_projects = (
            f"{_SYSTEM_PROMPT}\n\n"
            f"---\n"
            f"НАЙДЕННЫЕ ПРОЕКТЫ С KWORK:\n\n"
            + "\n\n".join(ctx_lines)
            + "\n\n---\n"
            "Помоги выбрать подходящие. Когда попросят — напиши КП по профилю выше."
        )
        self._conversations[chat_id] = [{"role": "system", "content": system_with_projects}]

        try:
            await self._app.bot.send_message(
                chat_id=chat_id,
                text="\n".join(msg_lines),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            log_agent_action("Telegram", f"Sent {len(projects)} projects to chat")
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send projects: {e}", level="ERROR")

    async def _handle_message(self, update: Update, context) -> None:
        if not update.message or not update.message.text:
            return

        chat_id = str(update.effective_chat.id)
        text = update.message.text.strip()

        # If no active search context — use bare system prompt
        if chat_id not in self._conversations:
            self._conversations[chat_id] = [{"role": "system", "content": _SYSTEM_PROMPT}]

        conv = self._conversations[chat_id]
        conv.append({"role": "user", "content": text})

        # Show placeholder while LLM thinks, then replace with real answer
        thinking_msg = None
        try:
            thinking_msg = await update.message.reply_text("⏳")
        except TelegramError:
            pass

        reply = await chat_completion(conv)

        # Don't store error strings in conversation history
        _is_error = reply.startswith("Ошибка запроса:") or reply.startswith("OpenRouter API key")
        if _is_error:
            log_agent_action("Telegram", f"LLM error: {reply}", level="ERROR")
            conv.pop()  # remove the unanswered user message
            safe = "⚠️ Не удалось получить ответ. Попробуй ещё раз."
            try:
                if thinking_msg:
                    await thinking_msg.edit_text(safe)
                else:
                    await update.message.reply_text(safe)
            except TelegramError:
                pass
            return

        conv.append({"role": "assistant", "content": reply})

        # Keep history bounded: system[0] + last _MAX_HISTORY messages
        if len(conv) > _MAX_HISTORY + 1:
            self._conversations[chat_id] = [conv[0]] + conv[-_MAX_HISTORY:]

        # Replace placeholder with actual reply
        try:
            if thinking_msg:
                await thinking_msg.edit_text(reply, parse_mode="HTML")
            else:
                await update.message.reply_text(reply, parse_mode="HTML")
        except TelegramError:
            # Fallback: plain text if HTML parsing fails
            try:
                if thinking_msg:
                    await thinking_msg.edit_text(reply)
                else:
                    await update.message.reply_text(reply)
            except TelegramError as e:
                log_agent_action("Telegram", f"Failed to send reply: {e}", level="ERROR")

        log_agent_action("Telegram", f"Chat reply sent ({len(reply)} chars)")

    async def send_notification(self, text: str) -> None:
        if not self._app or not config.TELEGRAM_CHANNEL_ID:
            return
        try:
            await self._app.bot.send_message(
                chat_id=config.TELEGRAM_CHANNEL_ID,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send notification: {e}", level="ERROR")


telegram_bot = TelegramBot()
