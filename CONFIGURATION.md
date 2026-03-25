# Configuration

All configuration is via environment variables loaded from `.env` by python-dotenv. See `.env.example` for a template.

## Required

| Variable | Type | Purpose |
|----------|------|---------|
| `DATABASE_URL` | str | PostgreSQL connection string. App exits on startup if not set. |

## Conditionally Required

These are required only when their feature flag is enabled. `config.validate()` checks each at startup.

| Variable | Required when | Purpose |
|----------|--------------|---------|
| `DATABASE_URL` | Always | PostgreSQL connection string |

Additionally, `AI_TRANSLATOR_MODE` must be one of `nllb`, `local`, or `off`, and `CONTENT_FILTER_MODE` must be one of `whitelist`, `blacklist`, or `both`.

---

## Database

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `DATABASE_URL` | str | `''` | PostgreSQL connection string |
| `MAX_SIGNALS_LIMIT` | int | `75000` | Maximum signals retained in database |
| `DB_POOL_MIN_SIZE` | int | `3` | Minimum asyncpg pool connections |
| `DB_POOL_MAX_SIZE` | int | `10` | Maximum asyncpg pool connections |

## Server

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `HOST` | str | `0.0.0.0` | Bind address |
| `PORT` | int | `8999` | Bind port |
| `DEBUG` | bool | `false` | Debug logging and uvicorn log level |
| `ALLOWED_ORIGINS` | str | `http://localhost:8999` | Comma-separated CORS origins |

## Feature Flags

| Variable | Type | Default | Controls |
|----------|------|---------|----------|
| `FEED_COLLECTION_ENABLED` | bool | `true` | Article pipeline (RSS + scrapers) |
| `SCRAPER_COLLECTION_ENABLED` | bool | `true` | Newspaper4k web scraper collector |
| `NEWSAPI_ENABLED` | bool | `false` | NewsAPI breaking news collector |
| `GEMINI_ENABLED` | bool | `true` | Gemini feed discovery |
| `EMBEDDINGS_ENABLED` | bool | `true` | Sentence-transformers dedup + classification |
| `VIRUSTOTAL_ENABLED` | bool | `false` | VirusTotal feed URL scanning |
| `URLSCAN_ENABLED` | bool | `false` | urlscan.io feed URL scanning |
| `WIKI_EVENTS_ENABLED` | bool | `true` | Wikipedia current events refresh |
| `INTERPOL_ENABLED` | bool | `false` | Interpol Red Notice screening |
| `FBI_ENABLED` | bool | `true` | FBI Most Wanted screening |
| `SANCTIONS_NET_ENABLED` | bool | `true` | OpenSanctions network screening |

## API Keys

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `GEMINI_API_KEY` | str | `None` | Google Gemini (feed discovery, chat) |
| `NEWSAPI_KEY` | str | `None` | NewsAPI.org |
| `VIRUSTOTAL_API_KEY` | str | `None` | VirusTotal URL scanning |
| `URLSCAN_API_KEY` | str | `None` | urlscan.io URL scanning |

## Translation

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `AI_TRANSLATOR_MODE` | str | `nllb` | Translation backend: `nllb`, `local` (Ollama), or `off` |

Derived booleans (not set directly):
- `TRANSLATION_ENABLED` — true when mode is not `off`
- `TRANSLATION_USE_NLLB` — true when mode is `nllb`
- `TRANSLATION_USE_LOCAL` — true when mode is `local`

### NLLB-200 (CTranslate2)

Requires a one-time model conversion (see README Quick Start). The converted model
must exist at `NLLB_MODEL` before NLLB translation will work. Without it the service
falls back to Ollama or disables translation.

```bash
pip install transformers torch huggingface_hub   # temporary, for conversion only
python scripts/download_nllb.py                  # downloads + converts (~1.2 GB)
pip uninstall transformers torch -y              # safe to remove after
```

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `NLLB_MODEL` | str | `models/nllb-200-distilled-600M-ct2` | CTranslate2 model directory |
| `NLLB_SP_MODEL` | str | `models/nllb-200-distilled-600M-ct2/sentencepiece.bpe.model` | SentencePiece tokenizer path |
| `NLLB_MAX_LENGTH` | int | `512` | Maximum output token length |
| `NLLB_MAX_INPUT_LENGTH` | int | `0` | Maximum input length (0 = use NLLB_MAX_LENGTH) |
| `NLLB_BATCH_SIZE` | int | `16` | Batch size for translation |
| `NLLB_DEVICE` | str | `auto` | Device: `cpu`, `cuda`, or `auto` |
| `NLLB_COMPUTE_TYPE` | str | `auto` | Compute type: `int8`, `float16`, `float32`, or `auto` |
| `NLLB_INTER_THREADS` | int | `1` | Parallel translation workers |
| `NLLB_INTRA_THREADS` | int | `4` | CPU cores per worker |

### NLLB Tuning

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `NLLB_BEAM_SIZE` | int | `1` | Beam search width |
| `NLLB_LENGTH_PENALTY` | float | `1.0` | Length penalty for beam search |
| `NLLB_REPETITION_PENALTY` | float | `1.0` | Repetition penalty |
| `NLLB_NO_REPEAT_NGRAM` | int | `0` | N-gram no-repeat size |
| `NLLB_BATCH_TYPE` | str | `examples` | Batch type: `examples` or `tokens` |
| `NLLB_SAMPLING_TOPK` | int | `1` | Top-k sampling |
| `NLLB_SAMPLING_TOPP` | float | `1.0` | Top-p (nucleus) sampling |
| `NLLB_SAMPLING_TEMPERATURE` | float | `1.0` | Sampling temperature |

