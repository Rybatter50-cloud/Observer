# Architecture

For deployment topology (main server vs. field unit), hardware requirements,
and offline operation, see [DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md).

## Startup Sequence

`main.py` uses FastAPI's lifespan context manager. The initialization order is:

```
1. setup_logging(config.DEBUG)
2. config.display()           # Print active configuration
3. config.validate()          # Validate required settings, exit(1) on failure
4. db.connect()               # Create asyncpg pool, initialize schema, create repositories
5. Start background tasks:
   a. ArticlePipeline         (if FEED_COLLECTION_ENABLED)
   b. ScreeningService        (warm sanctions cache)
   c. VirusTotal scheduler    (if VIRUSTOTAL_ENABLED)
   d. urlscan.io scheduler    (if URLSCAN_ENABLED)
   e. Wikipedia events loop   (if WIKI_EVENTS_ENABLED)
   f. Metrics hydration       (load discover call history from DB)
6. yield                      # App serves requests
7. Cancel all background tasks
8. db.close()                 # Close pool (5s timeout, then terminate)
```

### Middleware Stack

Applied in order:

1. **CORSMiddleware** — Origins from `config.ALLOWED_ORIGINS`, all methods/headers, credentials enabled.
2. **SecurityHeadersMiddleware** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, CSP allowing self + WebSocket.

### Routers

12 routers registered in `main.py`:

| Router | Source file | Prefix |
|--------|------------|--------|
| scraper_router | routes_scraper.py | (none) |
| metrics_router | routes_metrics.py | `/api/v1/metrics` |
| router (main) | routes.py | (none) |
| collectors_router | routes_collectors.py | `/api/v1/collectors` |
| debug_router | routes_debug.py | (none) |
| chat_router | routes_chat.py | `/api/v1/chat` |
| screening_router | routes_screening.py | `/api/v1/screening` |
| database_router | routes_database.py | `/api/v1/database` |
| admin_router | routes_admin.py | `/api/v1/admin` |
| query_router | routes_query.py | `/api/v1/intelligence` |
| vt_router | routes_virustotal.py | `/api/v1/virustotal` |
| us_router | routes_urlscan.py | `/api/v1/urlscan` |

Additionally, `feeds_router` (routes_feeds.py) is included via `router.include_router()` with prefix `/api/v1/feeds`. Feed sources are stored in the `feed_sources` PostgreSQL table (seeded from `data/feed_sources_seed.csv` on first run).

Static files mounted at `/static` from the `static/` directory.

---

## Data Flow

### Article Pipeline

The `ArticlePipeline` class (`services/article_pipeline.py`) orchestrates collection through broadcast. It runs as a background `asyncio.create_task`.

```
┌─────────────────────────────────────────────────────────────┐
│  Collection Cycle (repeats every FEED_CHECK_INTERVAL secs)  │
└─────────────────────────────────────────────────────────────┘

SourceStateManager.enabled_groups + enabled_collectors
        │
        ▼
CollectorRegistry.stream_all(groups)
        │
        ├── RSSCollector    ──▶ feedparser, yields articles
        ├── NP4KCollector   ──▶ trafilatura, yields articles
        └── NewsAPICollector ──▶ NewsAPI HTTP, yields articles
        │
        ▼ (for each article yielded)

DEDUPLICATION (5 layers, in order):
  1. In-flight URL map    (url→timestamp, TTL 10min)
  2. DB URL existence      (asyncpg query)
  3. pg_trgm fuzzy title   (GIN index, similarity ≥ 0.85)
  4. Content filter         (whitelist/blacklist keywords)
  5. Semantic dedup         (sentence-transformers, cosine ≥ 0.88)
        │
        ▼ (passes all checks)

asyncio.Queue (maxsize=200, provides backpressure)
        │
        ├── Worker 0 ──┐
        ├── Worker 1 ──┤
        └── Worker 2 ──┘
                │
                ▼
        finalize_article()
          ├── extract_location(title)    — regex
          ├── extract_casualties(title)  — regex
          └── source_confidence from tier (1→80, 2→60, 3+→40)
                │
                ▼
        Local classification (optional, if EMBEDDINGS_ENABLED)
          ├── embeddings.classify(title)
          ├── risk_indicators from classifier
          └── relevance_score from confidence
                │
                ▼
        db.signals.insert_final_signal()  — PostgreSQL INSERT
                │
                ▼
        manager.broadcast_new_signal()  — WebSocket to all clients
```

### Article Preparation Detail

`IntelligenceService._prepare_article()` handles the middle stage:

