import os
from typing import Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.error import TelegramError

from config import config
from utils.logger import log_agent_action
from utils.llm import chat_completion

_PROMPT_FILE = os.path.join(os.path.dirname(__file__), 'prompts', 'cp_system.txt')


def _load_system_prompt() -> str:
    try:
        with open(_PROMPT_FILE, encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        log_agent_action("Telegram", f"⚠️ Could not load cp_system.txt: {e}", level="WARNING")
        return "Ты — Александр, фрилансер. Пишешь коммерческие предложения на русском языке. Пиши кратко, конкретно, без шаблонов."


_SYSTEM_PROMPT = _load_system_prompt()

# Отдельный промпт для свободного чата в Telegram (меняй здесь)
_CHAT_SYSTEM_PROMPT = """Ты — Богдан, глава Федерации Здоровья. Пиши от первого лица, прямо и живо, как человек который сам прошёл через всё это и делится личным опытом. Не как ассистент и не как бот. Отвечай ТОЛЬКО на основе базы знаний ниже.

ФОРМАТ ОТВЕТА:
— Пиши чистым текстом, без markdown: без **, без *, без # и без дефисов в начале строк для списков
— Используй обычные абзацы с переносом строки между ними
— Нумерованные списки пиши цифрами: "1. ... 2. ..."
— В конце каждого ответа задай ОДИН осмысленный вопрос, который логично продолжает тему разговора и приглашает углубиться дальше. Вопрос должен быть разным каждый раз и вытекать из того, о чём говорили.
— Примерно в каждом третьем ответе (не в каждом, естественно и к месту) упомяни одну из наших соцсетей как источник дополнительного контента:
  TikTok: https://www.tiktok.com/@federaciya_zdoroviya
  Telegram-канал: https://t.me/+u9rdrsCuJfhlYmI6
  Упоминай их по очереди, коротко и без навязчивости — например: "Больше практик — в нашем Telegram-канале: ..."

БАЗА ЗНАНИЙ:

БЕГ БОСИКОМ

По росе — когда бежишь босиком по росе, ноги напитываются влагой, кожа очищается. Роса — самая чистая вода, доступная утром и вечером. Летом роса прохладная, осенью и весной тренирует терморегуляцию. Даже 20–30 секунд бега по росе дадут новый прилив энергии.

По снегу — бодрящий способ разбудить всё тело. 5–30 секунд достаточно для детей и взрослых. Лучше всего — после пробежки разуться и пробежать по чистому снегу.

По камешкам — массирует ступни и все внутренние органы через нервные окончания. Позволяет найти болевые точки и связать их с состоянием органов. Утром пробуждает тело, вечером снимает напряжение.

По ракушкам — очень приятно. Можно попросить собрать ракушки после шторма или привезти с моря. Дома стоять на них после сна — мягкий массаж стоп.

По воде / морю / берегу:
1. Ступни очищаются и впитывают влагу
2. Прохладная вода — закаливание (направленная терморегуляция)
3. Самомассаж через неровности дна
4. Включение внутренних органов через нервные окончания

По песку на пляже — кажется сложным, но это плюс: песок двигается под ногами, включаются дополнительные мышцы, которые не работают на твёрдом покрытии. Бежать в спокойном темпе. Минимум 3–4 недели практики раскрывают эффект полностью.

Подготовка трассы — обязательно пройти маршрут в обуви, убрать стекло и металлический мусор. Проверять каждый день: кто-то мог разбить бутылку накануне.

ПОЛЬЗА БЕГА БОСИКОМ:
1. Самомассаж внутренних органов через ступни
2. Закаливание
3. Тренировка терморегуляции
4. Очищение кожи ног
5. Заряд от земли
6. Гибкость и прокачка ступней
7. Ощущение опоры и уверенности

ВИДЫ БЕГА:

Перекат с пятки на носок — выполняется медленно, плавно. Главное — максимальная амплитуда переката и отталкивание пальцами в лёгкий прыжок. Дистанция 50–100 м, затем смена стиля.

Только на подушках — приземляться на подушки, отталкиваться разгибанием коленей. Создаёт ощущение парения. Концентрация на плавности и расслаблении. 100–200 м.

Полной стопой — хаотично хлопать всей стопой об землю. Создаёт вибрации, пробуждает внутренние органы. 100–500 м по ощущениям. После — 50 м спокойной ходьбы, прислушаться к телу.

Только на пальцах — как прыгает олень. Приземляться и сразу отталкиваться. Прыжок под 45° по направлению бега. Темп спокойный, скорость по ощущениям. Главное — ритм и плавность.

Быстрая ходьба / скоробег — в конце пробежки. Раскачивать таз вправо-влево, ускоряться на 30–50 м, держать скорость, затем замедляться. 2–3 подхода завершают пробежку.

ТЕХНИКА ДЫХАНИЯ:
— Медленный бег + максимальное дыхание: вдох на полную грудь, выдох с задержкой 1–2 сек
— Вдох и выдох ртом — только в чистых местах (лес, поляна, море)
— Бегать у дороги вредно: выхлопы распространяются на 1–2 км. Это накапливается в организме
— 1,5–2 км бега (~1000 вдохов) достаточно для насыщения организма кислородом
— Техника с чесноком: пожёвывать зубчик чеснока на пробежке — профилактика вирусов

ВИДЫ БЕГА ПО ЦЕЛЯМ:
— Перед тренировкой: разогрев, сброс калорий, снятие стресса
— Для марафона: развивает веру в себя — после 20–50 км понимаешь, что невозможного нет
— Для долголетия: тело — транспортное средство Души. Ежедневный уход накапливает здоровье
— Для оздоровления: кислород — первая еда для тела. Постепенное восстановление
— Для мотивации: бег даёт веру в преодоление препятствий. Кислород меняет восприятие ситуации
— Перед закаливанием: разогрев тела перед холодной водой

ПСИХОЛОГИЧЕСКАЯ ПОЛЬЗА:
1. Вера в преодоление препятствий
2. Вдохновение и новые идеи
3. Пробуждение организма утром
4. Сброс негативной энергии вечером

ВРЕД БЕГА:
— Бег у дороги: тяжёлые металлы из выхлопов не выводятся из организма
— Бег с лишним весом +50 кг: нагрузка на суставы, колени и сосуды

ВЫБОР КРОССОВОК:
— Подошва должна быть очень гибкой
— Размер — на полразмера больше для свободы стопы

ВАЖНО:
— Прислушивайся к телу: есть дни, когда лучше просто пройтись, а не бежать
— Перегруз ведёт к потере энергии — это минус, а не плюс
— Перепады температуры и давления влияют на готовность к нагрузке
— После снега: снять обувь на 5–10 секунд, потом сразу обуться и бежать согреваться
"""

_MAX_HISTORY = 20


class TelegramBot:
    def __init__(self):
        self._app: Application | None = None
        # chat_id -> list of projects from last search
        self._projects: dict[str, list[dict[str, Any]]] = {}
        # chat_id -> conversation history for free chat
        self._conversations: dict[str, list[dict[str, str]]] = {}
        # (chat_id, project_index) -> generated CP text (for resend/edit)
        self._pending_cp: dict[tuple[str, int], str] = {}

    async def start(self) -> None:
        if not config.TELEGRAM_BOT_ENABLED:
            log_agent_action("Telegram", "Bot disabled (TELEGRAM_BOT_ENABLED not set) — skipping polling")
            return
        if not config.TELEGRAM_BOT_TOKEN:
            log_agent_action("Telegram", "Bot token not configured — disabled")
            return
        try:
            self._app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
            self._app.add_handler(CommandHandler("start", self._handle_start))
            self._app.add_handler(CallbackQueryHandler(self._handle_callback))
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
        """Send each project as a separate message with inline КП button."""
        if not self._app or not config.TELEGRAM_CHANNEL_ID:
            return
        if not projects:
            return

        chat_id = str(config.TELEGRAM_CHANNEL_ID)
        self._projects[chat_id] = projects

        await self.send_notification(f"🎯 <b>Найдено {len(projects)} проектов:</b>")

        for i, p in enumerate(projects):
            title = (p.get("title") or "?")[:80]
            budget = p.get("budget") or "не указан"
            url = p.get("url") or ""
            desc = (p.get("description") or "")[:400]
            time_left = p.get("timeLeft") or ""

            text = (
                f"<b>{i + 1}. {title}</b>\n"
                f"💰 {budget}"
                + (f"  ⏳ {time_left}" if time_left else "") + "\n"
                + (f"\n{desc}\n" if desc else "")
                + (f"\n🔗 {url}" if url else "")
            )

            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✍️ Написать КП", callback_data=f"cp:{i}")
            ]])

            try:
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=keyboard,
                )
            except TelegramError as e:
                log_agent_action("Telegram", f"Failed to send project {i + 1}: {e}", level="ERROR")

        log_agent_action("Telegram", f"Sent {len(projects)} project cards to chat")

    async def _handle_callback(self, update: Update, context) -> None:
        query = update.callback_query
        await query.answer()

        chat_id = str(update.effective_chat.id)
        data = query.data or ""

        if data.startswith("cp:"):
            await self._generate_cp(query, chat_id, int(data[3:]))

        elif data.startswith("rewrite:"):
            await self._generate_cp(query, chat_id, int(data[8:]), rewrite=True)

        elif data.startswith("send:"):
            await self._send_response(query, chat_id, int(data[5:]))

    async def _generate_cp(self, query, chat_id: str, idx: int, rewrite: bool = False) -> None:
        projects = self._projects.get(chat_id, [])
        if idx >= len(projects):
            await query.edit_message_reply_markup(reply_markup=None)
            return

        p = projects[idx]
        title = p.get("title") or "?"
        budget = p.get("budget") or "не указан"
        desc = p.get("description") or "(нет описания)"

        action = "Переписываю" if rewrite else "Генерирую"
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except TelegramError:
            pass

        thinking_msg = None
        try:
            thinking_msg = await query.message.reply_text(f"⏳ {action} КП...")
        except TelegramError:
            pass

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Напиши КП для заказа с Kwork.\n\n"
                f"Название: {title}\n"
                f"Бюджет: {budget}\n"
                f"Описание:\n{desc}"
            )},
        ]
        if rewrite:
            prev = self._pending_cp.get((chat_id, idx), "")
            if prev:
                messages.append({"role": "assistant", "content": prev})
                messages.append({"role": "user", "content": "Перепиши КП — другой подход, другие слова."})

        cp_text = await chat_completion(messages)

        self._pending_cp[(chat_id, idx)] = cp_text

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Переписать", callback_data=f"rewrite:{idx}"),
            InlineKeyboardButton("✅ Отправить отклик", callback_data=f"send:{idx}"),
        ]])

        try:
            if thinking_msg:
                await thinking_msg.edit_text(cp_text, reply_markup=keyboard)
            else:
                await query.message.reply_text(cp_text, reply_markup=keyboard)
        except TelegramError:
            try:
                if thinking_msg:
                    await thinking_msg.edit_text(cp_text, reply_markup=keyboard, parse_mode=None)
            except TelegramError as e:
                log_agent_action("Telegram", f"Failed to send CP: {e}", level="ERROR")

        log_agent_action("Telegram", f"КП сгенерировано для проекта {idx + 1} ({len(cp_text)} симв.)")

    async def _send_response(self, query, chat_id: str, idx: int) -> None:
        """Submit the approved CP as a Kwork response via Selenium."""
        projects = self._projects.get(chat_id, [])
        cp_text = self._pending_cp.get((chat_id, idx))

        if idx >= len(projects) or not cp_text:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text("⚠️ КП не найдено. Сначала сгенерируй его.")
            except TelegramError:
                pass
            return

        p = projects[idx]
        url = p.get("url") or ""

        try:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text("⏳ Отправляю отклик на Kwork...")
        except TelegramError:
            pass

        # Import here to avoid circular import
        from agents.agent_a import agent_a_instance
        try:
            success = await agent_a_instance.submit_response(url, cp_text)
        except Exception as e:
            log_agent_action("Telegram", f"submit_response raised: {e}", level="ERROR")
            success = False

        result_text = (
            f"✅ Отклик отправлен на:\n{url}"
            if success else
            f"❌ Не удалось отправить отклик.\nПроверь вручную: {url}"
        )

        try:
            await query.message.reply_text(result_text, disable_web_page_preview=True)
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send result: {e}", level="ERROR")

    async def _handle_start(self, update: Update, context) -> None:
        if not update.message:
            return
        welcome = (
            "Приветствую! На связи Богдан, глава Федерации Здоровья.\n\n"
            "Здесь мы говорим о беге, здоровье и практиках, которые реально работают — проверено на себе и тысячах людей.\n\n"
            "Можешь спросить меня о:\n"
            "— беге босиком и его пользе\n"
            "— видах бега и технике\n"
            "— закаливании и терморегуляции\n"
            "— самомассаже через ступни\n"
            "— дыхании во время бега\n"
            "— подготовке к марафону\n\n"
            "Пиши — разберём подробно.\n\n"
            "Наши соцсети:\n"
            "TikTok: https://www.tiktok.com/@federaciya_zdoroviya\n"
            "Telegram-канал: https://t.me/+u9rdrsCuJfhlYmI6"
        )
        try:
            await update.message.reply_text(welcome, disable_web_page_preview=True)
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send welcome: {e}", level="ERROR")

    async def _handle_message(self, update: Update, context) -> None:
        """Free-form chat with LLM."""
        if not update.message or not update.message.text:
            return

        chat_id = str(update.effective_chat.id)
        text = update.message.text.strip()

        if chat_id not in self._conversations:
            self._conversations[chat_id] = [{"role": "system", "content": _CHAT_SYSTEM_PROMPT}]

        conv = self._conversations[chat_id]
        conv.append({"role": "user", "content": text})

        thinking_msg = None
        try:
            thinking_msg = await update.message.reply_text("⏳")
        except TelegramError:
            pass

        reply = await chat_completion(conv)

        _is_error = reply.startswith("Ошибка запроса:") or reply.startswith("DeepSeek API key")
        if _is_error:
            log_agent_action("Telegram", f"LLM error: {reply}", level="ERROR")
            conv.pop()
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
        if len(conv) > _MAX_HISTORY + 1:
            self._conversations[chat_id] = [conv[0]] + conv[-_MAX_HISTORY:]

        try:
            if thinking_msg:
                await thinking_msg.edit_text(reply, parse_mode="HTML")
            else:
                await update.message.reply_text(reply, parse_mode="HTML")
        except TelegramError:
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
