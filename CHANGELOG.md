# CHANGELOG

All notable changes to the Observer Intelligence Platform are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.2.0] — 2026-03-25

### Added
- **GLiNER entity extraction** (`services/entity_extraction.py`): Named entity recognition using `urchade/gliner_medium-v2.1` model. Extracts Person, Organization, Location, Country, Military Unit, and Weapon entities from article titles and descriptions.
- **Batch extraction script** (`scripts/extract_entities.py`): Standalone script to process signals in bulk. Supports `--limit`, `--batch-size`, `--auto-screen`, and `--reprocess` flags.
- **Entity auto-screening**: Extracted Person entities (confidence ≥ 0.6) are automatically screened against OpenSanctions, FBI, and Interpol databases. Results stored in `screening_hits` JSONB column.
- **Screening hits in article detail modal**: Red alert section showing matched entities with source, score, category, and key details. Exact matches (100%) highlighted with red border.
- **Entity pills in article detail modal**: Extracted entities displayed as color-coded tags with confidence percentages.
- **New entity type CSS**: Added color styles for Country (teal), Military (dark red), and Weapon (orange-red) entity pills.
- **GLiNER model pre-download** in `setup_observer.py`: Downloads model during installation so first extraction doesn't pause.
- `gliner>=0.2.0` added to `requirements.txt`.

### Changed
- `ENTITY_EXTRACTION_ENABLED` and `ENTITY_AUTO_SCREEN` now default to `true` (configurable via `.env`).

---

## [1.1.0] — 2026-03-25

### Added
- **Automated PostgreSQL setup** in `setup_observer.py`: creates database user, database, enables pg_trgm extension, generates secure password, and updates `.env` automatically. Tries `sudo -u postgres` first, falls back to credential prompt.
- **CSV feed seeding**: `feed_sources_seed.csv` (200+ curated feeds, 1 per country + global sources) replaces the old 3,500+ JSON registry. Seeded automatically on first run via `seed_from_csv()`.
- **Migration 021** (`021_add_entities_columns.sql`): adds `entities_json` (JSONB) and `entities_tier` (INTEGER) columns to `intel_signals`.
- `colorama` added to `requirements.txt` (required by `utils/logging.py`).

### Changed
- **Default port** changed from 8000 to 8999 (config, `.env.example`, CORS origins).
- **All feed groups enabled by default** (`SOURCE_STARTUP_ALL` defaults to `true`).
- **Feed sources fully DB-backed**: removed all JSON feed registry references. RSS and NP4K collectors load feeds from PostgreSQL via `load_registry_from_db()`.
- **Starlette 1.0 compatibility**: updated all `TemplateResponse` calls to new signature (`request` as first positional arg).
- **NLLB converter PATH fix**: `download_nllb.py` now checks the venv bin directory for `ct2-transformers-converter` before falling back to system PATH.
- **Migrations 019/020** wrapped in `IF EXISTS` check for `article_clusters` table, so they no longer crash when pgvector is not installed.
- **Client layout fix**: corrected `main-layout` CSS so sidebar and feed list no longer render under the fixed header.
- Removed Docker prerequisite check from setup (not used by Observer).

### Removed
- Old 3,500+ feed JSON registry and all references to `FEED_REGISTRY_PATH`.
- `feed_registry_comprehensive.json` removed from repo and git history.

---

## [Unreleased] — Vector Translation Memory

### Added
- **Vector Translation Service** (`services/vector_translation.py`):
  Multilingual embedding-based "speed translation" that bypasses NLLB for
  headlines whose semantic signature closely matches a previously translated
  article. Falls back to NLLB when the cosine similarity is below the
  configurable confidence threshold.
- **Translation Memory Repository** (`database/repositories/translation_memory.py`):
  pgvector-backed store of `(source_embedding, source_language, english_text)`
  triples. Supports nearest-neighbor lookup for incoming foreign headlines.
- **Migration 016** (`database/migrations/sql/016_add_translation_memory.sql`):
  Creates `translation_memory` table with pgvector embedding column and
  IVFFlat index. Adds `original_title` column to `intel_signals` so the
  pre-translation foreign text is preserved for future re-vectorization.
- **NLLB backfill stub** in `VectorAnalysisService`:
  New Phase 4 in the background loop. When the system detects low
  utilization, vector-estimated translations are re-translated via NLLB
  and the corrected pair is added back to the translation memory cloud,
  creating a virtuous accuracy cycle.
- **Seed script** (`scripts/seed_translation_memory.py`):
  One-time migration helper that re-embeds all existing translated signals
  with the multilingual model and inserts them into the translation memory
  table, bootstrapping the vector cloud from historical data.
- Config keys: `VECTOR_TRANSLATION_ENABLED`, `VECTOR_TRANSLATION_THRESHOLD`,
  `VECTOR_TRANSLATION_MODEL`.

### Changed
- **Embedding model default** updated from `all-MiniLM-L6-v2` to
  `paraphrase-multilingual-MiniLM-L12-v2` (same 384-dim output, same
  architecture, but trained on 50+ languages for cross-lingual alignment).
- **`scripts/train_classifier.py`** now accepts `--re-embed` flag to
  NULL existing embeddings after retraining, triggering a full
  re-vectorization pass by VectorAnalysisService on next cycle.
- **`TranslationService`** checks vector translation memory before
  dispatching to NLLB. Successful vector matches are tagged with
  `translation_source='vector'` in the database.
- **Article pipeline** now preserves the original foreign-language title
  in `intel_signals.original_title` before overwriting with the English
  translation.

### Technical Notes
- `paraphrase-multilingual-MiniLM-L12-v2` is a drop-in replacement:
  same 384 dimensions, same `SentenceTransformer` API, same IVFFlat
  index compatibility. The classifier in `models/classifier.pkl` must
  be retrained after the model swap because the embedding geometry differs.
- The translation memory table uses a dedicated IVFFlat index separate
  from the `intel_signals` embedding index to keep search scopes isolated.
- All existing embeddings and cluster centroids must be regenerated
  after the model swap. The retrain script's `--re-embed` flag handles
  this by NULLing `embedded_at` across the signals table.
