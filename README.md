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

## Note

This template uses mock data for demonstration. To connect to a real freelance platform API, update the API endpoints in `pages/api/projects/`.

