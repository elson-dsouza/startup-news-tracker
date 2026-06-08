# Frontend Architecture

The frontend is a Next.js React dashboard website. It is intentionally focused on the operational workflow for Phase 1: showing the latest ingested startup funding articles, giving quick feed-level metrics, and allowing local filtering in the browser.

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
- React client component for dashboard state and browser-side filtering.
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
fetch(`${NEXT_PUBLIC_API_BASE_URL}/articles?limit=100`)
  |
  v
FastAPI backend
  |
  v
PostgreSQL articles table
```

The dashboard fetches up to 100 articles and performs search, source filtering, source counts, and summary metrics in memory.

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

- Total articles fetched by the dashboard.
- Number of unique sources.
- Latest published timestamp.
- Number of articles visible after local filters.

### Toolbar

The toolbar contains:

- Search input for title and content matching.
- Source select filter.
- Refresh button that re-fetches articles from the backend.

### Article List

The article list shows:

- Source badge.
- Published timestamp.
- Article title linked to the source URL.
- Cleaned summary content from the RSS feed.

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
const [source, setSource] = useState("all");
const [status, setStatus] = useState<"loading" | "live" | "error">("loading");
```

Derived data is computed with `useMemo`:

- `sourceCounts`
- `sources`
- `filteredArticles`
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
- Empty filter state when local search or source filters hide all articles.

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
- Add pagination once the API supports it beyond local fetching.
- Add source and date filters from backend query parameters.
- Add visual regression coverage for the dashboard.
