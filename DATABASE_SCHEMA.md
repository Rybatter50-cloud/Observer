# Database Schema

PostgreSQL 14+ with asyncpg connection pool. Schema defined in `database/schema.py`, applied on first connection.

## Extensions

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Used for fuzzy text matching on `intel_signals.title` (deduplication) and `sanctions_names.name_normalized` (entity search).

## Enum Types

```sql
CREATE TYPE signal_classification AS ENUM (
    'CONFLICT', 'TERRORISM', 'POLITICAL', 'ECONOMIC',
    'HUMANITARIAN', 'CYBER', 'ENVIRONMENTAL', 'UNKNOWN'
);

CREATE TYPE analysis_mode AS ENUM (
    'PENDING', 'LOCAL', 'FALLBACK', 'SKIPPED', 'MANUAL'
);
```

`signal_classification` is a legacy type preserved for compatibility; new code uses `risk_indicators TEXT[]` instead. `analysis_mode` tracks how a signal was scored: PENDING (awaiting), LOCAL (sentence-transformers), FALLBACK (alternate path), SKIPPED (no scoring at collection), MANUAL (analyst-curated).

---

## Tables

### intel_signals

Primary intelligence signal records.

```sql
CREATE TABLE IF NOT EXISTS intel_signals (
    id                 SERIAL PRIMARY KEY,
    title              TEXT NOT NULL,
    description        TEXT,
    full_text          TEXT,
    location           TEXT NOT NULL DEFAULT 'Unknown',
    relevance_score    INTEGER NOT NULL DEFAULT 0,
    casualties         INTEGER DEFAULT 0,
    published_at       TIMESTAMPTZ,
    url                TEXT UNIQUE NOT NULL,
    source             TEXT NOT NULL,
    collector          TEXT,
    risk_indicators    TEXT[] NOT NULL DEFAULT '{}',
    processed          BOOLEAN NOT NULL DEFAULT FALSE,
    analysis_mode      analysis_mode NOT NULL DEFAULT 'PENDING',
    is_translated      BOOLEAN NOT NULL DEFAULT FALSE,
    source_language    TEXT,
    translation_source TEXT,
    author             TEXT,
    source_group       TEXT,
    source_confidence  INTEGER NOT NULL DEFAULT 0,
    author_confidence  INTEGER NOT NULL DEFAULT 0,
    title_tsvector     tsvector,
    screening_hits     JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    original_title     TEXT,
    entities_json      JSONB,
    entities_tier      INTEGER NOT NULL DEFAULT 0
);
```

**Indexes:**

```sql
idx_signals_processed_created  ON (processed, created_at DESC)
idx_signals_created            ON (created_at DESC)
idx_signals_relevance_score    ON (relevance_score DESC)
idx_signals_source             ON (source)
idx_signals_risk_indicators    ON USING GIN (risk_indicators)
idx_signals_url                ON (url)
idx_signals_analysis_mode      ON (analysis_mode)
idx_signals_title_tsvector     ON USING GIN (title_tsvector)
idx_signals_title_trgm         ON USING GIN (title gin_trgm_ops)
```

**Triggers:**

- `trg_signals_updated_at` — Auto-updates `updated_at` on row modification.
- `trg_signals_title_tsvector` — Auto-populates `title_tsvector` from `title` on insert/update.

**Repository:** `SignalRepository` (`database/repositories/signals.py`)

---

### source_reputation

Rolling-average reliability scores for news sources.

