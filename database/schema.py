"""
Observer Lite v1.0.0 - Database Schema (PostgreSQL)
Stripped-down schema for portable/field deployment.

Tables: intel_signals, feed_sources, sanctions, reputation, utility.
No vector/embedding tables, no UCDP/GNS reference data, no scanning tables.
"""

import asyncpg

from utils.logging import get_logger

logger = get_logger(__name__)


class DatabaseSchema:
    """PostgreSQL-native schema management for Observer Lite"""

    EXTENSIONS = [
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    ]

    ENUMS = {
        "analysis_mode": """
            DO $$ BEGIN
                CREATE TYPE analysis_mode AS ENUM (
                    'PENDING', 'LOCAL', 'FALLBACK', 'SKIPPED', 'MANUAL'
                );
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$
        """,
    }

    TABLES = {
        "intel_signals": """
            CREATE TABLE IF NOT EXISTS intel_signals (
                id              SERIAL PRIMARY KEY,
                title           TEXT NOT NULL,
                description     TEXT,
                full_text       TEXT,
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
                original_title     TEXT
            )
        """,

        "source_reputation": """
            CREATE TABLE IF NOT EXISTS source_reputation (
                source_name       TEXT PRIMARY KEY,
                reliability_score REAL NOT NULL DEFAULT 50.0,
                sample_count      INTEGER NOT NULL DEFAULT 0,
                last_updated      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """,

        "author_reputation": """
            CREATE TABLE IF NOT EXISTS author_reputation (
                author_name       TEXT PRIMARY KEY,
                credibility_score REAL NOT NULL DEFAULT 50.0,
                sample_count      INTEGER NOT NULL DEFAULT 0,
                last_updated      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """,

        "metadata": """
            CREATE TABLE IF NOT EXISTS metadata (
                key        TEXT PRIMARY KEY,
                value      TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """,

        "sanctions_entities": """
            CREATE TABLE IF NOT EXISTS sanctions_entities (
                id              TEXT PRIMARY KEY,
                schema_type     TEXT NOT NULL DEFAULT 'Person',
                name            TEXT NOT NULL,
                aliases         TEXT,
                birth_date      TEXT,
                countries       TEXT,
                sanctions       TEXT,
                dataset         TEXT,
                identifiers     TEXT,
                source          TEXT NOT NULL DEFAULT 'opensanctions',
                loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """,

        "sanctions_names": """
            CREATE TABLE IF NOT EXISTS sanctions_names (
                id              SERIAL PRIMARY KEY,
                entity_id       TEXT NOT NULL REFERENCES sanctions_entities(id) ON DELETE CASCADE,
                name_normalized TEXT NOT NULL,
                name_display    TEXT NOT NULL
            )
        """,

        "cache_store": """
            CREATE TABLE IF NOT EXISTS cache_store (
                key         TEXT PRIMARY KEY,
                value       JSONB NOT NULL DEFAULT '{}',
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """,

        "source_fetch_flags": """
            CREATE TABLE IF NOT EXISTS source_fetch_flags (
                domain              TEXT PRIMARY KEY,
                has_subscriber_wall BOOLEAN NOT NULL DEFAULT FALSE,
                has_paywall         BOOLEAN NOT NULL DEFAULT FALSE,
                source_name         TEXT,
                detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """,

        "feed_sources": """
            CREATE TABLE IF NOT EXISTS feed_sources (
                id              SERIAL PRIMARY KEY,
                group_key       TEXT NOT NULL,
                group_label     TEXT,
                name            TEXT NOT NULL,
                url             TEXT NOT NULL,
                domain          TEXT NOT NULL,
                feed_type       TEXT NOT NULL DEFAULT 'rss',
                language        TEXT DEFAULT 'en',
                city            TEXT,
                country         TEXT,
                enabled         BOOLEAN NOT NULL DEFAULT TRUE,
                lat             REAL,
                lon             REAL,
                description     TEXT,
                discovered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_probed     TIMESTAMPTZ,
                probe_status    TEXT DEFAULT 'active',
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(url, feed_type)
            )
        """,
    }

    INDEXES = [
        # intel_signals
        "CREATE INDEX IF NOT EXISTS idx_signals_processed_created ON intel_signals (processed, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_signals_created           ON intel_signals (created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_signals_relevance_score   ON intel_signals (relevance_score DESC)",
        "CREATE INDEX IF NOT EXISTS idx_signals_source            ON intel_signals (source)",
        "CREATE INDEX IF NOT EXISTS idx_signals_risk_indicators    ON intel_signals USING GIN (risk_indicators)",
        "CREATE INDEX IF NOT EXISTS idx_signals_url               ON intel_signals (url)",
        "CREATE INDEX IF NOT EXISTS idx_signals_analysis_mode     ON intel_signals (analysis_mode)",

        # sanctions
        "CREATE INDEX IF NOT EXISTS idx_sanctions_names_trgm      ON sanctions_names USING GIN (name_normalized gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_sanctions_names_entity     ON sanctions_names (entity_id)",
        "CREATE INDEX IF NOT EXISTS idx_sanctions_entities_schema  ON sanctions_entities (schema_type)",
        "CREATE INDEX IF NOT EXISTS idx_sanctions_entities_source ON sanctions_entities (source)",

        # source_fetch_flags
        "CREATE INDEX IF NOT EXISTS idx_source_fetch_flags_type ON source_fetch_flags (has_subscriber_wall, has_paywall)",

        # feed_sources
        "CREATE INDEX IF NOT EXISTS idx_feed_sources_group      ON feed_sources (group_key)",
        "CREATE INDEX IF NOT EXISTS idx_feed_sources_type       ON feed_sources (feed_type)",
        "CREATE INDEX IF NOT EXISTS idx_feed_sources_enabled    ON feed_sources (enabled)",
        "CREATE INDEX IF NOT EXISTS idx_feed_sources_domain     ON feed_sources (domain)",
        "CREATE INDEX IF NOT EXISTS idx_feed_sources_language   ON feed_sources (language)",
        "CREATE INDEX IF NOT EXISTS idx_feed_sources_group_type ON feed_sources (group_key, feed_type)",
    ]

    VECTOR_INDEXES = []  # No pgvector in Lite

    TSVECTOR_INDEXES = [
        "CREATE INDEX IF NOT EXISTS idx_signals_title_tsvector    ON intel_signals USING GIN (title_tsvector)",
        "CREATE INDEX IF NOT EXISTS idx_signals_title_trgm        ON intel_signals USING GIN (title gin_trgm_ops)",
    ]

    TRIGGERS = [
        # Auto-update updated_at on row modification
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """,
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_signals_updated_at'
            ) THEN
                CREATE TRIGGER trg_signals_updated_at
                    BEFORE UPDATE ON intel_signals
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column();
            END IF;
        END $$
        """,

        # Auto-populate title_tsvector on insert/update
        """
        CREATE OR REPLACE FUNCTION update_title_tsvector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.title_tsvector = to_tsvector('english', COALESCE(NEW.title, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """,
        """
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'intel_signals' AND column_name = 'title_tsvector'
            ) AND NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_signals_title_tsvector'
            ) THEN
                CREATE TRIGGER trg_signals_title_tsvector
                    BEFORE INSERT OR UPDATE OF title ON intel_signals
                    FOR EACH ROW
                    EXECUTE FUNCTION update_title_tsvector();
            END IF;
        END $$
        """,

        # Auto-update updated_at for feed_sources
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_feed_sources_updated_at'
            ) THEN
                CREATE TRIGGER trg_feed_sources_updated_at
                    BEFORE UPDATE ON feed_sources
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column();
            END IF;
        END $$
        """,
    ]

    @staticmethod
    async def initialize_tables(pool: asyncpg.Pool) -> None:
        """Phase 1: Create extensions, enum types, and tables."""
        logger.info("Initializing PostgreSQL schema (tables)...")

        async with pool.acquire() as conn:
            for ext_sql in DatabaseSchema.EXTENSIONS:
                try:
                    await conn.execute(ext_sql)
                except asyncpg.InsufficientPrivilegeError:
                    ext_name = ext_sql.split()[-1].strip('"')
                    logger.warning(
                        f"Cannot create extension '{ext_name}' — "
                        f"requires superuser. Ask your DBA to run: {ext_sql};"
                    )

            for name, sql in DatabaseSchema.ENUMS.items():
                logger.debug(f"Creating enum: {name}")
                await conn.execute(sql)

            for name, sql in DatabaseSchema.TABLES.items():
                logger.debug(f"Creating table: {name}")
                await conn.execute(sql)

        logger.info("Tables ready")

    @staticmethod
    async def initialize_indexes(pool: asyncpg.Pool) -> None:
        """Phase 2: Create triggers, backfill tsvector, and build indexes."""
        logger.info("Applying triggers and indexes...")

        async with pool.acquire() as conn:
            for sql in DatabaseSchema.TRIGGERS:
                await conn.execute(sql)

            has_tsvector = await conn.fetchval("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'intel_signals' AND column_name = 'title_tsvector'
            """)
            if has_tsvector:
                await conn.execute("""
                    UPDATE intel_signals
                    SET title_tsvector = to_tsvector('english', COALESCE(title, ''))
                    WHERE title_tsvector IS NULL
                """)

            for sql in DatabaseSchema.INDEXES:
                await conn.execute(sql)

            if has_tsvector:
                for sql in DatabaseSchema.TSVECTOR_INDEXES:
                    await conn.execute(sql)

        logger.info("Triggers and indexes applied")

    @staticmethod
    async def initialize_database(pool: asyncpg.Pool) -> None:
        """Full init for fresh databases."""
        await DatabaseSchema.initialize_tables(pool)
        await DatabaseSchema.initialize_indexes(pool)
