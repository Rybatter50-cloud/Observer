"""
Observer Intelligence Platform - Migration Runner

Lightweight migration system using versioned SQL.
Tracks applied migrations in a schema_migrations table.

Usage:
    await MigrationRunner.run(pool)

2026-02-09 | Mr Cat + Claude | New migration system for PostgreSQL rebuild
"""

import asyncpg
from pathlib import Path
from typing import List

from utils.logging import get_logger

logger = get_logger(__name__)

# Directory containing numbered .sql migration files
MIGRATIONS_DIR = Path(__file__).parent / "sql"


class MigrationRunner:
    """
    Runs versioned SQL migrations in order.

    Migrations are .sql files in database/migrations/sql/ named like:
        001_initial_schema.sql
        002_add_some_column.sql

    Each migration runs exactly once. Applied migrations are tracked
    in the schema_migrations table.
    """

    @staticmethod
    async def run(pool: asyncpg.Pool) -> int:
        """
        Run all pending migrations.

        Returns the number of migrations applied.
        """
        async with pool.acquire() as conn:
            # Ensure tracking table exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version  TEXT PRIMARY KEY,
                    applied  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            # Get already-applied versions
            rows = await conn.fetch("SELECT version FROM schema_migrations")
            applied = {r['version'] for r in rows}

            # Discover pending migrations
            pending = MigrationRunner._discover_pending(applied)
            if not pending:
                logger.debug("No pending migrations")
                return 0

            # Apply each in order
            count = 0
            for version, path in pending:
                logger.info(f"Applying migration: {version}")
                sql = path.read_text(encoding="utf-8")

                try:
                    async with conn.transaction():
                        await conn.execute(sql)
                        await conn.execute(
                            "INSERT INTO schema_migrations (version) VALUES ($1)",
                            version,
                        )
                    count += 1
                    logger.info(f"Migration applied: {version}")
                except Exception as e:
                    logger.error(f"Migration {version} failed: {e}")
                    raise RuntimeError(
                        f"Migration '{version}' failed: {e}. "
                        "Fix the issue and restart."
                    ) from e

            return count

    @staticmethod
    def _discover_pending(applied: set) -> List[tuple]:
        """Return sorted list of (version, path) for unapplied migrations."""
        if not MIGRATIONS_DIR.is_dir():
            return []

        pending = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem  # e.g. "001_initial_schema"
            if version not in applied:
                pending.append((version, path))

        return pending
