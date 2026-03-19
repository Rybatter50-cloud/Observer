# Observer v1.0.0

Field-portable intelligence aggregation system. Collects articles from RSS feeds across global news sources, translates non-English content via NLLB-200, screens entities against sanctions databases, and delivers signals through a real-time WebSocket dashboard.

No LLMs, no cloud APIs, no GPU required.

## Features

- **RSS Collection**: 170+ curated feeds across global news sources with configurable check intervals
- **NLLB Translation**: Translates non-English articles to English using NLLB-200 via CTranslate2 (CPU-friendly, int8 quantization)
- **Content Filtering**: Whitelist/blacklist keyword filtering with regex support (13 filter lists included)
- **Entity Screening**: Matches against OpenSanctions database locally via pg_trgm fuzzy matching. Optional FBI/Interpol API lookups
- **Field Extraction**: Regex-based location and casualty extraction from headlines
- **On-Demand Scraping**: Full-text article fetch via trafilatura with paywall detection
- **Real-Time Dashboard**: WebSocket-powered feed with time filtering, full-text search, CSV/JSON export, keyboard shortcuts
- **Feed Management**: Add/remove/disable feeds from the built-in feed registry UI

## Requirements

- Python 3.11+
- PostgreSQL 14+ with `pg_trgm` extension
- ~2 GB disk for NLLB translation model
- ~4 GB RAM minimum

## Quick Start

```bash
# Clone and enter
git clone git@github.com:Rybatter50-cloud/Observer.git && cd Observer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — set DATABASE_URL with your PostgreSQL password

# Start
python main.py
```

Dashboard at `http://localhost:8000`.

### Windows Quick Start

```powershell
# Run the installer (creates venv, installs deps, sets up .env)
.\install.ps1

# Start the server
.\start.bat
```

### NLLB Translation Model (one-time setup)

Translation requires the NLLB-200 model in CTranslate2 format (~1.2 GB). Place the converted model in `models/nllb-200-distilled-600M-ct2/`.

To run on CPU with int8 quantization (recommended):
```
NLLB_DEVICE=cpu
NLLB_COMPUTE_TYPE=int8
```

Without the model, the app still runs but translation is disabled.

## Configuration

Only `DATABASE_URL` is required. Everything else has working defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL connection string (required) |
| `AI_TRANSLATOR_MODE` | `nllb` | Translation mode: `nllb` or `off` |
| `FEED_COLLECTION_ENABLED` | `true` | Enable RSS feed collection |
| `FEED_CHECK_INTERVAL` | `300` | Seconds between collection cycles |
| `CONTENT_FILTER_ENABLED` | `true` | Enable content filtering |
| `SANCTIONS_NET_ENABLED` | `true` | Enable OpenSanctions screening |
| `FBI_ENABLED` | `false` | Enable FBI Most Wanted API |
| `INTERPOL_ENABLED` | `false` | Enable Interpol Notices API |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |

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
├── templates/                  # Jinja2 HTML (client dashboard)
├── static/                     # CSS and JS (modular, per-view)
├── filters/                    # Whitelist/blacklist keyword files
├── models/                     # NLLB CTranslate2 model
├── data/                       # Runtime state (feed_state.json, cache)
├── requirements.txt            # Python dependencies
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
