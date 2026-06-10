# Startup News Tracker

Startup News Tracker is a startup funding intelligence platform. It ingests startup funding articles from Google News RSS and public feeds, stores canonical article records in PostgreSQL, enriches articles with local llama.cpp-powered AI insights, exposes them through a FastAPI REST API, and renders an operational Next.js dashboard for browsing and filtering the feed.

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
- Loads Google News RSS search queries from a small YAML config file.
- Uses a plugin interface so additional article sources can be added without changing ingestion orchestration.
- Deduplicates articles by URL before writing to the database.
- Stores article source, title, URL, published timestamp, feed content, and creation timestamp.
- Resolves article URLs to publisher pages and extracts readable full text for enrichment.
- Uses llama.cpp by default to generate article summaries, typed entities, country fields, and funding values through its OpenAI-compatible chat completions API.
- Provides REST endpoints for health checks and article reads.
- Runs API, ingestion, enrichment, migration, database, and dashboard services through Docker Compose.
- Shows a dashboard with article metrics, search, source/entity/country/funding filters, AI summaries, source mix, live/error/empty states, and links to original articles.

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
GOOGLE_NEWS_QUERIES_PATH=app/ingestion/config/google_news.yaml
LLAMA_CPP_BASE_URL=http://localhost:8080/v1
LLAMA_CPP_MODEL=qwen3-1.7b
LLAMA_CPP_MODEL_FILE=qwen3-1.7b-q4_k_m.gguf
ENRICHMENT_ENABLED=true
ENRICHMENT_BATCH_SIZE=10
ENRICHMENT_IDLE_INTERVAL_SECONDS=5
ENRICHMENT_JOB_MAX_ATTEMPTS=3
ENRICHMENT_JOB_RETRY_DELAY_SECONDS=300
ENRICHMENT_JOB_STALE_AFTER_SECONDS=1800
RABBITMQ_URL=amqp://startup_news:startup_news@localhost:5672/
ARTICLE_QUEUE_NAME=article.enrichment
ARTICLE_QUEUE_MAX_PRIORITY=255
ARTICLE_QUEUE_PREFETCH_COUNT=1
ARTICLE_QUEUE_RETRY_DELAY_SECONDS=300
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Docker Compose overrides the backend database host to `postgres` for containers.
Leave `ENABLED_SOURCES` empty to run all public source plugins, or set a comma-separated list such as `google_news_funding,entrackr_funding`.
Add or remove Google News search terms in `services/backend/app/ingestion/config/google_news.yaml`; the ingester reads the file when each backend process starts. Override `GOOGLE_NEWS_QUERIES_PATH` when a deployment needs a different config file.
Docker Compose runs llama.cpp from `ghcr.io/ggml-org/llama.cpp:server` and exposes its OpenAI-compatible API on `http://localhost:8080/v1`. The backend and enricher use the internal Compose URL `http://llama-cpp:8080/v1`.

Place your GGUF model file in `./models`. The default Compose command expects:

```text
models/qwen3-1.7b-q4_k_m.gguf
```

To use a different file or alias, set `LLAMA_CPP_MODEL_FILE` and `LLAMA_CPP_MODEL` in `.env`.

Manual equivalent for an 8 GB RAM machine:

```bash
docker run --rm -p 8080:8080 -v "$PWD/models:/models:ro" ghcr.io/ggml-org/llama.cpp:server --model /models/qwen3-1.7b-q4_k_m.gguf --alias qwen3-1.7b --host 0.0.0.0 --port 8080 -c 4096 -np 1
```

The default `qwen3-1.7b` alias is intentionally lightweight for constrained machines. If you have more RAM/VRAM, `qwen3-4b` is a better quality upgrade before trying `qwen3-8b`.

## Run The Full Project

```bash
./scripts/start-all.sh
```

This starts:

- `postgres`: PostgreSQL database.
- `rabbitmq`: durable priority queue and management UI on port `15672`.
- `llama-cpp`: local OpenAI-compatible AI model server on port `8080`.
- `migrate`: Alembic migration job.
- `backend-api`: FastAPI REST API on port `8000`.
- `ingester`: recurring ingestion worker.
- `enricher`: queued article text extraction and AI enrichment worker.
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

The recurring interval defaults to `3600` seconds in `docker-compose.yml`. Ingestion publishes normalized article messages to RabbitMQ; it does not write raw, non-enriched articles to PostgreSQL.

Run one legacy database enrichment pass:

```bash
docker compose run --rm backend-api python -m scripts.enrich --once
```

Run the recurring enricher:

```bash
docker compose up --build enricher
```

Ingestion publishes one RabbitMQ message for each newly discovered article, sorted newest first and assigned message priorities so newer articles are consumed ahead of older backlog. The enricher consumes with `ARTICLE_QUEUE_PREFETCH_COUNT=1` by default, enriches the raw article, and writes to PostgreSQL only after AI enrichment succeeds. Failed or skipped raw articles are not inserted into the article tables.

Current public source plugins:

- `google_news_funding`
- `google_news_venture_capital`
- `entrackr_funding`
- `inc42_india_funding`
- `yourstory_startup_funding`
- `vccircle_startup_funding`

Google News query configuration:

```yaml
sources:
  google_news_funding:
    queries:
      - india startup funding
      - indian startup raises funding
  google_news_venture_capital:
    queries:
      - india startup venture funding
```

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
- `source`: repeatable source id filter.
- `q`: title, feed content, AI summary, or extracted text search.
- `entity`: repeatable normalized entity filter.
- `entity_type`: repeatable `startup`, `investor`, or `person` filter.
- `funding_min_usd` and `funding_max_usd`: normalized USD range filters.
- `startup_country`, `publisher_country`, and `mentioned_country`: repeatable country filters.

Example:

```bash
curl "http://localhost:8000/articles?limit=20&offset=0"
```

### `GET /articles/facets`

Returns available entity, country, and funding range facets for dashboard filters.

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

## Current Boundaries

- No authentication or authorization.
- No Redis cache.
- No production deployment manifests.

See the architecture docs for recommended next steps.
