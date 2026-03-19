# CHANGELOG

All notable changes to the Observer Intelligence Platform are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
