# API Reference

All endpoints are unauthenticated. Deploy behind a reverse proxy with auth if needed. FastAPI auto-generates OpenAPI docs at `/docs` and `/redoc`.

---

## Dashboard & Pages

| Method | Path | Response |
|--------|------|----------|
| GET | `/` | Dashboard HTML |
| GET | `/client` | Read-only client HTML |
| GET | `/feeds` | Feed manager HTML |
| GET | `/scraper` | Scraper manager HTML |

---

## WebSocket

### Connection

**Endpoint:** `ws://host:port/ws`

**Limits:** 50 total connections, 5 per IP. Rejected with close code 1008.

**Keepalive:** Client sends `"ping"` (text), server responds `"pong"`.

### Server → Client Message Types

| type | data | Source |
|------|------|--------|
| `new_signals` | `[signal]` | Pipeline worker insert |
| `signal_update` | `{id, data}` | Analyst PATCH on signal |
| `status_update` | `{...}` | System status change |
| `vt_scan_result` | `{...}` | VirusTotal background scan |
| `urlscan_result` | `{...}` | urlscan.io background scan |
| `report_update` | `{content}` | Report generation |

---

## Intelligence

### GET /api/v1/intelligence

Query signals with filters.

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `time_window` | str | `all` | `4h`, `24h`, `72h`, `7d`, or `all` |
| `limit` | int | `200` | 1–5000 |
| `offset` | int | `0` | Pagination offset |
| `search` | str | `""` | Full-text search across title, description, location, source, author |
| `source_groups` | str | `""` | Comma-separated source group names |
| `content_search` | str | `""` | Comma-separated content filters |
| `min_score` | int | `0` | Minimum relevance score (0–100) |
| `risk_indicators` | str | `""` | Comma-separated codes (e.g. `T,K,U`) |
| `translated_only` | bool | `false` | Only translated signals |
| `screening_only` | bool | `false` | Only signals with screening hits |

**Response:** `{intel, pagination, logs, connection_count, articles_processed, articles_rejected}`

### PATCH /api/v1/intelligence/{signal_id}

Manual analyst re-scoring.

**Body:** `{relevance_score: 0-100, risk_indicators: [...]}`

**Response:** `{success, signal}`

Broadcasts `signal_update` to all WebSocket clients. Sets `analysis_mode='MANUAL'`.

### GET /api/v1/intelligence/blocked-domains

**Response:** `{domains: {domain: flag_type}}`

### POST /api/v1/intelligence/{signal_id}/fetch-fulltext

Fetch and store full article text. Detects paywalls via Schema.org `isAccessibleForFree`. Auto-translates if non-English.

**Response:** `{success, full_text, char_count, error, block_type, domain}`

### POST /api/v1/intelligence/query

Execute read-only SQL against `intel_signals`.

**Body:** `{sql: "SELECT ... FROM intel_signals WHERE ..."}`

**Response:** `{success, results, columns, row_count, execution_time_ms, error}`

**Security (5-layer):**
1. Regex/keyword blocklist
2. DB-enforced `READ ONLY` transaction
3. Restricted `search_path`
4. 5-second statement timeout
5. 1000-row limit

Must be SELECT-only and reference `intel_signals`. No system catalogs.

---

## Health

### GET /api/v1/health

**Response:** `{status, database, websocket_clients, config, feeds}`

---

## Feeds

### GET /api/v1/feeds/status

Feed counts, enabled groups, filter mode, group details, health summary, collector info.

### POST /api/v1/feeds/groups/enable

**Body:** `{groups: [...]}`

**Response:** `{success, enabled, already_enabled, total_enabled}`

### POST /api/v1/feeds/groups/disable

**Body:** `{groups: [...]}`

**Response:** `{success, disabled, protected, not_enabled, total_enabled}`

Protected groups `global` and `osint` (Tier 1) cannot be disabled.

### GET /api/v1/feeds/groups

