# Backend Architecture

The backend service is a FastAPI application that owns ingestion, enrichment, REST APIs, database access, schema validation, and migrations for the startup news article domain.

## Responsibilities

- Fetch startup funding news from source plugins.
- Normalize feed entries into `RawArticle` domain objects.
- Deduplicate articles by URL.
- Persist new articles in PostgreSQL.
- Resolve article URLs to publisher pages and extract readable text.
- Enrich articles with local llama.cpp-generated summaries, named entities, countries, and funding values.
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

The backend code is used by Docker Compose services:

- `backend-api`: runs `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`.
- `ingester`: runs `python -m scripts.ingest --interval 3600`.
- `enricher`: runs `python -m scripts.enrich`.
- `migrate`: runs `alembic upgrade head` before the API and ingester start.
- `rabbitmq`: stores raw article messages before enrichment using a durable priority queue.

Splitting API, ingestion, enrichment, and migration into separate containers keeps their process lifecycles independent while allowing them to share the same backend image and codebase.

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

## Enrichment Flow

```text
scripts/enrich.py
        |
        v
EnrichmentService.enrich_batch()
        |
        v
Select missing or retryable enrichments
        |
        v
ArticleExtractor resolves publisher URLs and extracts readable text
        |
        v
Use extracted article text, or cleaned feed content when publisher extraction fails
        |
        v
LlamaCppClient requests strict JSON insights through chat completions
        |
        v
Store ArticleEnrichment and ArticleEntity rows
```

## Modules

### `app/main.py`

Creates the FastAPI app, configures CORS, registers API routes, and exposes `/health`.

### `app/api/routes.py`

Defines article read endpoints:

- `GET /articles`
- `GET /articles/sources`
- `GET /articles/facets`
- `GET /articles/{article_id}`

The list endpoint applies `limit` and `offset`, with a maximum `limit` of `100`. It also supports optional `source`, `q`, entity, entity type, funding range, startup country, publisher country, mentioned country, and published date filters.

### `app/core/config.py`

Loads environment-backed settings through Pydantic Settings:

- `DATABASE_URL`
- `CORS_ORIGINS`
- `ENABLED_SOURCES`
- `SOURCE_TIMEOUT_SECONDS`
- `SOURCE_USER_AGENT`
- `LLAMA_CPP_BASE_URL`
- `LLAMA_CPP_MODEL`
- `ENRICHMENT_ENABLED`
- `ENRICHMENT_BATCH_SIZE`
- `ENRICHMENT_IDLE_INTERVAL_SECONDS`
- `ENRICHMENT_JOB_MAX_ATTEMPTS`
- `ENRICHMENT_JOB_RETRY_DELAY_SECONDS`
- `ENRICHMENT_JOB_STALE_AFTER_SECONDS`
- `RABBITMQ_URL`
- `ARTICLE_QUEUE_NAME`
- `ARTICLE_QUEUE_MAX_PRIORITY`
- `ARTICLE_QUEUE_PREFETCH_COUNT`
- `ARTICLE_QUEUE_RETRY_DELAY_SECONDS`

`CORS_ORIGINS` is parsed from a comma-separated string into a list for FastAPI CORS middleware.
`ENABLED_SOURCES` is also comma-separated; leaving it empty enables every public source plugin.

### `app/db`

Owns async SQLAlchemy session setup and dependency injection.

The API uses dependency injection to create request-scoped sessions. The ingester uses the same session factory directly.

### `app/models/article.py`

Defines the SQLAlchemy ORM base plus `Article`, `ArticleEnrichment`, `ArticleEntity`, and legacy `ArticleEnrichmentJob` models. Articles are written only after successful enrichment; enrichment rows store extracted text and AI fields; entity rows store typed startup, investor, and person names for filtering.

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

Coordinates plugin loading, fetching, deduplication, existing URL checks, and RabbitMQ publishing. It does not persist raw/non-enriched articles to PostgreSQL.

### `app/messaging/articles.py`

Owns the durable RabbitMQ priority queue for raw article messages. Ingestion publishes normalized articles newest-first with message priorities. The enrichment worker consumes with bounded prefetch so llama.cpp is not overloaded.

### `app/enrichment`

Owns publisher text extraction, the llama.cpp chat-completions client, and the enrichment service that records full text, summaries, country fields, funding values, and typed entities. The worker consumes raw article messages from RabbitMQ, enriches them, and persists the article only when the AI result succeeds. When publisher extraction fails but RSS/feed content exists, enrichment uses that feed text and stores `extraction_status="feed_fallback"`. Rows with no usable text are skipped and are not written to PostgreSQL.

### `scripts/ingest.py`

CLI entrypoint for ingestion. It supports:

- `--once`: run a single ingestion pass and exit.
- `--interval <seconds>`: run continuously with a sleep interval between passes.

### `scripts/enrich.py`

CLI entrypoint for enrichment. It supports:

- default mode: consume raw article messages from RabbitMQ forever.
- `--once`: run one legacy database-backed enrichment pass and exit.
- `--poll-db`: run the deprecated database-backed enrichment job loop.
- `--batch-size <count>`: override the configured batch size for legacy database-backed runs.

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
  "created_at": "2026-06-08T10:05:00",
  "summary": "AI generated article summary.",
  "entities": [{"entity_type": "startup", "name": "Acme", "normalized_name": "acme"}],
  "startup_country": "India",
  "publisher_country": "India",
  "mentioned_countries": ["India"],
  "funding_amount_usd": "5000000.00",
  "funding_amount_original": "$5 million",
  "funding_currency_original": "USD",
  "funding_round": "Seed",
  "enrichment_status": "enriched"
}
```

## Error Handling

- Article lookup returns `404` when the UUID does not match a stored row.
- Ingestion catches source-level or database-level exceptions in the recurring loop and logs them without stopping the process.
- Enrichment stores partial failure state per article so extraction or llama.cpp failures can be retried without blocking ingestion.
- URL uniqueness is enforced both in application-level checks and by the database unique constraint.

## Testing

Current tests cover:

- API health and article endpoints.
- Google News plugin parsing behavior.
- Ingestion service deduplication and persistence behavior.
- Article extraction, llama.cpp payload parsing, enrichment application, and enrichment filters.

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