1. Extract title, URL, source, description, full_text, author from raw article
2. Validate: reject if title or URL empty
3. Dedup: `db.find_similar_title()` via pg_trgm
4. Sanitize URL via `sanitize_url()`
5. Parse publication timestamp (ISO fallback to `datetime.now()`)
6. Translate via NLLB/Ollama if `translator.needs_translation(title)` — translates title, description, and full_text
7. Return prepared dict with original and translated fields

### Article Finalization Detail

`IntelligenceService.finalize_article()` adds metadata:

- Location extracted from title (regex-based)
- Casualty count extracted from title (regex-based)
- Source confidence mapped from tier (`{1: 80, 2: 60}`, default 40)
- Defaults: `relevance_score=0`, `risk_indicators=[]`, `analysis_mode='SKIPPED'`, `processed=True`

No AI scoring at collection time. Scoring happens post-hoc via local classifier or manual analyst curation.

---

## Service Layer

All services are singletons instantiated at import time or via `get_*()` factory functions.

### Core Services

| Service | File | Singleton | Purpose |
|---------|------|-----------|---------|
| `IntelligenceService` | services/intelligence.py | `intel_service` (api/deps.py) | Article preparation and finalization |
| `ArticlePipeline` | services/article_pipeline.py | Created in lifespan | Collection→persist→broadcast orchestrator |
| `ConnectionManager` | services/websocket.py | `manager` (module-level) | WebSocket connection pool and broadcast |
| `MetricsCollector` | services/metrics.py | `metrics_collector` (module-level) | Runtime telemetry (tokens, articles, cache hits) |

### Collection Services

| Service | File | Singleton | Purpose |
|---------|------|-----------|---------|
| `FeedManager` | services/feed_manager.py | `get_feed_manager()` | Feed registry loading, RSS parsing, content filtering |
| `SourceStateManager` | services/source_state.py | `get_source_state_manager()` | Enabled groups/collectors, persistent state (JSON) |
| `ContentFilter` | services/content_filter.py | `get_content_filter()` | Whitelist/blacklist keyword matching |
| `CollectorRegistry` | services/collectors/ | `get_collector_registry()` | Registry of BaseCollector implementations |
| `RSSCollector` | services/collectors/rss_collector.py | Via registry | feedparser-based RSS collection |
| `NP4KCollector` | services/collectors/np4k_collector.py | Via registry | Newspaper4k/trafilatura web scraping |
| `NewsAPICollector` | services/collectors/newsapi_collector.py | Via registry | NewsAPI HTTP integration |

### Analysis Services

| Service | File | Singleton | Purpose |
|---------|------|-----------|---------|
| `TranslationService` | services/translation.py | Created in pipeline | NLLB-200 + Ollama translation with cache |
| `EmbeddingService` | services/embeddings.py | Created in pipeline | sentence-transformers classification + semantic dedup |

### External Integration Services

| Service | File | Purpose |
|---------|------|---------|
| `EntityScreeningService` | services/entity_screening.py | OpenSanctions (local CSV), FBI, Interpol matching |
| `VirusTotalService` | services/virustotal.py | Feed URL malware scanning with quota management |
| `UrlscanService` | services/urlscan.py | Feed URL phishing detection |
| `WikipediaEventsService` | services/wikipedia_events.py | Current events scraping (hourly) |

---

## Database Layer

### Connection Pool

`Database` class (`database/connection.py`) wraps asyncpg:

```python
asyncpg.create_pool(
    dsn,
    min_size=config.DB_POOL_MIN_SIZE,    # default 1
    max_size=config.DB_POOL_MAX_SIZE,    # default 3
    command_timeout=30,
    statement_cache_size=256,
    server_settings={'jit': 'off'}
)
```

### Repository Pattern

8 repositories, each scoped to specific tables:

| Repository | Table(s) | Purpose |
|-----------|----------|---------|
| `SignalRepository` | intel_signals | Signal CRUD, filtering, dedup, full-text search |
| `ReputationRepository` | source_reputation, author_reputation | Rolling-average credibility scores |
| `MetricsRepository` | token_usage, gemini_discover_calls | AI telemetry, rate limiting |
| `ScreeningRepository` | sanctions_entities, sanctions_names, screening_log | Sanctions bulk load, fuzzy search |
| `CacheRepository` | cache_store | Generic key/value with TTL |
| `VirusTotalRepository` | virustotal_scans | VT scan results, staleness-based scheduling |
| `URLScanRepository` | urlscan_scans | urlscan results, scheduling |
| `SourceFlagsRepository` | source_fetch_flags | Paywall/subscriber-wall domain tracking |

### Facade

`IntelligenceDB` (`database/models.py`) wraps `Database` and exposes legacy convenience methods that delegate to repositories. Both new code (using `db.signals.method()`) and legacy code (using `db.method()`) coexist.