All groups with status, tier, feed count, enabled state.

### POST /api/v1/feeds/reset

Reset to default enabled groups.

### Content Filtering

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/feeds/content-filter/status` | Active filter files and mode |
| POST | `/api/v1/feeds/content-filter/mode` | Set mode (`blacklist`/`whitelist`/`both`) |
| POST | `/api/v1/feeds/content-filter/select` | Select active BL/WL files |
| DELETE | `/api/v1/feeds/content-filter/file` | Delete `WL_ollama_*` files only |

### Feed Registry

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/feeds/registry` | Full registry JSON |
| PUT | `/api/v1/feeds/registry` | Replace entire registry |
| GET | `/api/v1/feeds/registry/download` | Download registry file |
| POST | `/api/v1/feeds/test` | Test a feed URL — `{url}` → `{success, article_count, feed_title, sample_titles}` |
| GET | `/api/v1/feeds/health` | Feed health tracking data |
| POST | `/api/v1/feeds/health` | Report feed health |
| DELETE | `/api/v1/feeds/health` | Clear health data |
| GET | `/api/v1/feeds/stats` | Group/feed/language/country stats |

### Feed Discovery

**POST /api/v1/feeds/discover** — `{url}` → Discover RSS feeds for a domain.

3-phase strategy: HTML autodiscovery → RSS listing pages → well-known paths.

**Response:** `{success, domain, feeds: [{url, title, name}]}`

---

## Scraper

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/scraper/sites` | List scraper sites with stats |
| GET | `/api/v1/scraper/stats` | Scraper statistics |
| POST | `/api/v1/scraper/save-registry` | Save registry — `{registry}` |
| POST | `/api/v1/scraper/test` | Test scrape a URL — `{url}` (max 3 articles) |
| POST | `/api/v1/scraper/collect-site` | Collect from one site — `{group, index}` |
| POST | `/api/v1/scraper/collect-all` | Collect from all enabled sites |
| POST | `/api/v1/scraper/sites/{site_id}/toggle` | Toggle site enabled state |
| DELETE | `/api/v1/scraper/sites/{site_id}` | Delete a site |

---

## Chat

### Ollama Chat

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/chat/status` | Ollama availability, model, installed models |
| POST | `/api/v1/chat/message` | Send message — `{message}` → `{response, model}`. DB-context aware, 6-exchange history. |
| POST | `/api/v1/chat/clear` | Clear conversation history |

### Filter Generation

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/chat/build-filter` | Generate WL_ollama_* filter — `{topic, name?}` |
| POST | `/api/v1/chat/append-filter` | Append patterns to filter file — `{filename, patterns}` |

### Feed Management via Chat

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/chat/manage-feeds` | Enable/disable by region — `{region}` |
| POST | `/api/v1/chat/enable-all-feeds` | Enable all feed groups |
| POST | `/api/v1/chat/filter-lang` | Filter feeds by language — `{lang}` |
| POST | `/api/v1/chat/reset-feeds` | Restore pre-manage-feeds state |

### Feed Discovery (Gemini)

**POST /api/v1/chat/discover-feeds** — `{country}` → Gemini-powered discovery.

1. Gemini finds news outlets for the country
2. Probes each domain for RSS endpoints (3-phase)
3. Non-RSS sites staged as NP4K scraper targets

**Response:** `{success, country, discovered, scraper_sites, total_rss, pending_confirmation, gemini_usage}`

Requires `GEMINI_ENABLED=true` and `GEMINI_API_KEY`.

**POST /api/v1/chat/confirm-feeds** — Confirm discovered feeds.

**Body:** `{selected: [0,1,3], selected_scrapers: [0,2]}` or `{all: true}`

Geocodes via Nominatim. Creates group if needed.

---

## Collectors

