# Frontend Architecture

The frontend is a Next.js React dashboard website. It is focused on the operational workflow of browsing enriched startup funding articles, filtering by structured AI insights, and reading summaries without leaving the dashboard.

## Service Location

```text
services/dashboard
|-- app
|   |-- globals.css
|   |-- layout.tsx
|   `-- page.tsx
|-- Dockerfile
|-- next.config.mjs
|-- package-lock.json
|-- package.json
`-- tsconfig.json
```

## Runtime

Docker Compose runs the dashboard as the `dashboard` service:

```bash
npm run dev -- --hostname 0.0.0.0 --port 3000
```

The local dashboard URL is:

```text
http://localhost:3000
```

The dashboard reads the backend base URL from:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

When the variable is missing, `page.tsx` falls back to `http://localhost:8000`.

## Technology Choices

- Next.js App Router for application structure.
- React client component for dashboard state, server-side article filters, and infinite scrolling.
- TypeScript for article API typing.
- Plain global CSS for a small, focused UI surface.

The current dashboard is a single-screen application. That keeps Phase 1 simple while still leaving room to split views into components as the interface grows.

## Data Flow

```text
Browser
  |
  v
Next.js Dashboard
  |
  v
fetch(`${NEXT_PUBLIC_API_BASE_URL}/articles?limit=20&offset=0`)
fetch(`${NEXT_PUBLIC_API_BASE_URL}/articles?limit=20&offset=20&source=...&q=...&entity=...`)
fetch(`${NEXT_PUBLIC_API_BASE_URL}/articles/sources`)
fetch(`${NEXT_PUBLIC_API_BASE_URL}/articles/facets`)
  |
  v
FastAPI backend
  |
  v
PostgreSQL articles table
```

The dashboard fetches source metadata and AI filter facets from the backend, then fetches articles in pages of 20. Source, search, entity, country, and funding filters are sent to the backend as query parameters. Scrolling near the end of the list requests the next page with `offset`; the Load More button remains available as a manual fallback. Source counts and summary metrics are calculated from the loaded article set.

## Main UI Areas

### Sidebar

The sidebar provides stable navigation anchors:

- Articles
- Signals
- Sources

It also displays the current RSS query: `india startup funding`.

### Top Bar

The top bar contains the dashboard title and a direct link to the backend API docs.

### Metrics

The metric strip summarizes:

- Articles currently loaded by the dashboard.
- Number of unique sources.
- Latest published timestamp.
- Current article page size.

### Toolbar

The toolbar contains:

- Search input for backend title and content matching.
- Dropdown checkbox source filter backed by the article API.
- Entity type and entity filters backed by `/articles/facets`.
- Startup country, publisher country, mentioned country, and funding range filters.
- Refresh button that resets pagination and re-fetches articles from the backend.
- Clear button for structured insight filters.

### Article List

The article list shows:

- Source badge.
- Published timestamp.
- Article title linked to the source URL.
- AI-generated summary when available, with RSS content as fallback.
- Funding, round, country, and entity chips when enrichment has completed.
- Infinite scrolling with a manual Load More fallback.

### Insights Panel

The insights panel shows:

- Most active source.
- Newest published date.
- Content coverage percentage.
- Source mix bars.

## State Model

`services/dashboard/app/page.tsx` owns the dashboard state:

```ts
const [articles, setArticles] = useState<Article[]>([]);
const [query, setQuery] = useState("");
const [selectedSources, setSelectedSources] = useState<string[]>([]);
const [selectedEntity, setSelectedEntity] = useState("");
const [startupCountry, setStartupCountry] = useState("");
const [fundingMinUsd, setFundingMinUsd] = useState("");
const [status, setStatus] = useState<"loading" | "live" | "error">("loading");
const [offset, setOffset] = useState(0);
const [hasMoreArticles, setHasMoreArticles] = useState(true);
const [isLoadingMore, setIsLoadingMore] = useState(false);
```

Derived data is computed with `useMemo`:

- `sourceCounts`
- `sources`
- `topSource`

## API Type

The frontend expects article records in this shape:

```ts
type Article = {
  id: string;
  source: string;
  title: string;
  url: string;
  published_at: string | null;
  content: string | null;
  summary: string | null;
  entities: ArticleEntity[];
  startup_country: string | null;
  publisher_country: string | null;
  mentioned_countries: string[];
  funding_amount_usd: string | null;
  funding_round: string | null;
  enrichment_status: string;
  created_at: string;
};
```

This mirrors the backend `ArticleRead` schema.

## Styling

All current styling lives in:

```text
services/dashboard/app/globals.css
```

The UI is designed as a dense operational dashboard rather than a marketing page. It uses a fixed sidebar on wider screens, compact metrics, constrained article cards, and responsive layout rules for smaller screens.

## Error And Empty States

The dashboard handles:

- Loading state while fetching articles.
- Error state when the backend request fails.
- Empty state when no articles have been ingested.
- Empty filter state when backend search or source filters return no articles.

## Local Development

Run only the dashboard:

```bash
./scripts/start-dashboard.sh
```

Run checks:

```bash
cd services/dashboard
npm run typecheck
npm run build
```

## Extension Points

Good next frontend improvements:

- Extract reusable components such as `MetricCard`, `ArticleCard`, `SourceFilter`, and `SignalsPanel`.
- Add URL-synced filters.
- Add server-side API proxy routes if the deployment topology requires hiding backend origins.
- Add total result counts to the articles API if the dashboard needs full-dataset metrics.
- Add source and date filters from backend query parameters.
- Add visual regression coverage for the dashboard.
