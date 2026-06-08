# Startup News Tracker

Phase 1 startup funding news ingestion platform split into two services:

- `services/backend`: FastAPI ingestion engine and REST API
- `services/dashboard`: Next.js React dashboard

## Run locally

```bash
cp .env.example .env
./scripts/start-all.sh
```

The dashboard runs at `http://localhost:3000`.

The backend API runs at `http://localhost:8000`.

The API docs are available at `http://localhost:8000/docs`.

## Scripts

- `./scripts/start-all.sh`: starts Postgres, backend API, ingester, migrations, and dashboard
- `./scripts/start-backend.sh`: starts Postgres, backend API, ingester, and migrations
- `./scripts/start-dashboard.sh`: starts the Next.js dashboard locally

## Endpoints

- `GET /health`
- `GET /articles?limit=50`

## Ingestion

The `ingester` service fetches Google News RSS results for `india startup funding` and stores new articles in PostgreSQL. To run a single ingestion manually:

```bash
docker compose run --rm backend-api python -m scripts.ingest --once
```
