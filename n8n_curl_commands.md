# cURL команды для импорта в n8n

Замените `YOUR_RENDER_URL` на ваш реальный URL Render (например: `https://agent-a-kwork-mvp.onrender.com`)

## 1. Получить все проекты

```bash
curl -X GET "https://YOUR_RENDER_URL.onrender.com/projects" \
  -H "Content-Type: application/json"
```

## 2. Получить только подходящие проекты

```bash
curl -X GET "https://YOUR_RENDER_URL.onrender.com/projects/suitable" \
  -H "Content-Type: application/json"
```

## 3. Получить статус агента

```bash
curl -X GET "https://YOUR_RENDER_URL.onrender.com/status" \
  -H "Content-Type: application/json"
```

## 4. Запустить одну сессию поиска

```bash
curl -X POST "https://YOUR_RENDER_URL.onrender.com/agent/run-session" \
  -H "Content-Type: application/json"
```

## 5. Запустить continuous режим

```bash
curl -X POST "https://YOUR_RENDER_URL.onrender.com/agent/start" \
  -H "Content-Type: application/json"
```

## 6. Остановить агента

```bash
curl -X POST "https://YOUR_RENDER_URL.onrender.com/agent/stop" \
  -H "Content-Type: application/json"
```

## 7. N8N Webhook - Получить все проекты (POST)

```bash
curl -X POST "https://YOUR_RENDER_URL.onrender.com/webhook/n8n/projects" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "all"
  }'
```

## 8. N8N Webhook - Получить только подходящие проекты (POST)

```bash
curl -X POST "https://YOUR_RENDER_URL.onrender.com/webhook/n8n/projects" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "suitable"
  }'
```

## 9. N8N Webhook - Получить конкретный проект по ID

```bash
curl -X POST "https://YOUR_RENDER_URL.onrender.com/webhook/n8n/projects" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "get",
    "project_id": "1234567"
  }'
```

## 10. N8N Webhook - Управление агентом (start/stop)

```bash
# Запустить агента
curl -X POST "https://YOUR_RENDER_URL.onrender.com/webhook/n8n" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "start"
  }'

# Остановить агента
curl -X POST "https://YOUR_RENDER_URL.onrender.com/webhook/n8n" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "stop"
  }'
```

## Как импортировать в n8n:

1. Откройте n8n
2. Создайте новый workflow
3. Добавьте ноду "HTTP Request"
4. В настройках ноды выберите "Import from cURL"
5. Вставьте одну из команд выше (заменив YOUR_RENDER_URL)
6. Сохраните и протестируйте

## Структура ответа для `/webhook/n8n/projects` (action: "suitable"):

```json
{
  "status": "success",
  "total": 3,
  "projects": [
    {
      "id": "1234567",
      "title": "Создать Telegram бота для уведомлений о скидках",
      "description": "Полное описание проекта...",
      "budget": "15 000 ₽",
      "url": "https://kwork.ru/projects/1234567/view",
      "proposals": 8,
      "hired": 0,
      "found_at": "2025-01-08T12:30:00",
      "evaluation": {
        "score": 0.87,
        "suitable": true,
        "reasons": ["Bot-related keywords found", "Good match"]
      }
    }
  ]
}
```

