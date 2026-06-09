# Startup News Tracker

Startup News Tracker is a Phase 1 startup funding intelligence platform. It ingests startup funding articles from Google News RSS, stores canonical article records in PostgreSQL, exposes them through a FastAPI REST API, and renders an operational Next.js dashboard for browsing and filtering the feed.

The project is split into two application services plus shared root scripts:

- `services/backend`: FastAPI ingestion engine, REST API, database models, Alembic migrations, and tests.
- `services/dashboard`: Next.js React dashboard website.
- `scripts`: convenience scripts for starting the backend stack, dashboard, or full project.

## Documentation

- [Backend Architecture](docs/backend-architecture.md)
- [Frontend Architecture](docs/frontend-architecture.md)
- [Database Architecture](docs/database-architecture.md)

## Current Capabilities

- Ingests Google News RSS results for `india startup funding`.
- Uses a plugin interface so additional article sources can be added without changing ingestion orchestration.
- Deduplicates articles by URL before writing to the database.
- Stores article source, title, URL, published timestamp, feed content, and creation timestamp.
- Provides REST endpoints for health checks and article reads.
- Runs as independent backend and dashboard services through Docker Compose.
- Shows a dashboard with article metrics, search, source filtering, source mix, live/error/empty states, and links to original articles.

## Tech Stack

Backend:

- Python
- FastAPI
- SQLAlchemy 2.0 async ORM
- asyncpg
- PostgreSQL 17
- Alembic
- Pydantic v2
- httpx
- feedparser
- pytest, black, ruff

Frontend:

- Next.js
- React
- TypeScript
- CSS modules through the App Router global stylesheet

Infrastructure:

- Docker Compose
- Shared shell scripts under `scripts/`

## Repository Layout

```text
.
|-- docker-compose.yml
|-- docs
|   |-- backend-architecture.md
|   |-- database-architecture.md
|   `-- frontend-architecture.md
|-- scripts
|   |-- start-all.sh
|   |-- start-backend.sh
|   `-- start-dashboard.sh
|-- services
|   |-- backend
|   |   |-- alembic
|   |   |-- app
|   |   |-- scripts
|   |   `-- tests
|   `-- dashboard
|       `-- app
`-- README.md
```

## Prerequisites

- Docker Desktop or another Docker daemon.
- Docker Compose.
- Node.js 22+ if running the dashboard outside Docker.
- Python 3.14-compatible environment if running backend tests outside Docker.

If `./scripts/start-all.sh` fails with a message like `Cannot connect to the Docker daemon`, start Docker Desktop first and wait until `docker info` succeeds.

## Environment

Create a local `.env` from the example:

```bash
cp .env.example .env
```

Default values:

```env
DATABASE_URL=postgresql+asyncpg://startup_news:startup_news@localhost:5432/startup_news
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
ENABLED_SOURCES=
SOURCE_TIMEOUT_SECONDS=30
SOURCE_USER_AGENT=StartupNewsTracker/1.0 (+https://localhost)
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Docker Compose overrides the backend database host to `postgres` for containers.
Leave `ENABLED_SOURCES` empty to run all public source plugins, or set a comma-separated list such as `google_news_funding,entrackr_funding`.

## Run The Full Project

```bash
./scripts/start-all.sh
```

This starts:

- `postgres`: PostgreSQL database.
- `migrate`: Alembic migration job.
- `backend-api`: FastAPI REST API on port `8000`.
- `ingester`: recurring ingestion worker.
- `dashboard`: Next.js dashboard on port `3000`.

Local URLs:

- Dashboard: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

## Run Services Separately

Backend stack only:

```bash
./scripts/start-backend.sh
```

Dashboard only:

```bash
./scripts/start-dashboard.sh
```

The dashboard expects the backend API to be reachable at `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://localhost:8000`.

## Manual Ingestion

Run one ingestion pass:

```bash
docker compose run --rm backend-api python -m scripts.ingest --once
```

Run the recurring ingester:

```bash
docker compose up --build ingester
```

The recurring interval defaults to `3600` seconds in `docker-compose.yml`.

Current public source plugins:

- `google_news_funding`
- `google_news_venture_capital`
- `entrackr_funding`
- `inc42_india_funding`
- `yourstory_startup_funding`
- `vccircle_startup_funding`

## REST API

### `GET /health`

Returns API health status.

Example:

```json
{
  "status": "ok"
}
```

### `GET /articles`

Returns articles ordered by `published_at` descending, then `created_at` descending.

Query parameters:

- `limit`: number of records to return, default `20`, minimum `1`, maximum `100`.
- `offset`: pagination offset, default `0`.

Example:

```bash
curl "http://localhost:8000/articles?limit=20&offset=0"
```

### `GET /articles/{article_id}`

Returns one article by UUID. Returns `404` when the article is not found.

## Development

Backend checks:

```bash
cd services/backend
../../.venv/bin/python -m pytest
../../.venv/bin/black --check app scripts tests alembic
../../.venv/bin/ruff check app scripts tests alembic
```

Dashboard checks:

```bash
cd services/dashboard
npm run typecheck
npm run build
```

Docker Compose validation:

```bash
docker compose config
```

## Adding A New Source Plugin

1. Create a new class under `services/backend/app/ingestion/plugins/`.
2. Subclass `SourcePlugin`.
3. Implement `async def fetch(self) -> list[RawArticle]`.
4. Import the plugin from `services/backend/app/ingestion/plugins/__init__.py` or the plugin loader so it registers.
5. Add focused tests under `services/backend/tests/`.

The ingestion service automatically discovers registered plugin classes through the `SourcePlugin` registry.

## Phase 1 Boundaries

This phase intentionally keeps the system small:

- No authentication or authorization.
- No AI enrichment.
- No task queue.
- No Redis cache.
- No article update pipeline after initial insert.
- No dashboard-side pagination beyond fetching the latest 100 records.
- No production deployment manifests.

See the architecture docs for recommended next steps.
