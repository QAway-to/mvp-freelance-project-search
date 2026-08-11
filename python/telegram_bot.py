import asyncio
from dataclasses import replace
from typing import Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, PreCheckoutQueryHandler, filters
from telegram.error import TelegramError

from config import config
from utils.logger import log_agent_action
from utils.llm import chat_completion
from utils.content_library import ContentItem, library, parse_caption
from utils.funnel_store import UserState, journal_premium, store
from utils.offer import load_offer

# Отдельный промпт для свободного чата в Telegram (меняй здесь)
_CHAT_SYSTEM_PROMPT = """Ты — представитель Федерации Здоровья. Говоришь от лица Федерации, прямо и по делу. Отвечай ТОЛЬКО на основе базы знаний ниже.

СТРОГИЕ ЗАПРЕТЫ:
— Никогда не выдумывай личные ситуации: "только что вернулся", "сегодня утром", "я как раз бежал" и подобное — запрещено
— Не ссылайся на текущее время, погоду, своё самочувствие или активности
— Не придумывай ничего, чего нет в базе знаний — лучше скажи что этой темы нет в базе

ФОРМАТ ОТВЕТА:
— Отвечай 4-5 предложениями, от первого лица, без вступлений и без ссылок на "базу знаний" или "материалы" — просто говори как человек, который это знает
— Без markdown-символов (**, *, #). Для выделения используй ТОЛЬКО HTML-теги Telegram: <b>важная фраза</b>
— Выделяй жирным ключевые термины и важные мысли — 2-4 выделения на ответ
— Нумерованные списки пиши цифрами: "1. ... 2. ..."
— В конце каждого ответа оставь пустую строку, затем задай ОДИН закрытый вопрос на отдельной строке, оберни его в <b>...</b>
— Вопрос должен предлагать выбор между двумя конкретными темами из нашей базы, которые ещё не обсуждались. Формат: "Что разберём дальше — <b>тема А</b> или <b>тема Б</b>?"
— Темы для выбора: бег по росе, бег по снегу, бег по камешкам, бег по песку, бег в воде, техника дыхания, виды бега (перекат/подушки/пальцы), закаливание, самомассаж через ступни, бег в дождь, как начать бегать, выбор кроссовок, бег для долголетия, бег перед закалкой
— Не повторяй темы вопросов которые уже звучали в диалоге
— Примерно в каждом третьем ответе (естественно и к месту) упомяни одну из соцсетей:
  TikTok: https://www.tiktok.com/@federaciya_zdoroviya
  Telegram-канал: https://t.me/+u9rdrsCuJfhlYmI6

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

ДВА ВИДА БЕГА:
Бег для долголетия — для 80% людей. Нужен всем: и спортсменам после карьеры, и обычным людям любого возраста.
Бег для спорта — марафоны, соревнования, дистанции от 10 км. Для профессионалов.

ГЛАВНАЯ КОНЦЕПЦИЯ — БЕЖАТЬ ЧТОБЫ ДЫШАТЬ:
Задача бега — наполнить организм кислородом. Кислород — самая важная еда для тела. Утром и вечером — два приёма этой еды.
1,5–2 км (примерно 1000 вдохов и выдохов) достаточно для полного насыщения всех органов. Больше — избыток, как переполненный стакан.

КОГДА БЕГАТЬ:
Утром на рассвете и вечером на закате — два лучших времени.

БЕГ В ДОЖДЬ:
Бег под дождём даёт заряд в 100–200% больше обычного. Дождь — это благодать. Вода с небес питает всё вокруг. Бежать в дождь — естественно и мощно.

ЛУЧШИЕ МЕСТА ДЛЯ БЕГА:
Лес — лучший вариант. Поле с разнотравьем — дышишь пыльцой, это дополнительное питание. Берег моря — соль и свежий воздух. Стадион с резиновым покрытием — вреден (запах резины в лёгкие). У дороги — категорически нет.

ДЫХАНИЕ ВО ВРЕМЯ БЕГА:
Начало — вдох и выдох ртом. Потом — вдох ртом, выдох носом. Потом — вдох носом, выдох носом. Носовое дыхание включает терморегуляцию и обогрев тела.
Боль в боку — сигнал нехватки кислорода (печень или селезёнка). Нужно участить дыхание, выдыхать полностью.

РАЗМИНКА:
Перед бегом — приседания и растяжка. Если бежишь легко ради дыхания — можно без разминки.

КАК НАЧИНАТЬ:
Первый раз — 500 м. Потом 1 км, 2 км — увеличивай постепенно. Никогда не начинай сразу с 5 км.

ДВИЖЕНИЕ РУК:
Во время бега сжимать и разжимать кисти рук — прокачка рук и улучшение кровообращения.

ТРАВМЫ — ПРИЧИНЫ:
— Бег у дороги
— Неправильная техника
— Чрезмерные нагрузки без отдыха
— Неподходящая обувь
— Слабые неподготовленные мышцы
— Лишний вес (+50 кг — большая нагрузка на колени и суставы)

ОТВЕТЫ НА ЧАСТЫЕ ВОПРОСЫ:
Как долго бегать? 1,5–2 км, 10–15 минут. Два раза в день — утром и вечером.
В какой обуви? Только в кроссовках с гибкой подошвой. Не в тапочках, не в ботинках.
По какой поверхности? Трава, лес, тропинка, песок. Асфальт — последний выбор.
Нужна ли разминка? Да, если планируешь нагрузку. Для лёгкого бега — необязательно.
Можно ли каждый день? Да, нужно. Два раза в день — норма.
Как выбрать темп? Бежишь в кайф, без напряжения. Устал — перешёл на шаг. Это нормально.
"""