## Ollama

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `OLLAMA_MODEL` | str | `llama3.2:3b` | Active Ollama model for chat/fallback translation |
| `OLLAMA_TIMEOUT` | int | `300` | Request timeout in seconds |

Additional Ollama parameters are configurable at runtime via the admin API (`POST /api/v1/admin/ollama/config`) and persisted to `.env` with `OLLAMA_*` prefix. These include `TEMPERATURE`, `TOP_P`, `TOP_K`, `NUM_CTX`, `NUM_PREDICT`, `REPEAT_PENALTY`, `REPEAT_LAST_N`, `SEED`, `STOP`, `TFS_Z`, `MIROSTAT`, `MIROSTAT_TAU`, `MIROSTAT_ETA`, `NUM_THREAD`, `NUM_GPU`.

## Gemini

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `GEMINI_MODEL` | str | `gemini-2.5-flash` | Gemini model for feed discovery |

## Feed Collection

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `FEED_CHECK_INTERVAL` | int | `300` | Seconds between collection cycles |
| `COLLECTOR_TIMEOUT` | int | `1200` | Max seconds per collector run |
| `FEED_MAX_ARTICLES_PER_SOURCE` | int | `5` | Max articles per feed per cycle |
| `FEED_CONCURRENCY` | int | `10` | Concurrent feed fetches |

### Source State

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `SOURCE_STARTUP_ALL` | bool | `true` | Enable all feed groups at startup |
| `SOURCE_STATE_RESTORE` | bool | `true` | Restore group state from JSON on startup |

## Content Filtering

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `CONTENT_FILTER_ENABLED` | bool | `true` | Enable content filtering |
| `CONTENT_FILTER_MODE` | str | `both` | Mode: `whitelist`, `blacklist`, or `both` |
| `CONTENT_FILTER_BL` | str | `BL_default` | Active blacklist filename (without extension) |
| `CONTENT_FILTER_WL` | str | `WL_geopolitical` | Active whitelist filename (without extension) |
| `CONTENT_FILTER_LOG_REJECTED` | bool | `false` | Log rejected articles |

## Scraper (Trafilatura)

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `SCRAPER_REQUEST_TIMEOUT` | int | `30` | HTTP timeout in seconds |
| `SCRAPER_MIN_WORD_COUNT` | int | `100` | Minimum article word count |
| `SCRAPER_MAX_ARTICLES_PER_SITE` | int | `20` | Max articles per scraper site |
| `SCRAPER_DEFAULT_LANGUAGE` | str | `en` | Default language hint (ISO 639-1) |
| `SCRAPER_DELAY_BETWEEN_ARTICLES` | float | `2.0` | Rate limiting delay in seconds |
| `SCRAPER_MAX_REQUESTS_PER_HOUR` | int | `100` | Hourly rate limit |
| `SCRAPER_FAST_MODE` | bool | `true` | Trafilatura fast extraction |
| `SCRAPER_FAVOR_PRECISION` | bool | `false` | Favor precision over recall |
| `SCRAPER_FAVOR_RECALL` | bool | `false` | Favor recall over precision |
| `SCRAPER_INCLUDE_TABLES` | bool | `false` | Include HTML tables |
| `SCRAPER_INCLUDE_LINKS` | bool | `false` | Include hyperlinks |
| `SCRAPER_INCLUDE_IMAGES` | bool | `false` | Include image references |
| `SCRAPER_INCLUDE_COMMENTS` | bool | `false` | Include page comments |
| `SCRAPER_DEDUPLICATE` | bool | `true` | Deduplicate extracted content |
| `SCRAPER_URL_BLACKLIST` | str | `''` | Comma-separated URL patterns to skip |

## Embeddings

Requires `sentence-transformers`, `scikit-learn`, and `joblib` (all in `requirements.txt`).
The multilingual model (`paraphrase-multilingual-MiniLM-L12-v2`) is required for vector-based translation.

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `EMBEDDINGS_ENABLED` | bool | `true` | Enable sentence-transformers |
| `EMBEDDINGS_MODEL` | str | `paraphrase-multilingual-MiniLM-L12-v2` | Sentence-transformer model name |
| `EMBEDDINGS_CLASSIFIER_PATH` | str | `models/classifier.pkl` | Trained classifier pickle path |
| `EMBEDDINGS_DEDUP_THRESHOLD` | float | `0.88` | Cosine similarity threshold for dedup |
| `EMBEDDINGS_SKIP_API_BELOW` | int | `0` | Skip API scoring below this confidence |

## VirusTotal

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `VIRUSTOTAL_DAILY_LIMIT` | int | `450` | Daily API request budget (free tier: 500) |
| `VIRUSTOTAL_AUTO_DISABLE_THRESHOLD` | int | `3` | Detections to auto-disable a feed |
| `VIRUSTOTAL_WARNING_THRESHOLD` | int | `1` | Detections to flag for review |

## urlscan.io

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `URLSCAN_DAILY_LIMIT` | int | `800` | Daily API request budget |
| `URLSCAN_WARNING_THRESHOLD` | int | `50` | Risk score to flag for review |
| `URLSCAN_AUTO_DISABLE_THRESHOLD` | int | `75` | Risk score to auto-disable a feed |

## Startup Validation

`config.validate()` checks the following at startup and raises `ConfigurationError` (causing `sys.exit(1)`) on failure:

1. `AI_TRANSLATOR_MODE` must be `nllb`, `local`, or `off`
2. `DATABASE_URL` must be set
3. If `FEED_COLLECTION_ENABLED`: `CONTENT_FILTER_MODE` must be valid
4. If `NEWSAPI_ENABLED`: `NEWSAPI_KEY` must be set
5. If `VIRUSTOTAL_ENABLED`: `VIRUSTOTAL_API_KEY` must be set
6. If `URLSCAN_ENABLED`: `URLSCAN_API_KEY` must be set
