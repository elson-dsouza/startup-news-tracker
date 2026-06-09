# Backend Architecture

The backend service is a FastAPI application that owns ingestion, REST APIs, database access, schema validation, and migrations for the startup news article domain.

## Responsibilities

- Fetch startup funding news from source plugins.
- Normalize feed entries into `RawArticle` domain objects.
- Deduplicate articles by URL.
- Persist new articles in PostgreSQL.
- Expose read-only REST APIs for the dashboard and external clients.
- Manage schema migrations through Alembic.

## Service Location

```text
services/backend
|-- app
|   |-- api
|   |-- core
|   |-- db
|   |-- domain
|   |-- ingestion
|   |-- models
|   |-- schemas
|   `-- main.py
|-- alembic
|-- scripts
|-- tests
|-- Dockerfile
`-- requirements.txt
```

## Runtime Containers

The backend code is used by three Docker Compose services:

- `backend-api`: runs `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`.
- `ingester`: runs `python -m scripts.ingest --interval 3600`.
- `migrate`: runs `alembic upgrade head` before the API and ingester start.

Splitting API, ingestion, and migration into separate containers keeps their process lifecycles independent while allowing them to share the same backend image and codebase.

## Request Flow

```text
Dashboard or API client
        |
        v
FastAPI app in app/main.py
        |
        v
Article routes in app/api/routes.py
        |
        v
Async SQLAlchemy session from app/db/deps.py
        |
        v
Article ORM model in app/models/article.py
        |
        v
PostgreSQL
```

## Ingestion Flow

```text
scripts/ingest.py
        |
        v
IngestionService.ingest()
        |
        v
load_plugins()
        |
        v
SourcePlugin registry
        |
        v
GoogleNewsFundingPlugin.fetch()
        |
        v
RawArticle objects
        |
        v
Deduplicate by URL
        |
        v
Fetch existing article URLs
        |
        v
Insert new Article rows
```

## Modules

### `app/main.py`

Creates the FastAPI app, configures CORS, registers API routes, and exposes `/health`.

### `app/api/routes.py`

Defines article read endpoints:

- `GET /articles`
- `GET /articles/sources`
- `GET /articles/{article_id}`

The list endpoint applies `limit` and `offset`, with a maximum `limit` of `100`. It also supports optional `source`, `q`, `published_after`, and `published_before` filters.

### `app/core/config.py`

Loads environment-backed settings through Pydantic Settings:

- `DATABASE_URL`
- `CORS_ORIGINS`
- `ENABLED_SOURCES`
- `SOURCE_TIMEOUT_SECONDS`
- `SOURCE_USER_AGENT`

`CORS_ORIGINS` is parsed from a comma-separated string into a list for FastAPI CORS middleware.
`ENABLED_SOURCES` is also comma-separated; leaving it empty enables every public source plugin.

### `app/db`

Owns async SQLAlchemy session setup and dependency injection.

The API uses dependency injection to create request-scoped sessions. The ingester uses the same session factory directly.

### `app/models/article.py`

Defines the SQLAlchemy ORM base and `Article` model. The model maps to the `articles` table and enforces unique article URLs.

### `app/schemas/article.py`

Defines Pydantic response models. `ArticleRead` is configured with `from_attributes=True`, allowing FastAPI to serialize SQLAlchemy ORM instances.

### `app/domain/raw_article.py`

Represents normalized article data produced by source plugins before persistence.

### `app/ingestion/plugins/source_plugin.py`

Defines the plugin base class and registry. Subclasses register themselves through `__init_subclass__`.

### `app/ingestion/plugins/google_news.py`

Fetches Google News RSS search feeds for funding and venture-capital queries, parses them with `feedparser`, and maps entries into `RawArticle` objects. Query lists are loaded from `app/ingestion/config/google_news.yaml` by default, with `GOOGLE_NEWS_QUERIES_PATH` available for environment-specific overrides.

### `app/ingestion/plugins/public_feeds.py`

Fetches public RSS feeds and listing pages for Entrackr, Inc42, YourStory, and VCCircle. Each plugin keeps a source id and display name for API and dashboard usage.

### `app/ingestion/services/ingestion_service.py`

Coordinates plugin loading, fetching, deduplication, existing URL checks, persistence, and transaction handling.

### `scripts/ingest.py`

CLI entrypoint for ingestion. It supports:

- `--once`: run a single ingestion pass and exit.
- `--interval <seconds>`: run continuously with a sleep interval between passes.

## API Contract

Article responses have this shape:

```json
{
  "id": "uuid",
  "source": "google_news",
  "title": "Article title",
  "url": "https://example.com/article",
  "published_at": "2026-06-08T10:00:00",
  "content": "Feed summary content",
  "created_at": "2026-06-08T10:05:00"
}
```

## Error Handling

- Article lookup returns `404` when the UUID does not match a stored row.
- Ingestion catches source-level or database-level exceptions in the recurring loop and logs them without stopping the process.
- URL uniqueness is enforced both in application-level checks and by the database unique constraint.

## Testing

Current tests cover:

- API health and article endpoints.
- Google News plugin parsing behavior.
- Ingestion service deduplication and persistence behavior.

Recommended commands:

```bash
cd services/backend
../../.venv/bin/python -m pytest
../../.venv/bin/black --check app scripts tests alembic
../../.venv/bin/ruff check app scripts tests alembic
```

## Extension Points

To add another source:

1. Implement a new `SourcePlugin` subclass.
2. Return normalized `RawArticle` objects from `fetch`.
3. Ensure the plugin is imported by the plugin loader.
4. Add parser and ingestion tests.

Potential next backend features:

- Article search and source filters in the API.
- Cursor pagination.
- Source health metadata.
- Ingestion run history.
- Retry policy per source.
- Structured logging.
- Authentication for non-local deployments.