### Initialization Flow

```
IntelligenceDB.connect()
  ├── Database.connect()
  │   ├── asyncpg.create_pool()
  │   ├── Phase 1: DatabaseSchema.initialize_tables()
  │   │   ├── CREATE EXTENSION pg_trgm
  │   │   ├── CREATE TYPE signal_classification, analysis_mode
  │   │   └── CREATE TABLE (10 tables)
  │   └── Initialize 8 repositories
  ├── Phase 2: MigrationRunner.run()
  │   └── Column migrations (type fixes, new columns)
  └── Phase 3: DatabaseSchema.initialize_indexes()
      ├── CREATE TRIGGERS (updated_at auto-update, title_tsvector auto-populate)
      ├── Backfill title_tsvector for existing rows
      └── CREATE INDEX (18 indexes)
```

---

## WebSocket Layer

`ConnectionManager` manages real-time client connections.

**Limits**: 50 total connections, 5 per IP. Enforced at WebSocket accept time (close code 1008 on rejection).

**Broadcast pattern**: Snapshots `active_connections` list before iterating. Failed sends trigger automatic disconnect cleanup.

**Message types** (server → client):

| Type | Triggered by |
|------|-------------|
| `new_signals` | Pipeline worker inserts a signal |
| `signal_update` | Analyst PATCHes a signal's score/indicators |
| `status_update` | System status changes |
| `vt_scan_result` | VirusTotal background scan completes |
| `urlscan_result` | urlscan.io background scan completes |
| `report_update` | Executive report generation |

**Keepalive**: Client sends `"ping"`, server responds `"pong"`.

---

## Dependency Injection

`api/deps.py` creates the two core singletons at import time:

```python
db = IntelligenceDB(config.DATABASE_URL)     # No pool yet
intel_service = IntelligenceService(db)
```

The pool is opened during lifespan startup (`db.connect()`). All route handlers import from `api.deps`.

---

## Background Tasks

| Task | Interval | Condition |
|------|----------|-----------|
| ArticlePipeline.run() | `FEED_CHECK_INTERVAL` (default 300s) | `FEED_COLLECTION_ENABLED=true` |
| VirusTotal scheduler | Continuous (quota-paced) | `VIRUSTOTAL_ENABLED=true` |
| urlscan.io scheduler | Continuous (quota-paced) | `URLSCAN_ENABLED=true` |
| Wikipedia events refresh | 1 hour | `WIKI_EVENTS_ENABLED=true` |
| Screening cache warm | Once at startup | Always |
| Metrics hydration | Once at startup | Always |

All tasks are `asyncio.create_task()` instances tracked in a list. On shutdown, all are cancelled via `task.cancel()` + `asyncio.gather(*tasks, return_exceptions=True)`.

---

## Crash Recovery

On startup, `ArticlePipeline._recover_pending()` queries all signals where `processed=FALSE` (from interrupted previous runs). For each:

1. Extract location and casualties from title (regex)
2. Call `update_signal_analysis()` with defaults (`analysis_mode='SKIPPED'`)
3. Broadcast recovered signal to connected clients

---

## State Persistence

| What | Where | Format |
|------|-------|--------|
| Feed group enable/disable state | `data/feed_state.json` | JSON (atomic write via temp file) |
| Scraper site configuration | `data/scraper_sites.json` | JSON |
| Translation cache | `data/translation_cache.json` | JSON (30-day TTL, 30K max entries) |
| Sanctions database | `data/opensanctions/` | CSV (downloaded from OpenSanctions) |
| Trained classifier | `models/classifier.pkl` | sklearn pickle |
| All intelligence signals | PostgreSQL | `intel_signals` table |
| Runtime config overrides | `.env` file | dotenv (some admin endpoints persist here) |

---

## Key Design Patterns

**Streaming collectors**: All collectors implement `async def collect()` as `AsyncGenerator`. Articles yield immediately — no batching.

**Bounded work queue**: `asyncio.Queue(maxsize=200)` provides backpressure between collectors and workers. If the queue is full, collectors block.

**5-layer deduplication**: In-flight URL map → DB URL check → pg_trgm fuzzy title → content filter → semantic similarity. Each layer catches progressively subtler duplicates.

**No AI at collection time**: Signals are collected, translated, and persisted with extracted metadata only. Scoring fields are populated later via local classifier or manual analyst curation.

**Atomic transactions**: `insert_final_signal()` and `update_analysis()` use explicit asyncpg transactions to atomically write signals + reputation upserts.

**Singleton services**: Core services use module-level instances or `get_*()` factory functions for thread-safe lazy initialization.
