import asyncio
from typing import Any

from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from telegram.error import TelegramError

from config import config
from utils.logger import log_agent_action


class TelegramBot:
    def __init__(self):
        self._app: Application | None = None
        # chat_id -> list of pending projects waiting for КП selection
        self._pending: dict[str, list[dict[str, Any]]] = {}

    async def start(self) -> None:
        if not config.TELEGRAM_BOT_TOKEN:
            log_agent_action("Telegram", "Bot token not configured — disabled")
            return
        try:
            self._app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
            self._app.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_reply)
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
        if not self._app or not config.TELEGRAM_CHANNEL_ID:
            return
        if not projects:
            return

        chat_id = str(config.TELEGRAM_CHANNEL_ID)
        self._pending[chat_id] = projects

        lines = ["🎯 <b>Найдено подходящих проектов:</b>\n"]
        for i, p in enumerate(projects, 1):
            score = p.get("evaluation", {}).get("score", 0)
            budget = p.get("budget") or "?"
            lines.append(
                f"{i}. <b>{p.get('title', '?')[:60]}</b>\n"
                f"   💰 {budget}  ⭐ {score:.0%}\n"
                f"   🔗 {p.get('url', '')}\n"
            )

        lines.append(
            "\n📝 <b>Для каких проектов сгенерировать КП?</b>\n"
            "Ответьте номерами через пробел: <code>1 3 5</code> или <code>все</code>"
        )

        try:
            await self._app.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send projects: {e}", level="ERROR")

    async def _handle_reply(self, update: Update, context) -> None:
        chat_id = str(update.effective_chat.id)
        text = (update.message.text or "").strip()
        pending = self._pending.get(chat_id)

        if not pending:
            return

        if text.lower() in ("все", "all"):
            indices = list(range(len(pending)))
        else:
            indices = []
            for part in text.replace(",", " ").split():
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(pending):
                        indices.append(idx)
                except ValueError:
                    pass

        if not indices:
            await update.message.reply_text(
                "Не понял выбор. Пример: <code>1 3</code> или <code>все</code>",
                parse_mode="HTML",
            )
            return

        del self._pending[chat_id]
        await update.message.reply_text(f"⏳ Генерирую КП для {len(indices)} проект(ов)...")

        # Import here to avoid circular dependency at module load time
        from utils.cp_generator import cp_generator

        for idx in indices:
            project = pending[idx]
            try:
                proposal = await cp_generator.generate_proposal(
                    project.get("description", ""),
                    project.get("budget") or "Не указан",
                )
                msg = (
                    f"📋 <b>КП #{idx + 1}: {project.get('title', '')[:50]}</b>\n\n"
                    f"{proposal}"
                )
                await update.message.reply_text(msg, parse_mode="HTML")
                log_agent_action("Telegram", f"КП sent for project #{idx + 1}")
            except Exception as e:
                log_agent_action("Telegram", f"КП generation failed for #{idx + 1}: {e}", level="ERROR")
                await update.message.reply_text(f"❌ Не удалось сгенерировать КП для проекта {idx + 1}")

    async def send_notification(self, text: str) -> None:
        """Send a plain text notification (used for session summaries etc.)"""
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
