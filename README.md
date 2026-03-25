# Observer v1.0.0

Field-portable intelligence aggregation system. Collects articles from RSS feeds across global news sources, translates non-English content via NLLB-200, screens entities against sanctions databases, and delivers signals through a real-time WebSocket dashboard.

No LLMs, no cloud APIs, no GPU required.

## Features

- **RSS Collection**: 200+ curated feeds across global news sources with configurable check intervals
- **NLLB Translation**: Translates non-English articles to English using NLLB-200 via CTranslate2 (CPU-friendly, int8 quantization)
- **Content Filtering**: Whitelist/blacklist keyword filtering with regex support (13 filter lists included)
- **Entity Screening**: Matches against OpenSanctions database locally via pg_trgm fuzzy matching. Optional FBI/Interpol API lookups
- **Field Extraction**: Regex-based location and casualty extraction from headlines
- **On-Demand Scraping**: Full-text article fetch via trafilatura with paywall detection
- **Real-Time Dashboard**: WebSocket-powered feed with time filtering, full-text search, CSV/JSON export, keyboard shortcuts
- **Admin Console**: Built-in management interface for system monitoring, feed management, collector controls, filter editing, translation tuning, and entity screening status
- **Feed Management**: Add/remove/disable feeds individually or by group/region from the admin console

## Requirements

- Python 3.11+
- PostgreSQL 14+ with `pg_trgm` extension
- ~2 GB disk for NLLB translation model
- ~4 GB RAM minimum

## Quick Start

```bash
# Clone and enter
git clone git@github.com:Rybatter50-cloud/Observer.git && cd Observer

# Run setup (creates venv, installs deps, configures PostgreSQL, downloads NLLB model)
python setup_observer.py

# Start
source venv/bin/activate
python main.py
```

News feed at `http://localhost:8999`. Admin console at `http://localhost:8999/dev`.

On first run, Observer automatically seeds the database with 200+ RSS feed sources covering all UN member states.

### Admin Console

The admin console (`/dev`) provides full system management:

- **System** — Active feed count, accept rate, queue depth, translator status, pipeline and app restart controls
- **Database** — DB size, signal counts, pool status, max signals limit, backup/restore
- **Collectors** — RSS and Trafilatura collector status, 24h counts, error tracking, on/off toggle and manual collect
- **Content Filters** — Switch between blacklist/whitelist/both modes, select filter files, edit patterns inline
- **NLLB Translation** — Configure device, compute type, workers, beam size, length/repetition penalty, temperature, top-k, batch size
- **Entity Screening** — Live status for FBI, Interpol, Sanctions Network, and OpenSanctions screeners with hit counts
- **Signals** — Searchable, time-filtered signal table with score, source, title, and location
- **Feed Groups** — Group-level stats, region presets (Ukraine, Middle East, Asia, Africa, Americas, Caucasus/Central Asia), bulk enable/disable
- **Feed Sites** — Individual feed search/filter by name, URL, group, or type (RSS/Scraper), with per-feed toggle and delete

### Windows Quick Start

```powershell
# Run the installer (creates venv, installs deps, sets up .env)
.\install.ps1

# Start the server
.\start.bat
```

### NLLB Translation Model

The setup script (`python setup_observer.py` or `.\install.ps1`) automatically downloads and converts the NLLB-200 model to CTranslate2 int8 format. This requires a one-time download of ~1.2 GB.

If you skipped setup or need to install the model manually:
```bash
pip install transformers torch huggingface_hub   # build-time only
python scripts/download_nllb.py                  # download + convert
pip uninstall transformers torch                  # free ~2 GB disk
```

To run on CPU with int8 quantization (recommended, set in `.env`):
```
NLLB_DEVICE=cpu
NLLB_COMPUTE_TYPE=int8
```

Without the model, the app still runs but translation is disabled.

## Configuration

The setup script handles `DATABASE_URL` automatically. Everything else has working defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL connection string (set by setup) |
| `AI_TRANSLATOR_MODE` | `nllb` | Translation mode: `nllb` or `off` |
| `FEED_COLLECTION_ENABLED` | `true` | Enable RSS feed collection |
| `FEED_CHECK_INTERVAL` | `300` | Seconds between collection cycles |
| `CONTENT_FILTER_ENABLED` | `true` | Enable content filtering |
| `SANCTIONS_NET_ENABLED` | `true` | Enable OpenSanctions screening |
| `FBI_ENABLED` | `false` | Enable FBI Most Wanted API |
| `INTERPOL_ENABLED` | `false` | Enable Interpol Notices API |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8999` | Server port |

See `.env.example` for all available settings.

## Project Structure

```
Observer/
├── main.py                     # FastAPI app, lifespan, middleware
├── config.py                   # Environment variables and validation
├── api/                        # Route handlers
├── services/                   # Business logic
│   └── collectors/             # RSS, NP4K collectors
├── database/                   # Schema, connection pool, repositories
├── templates/                  # Jinja2 HTML (news feed + admin console)
├── static/                     # CSS and JS (modular, per-view)
├── filters/                    # Whitelist/blacklist keyword files
├── models/                     # NLLB CTranslate2 model (auto-downloaded)
├── data/                       # Feed seed data, runtime state, cache
├── scripts/                    # Setup utilities
│   └── download_nllb.py        # NLLB model download & conversion
├── requirements.txt            # Python dependencies
├── setup_observer.py           # Cross-platform setup script
├── install.ps1                 # Windows PowerShell installer
├── start.bat                   # Windows quick-start script
└── .env.example                # Configuration template
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Web framework | FastAPI + Uvicorn |
| Database | PostgreSQL 14+ via asyncpg |
| Translation | CTranslate2 (NLLB-200) + sentencepiece |
| Language detection | langdetect |
| Web scraping | trafilatura + lxml |
| RSS parsing | feedparser |
| Rate limiting | slowapi |
| Frontend | HTML5/Jinja2, WebSocket, vanilla JS/CSS |

## License

MIT
