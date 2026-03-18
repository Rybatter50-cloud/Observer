-- Migration 015: Add pgvector extension and embedding columns
-- Stores sentence-transformer embeddings for RAG-enhanced Ollama analysis
-- and article clustering.
--
-- Uses pgvector for native vector operations (cosine similarity, IVFFlat index).
-- Falls back gracefully if pgvector extension is not installed or if the
-- current user lacks superuser privileges to create it.
--
-- 2026-02-23 | Mr Cat + Claude | Vector DB for RAG analysis

-- Attempt to enable pgvector; skip on insufficient privileges
DO $$ BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION WHEN insufficient_privilege THEN
    RAISE WARNING 'pgvector requires superuser — vector features will be unavailable. Ask your DBA to run: CREATE EXTENSION vector;';
END $$;

-- All vector-dependent objects are wrapped in a conditional block
-- so the migration succeeds even without pgvector.
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN

    -- Add embedding column to intel_signals
    -- 384 dimensions = all-MiniLM-L6-v2 output size
    ALTER TABLE intel_signals
        ADD COLUMN IF NOT EXISTS embedding vector(384);

    ALTER TABLE intel_signals
        ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;

    -- Article clusters table: groups semantically related signals
    CREATE TABLE IF NOT EXISTS article_clusters (
        id              SERIAL PRIMARY KEY,
        label           TEXT,
        summary         TEXT,
        summary_updated TIMESTAMPTZ,
        signal_count    INTEGER NOT NULL DEFAULT 0,
        centroid        vector(384),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- Junction table: many-to-many between signals and clusters
    CREATE TABLE IF NOT EXISTS cluster_members (
        cluster_id  INTEGER NOT NULL REFERENCES article_clusters(id) ON DELETE CASCADE,
        signal_id   INTEGER NOT NULL REFERENCES intel_signals(id) ON DELETE CASCADE,
        similarity  REAL NOT NULL DEFAULT 0.0,
        added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (cluster_id, signal_id)
    );

    -- IVFFlat indexes for vector similarity search
    BEGIN
        CREATE INDEX IF NOT EXISTS idx_signals_embedding
            ON intel_signals USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 500);
    EXCEPTION WHEN others THEN
        RAISE WARNING 'IVFFlat index on intel_signals deferred: %', SQLERRM;
    END;

    CREATE INDEX IF NOT EXISTS idx_signals_embedded_at
        ON intel_signals (embedded_at)
        WHERE embedded_at IS NULL;

    CREATE INDEX IF NOT EXISTS idx_cluster_members_signal
        ON cluster_members (signal_id);

    CREATE INDEX IF NOT EXISTS idx_cluster_members_cluster
        ON cluster_members (cluster_id);

    BEGIN
        CREATE INDEX IF NOT EXISTS idx_clusters_centroid
            ON article_clusters USING ivfflat (centroid vector_cosine_ops)
            WITH (lists = 50);
    EXCEPTION WHEN others THEN
        RAISE WARNING 'IVFFlat index on article_clusters deferred: %', SQLERRM;
    END;

    -- Apply updated_at trigger to article_clusters
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_clusters_updated_at'
    ) THEN
        CREATE TRIGGER trg_clusters_updated_at
            BEFORE UPDATE ON article_clusters
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    END IF;

    RAISE NOTICE 'pgvector embedding schema applied successfully';

ELSE
    -- Still add the non-vector column so the schema stays consistent
    ALTER TABLE intel_signals
        ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;

    RAISE WARNING 'pgvector not available — skipping embedding columns and cluster tables';
END IF;
END $$;
