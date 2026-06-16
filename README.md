# mvp-freelance-project-search

> Automated freelance project search — scrapes kwork.ru with Selenium, scores results, and surfaces the best matches via a REST API and Next.js UI.

A Python agent logs into kwork.ru headlessly, runs configurable keyword searches, applies multi-factor filters (response rate, proposals count, time remaining), scores each project, and stores the results. The Next.js frontend polls the agent and displays live results. Deployed on Render.

## Features

- **Headless login** — Selenium-based authenticated session, no API key required
- **Keyword search** — supports Cyrillic queries across project titles and descriptions
- **Multi-factor filtering** — time left, hired %, max proposals cap
- **Scoring engine** — ranks projects by relevance signal combination
- **Live debug feed** — `/api/debug` streams the last 300 log lines and agent state
- **Docker-ready** — `docker-compose.yml` for local and self-hosted deployment

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Scraping agent | Python, Selenium, Chrome |
| API | Next.js API routes |
| Frontend | Next.js (Pages Router), React |
| Deployment | Render (live), Vercel-compatible |
| Container | Docker, docker-compose |

## Getting Started

```bash
# Copy env template and fill in credentials
cp .env.example .env

# Start with Docker
docker-compose up

# Or run locally
npm install && npm run dev   # Next.js on :3000
cd python && pip install -r requirements.txt && python agent.py
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `KWORK_EMAIL` | kwork.ru account email |
| `KWORK_PASSWORD` | kwork.ru account password |

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/projects/search` | POST | Search with keyword + filters |
| `/api/projects/parse` | POST | Parse a single project URL |
| `/api/projects` | GET | List cached results |
| `/api/debug` | GET | Agent logs and status |

## License

MIT
