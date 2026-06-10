"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type ArticleEntity = {
  entity_type: "startup" | "investor" | "person" | string;
  name: string;
  normalized_name: string;
};

type Article = {
  id: string;
  source: string;
  title: string;
  url: string;
  external_id: string | null;
  source_url: string | null;
  published_at: string | null;
  content: string | null;
  created_at: string;
  summary: string | null;
  entities: ArticleEntity[];
  startup_country: string | null;
  publisher_country: string | null;
  mentioned_countries: string[];
  funding_amount_usd: string | null;
  funding_amount_original: string | null;
  funding_currency_original: string | null;
  funding_round: string | null;
  enrichment_status: string;
};

type ArticleSource = {
  id: string;
  display_name: string;
  enabled: boolean;
  latest_article_at: string | null;
};

type ArticleFacetEntity = ArticleEntity & {
  count: number;
};

type ArticleFacets = {
  entities: ArticleFacetEntity[];
  countries: {
    startup: string[];
    publisher: string[];
    mentioned: string[];
  };
  funding: {
    min_usd: string | null;
    max_usd: string | null;
  };
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const PAGE_SIZE = 20;

function formatDate(value: string | null) {
  if (!value) {
    return "Unknown date";
  }

  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function fallbackSourceLabel(source: string) {
  return source
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function summarize(value: string | null) {
  if (!value) {
    return "Summary pending enrichment.";
  }

  const cleanText = value.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  return cleanText.length > 220 ? `${cleanText.slice(0, 217)}...` : cleanText;
}

function formatFunding(article: Article) {
  if (article.funding_amount_usd) {
    const amount = Number(article.funding_amount_usd);
    if (Number.isFinite(amount)) {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
        notation: amount >= 1_000_000 ? "compact" : "standard"
      }).format(amount);
    }
  }

  return article.funding_amount_original;
}

function countBySource(articles: Article[]) {
  return articles.reduce<Map<string, number>>((counts, article) => {
    counts.set(article.source, (counts.get(article.source) ?? 0) + 1);
    return counts;
  }, new Map());
}

export default function DashboardPage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [sourceOptions, setSourceOptions] = useState<ArticleSource[]>([]);
  const [facets, setFacets] = useState<ArticleFacets | null>(null);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [selectedEntity, setSelectedEntity] = useState("");
  const [selectedEntityType, setSelectedEntityType] = useState("");
  const [startupCountry, setStartupCountry] = useState("");
  const [publisherCountry, setPublisherCountry] = useState("");
  const [mentionedCountry, setMentionedCountry] = useState("");
  const [fundingMinUsd, setFundingMinUsd] = useState("");
  const [fundingMaxUsd, setFundingMaxUsd] = useState("");
  const [isSourceDropdownOpen, setIsSourceDropdownOpen] = useState(false);
  const [status, setStatus] = useState<"loading" | "live" | "error">("loading");
  const [offset, setOffset] = useState(0);
  const [hasMoreArticles, setHasMoreArticles] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const sourceDropdownRef = useRef<HTMLDivElement | null>(null);

  const sourceCounts = useMemo(() => countBySource(articles), [articles]);
  const sourceLabels = useMemo(
    () =>
      new Map(
        sourceOptions.map((item) => [
          item.id,
          item.display_name || fallbackSourceLabel(item.id)
        ])
      ),
    [sourceOptions]
  );
  const enabledSources = useMemo(
    () => sourceOptions.filter((item) => item.enabled),
    [sourceOptions]
  );
  const filteredEntityFacets = useMemo(() => {
    if (!facets) {
      return [];
    }
    return selectedEntityType
      ? facets.entities.filter((item) => item.entity_type === selectedEntityType)
      : facets.entities;
  }, [facets, selectedEntityType]);

  function sourceLabel(sourceId: string) {
    return sourceLabels.get(sourceId) ?? fallbackSourceLabel(sourceId);
  }

  function toggleSource(sourceId: string) {
    setSelectedSources((currentSources) =>
      currentSources.includes(sourceId)
        ? currentSources.filter((item) => item !== sourceId)
        : [...currentSources, sourceId]
    );
  }

  function resetInsightFilters() {
    setSelectedEntity("");
    setSelectedEntityType("");
    setStartupCountry("");
    setPublisherCountry("");
    setMentionedCountry("");
    setFundingMinUsd("");
    setFundingMaxUsd("");
  }

  const selectedSourceSummary = useMemo(() => {
    if (selectedSources.length === 0) {
      return "All sources";
    }

    if (selectedSources.length === 1) {
      return sourceLabel(selectedSources[0]);
    }

    return `${selectedSources.length} sources selected`;
  }, [selectedSources, sourceLabels]);

  const topSource = useMemo(
    () => [...sourceCounts.entries()].sort((a, b) => b[1] - a[1])[0],
    [sourceCounts]
  );
  const newestArticle = articles[0];
  const enrichedCoverage = articles.length
    ? Math.round(
        (articles.filter((article) => article.enrichment_status === "enriched").length /
          articles.length) *
          100
      )
    : 0;
  const maxSourceCount = Math.max(...[...sourceCounts.values()], 1);

  const fetchArticlePage = useCallback(
    async ({
      nextOffset,
      reset = false,
      signal
    }: {
      nextOffset: number;
      reset?: boolean;
      signal?: AbortSignal;
    }) => {
      if (reset) {
        setStatus("loading");
        setArticles([]);
        setOffset(0);
        setHasMoreArticles(true);
      } else {
        setIsLoadingMore(true);
      }

      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(nextOffset)
      });
      for (const sourceId of selectedSources) {
        params.append("source", sourceId);
      }
      if (debouncedQuery.trim()) {
        params.set("q", debouncedQuery.trim());
      }
      if (selectedEntity) {
        params.set("entity", selectedEntity);
      }
      if (selectedEntityType) {
        params.set("entity_type", selectedEntityType);
      }
      if (startupCountry) {
        params.set("startup_country", startupCountry);
      }
      if (publisherCountry) {
        params.set("publisher_country", publisherCountry);
      }
      if (mentionedCountry) {
        params.set("mentioned_country", mentionedCountry);
      }
      if (fundingMinUsd) {
        params.set("funding_min_usd", fundingMinUsd);
      }
      if (fundingMaxUsd) {
        params.set("funding_max_usd", fundingMaxUsd);
      }

      const response = await fetch(`${API_BASE_URL}/articles?${params.toString()}`, {
        cache: "no-store",
        signal
      });
      if (!response.ok) {
        throw new Error(`Articles request failed with ${response.status}`);
      }

      const nextArticles = (await response.json()) as Article[];
      setArticles((currentArticles) => {
        if (reset) {
          return nextArticles;
        }

        const seenIds = new Set(currentArticles.map((article) => article.id));
        return [
          ...currentArticles,
          ...nextArticles.filter((article) => !seenIds.has(article.id))
        ];
      });
      setOffset(nextOffset + nextArticles.length);
      setHasMoreArticles(nextArticles.length === PAGE_SIZE);
      setStatus("live");
      setIsLoadingMore(false);
    },
    [
      debouncedQuery,
      fundingMaxUsd,
      fundingMinUsd,
      mentionedCountry,
      publisherCountry,
      selectedEntity,
      selectedEntityType,
      selectedSources,
      startupCountry
    ]
  );

  async function fetchSources() {
    const response = await fetch(`${API_BASE_URL}/articles/sources`, {
      cache: "no-store"
    });
    if (!response.ok) {
      throw new Error(`Sources request failed with ${response.status}`);
    }
    setSourceOptions(await response.json());
  }

  async function fetchFacets() {
    const response = await fetch(`${API_BASE_URL}/articles/facets`, {
      cache: "no-store"
    });
    if (!response.ok) {
      throw new Error(`Facets request failed with ${response.status}`);
    }
    setFacets(await response.json());
  }

  async function refreshDashboard() {
    setStatus("loading");
    try {
      await Promise.all([
        fetchSources(),
        fetchFacets(),
        fetchArticlePage({ nextOffset: 0, reset: true })
      ]);
      setStatus("live");
    } catch {
      setStatus("error");
      setIsLoadingMore(false);
    }
  }

  useEffect(() => {
    Promise.all([fetchSources(), fetchFacets()]).catch(() => setStatus("error"));
  }, []);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (
        sourceDropdownRef.current &&
        !sourceDropdownRef.current.contains(event.target as Node)
      ) {
        setIsSourceDropdownOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);

    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedQuery(query.trim());
    }, 350);

    return () => window.clearTimeout(timeoutId);
  }, [query]);

  useEffect(() => {
    const controller = new AbortController();

    fetchArticlePage({
      nextOffset: 0,
      reset: true,
      signal: controller.signal
    }).catch((error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setStatus("error");
      setIsLoadingMore(false);
    });

    return () => controller.abort();
  }, [fetchArticlePage]);

  useEffect(() => {
    if (!loadMoreRef.current || status !== "live" || !hasMoreArticles || isLoadingMore) {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) {
          return;
        }

        fetchArticlePage({ nextOffset: offset }).catch(() => {
          setStatus("error");
          setIsLoadingMore(false);
        });
      },
      { rootMargin: "360px 0px" }
    );
    observer.observe(loadMoreRef.current);

    return () => observer.disconnect();
  }, [fetchArticlePage, hasMoreArticles, isLoadingMore, offset, status]);

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
          <a className="navItem" href="#filters">
            Filters
          </a>
          <a className="navItem" href="#signals">
            Signals
          </a>
        </nav>
        <div className="sidebarPanel">
          <span>AI runtime</span>
          <strong>llama.cpp qwen3-1.7b</strong>
        </div>
      </aside>

      <section className="page">
        <header className="topbar">
          <div>
            <p className="eyebrow">Phase 2 Intelligence Intake</p>
            <h1>Startup Funding Dashboard</h1>
          </div>
          <a className="primaryAction" href={`${API_BASE_URL}/docs`}>
            API Docs
          </a>
        </header>

        <section className="metrics" aria-label="Article metrics">
          <article className="metric">
            <span>Loaded Articles</span>
            <strong>{articles.length}</strong>
          </article>
          <article className="metric">
            <span>Sources</span>
            <strong>{enabledSources.length || sourceCounts.size}</strong>
          </article>
          <article className="metric">
            <span>Latest Signal</span>
            <strong>{newestArticle ? formatDate(newestArticle.published_at) : "-"}</strong>
          </article>
          <article className="metric">
            <span>AI Coverage</span>
            <strong>{articles.length ? `${enrichedCoverage}%` : "-"}</strong>
          </article>
        </section>

        <section className="workspace" id="articles">
          <div className="toolbar" id="filters">
            <div className="searchBox">
              <label htmlFor="searchInput">Search</label>
              <input
                id="searchInput"
                type="search"
                placeholder="Company, sector, investor..."
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    setDebouncedQuery(query.trim());
                  }
                }}
              />
            </div>
            <div className="controlGroup">
              <label htmlFor="sourceFilter">Sources</label>
              <div className="sourceDropdown" ref={sourceDropdownRef}>
                <button
                  aria-expanded={isSourceDropdownOpen}
                  aria-haspopup="listbox"
                  className="sourceDropdownButton"
                  id="sourceFilter"
                  type="button"
                  onClick={() => setIsSourceDropdownOpen((isOpen) => !isOpen)}
                >
                  <span>{selectedSourceSummary}</span>
                  <span aria-hidden="true">v</span>
                </button>
                {isSourceDropdownOpen && (
                  <div
                    aria-labelledby="sourceFilter"
                    className="sourceDropdownPanel"
                    role="listbox"
                  >
                    <label className="sourceOption">
                      <input
                        checked={selectedSources.length === 0}
                        type="checkbox"
                        onChange={() => setSelectedSources([])}
                      />
                      <span>All sources</span>
                    </label>
                    {enabledSources.map((item) => (
                      <label className="sourceOption" key={item.id}>
                        <input
                          checked={selectedSources.includes(item.id)}
                          type="checkbox"
                          onChange={() => toggleSource(item.id)}
                        />
                        <span>{sourceLabel(item.id)}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="controlGroup">
              <label htmlFor="entityTypeFilter">Entity Type</label>
              <select
                id="entityTypeFilter"
                value={selectedEntityType}
                onChange={(event) => {
                  setSelectedEntityType(event.target.value);
                  setSelectedEntity("");
                }}
              >
                <option value="">All entity types</option>
                <option value="startup">Startup</option>
                <option value="investor">Investor</option>
                <option value="person">Person</option>
              </select>
            </div>
            <div className="controlGroup">
              <label htmlFor="entityFilter">Entity</label>
              <select
                id="entityFilter"
                value={selectedEntity}
                onChange={(event) => setSelectedEntity(event.target.value)}
              >
                <option value="">All entities</option>
                {filteredEntityFacets.map((item) => (
                  <option
                    key={`${item.entity_type}:${item.normalized_name}`}
                    value={item.normalized_name}
                  >
                    {item.name} ({item.count})
                  </option>
                ))}
              </select>
            </div>
            <div className="controlGroup">
              <label htmlFor="startupCountryFilter">Startup Country</label>
              <select
                id="startupCountryFilter"
                value={startupCountry}
                onChange={(event) => setStartupCountry(event.target.value)}
              >
                <option value="">Any startup country</option>
                {facets?.countries.startup.map((country) => (
                  <option key={country} value={country}>
                    {country}
                  </option>
                ))}
              </select>
            </div>
            <div className="controlGroup">
              <label htmlFor="publisherCountryFilter">Publisher Country</label>
              <select
                id="publisherCountryFilter"
                value={publisherCountry}
                onChange={(event) => setPublisherCountry(event.target.value)}
              >
                <option value="">Any publisher country</option>
                {facets?.countries.publisher.map((country) => (
                  <option key={country} value={country}>
                    {country}
                  </option>
                ))}
              </select>
            </div>
            <div className="controlGroup">
              <label htmlFor="mentionedCountryFilter">Mentioned Country</label>
              <select
                id="mentionedCountryFilter"
                value={mentionedCountry}
                onChange={(event) => setMentionedCountry(event.target.value)}
              >
                <option value="">Any mentioned country</option>
                {facets?.countries.mentioned.map((country) => (
                  <option key={country} value={country}>
                    {country}
                  </option>
                ))}
              </select>
            </div>
            <div className="fundingControls">
              <div className="controlGroup">
                <label htmlFor="fundingMinFilter">Min USD</label>
                <input
                  id="fundingMinFilter"
                  min="0"
                  placeholder={facets?.funding.min_usd ?? "0"}
                  type="number"
                  value={fundingMinUsd}
                  onChange={(event) => setFundingMinUsd(event.target.value)}
                />
              </div>
              <div className="controlGroup">
                <label htmlFor="fundingMaxFilter">Max USD</label>
                <input
                  id="fundingMaxFilter"
                  min="0"
                  placeholder={facets?.funding.max_usd ?? "No max"}
                  type="number"
                  value={fundingMaxUsd}
                  onChange={(event) => setFundingMaxUsd(event.target.value)}
                />
              </div>
            </div>
            <button
              className="iconButton"
              type="button"
              onClick={refreshDashboard}
              aria-label="Refresh articles"
              title="Refresh articles"
            >
              <span aria-hidden="true">↻</span>
            </button>
            <button
              className="secondaryButton"
              type="button"
              onClick={resetInsightFilters}
            >
              Clear
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
                    {status === "loading"
                      ? "Loading articles..."
                      : "No articles match the current filters."}
                  </div>
                ) : (
                  articles.map((article) => {
                    const funding = formatFunding(article);
                    return (
                      <article className="articleCard" key={article.id}>
                        <div className="articleMeta">
                          <span className="pill">{sourceLabel(article.source)}</span>
                          <span>{formatDate(article.published_at)}</span>
                          <span className={`statusText ${article.enrichment_status}`}>
                            {article.enrichment_status}
                          </span>
                        </div>
                        <a
                          className="articleTitle"
                          href={article.url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {article.title}
                        </a>
                        <p className="articleSummary">
                          {article.summary ?? summarize(article.content)}
                        </p>
                        <div className="chipRow">
                          {funding && <span className="insightChip funding">{funding}</span>}
                          {article.funding_round && (
                            <span className="insightChip">{article.funding_round}</span>
                          )}
                          {article.startup_country && (
                            <span className="insightChip">
                              Startup: {article.startup_country}
                            </span>
                          )}
                          {article.publisher_country && (
                            <span className="insightChip">
                              Publisher: {article.publisher_country}
                            </span>
                          )}
                          {article.mentioned_countries.slice(0, 3).map((country) => (
                            <span className="insightChip" key={country}>
                              {country}
                            </span>
                          ))}
                        </div>
                        {article.entities.length > 0 && (
                          <div className="entityList">
                            {article.entities.slice(0, 8).map((entity) => (
                              <span
                                className={`entityChip ${entity.entity_type}`}
                                key={`${entity.entity_type}:${entity.normalized_name}`}
                              >
                                {entity.name}
                              </span>
                            ))}
                          </div>
                        )}
                      </article>
                    );
                  })
                )}
              </div>
              <div className="loadMoreArea" ref={loadMoreRef}>
                {status === "live" && hasMoreArticles ? (
                  <button
                    className="loadMoreButton"
                    type="button"
                    disabled={isLoadingMore}
                    onClick={() => {
                      fetchArticlePage({ nextOffset: offset }).catch(() => {
                        setStatus("error");
                        setIsLoadingMore(false);
                      });
                    }}
                  >
                    {isLoadingMore ? "Loading more..." : "Load more articles"}
                  </button>
                ) : status === "live" && articles.length > 0 ? (
                  <span className="endOfList">All matching articles loaded</span>
                ) : null}
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
                  <dt>AI enriched loaded</dt>
                  <dd>{articles.length ? `${enrichedCoverage}%` : "-"}</dd>
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