### List & Status

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/collectors` | All collectors with status and summary |
| GET | `/api/v1/collectors/{name}` | Detailed status for one collector |
| GET | `/api/v1/collectors/newsapi/status` | NewsAPI-specific status |
| GET | `/api/v1/collectors/np4k/status` | NP4K-specific status |

### Control

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/collectors/{name}/enable` | Enable a collector |
| POST | `/api/v1/collectors/{name}/disable` | Disable a collector |
| POST | `/api/v1/collectors/{name}/collect` | Force immediate collection |
| POST | `/api/v1/collectors/{name}/configure` | Update collector config |
| POST | `/api/v1/collectors/newsapi/enable` | Enable NewsAPI |
| POST | `/api/v1/collectors/newsapi/disable` | Disable NewsAPI |
| POST | `/api/v1/collectors/np4k/enable` | Enable NP4K |
| POST | `/api/v1/collectors/np4k/disable` | Disable NP4K |

### API Key Management

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/collectors/apikey/{key_name}` | Check if key is set (masked) |
| POST | `/api/v1/collectors/apikey` | Set API key — `{key_name, value}`. Persists to `.env`. |

Allowed keys: `NEWSAPI_KEY`, `GEMINI_API_KEY`, `INTERPOL_API_KEY`, `VIRUSTOTAL_API_KEY`, `URLSCAN_API_KEY`.

### API Toggles

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/collectors/api-toggles` | All toggle states |
| POST | `/api/v1/collectors/api-toggle` | Set toggle — `{key_name, enabled}` |

### Presets & Connectivity

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/collectors/presets/newsapi` | NewsAPI query presets |
| POST | `/api/v1/collectors/ping` | Test URL reachability — `{url}` |

---

## Screening

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/screening/check` | Screen entity — `{name, sources?, entity_type?, signal_id?}` |
| GET | `/api/v1/screening/status` | Service health, cache info, available sources |
| GET | `/api/v1/screening/log/recent` | Last 15 screening checks |
| POST | `/api/v1/screening/report` | Generate report — `{date_start, date_end, sources, format}` |
| GET | `/api/v1/screening/report/export` | CSV export — query params: `date_start`, `date_end`, `sources` |

**Valid sources:** `fbi`, `interpol`, `opensanctions`, `sanctions_network`

**Check response:** `{query, hit_count, max_score, sources_checked, sources_failed, elapsed_ms, hits: [{source, name, score, category, details, url}]}`

---

## Database Management

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/database/details` | DB size, table sizes, signal counts, pool status |
| GET | `/api/v1/database/config` | Current `max_signals_limit` |
| POST | `/api/v1/database/config` | Set `max_signals_limit` (1000–500000). Persists to `.env`. |
| POST | `/api/v1/database/backup` | Create pg_dump backup (5-min timeout) |
| GET | `/api/v1/database/backups` | List available backups |
| GET | `/api/v1/database/backup/download/{filename}` | Download backup SQL file |
| POST | `/api/v1/database/restore` | Restore from backup — `{filename}` (10-min timeout) |

---

## Metrics

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/metrics/ai` | Queue size, collector stats, cache hits, timestamp |
| GET | `/api/v1/metrics/token-budget` | Per-provider rolling 24h token budget and recovery rates |

---

## VirusTotal

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/virustotal/status` | Connection state, quota, cycle progress, stats |
| POST | `/api/v1/virustotal/scan` | Ad-hoc URL scan — `{url}` (not persisted) |
| GET | `/api/v1/virustotal/scans/latest` | Most recent scan per feed URL |
| GET | `/api/v1/virustotal/scans/flagged` | Feeds with detections — `?min_detections=1` |
| GET | `/api/v1/virustotal/scans/history` | Scan history — `?feed_url=...&limit=10` |
| POST | `/api/v1/virustotal/scheduler/start` | Resume background scanning |
| POST | `/api/v1/virustotal/scheduler/stop` | Pause background scanning |
| GET | `/api/v1/virustotal/config` | Current VT config |
| POST | `/api/v1/virustotal/config` | Update thresholds (in-memory only) |

---

## urlscan.io

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/urlscan/status` | Service status, quota, progress |
| POST | `/api/v1/urlscan/scan` | Ad-hoc URL scan — `{url}` |
| GET | `/api/v1/urlscan/scans/latest` | Most recent scan per feed URL |
| GET | `/api/v1/urlscan/scans/flagged` | Feeds above risk threshold — `?min_score=50` |
| GET | `/api/v1/urlscan/scans/history` | Scan history — `?feed_url=...&limit=10` |
| POST | `/api/v1/urlscan/scheduler/start` | Resume background scanning |
| POST | `/api/v1/urlscan/scheduler/stop` | Pause background scanning |
| GET | `/api/v1/urlscan/config` | Current urlscan config |
| POST | `/api/v1/urlscan/config` | Update thresholds (in-memory only) |

