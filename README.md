# Freelance Project Search MVP

Search and parse projects from freelance platforms with advanced filtering options.

## Features

- Search projects by keywords (Cyrillic only)
- Parse projects from URLs
- Advanced filtering:
  - Time left (hours)
  - Hired percentage
  - Maximum proposals
- Real-time search results
- Project evaluation and scoring

## API Endpoints

- `POST /api/projects/search` - Search projects with filters
- `POST /api/projects/parse` - Parse project by URL
- `GET /api/projects` - Get found projects

## Debug / Logs

`GET /api/debug` — возвращает последние 300 строк логов Python-сервиса и текущее состояние агента.

```json
{
  "agent_status": "waiting",
  "driver_ready": true,
  "logged_in": true,
  "mode": "full",
  "kwork_email_set": true,
  "kwork_password_set": true,
  "projects_in_memory": 3,
  "logs": [
    { "timestamp": "...", "level": "INFO", "message": "...", "module": "...", "function": "..." }
  ]
}
```

Логи пишутся на каждый шаг поиска: получение запроса → setup_driver → login → пагинация → детали проектов → семантическая оценка → ответ.

## Note

This template uses mock data for demonstration. To connect to a real freelance platform API, update the API endpoints in `pages/api/projects/`.