_MAX_HISTORY = 20
_MAX_CONVERSATIONS = 500   # сколько чатов держим в памяти на 512MB инстансе

# Воронка — платный доступ через Telegram Stars.
# Состояние пользователей живёт в utils/funnel_store (Sheets + кеш в памяти),
# ролики — в приватном канале (utils/content_library).
_FUNNEL_CTA_AT = config.FUNNEL_CTA_AT      # после скольких сообщений показывать оффер
_STARS_PRICE = 1000                        # 1000 Stars ≈ $20
_REINDEX_MAX_SPAN = 200                    # сколько message_id за один /reindex
_REINDEX_PAUSE = 0.3                       # пауза между пробами, чтобы не словить flood limit
_BOOTSTRAP_SCAN = 60                       # сколько message_id пробуем при авто-старте
_BOOTSTRAP_RETRY = 60                      # пауза между попытками достучаться до канала
_BOOTSTRAP_MAX_WAIT = 1800                 # сколько всего ждём, пока бота добавят

_CTA_BUTTON = "🔗 Что входит и сколько стоит"

# Карточка продукта, продающий блок и CTA — из prompts/*.txt. Пока там метки
# <<...>>, оффер не показывается и ИИ не обсуждает покупку.
_OFFER = load_offer(config.PURCHASE_URL)

_PREMIUM_UNLOCKED_TEXT = (
    "Отлично! Доступ открыт. Теперь тебе доступны все материалы Федерации Здоровья.\n"
    "Продолжай задавать вопросы — отвечу максимально подробно."
)

