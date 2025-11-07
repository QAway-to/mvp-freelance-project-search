# 🤖 Freelance Agents MVP

Минимальный жизнеспособный продукт для автоматизации поиска проектов на Kwork с оценкой релевантности и отправкой уведомлений в Telegram.

## 🎯 Возможности

- 🔍 **Поиск проектов** на Kwork по ключевому слову "бот"
- 📊 **Оценка релевантности** на основе алгоритма (ключевые слова, бюджет, описание)
- 📱 **Real-time dashboard** с логами и управлением
- 📢 **Telegram уведомления** о подходящих проектах
- 🚀 **Автоматический деплой** на Render

## 🚀 Быстрый старт

### 1. Клонирование и установка

```bash
git clone <your-repo-url>
cd freelance-mvp

# Создание виртуального окружения
python -m venv venv
venv\Scripts\activate  # Windows
# или
source venv/bin/activate  # Linux/Mac

# Установка зависимостей
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Создайте файл `.env` на основе `env.example`:

```bash
# Для демо-режима (без реального Kwork)
MODE=demo

# Для полного режима (с Kwork)
MODE=full
KWORK_EMAIL=your_email@kwork.ru
KWORK_PASSWORD=your_password

# Telegram бот (опционально)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHANNEL_ID=@your_channel
```

### 3. Создание Telegram бота (опционально)

1. Напишите [@BotFather](https://t.me/botfather) в Telegram
2. Создайте бота командой `/newbot`
3. Скопируйте токен в `.env`
4. Создайте канал и добавьте бота как администратора
5. Получите channel ID через [@userinfobot](https://t.me/userinfobot)

### 4. Запуск

```bash
# Локальный запуск
python main.py

# Откройте http://localhost:8000 в браузере
```

## 🏗️ Архитектура

```
freelance-mvp/
├── main.py                 # FastAPI сервер
├── config.py              # Конфигурация
├── agents/
│   └── agent_a.py         # Агент поиска на Kwork
├── evaluation/
│   └── evaluator.py       # Оценка проектов
├── telegram_bot.py        # Telegram уведомления
├── utils/
│   └── logger.py          # Система логирования
├── templates/
│   └── dashboard.html     # Веб-интерфейс
├── static/
│   ├── css/style.css      # Стили
│   └── js/dashboard.js    # JavaScript
└── requirements.txt
```

## 🔧 Настройка деплоя на Railway

### 1. Создание аккаунта
Перейдите на [railway.app](https://railway.app) и зарегистрируйтесь через GitHub.

### 2. Создание проекта
1. Нажмите "New Project"
2. Выберите "Deploy from GitHub repo"
3. Подключите ваш GitHub репозиторий (`agent-a-kwork-mvp`)
4. Railway автоматически определит Python проект и начнет деплой

### 3. Настройка переменных окружения
В настройках проекта (Variables) добавьте все переменные из `env.example`:

```bash
# Обязательные
MODE=demo  # или full для реального использования
SEARCH_KEYWORD=бот

# Опциональные (для полной интеграции)
N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/freelance-project
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHANNEL_ID=@your_channel

# Для full режима
KWORK_EMAIL=your_email@kwork.ru
KWORK_PASSWORD=your_password
```

### 4. Автоматический деплой
- Railway автоматически деплоит при каждом push в main ветку
- Логи доступны в Railway Dashboard
- Health check endpoint: `/health`
- Status endpoint: `/status`

### 5. Получение URL
После деплоя Railway предоставит публичный URL вашего сервиса:
- Dashboard: `https://your-app.railway.app/`
- API: `https://your-app.railway.app/status`

## 🔗 Интеграция с n8n (Agent B)

Agent A автоматически отправляет подходящие проекты в n8n workflow через webhook.

### Настройка n8n workflow:

1. **Создайте webhook в n8n:**
   - Добавьте ноду "Webhook"
   - Скопируйте URL webhook
   - Добавьте его в Railway переменные: `N8N_WEBHOOK_URL`

2. **Структура данных, отправляемых в n8n:**
```json
{
  "project_id": "demo_1",
  "title": "Создать Telegram бота...",
  "description": "Описание проекта...",
  "budget": "15 000 ₽",
  "url": "https://kwork.ru/projects/...",
  "evaluation": {
    "score": 0.87,
    "reasons": ["Bot-related keywords found", ...],
    "suitable": true
  },
  "found_at": "2025-11-07T21:40:00",
  "status": "pending_review"
}
```

3. **API endpoints для управления:**
   - `POST /webhook/n8n` - Управление агентом из n8n (start/stop)
   - `GET /status` - Статус агента
   - `GET /health` - Health check

## 📊 Dashboard

Веб-интерфейс доступен по адресу вашего деплоя и предоставляет:

- **Статус агента** в реальном времени
- **Управление** (запуск/остановка)
- **Статистика** найденных проектов
- **Live логи** всех действий агента
- **Real-time обновления** через Server-Sent Events

## 🔍 Алгоритм оценки проектов

Проект считается подходящим если:

1. **Ключевые слова ботов** (вес 0.5):
   - бот, telegram, discord, vk, чатбот, автоматизация

2. **Технические навыки** (вес 0.3):
   - python, javascript, api, webhook

3. **Бюджет** (вес 0.2):
   - Предпочтительно 1000-30000 ₽

4. **Дополнительно**:
   - Отсутствие негативных слов (дизайн, текст, видео)
   - Подробное описание

**Порог релевантности**: 0.7 (70%)

## 🛡️ Безопасность и анти-детект

- **Stealth браузер** с рандомным User-Agent
- **Имитация человека** (паузы, движения мыши)
- **Ограничение сессий** (демо-режим без реального Kwork)
- **Отключение WebRTC** для защиты IP

## 📝 Логи и мониторинг

Все действия логируются с уровнями:
- `INFO`: Основные действия агента
- `WARNING`: Предупреждения
- `ERROR`: Ошибки выполнения
- `DEBUG`: Детальная отладка

Логи доступны:
- В терминале (локально)
- В веб-dashboard (real-time)
- В Railway logs (при деплое)

## 🔄 Рабочие режимы

### Demo режим (рекомендуется)
- Без реального доступа к Kwork
- Имитация поиска и оценки
- Полностью безопасно для тестирования

### Full режим
- Реальный поиск на Kwork
- Требует учетных данных
- Соблюдение лимитов для безопасности

## 🚧 Ограничения MVP

- Только поиск по одному ключевому слову
- Базовый алгоритм оценки
- Демо-режим без реальных предложений
- Ограниченная обработка ошибок

## 🛠️ Разработка

### Добавление нового функционала
1. Создайте ветку: `git checkout -b feature/new-feature`
2. Внесите изменения
3. Протестируйте локально
4. Создайте PR на GitHub

### Локальное тестирование
```bash
# Запуск с авто-перезагрузкой
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Запуск тестов (если добавите)
pytest
```

## 📄 Лицензия

MIT License - свободное использование для личных целей.

## 🤝 Поддержка

При возникновении проблем:
1. Проверьте логи в dashboard
2. Убедитесь в корректности `.env` файла
3. Проверьте подключение к интернету
4. Создайте issue в репозитории

---

**Happy freelancing! 🚀**