```sql
CREATE TABLE IF NOT EXISTS source_reputation (
    source_name       TEXT PRIMARY KEY,
    reliability_score REAL NOT NULL DEFAULT 50.0,
    sample_count      INTEGER NOT NULL DEFAULT 0,
    last_updated      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Score formula: `new_score = (old_score * sample_count + new_sample) / (sample_count + 1)`

**Repository:** `ReputationRepository` (`database/repositories/reputation.py`)

---

### author_reputation

Rolling-average credibility scores for article authors.

```sql
CREATE TABLE IF NOT EXISTS author_reputation (
    author_name       TEXT PRIMARY KEY,
    credibility_score REAL NOT NULL DEFAULT 50.0,
    sample_count      INTEGER NOT NULL DEFAULT 0,
    last_updated      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Same rolling-average formula as source_reputation.

**Repository:** `ReputationRepository` (`database/repositories/reputation.py`)

---

### metadata

Key/value store for application metadata.

```sql
CREATE TABLE IF NOT EXISTS metadata (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Used by screening service (last load time, CSV last-modified header).

---

### sanctions_entities

Sanctions entity records loaded from OpenSanctions CSV.

```sql
CREATE TABLE IF NOT EXISTS sanctions_entities (
    id          TEXT PRIMARY KEY,
    schema_type TEXT NOT NULL DEFAULT 'Person',
    name        TEXT NOT NULL,
    aliases     TEXT,
    birth_date  TEXT,
    countries   TEXT,
    sanctions   TEXT,
    dataset     TEXT,
    identifiers TEXT,
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Indexes:**

```sql
idx_sanctions_entities_schema  ON (schema_type)
```

**Repository:** `ScreeningRepository` (`database/repositories/screening.py`)

---

### sanctions_names

Name index for fuzzy sanctions searching. Supports aliases.

```sql
CREATE TABLE IF NOT EXISTS sanctions_names (
    id              SERIAL PRIMARY KEY,
    entity_id       TEXT NOT NULL REFERENCES sanctions_entities(id) ON DELETE CASCADE,
    name_normalized TEXT NOT NULL,
    name_display    TEXT NOT NULL
);
```

**Indexes:**

```sql
idx_sanctions_names_trgm    ON USING GIN (name_normalized gin_trgm_ops)
idx_sanctions_names_entity  ON (entity_id)
```

**Repository:** `ScreeningRepository` (`database/repositories/screening.py`)

---

### cache_store

General-purpose JSONB cache with timestamps.

```sql
CREATE TABLE IF NOT EXISTS cache_store (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Repository:** `CacheRepository` (`database/repositories/cache.py`)

---

### virustotal_scans

Historical VirusTotal scan results for feed URLs.

```sql
CREATE TABLE IF NOT EXISTS virustotal_scans (
    id               SERIAL PRIMARY KEY,
    feed_url         TEXT NOT NULL,
    feed_name        TEXT,
    feed_group       TEXT,
    scan_id          TEXT,
    malicious_count  INTEGER NOT NULL DEFAULT 0,
    suspicious_count INTEGER NOT NULL DEFAULT 0,
    harmless_count   INTEGER NOT NULL DEFAULT 0,
    undetected_count INTEGER NOT NULL DEFAULT 0,
    timeout_count    INTEGER NOT NULL DEFAULT 0,
    total_engines    INTEGER NOT NULL DEFAULT 0,
    risk_score       INTEGER NOT NULL DEFAULT 0,
    threat_names     TEXT[] NOT NULL DEFAULT '{}',
    raw_result       JSONB,
    scanned_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Indexes:**

```sql
idx_vt_scans_feed_url    ON (feed_url)
idx_vt_scans_risk_score  ON (risk_score DESC)
idx_vt_scans_scanned_at  ON (scanned_at DESC)
```

**Repository:** `VirusTotalRepository` (`database/repositories/virustotal.py`)

---

### urlscan_scans

Historical urlscan.io scan results for feed URLs.

```sql
CREATE TABLE IF NOT EXISTS urlscan_scans (
    id                SERIAL PRIMARY KEY,
    feed_url          TEXT NOT NULL,
    feed_name         TEXT,
    feed_group        TEXT,
    scan_uuid         TEXT,
    verdict_score     INTEGER NOT NULL DEFAULT 0,
    verdict_malicious BOOLEAN NOT NULL DEFAULT FALSE,
    categories        TEXT[] NOT NULL DEFAULT '{}',
    brands            TEXT[] NOT NULL DEFAULT '{}',
    risk_score        INTEGER NOT NULL DEFAULT 0,
    page_domain       TEXT,
    page_ip           TEXT,
    page_country      TEXT,
    page_server       TEXT,
    page_status       INTEGER,
    raw_result        JSONB,
    scanned_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Indexes:**

```sql
idx_us_scans_feed_url    ON (feed_url)
idx_us_scans_risk_score  ON (risk_score DESC)
idx_us_scans_scanned_at  ON (scanned_at DESC)
```

**Repository:** `URLScanRepository` (`database/repositories/urlscan.py`)

---

### source_fetch_flags

Paywall and subscriber-wall domain tracking.

```sql
CREATE TABLE IF NOT EXISTS source_fetch_flags (
    domain              TEXT PRIMARY KEY,
    has_subscriber_wall BOOLEAN NOT NULL DEFAULT FALSE,
    has_paywall         BOOLEAN NOT NULL DEFAULT FALSE,
    source_name         TEXT,
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Indexes:**

```sql
idx_source_fetch_flags_type  ON (has_subscriber_wall, has_paywall)
```

**Repository:** `SourceFlagsRepository` (`database/repositories/source_flags.py`)

---

## Migration Tables

These tables are created by the migration runner (`database/migrations/runner.py`) rather than `schema.py`:

- `token_usage` — AI token usage tracking (used by `MetricsRepository`)
- `gemini_discover_calls` — Gemini rate limiting (used by `MetricsRepository`)
- `screening_log` — Screening audit trail (used by `ScreeningRepository`)
- `feed_sources` — RSS/scraper feed sources (seeded from `data/feed_sources_seed.csv` on first run)
- `translation_memory` — Vector translation cache (requires pgvector, optional)
- `article_clusters` / `cluster_members` — Semantic article grouping (requires pgvector, optional)

---

## Repository Method Reference

### SignalRepository

| Method | Purpose |
|--------|---------|
| `url_exists(url)` | Check if URL exists |
| `find_similar_title(title, threshold=0.85, hours=24)` | pg_trgm fuzzy dedup |
| `get_recent_titles(hours=24)` | Recent titles for context |
| `get_signals(time_window, limit, offset, search, ...)` | Filtered signal query |
| `count_signals(time_window, search, ...)` | Count matching signals |
| `get_by_id(signal_id)` | Single signal lookup |
| `count_unprocessed()` | Unprocessed signal count |
| `get_next_unprocessed()` | Next unprocessed signal |
| `insert_signal(...)` | Basic insert |
| `insert_final_signal(data)` | Atomic insert + reputation upsert |
| `update_analysis(signal_id, updates)` | Atomic update + reputation upsert |
| `update_score_indicators(signal_id, score, indicators)` | Manual re-score (sets MANUAL mode) |
| `update_screening_hits(signal_id, data)` | Store screening results |
| `update_full_text(signal_id, full_text)` | Store fetched full text |
| `cleanup_old(days=30)` | Delete old signals |

### ReputationRepository

| Method | Purpose |
|--------|---------|
| `get_source(source_name)` | Source reputation lookup |
| `upsert_source(source_name, new_score)` | Rolling-average source update |
| `upsert_source_on_conn(conn, source_name, new_score)` | Transactional variant |
| `get_author(author_name)` | Author reputation lookup |
| `upsert_author(author_name, new_score)` | Rolling-average author update |
| `upsert_author_on_conn(conn, author_name, new_score)` | Transactional variant |

### MetricsRepository

| Method | Purpose |
|--------|---------|
| `insert_token_usage(provider, tokens)` | Log AI token usage |
| `get_token_usage_24h()` | Rolling 24h token stats |
| `prune_old_token_usage(hours=48)` | Cleanup old records |
| `insert_discover_call()` | Log Gemini discover call |
| `get_discover_calls_48h()` | Rolling 48h call history |
| `prune_old_discover_calls(hours=48)` | Cleanup old records |

### ScreeningRepository

| Method | Purpose |
|--------|---------|
| `bulk_load(records, batch_size=2000)` | Replace all sanctions data |
| `search_by_name(name, threshold=0.3, ...)` | Fuzzy pg_trgm entity search |
| `get_entity_count()` | Total entities loaded |
| `get_name_count()` | Total name variants |
| `get_last_load_time()` | Last bulk load timestamp |
| `log_screening(name, hit_count, sources, ip)` | Audit log entry |
| `get_recent_screenings(limit=15)` | Recent screening log |
| `get_screening_log_stats()` | Aggregate screening stats |

### CacheRepository

| Method | Purpose |
|--------|---------|
| `get(key, max_age_seconds=None)` | Read with optional TTL |
| `set(key, value)` | Write JSONB value |
| `delete(key)` | Remove entry |

### VirusTotalRepository

| Method | Purpose |
|--------|---------|
| `insert_scan(...)` | Store scan result |
| `get_latest_scan(feed_url)` | Most recent scan for a URL |
| `get_scan_history(feed_url, limit=10)` | Scan history for a URL |
| `get_all_latest_scans()` | Latest scan per URL (DISTINCT ON) |
| `get_feeds_sorted_by_staleness(urls)` | Never-scanned first, then oldest |
| `get_cycle_progress(urls, max_age_days=3)` | Scheduler progress tracking |
| `get_stats()` | Aggregate scan statistics |
| `get_flagged_feeds(min_detections=1)` | Feeds with detections |

### URLScanRepository

| Method | Purpose |
|--------|---------|
| `insert_scan(...)` | Store scan result |
| `get_latest_scan(feed_url)` | Most recent scan for a URL |
| `get_scan_history(feed_url, limit=10)` | Scan history for a URL |
| `get_all_latest_scans()` | Latest scan per URL (DISTINCT ON) |
| `get_feeds_sorted_by_staleness(urls)` | Never-scanned first, then oldest |
| `get_cycle_progress(urls, max_age_days=3)` | Scheduler progress tracking |
| `get_stats()` | Aggregate scan statistics |
| `get_flagged_feeds(min_score=50)` | Feeds above risk threshold |

### SourceFlagsRepository

| Method | Purpose |
|--------|---------|
| `get_all_flags()` | All flagged domains |
| `get_blocked_domains()` | Domain → flag_type map |
| `is_domain_blocked(domain)` | Check if domain is blocked |
| `flag_domain(domain, flag_type, source_name)` | Flag a domain |
| `unflag_domain(domain)` | Remove flag |

---

## Database Facade

`IntelligenceDB` (`database/models.py`) wraps the `Database` class and exposes legacy convenience methods that delegate to the repository layer. New code accesses repositories directly via `db.signals`, `db.reputation`, etc.

## Initialization Phases

1. **Phase 1** — `DatabaseSchema.initialize_tables()`: Creates extensions, enums, and all tables.
2. **Phase 2** — `MigrationRunner.run()`: Applies column migrations (type fixes, new columns, migration-only tables).
3. **Phase 3** — `DatabaseSchema.initialize_indexes()`: Creates triggers, backfills tsvector, creates all indexes.