# Ролики, залитые до перехода на канал-библиотеку. Эти file_id действительны
# только для этого бота, поэтому /migrate_legacy перекладывает их в канал —
# оттуда они переиндексируются как обычные посты. После миграции блок можно
# удалить.
_LEGACY_VIDEOS: dict[str, str] = {
    "закаливание": "BAACAgIAAxkDAAIBfWpEezcX3nMGQU0RY8aSA3dp_HtEAALhlQAC5FcpSja2XjngTYNdPAQ",
    "снег": "BAACAgIAAxkDAAIBgGpEfUTbkFzB8Flt6RK_GSXKhJlyAALqlQAC5FcpSmtVPv4uGvoYPAQ",
    "бокс": "BAACAgIAAxkDAAIBgWpEfU33PREwDgfBYnPvozQJrU2QAALrlQAC5FcpSi8916ciVtpWPAQ",
    "пляж": "BAACAgIAAxkDAAIBkGpEiOMClAjxv3xG5LRKlmxHoSTnAAIKlgAC5FcpSj2V9d4AARU35TwE",
    "вода": "BAACAgIAAxkDAAIBkWpEiOnmo8Q9gOGQSE_s2RO0TPOMAAILlgAC5FcpSkUcjJ7zKjRGPAQ",
}


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
            # concurrent_updates=False задан явно: обработчики читают состояние
            # пользователя, потом уходят в await к LLM и сохраняют его обратно —
            # параллельная обработка апдейтов одного чата затрёт счётчики.
            self._app = (
                Application.builder()
                .token(config.TELEGRAM_BOT_TOKEN)
                .concurrent_updates(False)
                .build()
            )
            self._app.add_handler(CommandHandler("start", self._handle_start))
            self._app.add_handler(CommandHandler("status", self._handle_status))
            self._app.add_handler(CommandHandler("reindex", self._handle_reindex))
            self._app.add_handler(CommandHandler("migrate_legacy", self._handle_migrate_legacy))
            if config.PAYMENTS_ENABLED:
                self._app.add_handler(CommandHandler("buy", self._handle_buy))
                self._app.add_handler(CommandHandler("testpay", self._handle_testpay))
                self._app.add_handler(PreCheckoutQueryHandler(self._handle_precheckout))
                self._app.add_handler(
                    MessageHandler(filters.SUCCESSFUL_PAYMENT, self._handle_payment_success)
                )
            self._app.add_handler(CallbackQueryHandler(self._handle_callback))
            # Посты в канале-библиотеке — до общего текстового хендлера,
            # иначе подпись поста уйдёт в LLM как вопрос пользователя.
            self._app.add_handler(
                MessageHandler(filters.UpdateType.CHANNEL_POST, self._handle_channel_post)
            )
            self._app.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
            )

            await store.start()
            await library.load()
            self._warn_about_config_gaps()
            self._warn_about_unreachable_premium()

            await self._app.initialize()
            await self._app.start()
            # drop_pending_updates=False: посты в канал, сделанные пока сервис
            # спал, иначе потерялись бы вместе с индексом.
            await self._app.updater.start_polling(drop_pending_updates=False)
            log_agent_action("Telegram", f"Bot started (polling), {len(library)} videos indexed")
            # Фоном: перебор постов канала занимает десятки секунд, а бот
            # должен отвечать сразу.
            asyncio.create_task(self._bootstrap_content())
        except Exception as e:
            log_agent_action("Telegram", f"Bot startup failed: {e} — running without Telegram", level="WARNING")
            # store.start() мог уже поднять фоновый флашер — иначе он останется
            # сиротой и будет ходить в Sheets каждые 10с до конца жизни процесса.
            await store.stop()
            self._app = None

    def _warn_about_config_gaps(self) -> None:
        """Молчаливая недонастройка дороже шумного лога: без CONTENT_CHANNEL_ID
        бот не отдаст ни одного ролика и никак об этом не сообщит."""
        if not config.CONTENT_CHANNEL_ID:
            log_agent_action(
                "Content",
                "CONTENT_CHANNEL_ID не задан — ролики отключены полностью, "
                "бот будет отвечать только текстом",
                level="ERROR",
            )
        if not config.ADMIN_CHAT_ID:
            log_agent_action(
                "Telegram",
                "ADMIN_CHAT_ID не задан — /reindex и /migrate_legacy недоступны, "
                "алерты о сбоях никуда не уйдут",
                level="WARNING",
            )

    def _warn_about_unreachable_premium(self) -> None:
        """С выключенной кассой is_premium ни у кого не станет True, поэтому
        ролики с tier: premium не увидит никто и никогда — молча."""
        if config.PAYMENTS_ENABLED:
            return
        locked = library.premium_count()
        if locked:
            log_agent_action(
                "Content",
                f"{locked} роликов помечены tier: premium, но оплата выключена — "
                "их не увидит никто. Перемаркируйте посты в канале как free.",
                level="WARNING",
            )

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            await store.stop()
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

        elif data == "offer":
            await self._handle_offer_click(query, chat_id)

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

        from utils.cp_generator import build_system_prompt
        system_prompt, cp_type = await build_system_prompt(p)
        log_agent_action("Telegram", f"тип задания для КП: {cp_type.value}")

        messages = [
            {"role": "system", "content": system_prompt},
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

    # --- Касса внутри бота: спит при PAYMENTS_ENABLED=false ------------------
    # Четыре метода ниже не зарегистрированы как хендлеры, пока флаг опущен.
    # Оставлены намеренно: продажа сейчас закрывается на внешней странице,
    # но Stars может понадобиться снова — код рабочий и покрыт.

    async def _handle_buy(self, update: Update, context) -> None:
        if not update.message:
            return
        try:
            await update.message.reply_invoice(
                title="Доступ к материалам Федерации Здоровья",
                description="Полный доступ: расширенные практики, видеоматериалы и персональные рекомендации по бегу и долголетию.",
                payload="premium_access",
                currency="XTR",
                prices=[LabeledPrice(label="Полный доступ", amount=_STARS_PRICE)],
            )
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send invoice: {e}", level="ERROR")

    async def _handle_testpay(self, update: Update, context) -> None:
        """MVP: открывает доступ без реальной оплаты для тестирования."""
        if not update.message:
            return
        chat_id = str(update.effective_chat.id)
        await self._grant_premium(chat_id, "testpay")
        try:
            await update.message.reply_text(_PREMIUM_UNLOCKED_TEXT, parse_mode="HTML")
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send testpay confirm: {e}", level="ERROR")

    async def _handle_precheckout(self, update, context) -> None:
        query = update.pre_checkout_query
        if query.invoice_payload != "premium_access":
            await query.answer(ok=False, error_message="Неизвестный товар. Попробуй /buy заново.")
            log_agent_action(
                "Telegram", f"Rejected precheckout with payload {query.invoice_payload!r}", level="WARNING"
            )
            return
        await query.answer(ok=True)

    async def _handle_payment_success(self, update: Update, context) -> None:
        if not update.message:
            return
        chat_id = str(update.effective_chat.id)
        payment = update.message.successful_payment
        await self._grant_premium(
            chat_id,
            "stars",
            amount=getattr(payment, "total_amount", 0),
            charge_id=getattr(payment, "telegram_payment_charge_id", ""),
        )
        try:
            await update.message.reply_text(_PREMIUM_UNLOCKED_TEXT, parse_mode="HTML")
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send payment confirm: {e}", level="ERROR")

    async def _grant_premium(self, chat_id: str, reason: str, **details: Any) -> None:
        """Persist the unlock immediately — a lost payment is not recoverable.

        Order matters: the local journal is written first and synchronously, so
        even a container killed before Sheets answers can restore the grant on
        the next start.
        """
        journal_premium(chat_id, reason, details)
        state = store.user(chat_id)
        persisted = await store.save(replace(state, is_premium=True), immediate=True)
        await store.event(chat_id, "premium_granted", reason=reason, **details)
        log_agent_action("Telegram", f"Premium granted to {chat_id} ({reason})")

        if not persisted:
            # Диск на free tier эфемерный, поэтому журнал переживает не всякий
            # рестарт. Telegram — единственный канал, который точно переживёт
            # подмену контейнера: пусть запись останется хотя бы в чате админа.
            await self._alert_admin(
                "⚠️ <b>Оплата не записалась в Sheets</b>\n"
                f"chat_id: <code>{chat_id}</code>\n"
                f"причина: {reason}\n"
                f"детали: <code>{details}</code>\n\n"
                "Доступ выдан в памяти. Если сервис перезапустится до того, как "
                "запись уйдёт, восстановите premium вручную по этому сообщению."
            )

    async def _alert_admin(self, text: str) -> None:
        if not self._app or not config.ADMIN_CHAT_ID:
            log_agent_action("Telegram", "ADMIN_CHAT_ID not set — alert dropped", level="ERROR")
            return
        try:
            await self._app.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID, text=text, parse_mode="HTML"
            )
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to alert admin: {e}", level="ERROR")

    async def _handle_start(self, update: Update, context) -> None:
        if not update.message:
            return

        chat_id = str(update.effective_chat.id)
        # Deep link: t.me/<bot>?start=tiktok -> источник трафика
        source = (context.args[0] if getattr(context, "args", None) else "")[:40]
        state = store.user(chat_id, source=source)
        if source and not state.source:
            state = replace(state, source=source)
            await store.save(state)
        await store.event(chat_id, "start", bucket=state.bucket, source=state.source)

        try:
            await update.message.reply_photo(photo="AgACAgIAAxkDAAIBlGpEjyrhn3nTmkDj9hU9fh0JekdBAALGGGsb5FcpSiuxj4BBUhnnAQADAgADdwADPAQ")
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send welcome photo: {e}", level="WARNING")
        welcome = (
            "Приветствую! На связи Богдан, глава Федерации Здоровья.\n\n"
            "Здесь мы говорим о беге, здоровье и практиках, которые реально работают — проверено на себе и тысячах людей.\n\n"
            "Наши соцсети:\n"
            "TikTok: https://www.tiktok.com/@federaciya_zdoroviya\n"
            "Telegram-канал: https://t.me/+u9rdrsCuJfhlYmI6\n\n"
            "С чего начнём?\n\n"
            "<b>Бег босиком и его польза</b>\n"
            "<b>Виды бега и техника</b>\n"
            "<b>Закаливание и терморегуляция</b>\n"
            "<b>Дыхание во время бега</b>\n"
            "<b>Как начать бегать с нуля</b>\n"
            "<b>Бег для долголетия</b>"
        )
        try:
            await update.message.reply_text(welcome, parse_mode="HTML", disable_web_page_preview=True)
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send welcome: {e}", level="ERROR")

    async def _handle_message(self, update: Update, context) -> None:
        """Free-form chat with LLM."""
        if not update.message or not update.message.text:
            return

        chat_id = str(update.effective_chat.id)
        text = update.message.text.strip()

        state = store.user(chat_id)
        state = replace(state, messages=state.messages + 1)
        await store.save(state)
        is_premium = state.is_premium

        if chat_id not in self._conversations:
            system_prompt = _CHAT_SYSTEM_PROMPT + _OFFER.system_suffix()
            self._conversations[chat_id] = [{"role": "system", "content": system_prompt}]
        else:
            # LRU: перекладываем в конец, чтобы вытеснялись самые давние чаты
            self._conversations[chat_id] = self._conversations.pop(chat_id)
        while len(self._conversations) > _MAX_CONVERSATIONS:
            self._conversations.pop(next(iter(self._conversations)))

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

        reply, price_blocked = _OFFER.sanitize_reply(reply)
        if price_blocked:
            log_agent_action(
                "Telegram",
                f"Ответ с ценой заблокирован (оффер не настроен), chat {chat_id}",
                level="ERROR",
            )
            await store.event(chat_id, "price_talk_blocked", bucket=state.bucket)
            await self._alert_admin(
                "⚠️ Модель заговорила о цене при ненастроенном оффере.\n"
                f"chat_id: <code>{chat_id}</code>\n"
                "Ответ подменён. Заполни prompts/product.txt."
            )

        conv.append({"role": "assistant", "content": reply})
        if len(conv) > _MAX_HISTORY + 1:
            self._conversations[chat_id] = [conv[0]] + conv[-_MAX_HISTORY:]

        show_cta = _OFFER.is_ready and not is_premium and state.messages >= _FUNNEL_CTA_AT

        try:
            if thinking_msg:
                await thinking_msg.delete()
                thinking_msg = None
        except TelegramError:
            pass

        # Сначала видео — потом текст. Только по теме и только один раз:
        # случайный ролик не в тему обесценивает остальные.
        await self._send_topic_video(update, state, text)

        try:
            await update.message.reply_text(reply, parse_mode="HTML")
        except TelegramError:
            try:
                await update.message.reply_text(reply)
            except TelegramError as e:
                log_agent_action("Telegram", f"Failed to send reply: {e}", level="ERROR")

        log_agent_action("Telegram", f"Chat reply sent ({len(reply)} chars)")

        if show_cta:
            await self._send_offer_cta(update, state)

    async def _send_offer_cta(self, update: Update, state: UserState) -> None:
        """Оффер отдельным сообщением с кнопкой — так виден и показ, и клик."""
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(_CTA_BUTTON, callback_data="offer")
        ]])
        try:
            await update.message.reply_text(
                _OFFER.cta_text, parse_mode="HTML", reply_markup=keyboard
            )
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send CTA: {e}", level="WARNING")
            return

        await store.save(replace(state, cta_shown=state.cta_shown + 1))
        await store.event(
            state.chat_id, "cta_shown", bucket=state.bucket, at_message=state.messages
        )

    async def _handle_offer_click(self, query, chat_id: str) -> None:
        """Клик по офферу — единственная точка перед оплатой, которую бот видит."""
        state = store.user(chat_id)
        await store.event(chat_id, "offer_clicked", bucket=state.bucket, at_message=state.messages)

        if not _OFFER.is_ready:
            log_agent_action(
                "Telegram", "Offer clicked but not configured: " + "; ".join(_OFFER.blockers), level="ERROR"
            )
            await query.message.reply_text("Подробности скоро — напиши мне, всё расскажу.")
            return

        if not _OFFER.purchase_url:
            log_agent_action("Telegram", "Offer clicked, but PURCHASE_URL is empty", level="WARNING")
            await query.message.reply_text(
                "Страница оплаты ещё подключается. Напиши мне — отвечу на любые вопросы "
                "по программе и подскажу, с чего начать."
            )
            return

        separator = "&" if "?" in _OFFER.purchase_url else "?"
        url = f"{_OFFER.purchase_url}{separator}uid={chat_id}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Перейти к оплате", url=url)]])
        try:
            await query.message.reply_text(
                "Вот страница с условиями и оплатой:", reply_markup=keyboard
            )
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send purchase link: {e}", level="ERROR")

    # ------------------------------------------------------------------
    # Библиотека роликов (приватный канал)
    # ------------------------------------------------------------------

    async def _send_topic_video(self, update: Update, state: UserState, text: str) -> None:
        """Отправить релевантный ролик из канала, если он есть и ещё не показан."""
        if not config.CONTENT_CHANNEL_ID or not self._app:
            return

        item = library.match(text, is_premium=state.is_premium, exclude=state.seen_content)
        if not item:
            return

        try:
            await self._app.bot.copy_message(
                chat_id=update.effective_chat.id,
                from_chat_id=config.CONTENT_CHANNEL_ID,
                message_id=item.message_id,
            )
        except TelegramError as e:
            log_agent_action("Telegram", f"Failed to send video {item.message_id}: {e}", level="WARNING")
            return

        await store.save(replace(state, seen_content=state.seen_content + (item.message_id,)))
        await store.event(
            state.chat_id, "video_sent", message_id=item.message_id, title=item.title
        )

    async def _handle_channel_post(self, update: Update, context) -> None:
        """Индексировать новый пост в канале-библиотеке."""
        post = update.channel_post
        if not post or not config.CONTENT_CHANNEL_ID:
            return
        if str(post.chat_id) != str(config.CONTENT_CHANNEL_ID):
            return
        if not (post.video or post.video_note or post.animation):
            return

        item = parse_caption(post.caption, post.message_id)
        await library.upsert(item)
        log_agent_action(
            "Content",
            f"Indexed post {item.message_id}: tags={','.join(item.tags) or '—'} tier={item.tier}",
        )

    async def _deny_non_admin(self, update: Update, command: str) -> bool:
        """True, если вызвавший не админ. Молчаливый отказ неотличим от
        «команда не дошла», поэтому всегда отвечаем и логируем реальный id."""
        chat_id = str(update.effective_chat.id)
        if config.ADMIN_CHAT_ID and chat_id == str(config.ADMIN_CHAT_ID):
            log_agent_action("Telegram", f"{command} запущена админом {chat_id}")
            return False

        log_agent_action(
            "Telegram",
            f"{command} отклонена: chat_id={chat_id}, "
            f"ADMIN_CHAT_ID={config.ADMIN_CHAT_ID or 'не задан'}",
            level="WARNING",
        )
        try:
            await update.message.reply_text(
                "Команда только для администратора.\n"
                f"Твой chat_id: <code>{chat_id}</code>\n"
                "Если это ты — впиши его в ADMIN_CHAT_ID на Render.",
                parse_mode="HTML",
            )
        except TelegramError:
            pass
        return True

    async def _scan_channel(self, probe_chat: str, limit: int) -> list[ContentItem]:
        """Собрать ролики, уже лежащие в канале.

        Bot API не отдаёт историю канала, поэтому каждый пост пересылается и
        сразу удаляется — единственный способ увидеть подпись.
        """
        found: list[ContentItem] = []
        for message_id in range(1, limit + 1):
            try:
                forwarded = await self._app.bot.forward_message(
                    chat_id=probe_chat,
                    from_chat_id=config.CONTENT_CHANNEL_ID,
                    message_id=message_id,
                )
            except TelegramError:
                continue  # дырка в нумерации или пост удалён
            if forwarded.video or forwarded.video_note or forwarded.animation:
                found.append(parse_caption(forwarded.caption, message_id))
            try:
                await self._app.bot.delete_message(
                    chat_id=probe_chat, message_id=forwarded.message_id
                )
            except TelegramError:
                pass
            await asyncio.sleep(_REINDEX_PAUSE)
        return found

    async def _await_channel_access(self) -> bool:
        """Дождаться, пока бота добавят в канал.

        Проверка только на старте бесполезна: бота добавляют руками и уже после
        того, как сервис поднялся. Поэтому пробуем повторно — тогда ролики
        появятся сами, без перезапуска.
        """
        waited = 0
        complained = False
        while True:
            try:
                chat = await self._app.bot.get_chat(config.CONTENT_CHANNEL_ID)
                log_agent_action("Content", f"Канал доступен: {chat.title or chat.id}")
                return True
            except TelegramError as e:
                if not complained:
                    log_agent_action(
                        "Content",
                        f"НЕТ ДОСТУПА К КАНАЛУ {config.CONTENT_CHANNEL_ID} ({e}). "
                        "Добавьте бота администратором в канал — проверяю раз в минуту, "
                        "перезапуск не нужен. Если бот уже добавлен, сверьте ID: "
                        "он должен начинаться с -100 и принадлежать каналу.",
                        level="ERROR",
                    )
                    complained = True
                if waited >= _BOOTSTRAP_MAX_WAIT:
                    log_agent_action(
                        "Content",
                        f"Канал так и не открылся за {_BOOTSTRAP_MAX_WAIT // 60} минут — "
                        "перестаю проверять до следующего запуска",
                        level="ERROR",
                    )
                    return False
                await asyncio.sleep(_BOOTSTRAP_RETRY)
                waited += _BOOTSTRAP_RETRY

    async def _bootstrap_content(self) -> None:
        """Наполнить библиотеку без участия человека.

        Сначала подбираем то, что уже лежит в канале; если там пусто — заливаем
        легаси-ролики. Иначе индекс пришлось бы каждый раз восстанавливать
        руками, а команду в Telegram может нажать только владелец.
        """
        if not config.CONTENT_CHANNEL_ID or not self._app:
            return
        if len(library):
            return

        if not await self._await_channel_access():
            return

        probe_chat = str(config.ADMIN_CHAT_ID or config.CONTENT_CHANNEL_ID)
        try:
            found = await self._scan_channel(probe_chat, _BOOTSTRAP_SCAN)
            if found:
                await library.upsert_many(found)
                log_agent_action("Content", f"Авто-индексация: найдено роликов {len(found)}")
                return

            log_agent_action("Content", "В канале роликов нет — переношу легаси")
            moved = 0
            for tag, file_id in _LEGACY_VIDEOS.items():
                try:
                    await self._app.bot.send_video(
                        chat_id=config.CONTENT_CHANNEL_ID,
                        video=file_id,
                        caption=f"#{tag}\ntier: free",
                    )
                    moved += 1
                except TelegramError as e:
                    log_agent_action("Content", f"Легаси-ролик {tag} не перенесён: {e}", level="ERROR")
                await asyncio.sleep(_REINDEX_PAUSE)
            log_agent_action("Content", f"Перенесено легаси-роликов: {moved}")
        except Exception as e:  # старт бота важнее наполнения библиотеки
            log_agent_action("Content", f"Авто-наполнение прервано: {e}", level="ERROR")

    async def _handle_status(self, update: Update, context) -> None:
        """Что настроено, а что нет — видно прямо из бота."""
        if not update.message or await self._deny_non_admin(update, "/status"):
            return

        def mark(ok: bool) -> str:
            return "✅" if ok else "❌"

        offer_line = (
            f"{mark(_OFFER.is_ready)} оффер"
            + (" (ДЕМО-данные)" if _OFFER.is_demo else "")
            + ("" if _OFFER.is_ready else ": " + "; ".join(_OFFER.blockers))
        )
        lines = [
            "<b>Состояние бота</b>",
            f"{mark(bool(config.CONTENT_CHANNEL_ID))} канал с роликами",
            f"{mark(len(library) > 0)} роликов в индексе: {len(library)}",
            offer_line,
            f"{mark(True)} оффер после сообщений: {_FUNNEL_CTA_AT}",
            f"{'💳' if config.PAYMENTS_ENABLED else '➖'} касса в боте: "
            + ("включена" if config.PAYMENTS_ENABLED else "выключена"),
        ]
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _handle_reindex(self, update: Update, context) -> None:
        """/reindex <from_id> <to_id> — пересобрать индекс по постам канала.

        Bot API не умеет читать историю канала, поэтому каждый пост
        пересылается сюда (единственный способ увидеть подпись) и сразу
        удаляется.
        """
        if not update.message or await self._deny_non_admin(update, "/reindex"):
            return
        if not config.CONTENT_CHANNEL_ID:
            await update.message.reply_text("CONTENT_CHANNEL_ID не задан.")
            return

        args = getattr(context, "args", None) or []
        if len(args) != 2 or not all(a.isdigit() for a in args):
            await update.message.reply_text("Формат: /reindex <от_id> <до_id>")
            return

        start_id, end_id = int(args[0]), int(args[1])
        if end_id < start_id or end_id - start_id >= _REINDEX_MAX_SPAN:
            await update.message.reply_text(f"Диапазон до {_REINDEX_MAX_SPAN} сообщений.")
            return

        progress = await update.message.reply_text(f"⏳ Сканирую {start_id}–{end_id}...")
        found: list[ContentItem] = []
        for message_id in range(start_id, end_id + 1):
            try:
                forwarded = await self._app.bot.forward_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=config.CONTENT_CHANNEL_ID,
                    message_id=message_id,
                )
            except TelegramError:
                continue  # дырка в нумерации или пост удалён
            if forwarded.video or forwarded.video_note or forwarded.animation:
                found.append(parse_caption(forwarded.caption, message_id))
            try:
                await self._app.bot.delete_message(
                    chat_id=update.effective_chat.id, message_id=forwarded.message_id
                )
            except TelegramError:
                pass
            await asyncio.sleep(_REINDEX_PAUSE)

        count = await library.upsert_many(found)
        await progress.edit_text(f"✅ Проиндексировано роликов: {count}. Всего в библиотеке: {len(library)}")

    async def _handle_migrate_legacy(self, update: Update, context) -> None:
        """Перелить ролики из старых file_id в канал — без перезаливки файлов."""
        if not update.message or await self._deny_non_admin(update, "/migrate_legacy"):
            return
        if not config.CONTENT_CHANNEL_ID:
            await update.message.reply_text("CONTENT_CHANNEL_ID не задан.")
            return

        moved = 0
        errors: list[str] = []
        for tag, file_id in _LEGACY_VIDEOS.items():
            try:
                await self._app.bot.send_video(
                    chat_id=config.CONTENT_CHANNEL_ID,
                    video=file_id,
                    caption=f"#{tag}\ntier: free",
                )
                moved += 1
            except TelegramError as e:
                errors.append(f"{tag}: {e}")
                log_agent_action("Telegram", f"Legacy migration failed for {tag}: {e}", level="ERROR")
            await asyncio.sleep(_REINDEX_PAUSE)

        log_agent_action(
            "Telegram", f"/migrate_legacy: перенесено {moved} из {len(_LEGACY_VIDEOS)}"
        )
        report = f"Перенесено в канал: {moved} из {len(_LEGACY_VIDEOS)}."
        if errors:
            report += "\n\nОшибки:\n" + "\n".join(errors[:5])
        else:
            report += "\nПосты проиндексируются автоматически как обычные публикации."
        await update.message.reply_text(report)

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
