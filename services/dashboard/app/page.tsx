"use client";

import { useEffect, useMemo, useState } from "react";

type Article = {
  id: string;
  source: string;
  title: string;
  url: string;
  published_at: string | null;
  content: string | null;
  created_at: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function formatDate(value: string | null) {
  if (!value) {
    return "Unknown date";
  }

  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function sourceLabel(source: string) {
  return source
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function summarize(value: string | null) {
  if (!value) {
    return "Raw feed item stored without summary content.";
  }

  const cleanText = value.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  return cleanText.length > 180 ? `${cleanText.slice(0, 177)}...` : cleanText;
}

function countBySource(articles: Article[]) {
  return articles.reduce<Map<string, number>>((counts, article) => {
    counts.set(article.source, (counts.get(article.source) ?? 0) + 1);
    return counts;
  }, new Map());
}

export default function DashboardPage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("all");
  const [status, setStatus] = useState<"loading" | "live" | "error">("loading");

  const sourceCounts = useMemo(() => countBySource(articles), [articles]);
  const sources = useMemo(() => [...sourceCounts.keys()].sort(), [sourceCounts]);

  const filteredArticles = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return articles.filter((article) => {
      const matchesSource = source === "all" || article.source === source;
      const searchable = `${article.title} ${article.content ?? ""}`.toLowerCase();
      return matchesSource && (!normalizedQuery || searchable.includes(normalizedQuery));
    });
  }, [articles, query, source]);

  const topSource = useMemo(
    () => [...sourceCounts.entries()].sort((a, b) => b[1] - a[1])[0],
    [sourceCounts]
  );
  const newestArticle = articles[0];
  const contentCoverage = articles.length
    ? Math.round((articles.filter((article) => article.content).length / articles.length) * 100)
    : 0;
  const maxSourceCount = Math.max(...[...sourceCounts.values()], 1);

  async function fetchArticles() {
    setStatus("loading");
    try {
      const response = await fetch(`${API_BASE_URL}/articles?limit=100`, {
        cache: "no-store"
      });
      if (!response.ok) {
        throw new Error(`Articles request failed with ${response.status}`);
      }
      setArticles(await response.json());
      setStatus("live");
    } catch {
      setStatus("error");
    }
  }

  useEffect(() => {
    fetchArticles();
  }, []);

  return (
    <main className="shell">
      <aside className="sidebar" aria-label="Dashboard navigation">
        <div className="brand">
          <span className="brandMark" aria-hidden="true">
            S
          </span>
          <div>
            <strong>Startup News</strong>
            <span>Funding monitor</span>
          </div>
        </div>
        <nav className="navList" aria-label="Dashboard sections">
          <a className="navItem active" href="#articles">
            Articles
          </a>
          <a className="navItem" href="#signals">
            Signals
          </a>
          <a className="navItem" href="#sources">
            Sources
          </a>
        </nav>
        <div className="sidebarPanel">
          <span>RSS query</span>
          <strong>india startup funding</strong>
        </div>
      </aside>

      <section className="page">
        <header className="topbar">
          <div>
            <p className="eyebrow">Phase 1 Intelligence Intake</p>
            <h1>Startup Funding Dashboard</h1>
          </div>
          <a className="primaryAction" href={`${API_BASE_URL}/docs`}>
            API Docs
          </a>
        </header>

        <section className="metrics" aria-label="Article metrics">
          <article className="metric">
            <span>Total Articles</span>
            <strong>{articles.length}</strong>
          </article>
          <article className="metric">
            <span>Sources</span>
            <strong>{sourceCounts.size}</strong>
          </article>
          <article className="metric">
            <span>Latest Signal</span>
            <strong>{newestArticle ? formatDate(newestArticle.published_at) : "-"}</strong>
          </article>
          <article className="metric">
            <span>Visible</span>
            <strong>{filteredArticles.length}</strong>
          </article>
        </section>

        <section className="workspace" id="articles">
          <div className="toolbar">
            <div className="searchBox">
              <label htmlFor="searchInput">Search</label>
              <input
                id="searchInput"
                type="search"
                placeholder="Company, sector, investor..."
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <div className="controlGroup">
              <label htmlFor="sourceFilter">Source</label>
              <select
                id="sourceFilter"
                value={source}
                onChange={(event) => setSource(event.target.value)}
              >
                <option value="all">All sources</option>
                {sources.map((item) => (
                  <option key={item} value={item}>
                    {sourceLabel(item)}
                  </option>
                ))}
              </select>
            </div>
            <button
              className="iconButton"
              type="button"
              onClick={fetchArticles}
              aria-label="Refresh articles"
              title="Refresh articles"
            >
              <span aria-hidden="true">↻</span>
            </button>
          </div>

          <div className="contentGrid">
            <section className="articleList" aria-label="Latest articles">
              <div className="sectionHeader">
                <div>
                  <p className="eyebrow">Live feed</p>
                  <h2>Latest Funding Articles</h2>
                </div>
                <span className={`statusBadge ${status === "error" ? "error" : ""}`}>
                  {status === "loading" ? "Loading" : status === "live" ? "Live" : "Unavailable"}
                </span>
              </div>

              <div className="articlesList">
                {status === "error" ? (
                  <div className="emptyState">
                    Unable to load articles. Check the backend API and database connection.
                  </div>
                ) : articles.length === 0 ? (
                  <div className="emptyState">
                    No articles have been ingested yet. Run the ingester to populate the dashboard.
                  </div>
                ) : filteredArticles.length === 0 ? (
                  <div className="emptyState">No articles match the current filters.</div>
                ) : (
                  filteredArticles.map((article) => (
                    <article className="articleCard" key={article.id}>
                      <div className="articleMeta">
                        <span className="pill">{sourceLabel(article.source)}</span>
                        <span>{formatDate(article.published_at)}</span>
                      </div>
                      <a
                        className="articleTitle"
                        href={article.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {article.title}
                      </a>
                      <p className="articleSummary">{summarize(article.content)}</p>
                    </article>
                  ))
                )}
              </div>
            </section>

            <aside className="insights" id="signals" aria-label="Dashboard summary">
              <div className="sectionHeader compact">
                <div>
                  <p className="eyebrow">Snapshot</p>
                  <h2>Signals</h2>
                </div>
              </div>
              <dl className="signalList">
                <div>
                  <dt>Most active source</dt>
                  <dd>{topSource ? `${sourceLabel(topSource[0])} (${topSource[1]})` : "-"}</dd>
                </div>
                <div>
                  <dt>Newest published date</dt>
                  <dd>{newestArticle ? formatDate(newestArticle.published_at) : "-"}</dd>
                </div>
                <div>
                  <dt>Content coverage</dt>
                  <dd>{articles.length ? `${contentCoverage}%` : "-"}</dd>
                </div>
              </dl>

              <div className="sourcePanel" id="sources">
                <h3>Source Mix</h3>
                <div className="sourceBars">
                  {[...sourceCounts.entries()]
                    .sort((a, b) => b[1] - a[1])
                    .map(([item, count]) => (
                      <div className="sourceRow" key={item}>
                        <div className="sourceRowHeader">
                          <span>{sourceLabel(item)}</span>
                          <strong>{count}</strong>
                        </div>
                        <div className="sourceTrack" aria-hidden="true">
                          <div
                            className="sourceFill"
                            style={{ width: `${(count / maxSourceCount) * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  {!sourceCounts.size && <div className="emptyState">No source data yet.</div>}
                </div>
              </div>
            </aside>
          </div>
        </section>
      </section>
    </main>
  );
}