---

## Admin

### Filter Editor

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/admin/filter/content` | Read filter file — `?filename=...` |
| POST | `/api/v1/admin/filter/content` | Write filter file — `{filename, content}`. Validates regex. |
| GET | `/api/v1/admin/filter/patterns` | List patterns with validity — `?filename=...` |
| POST | `/api/v1/admin/filter/patterns` | Replace patterns — `{filename, patterns}` |

### Collector Environment Config

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/admin/collectors/config` | RSS, NP4K, NewsAPI config and registry stats |
| GET | `/api/v1/admin/collectors/env/list` | Available collector configs |
| GET | `/api/v1/admin/collectors/env` | Collector env vars — `?collector=...` |
| POST | `/api/v1/admin/collectors/env` | Update collector env vars. Persists to `.env`. |

### App Controls

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/admin/restart/pipeline` | Restart article pipeline (non-destructive) |
| POST | `/api/v1/admin/restart/app` | Restart app via SIGHUP (0.5s delay) |

### Ollama Configuration

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/admin/ollama/status` | Model, installed models, profiles with VRAM estimates |
| POST | `/api/v1/admin/ollama/config` | Update Ollama params — validates ranges, persists to `.env` |

### Transformer Status

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/admin/transformers/status` | NLLB and embeddings model status |
| GET | `/api/v1/admin/screening/status` | Screening service status |

### Embeddings

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/admin/embeddings/config` | Embeddings config and status |
| POST | `/api/v1/admin/embeddings/config` | Update enabled/threshold. Persists to `.env`. |
| POST | `/api/v1/admin/embeddings/reload-classifier` | Reload classifier from disk |
| POST | `/api/v1/admin/embeddings/clear-buffer` | Clear embedding buffer |
| POST | `/api/v1/admin/embeddings/train-classifier` | Train new classifier (10-min timeout) |

### NLLB Translation Tuning

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/admin/nllb/params` | Current NLLB parameters |
| POST | `/api/v1/admin/nllb/params` | Update tuning params. Persists to `.env`. |
| POST | `/api/v1/admin/nllb/model-params` | Update device/compute/threads. Requires restart. |

### Broadcast

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/admin/broadcast/status` | Mock endpoint (not configured) |

---

## Debug

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/debug/pipeline` | Full pipeline diagnostics (all stages, detected issues) |
| GET | `/api/v1/debug/embeddings` | Embedding service status and stats |
| POST | `/api/v1/debug/embeddings/reload-classifier` | Reload classifier |

---

## Wikipedia

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/wikipedia/current-events` | Current events and elections. 1h cache TTL. Requires `WIKI_EVENTS_ENABLED=true`. |

---

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Validation failure |
| 403 | Forbidden (e.g. deleting non-ollama filter) |
| 404 | Resource not found |
| 422 | Invalid request body |
| 500 | Internal server error |
| 503 | Service unavailable (collector system not ready) |
| 504 | Gateway timeout (backup/restore exceeded limit) |

---

## Static Files

Mounted at `/static` from the `static/` directory. Contains modular CSS and JS organized by view (dashboard, client).
