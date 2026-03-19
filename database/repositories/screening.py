"""
Observer Intelligence Platform - Screening Repository

PostgreSQL operations for the sanctions_entities + sanctions_names tables.
Supports bulk loading from OpenSanctions CSV and pg_trgm fuzzy name search.

2026-02-12 | Mr Cat + Claude
"""

import asyncpg
import unicodedata
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_name(name: str) -> str:
    """NFKD decompose, strip accents, lowercase."""
    decomposed = unicodedata.normalize('NFKD', name)
    stripped = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower().strip()


class ScreeningRepository:
    """Read/write operations for sanctions_entities + sanctions_names."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    # ==================================================================
    # BULK LOAD
    # ==================================================================

    async def bulk_load(
        self,
        records: List[Dict[str, Any]],
        batch_size: int = 2000,
    ) -> int:
        """
        Replace all sanctions data with a fresh load.

        Truncates both tables, then bulk-inserts entities and their name
        variants. Returns the number of entities loaded.
        """
        if not records:
            return 0

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Truncate (CASCADE handles sanctions_names FK)
                await conn.execute("TRUNCATE sanctions_names, sanctions_entities CASCADE")

                entity_count = 0
                name_rows = []

                for i in range(0, len(records), batch_size):
                    batch = records[i:i + batch_size]

                    # Bulk insert entities
                    entity_tuples = [
                        (
                            r['id'],
                            r.get('schema', 'Person'),
                            r.get('name', ''),
                            r.get('aliases', ''),
                            r.get('birth_date', ''),
                            r.get('countries', ''),
                            r.get('sanctions', ''),
                            r.get('dataset', ''),
                            r.get('identifiers', ''),
                        )
                        for r in batch
                    ]
                    await conn.executemany(
                        """INSERT INTO sanctions_entities
                           (id, schema_type, name, aliases, birth_date,
                            countries, sanctions, dataset, identifiers)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                           ON CONFLICT (id) DO NOTHING""",
                        entity_tuples,
                    )
                    entity_count += len(batch)

                    # Build name index rows for this batch
                    for r in batch:
                        eid = r['id']
                        primary = r.get('name', '').strip()
                        if primary:
                            name_rows.append((eid, _normalize_name(primary), primary))

                        aliases_str = r.get('aliases', '')
                        if aliases_str:
                            for alias in aliases_str.split(';'):
                                alias = alias.strip()
                                if alias and len(alias) > 1:
                                    name_rows.append((eid, _normalize_name(alias), alias))

                    # Flush name rows periodically to avoid huge memory
                    if len(name_rows) >= batch_size * 3:
                        await conn.executemany(
                            """INSERT INTO sanctions_names
                               (entity_id, name_normalized, name_display)
                               VALUES ($1,$2,$3)""",
                            name_rows,
                        )
                        name_rows = []

                # Final flush
                if name_rows:
                    await conn.executemany(
                        """INSERT INTO sanctions_names
                           (entity_id, name_normalized, name_display)
                           VALUES ($1,$2,$3)""",
                        name_rows,
                    )

                # Record load timestamp
                await conn.execute(
                    """UPDATE metadata SET value = $1, updated_at = NOW()
                       WHERE key = 'sanctions_last_load'""",
                    datetime.now().isoformat(),
                )

            # ANALYZE outside transaction — gives planner accurate stats for GIN index
            await conn.execute("ANALYZE sanctions_names")
            await conn.execute("ANALYZE sanctions_entities")

        logger.info(f"Sanctions bulk load complete: {entity_count} entities")
        return entity_count

    # ==================================================================
    # SEARCH
    # ==================================================================

    async def search_by_name(
        self,
        name: str,
        threshold: float = 0.3,
        schema_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Fuzzy-search sanctions entities by name using pg_trgm similarity().

        Returns entities sorted by best match score (descending), with
        the matched name variant included.
        """
        norm = _normalize_name(name)
        if not norm or len(norm) < 2:
            return []

        # Set the similarity threshold for the GIN index scan
        # This must be done per-connection as it's a session-level GUC
        async with self._pool.acquire() as conn:
            await conn.execute(
                "SELECT set_limit($1)", threshold
            )

            query = """
                SELECT DISTINCT ON (e.id)
                    e.id,
                    e.schema_type,
                    e.name,
                    e.aliases,
                    e.birth_date,
                    e.countries,
                    e.sanctions,
                    e.dataset,
                    e.identifiers,
                    n.name_display AS matched_name,
                    similarity(n.name_normalized, $1) AS sim_score
                FROM sanctions_names n
                JOIN sanctions_entities e ON e.id = n.entity_id
                WHERE n.name_normalized % $1
            """
            params = [norm]
            param_idx = 2

            if schema_type:
                query += f" AND e.schema_type = ${param_idx}"
                params.append(schema_type)
                param_idx += 1

            query += """
                ORDER BY e.id, sim_score DESC
            """

            rows = await conn.fetch(query, *params)

        # Re-sort by score descending across all entities, apply limit
        results = []
        for row in rows:
            results.append({
                'id': row['id'],
                'schema_type': row['schema_type'],
                'name': row['name'],
                'aliases': row['aliases'],
                'birth_date': row['birth_date'],
                'countries': row['countries'],
                'sanctions': row['sanctions'],
                'dataset': row['dataset'],
                'identifiers': row['identifiers'],
                'matched_name': row['matched_name'],
                'score': round(float(row['sim_score']) * 100, 1),
            })

        results.sort(key=lambda r: r['score'], reverse=True)
        return results[:limit]

    # ==================================================================
    # STATUS
    # ==================================================================

    async def get_entity_count(self) -> int:
        """Total entities in the sanctions table."""
        try:
            val = await self._pool.fetchval("SELECT COUNT(*) FROM sanctions_entities")
            return val or 0
        except Exception:
            return 0

    async def get_name_count(self) -> int:
        """Total name variants in the index."""
        try:
            val = await self._pool.fetchval("SELECT COUNT(*) FROM sanctions_names")
            return val or 0
        except Exception:
            return 0

    async def get_last_load_time(self) -> Optional[str]:
        """Timestamp of last bulk load."""
        try:
            val = await self._pool.fetchval(
                "SELECT value FROM metadata WHERE key = 'sanctions_last_load'"
            )
            return val
        except Exception:
            return None

    async def get_csv_last_modified(self) -> Optional[str]:
        """HTTP Last-Modified header from the last CSV download (persisted across restarts)."""
        try:
            val = await self._pool.fetchval(
                "SELECT value FROM metadata WHERE key = 'sanctions_csv_last_modified'"
            )
            return val
        except Exception:
            return None

    async def set_csv_last_modified(self, value: str) -> None:
        """Persist the HTTP Last-Modified header so If-Modified-Since works on cold start."""
        try:
            await self._pool.execute(
                """INSERT INTO metadata (key, value, updated_at)
                   VALUES ('sanctions_csv_last_modified', $1, NOW())
                   ON CONFLICT (key)
                   DO UPDATE SET value = $1, updated_at = NOW()""",
                value,
            )
        except Exception:
            pass

    async def table_exists(self) -> bool:
        """Check if the sanctions tables exist (migration may not have run yet)."""
        try:
            val = await self._pool.fetchval("""
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'sanctions_entities'
            """)
            return val is not None
        except Exception:
            return False

    # ==================================================================
    # SCREENING LOG
    # ==================================================================

    async def log_screening(
        self,
        queried_name: str,
        hit_count: int,
        sources_checked: List[str],
        client_ip: str = 'unknown',
    ) -> None:
        """Record a screening check in the log."""
        try:
            await self._pool.execute(
                """INSERT INTO screening_log
                   (queried_name, hit_count, sources_checked, client_ip)
                   VALUES ($1, $2, $3, $4)""",
                queried_name,
                hit_count,
                ','.join(sources_checked),
                client_ip,
            )
        except Exception as e:
            logger.error(f"Failed to log screening: {e}")

    async def get_recent_screenings(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Return the most recent screening log entries (newest first)."""
        try:
            exists = await self._pool.fetchval("""
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'screening_log'
            """)
            if not exists:
                return []

            rows = await self._pool.fetch(
                """SELECT id, queried_name, hit_count, sources_checked,
                          client_ip, created_at
                   FROM screening_log
                   ORDER BY created_at DESC
                   LIMIT $1""",
                limit,
            )
            return [
                {
                    'id': row['id'],
                    'queried_name': row['queried_name'],
                    'hit_count': row['hit_count'],
                    'sources_checked': row['sources_checked'],
                    'client_ip': row['client_ip'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to get recent screenings: {e}")
            return []

    async def get_screening_log_stats(self) -> Dict[str, Any]:
        """Get screening log statistics: total count and per-IP breakdown."""
        try:
            # Check table exists first
            exists = await self._pool.fetchval("""
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'screening_log'
            """)
            if not exists:
                return {'total': 0, 'by_ip': []}

            total = await self._pool.fetchval(
                "SELECT COUNT(*) FROM screening_log"
            ) or 0

            ip_rows = await self._pool.fetch("""
                SELECT client_ip, COUNT(*) AS checks
                FROM screening_log
                GROUP BY client_ip
                ORDER BY checks DESC
                LIMIT 20
            """)

            return {
                'total': total,
                'by_ip': [
                    {'ip': row['client_ip'], 'checks': row['checks']}
                    for row in ip_rows
                ],
            }
        except Exception as e:
            logger.error(f"Failed to get screening log stats: {e}")
            return {'total': 0, 'by_ip': []}
