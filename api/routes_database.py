"""
Observer Intelligence Platform - Database Control Panel API
=========================================================
Endpoints for database management:
  - GET  /api/v1/database/details     — DB size, table stats, signal counts
  - GET  /api/v1/database/config      — Current MAX_SIGNALS_LIMIT
  - POST /api/v1/database/config      — Update MAX_SIGNALS_LIMIT (persists to .env)
  - POST /api/v1/database/backup      — Create a pg_dump backup
  - GET  /api/v1/database/backups     — List available backup files
  - GET  /api/v1/database/backup/download/{filename} — Download a backup
  - POST /api/v1/database/restore     — Restore from a backup file

2026-02-16 | Mr Cat + Claude | Initial implementation
"""

import asyncio
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from api.deps import db
from config import config, Config
from utils.logging import get_logger


def _pretty_bytes(n: int) -> str:
    """Format byte count as human-readable string (matches pg_size_pretty)."""
    for unit in ("bytes", "kB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            if unit == "bytes":
                return f"{n} {unit}"
            return f"{n:.0f} {unit}" if n == int(n) else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

logger = get_logger(__name__)

database_router = APIRouter(prefix="/api/v1/database", tags=["database"])

# Backup directory
BACKUP_DIR = Path(__file__).resolve().parent.parent / 'data' / 'backups'


def _parse_dsn(dsn: str) -> dict:
    """Extract host, port, dbname from a PostgreSQL DSN."""
    # postgresql://user:pass@host:port/dbname
    match = re.match(
        r'postgresql://(?:[^@]+@)?([^:/]+)(?::(\d+))?/(.+?)(?:\?.*)?$',
        dsn,
    )
    if match:
        return {
            'host': match.group(1),
            'port': match.group(2) or '5432',
            'dbname': match.group(3),
        }
    return {'host': 'localhost', 'port': '5432', 'dbname': 'observer'}


@contextmanager
def _pgpass_env(dsn_url: str):
    """Create a temporary .pgpass file and yield an env dict that uses it.

    This avoids passing PGPASSWORD in the subprocess environment, where it
    would be visible via /proc/<pid>/environ to other users on the system.
    The temporary file is created with mode 0600 and removed on exit.
    """
    env = os.environ.copy()
    pw_match = re.search(r'://[^:]+:([^@]+)@', dsn_url)
    if not pw_match:
        yield env
        return

    password = pw_match.group(1)
    parsed = _parse_dsn(dsn_url)
    user_match = re.search(r'://([^:@]+)', dsn_url)
    username = user_match.group(1) if user_match else '*'

    # .pgpass format: hostname:port:database:username:password
    line = f"{parsed['host']}:{parsed['port']}:{parsed['dbname']}:{username}:{password}\n"

    fd = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix='.pgpass_', suffix='.tmp')
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        os.write(fd, line.encode())
        os.close(fd)
        fd = None
        env['PGPASSFILE'] = tmp_path
        yield env
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ==================== DB DETAILS ====================

@database_router.get("/details")
async def get_database_details():
    """Return comprehensive database statistics."""
    try:
        pool = db.pool

        async with pool.acquire(timeout=10) as conn:
            # Database size (single query)
            db_info = await conn.fetchrow("""
                SELECT pg_database_size(current_database()) AS size_bytes,
                       pg_size_pretty(pg_database_size(current_database())) AS size_pretty
            """)
            db_size = db_info['size_pretty']
            db_size_bytes = db_info['size_bytes']

            # Table sizes — use relpages from pg_class catalog metadata
            # instead of pg_total_relation_size() which does expensive
            # filesystem stat() calls and acquires locks on every relation
            table_sizes = await conn.fetch("""
                SELECT
                    t.relname AS table_name,
                    (t.relpages + COALESCE(idx.idx_pages, 0)
                        + COALESCE(toast.relpages, 0)) * 8192::bigint AS total_bytes,
                    t.relpages * 8192::bigint AS data_bytes,
                    COALESCE(s.n_live_tup, 0) AS row_count
                FROM pg_class t
                JOIN pg_stat_user_tables s ON s.relid = t.oid
                LEFT JOIN LATERAL (
                    SELECT COALESCE(SUM(ic.relpages), 0) AS idx_pages
                    FROM pg_index ix
                    JOIN pg_class ic ON ic.oid = ix.indexrelid
                    WHERE ix.indrelid = t.oid
                ) idx ON true
                LEFT JOIN pg_class toast ON toast.oid = t.reltoastrelid
                WHERE t.relkind = 'r'
                ORDER BY total_bytes DESC
            """)

            tables = [
                {
                    "name": r['table_name'],
                    "total_size": _pretty_bytes(r['total_bytes']),
                    "total_bytes": int(r['total_bytes']),
                    "data_size": _pretty_bytes(r['data_bytes']),
                    "row_count": int(r['row_count']),
                }
                for r in table_sizes
            ]

            # Signal stats — single scan instead of 5 separate queries
            signal_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE processed = TRUE) AS processed,
                    COUNT(*) FILTER (WHERE processed = FALSE) AS unprocessed,
                    MIN(created_at) AS oldest,
                    MAX(created_at) AS newest
                FROM intel_signals
            """, timeout=60)
            signal_count = signal_stats['total'] or 0
            processed_count = signal_stats['processed'] or 0
            unprocessed_count = signal_stats['unprocessed'] or 0
            oldest = signal_stats['oldest']
            newest = signal_stats['newest']

        # Connection pool info (outside acquire block)
        pool_size = pool.get_size()
        pool_free = pool.get_idle_size()
        pool_min = pool.get_min_size()
        pool_max = pool.get_max_size()

        return JSONResponse({
            "database": {
                "size_pretty": db_size,
                "size_bytes": int(db_size_bytes) if db_size_bytes else 0,
            },
            "tables": tables,
            "signals": {
                "total": int(signal_count),
                "processed": int(processed_count),
                "unprocessed": int(unprocessed_count),
                "oldest": oldest.isoformat() if oldest else None,
                "newest": newest.isoformat() if newest else None,
            },
            "pool": {
                "current": pool_size,
                "idle": pool_free,
                "min": pool_min,
                "max": pool_max,
            },
        })

    except Exception as e:
        logger.exception(f"Failed to get database details: {type(e).__name__}: {e}")
        return JSONResponse(
            {"error": f"{type(e).__name__}: {e}" if str(e) else type(e).__name__},
            status_code=500,
        )


# ==================== DB CONFIG (MAX_SIGNALS_LIMIT) ====================

class DbConfigRequest(BaseModel):
    max_signals_limit: int = Field(..., ge=1000, le=500000)


@database_router.get("/config")
async def get_db_config():
    """Return current database configuration."""
    return JSONResponse({
        "max_signals_limit": Config.MAX_SIGNALS_LIMIT,
    })


@database_router.post("/config")
async def update_db_config(req: DbConfigRequest):
    """Update MAX_SIGNALS_LIMIT and persist to .env."""
    old_value = Config.MAX_SIGNALS_LIMIT

    # Update in-memory config
    Config.MAX_SIGNALS_LIMIT = req.max_signals_limit

    # Persist to .env
    from api.routes_admin import _update_env_vars
    _update_env_vars({'MAX_SIGNALS_LIMIT': str(req.max_signals_limit)})

    logger.info(
        f"MAX_SIGNALS_LIMIT changed: {old_value:,} -> {req.max_signals_limit:,}"
    )

    return JSONResponse({
        "success": True,
        "max_signals_limit": req.max_signals_limit,
        "previous": old_value,
    })


# ==================== DB BACKUP ====================

@database_router.post("/backup")
async def create_backup():
    """Create a pg_dump backup of the database."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'observer_backup_{timestamp}.sql'
        filepath = BACKUP_DIR / filename

        dsn = _parse_dsn(config.DATABASE_URL)

        cmd = [
            'pg_dump',
            '-h', dsn['host'],
            '-p', dsn['port'],
            '-d', dsn['dbname'],
            '--no-owner',
            '--no-privileges',
            '-f', str(filepath),
        ]

        # Extract user from DSN
        user_match = re.search(r'://([^:@]+)', config.DATABASE_URL)
        if user_match:
            cmd.extend(['-U', user_match.group(1)])

        with _pgpass_env(config.DATABASE_URL) as env:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=300
            )

        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error(f"pg_dump failed: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"Backup failed: {error_msg}",
            )

        file_size = filepath.stat().st_size
        logger.info(f"Database backup created: {filename} ({file_size:,} bytes)")

        return JSONResponse({
            "success": True,
            "filename": filename,
            "size": file_size,
            "size_pretty": _pretty_size(file_size),
            "path": str(filepath),
        })

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Backup timed out (5 min limit)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@database_router.get("/backups")
async def list_backups():
    """List available backup files."""
    if not BACKUP_DIR.exists():
        return JSONResponse({"backups": []})

    backups = []
    for f in sorted(BACKUP_DIR.glob('observer_backup_*.sql'), reverse=True):
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "size": stat.st_size,
            "size_pretty": _pretty_size(stat.st_size),
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    return JSONResponse({"backups": backups})


@database_router.get("/backup/download/{filename}")
async def download_backup(filename: str):
    """Download a backup file."""
    # Sanitize filename to prevent path traversal
    if '/' in filename or '\\' in filename or '..' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = BACKUP_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Backup not found")

    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type='application/sql',
    )


# ==================== DB RESTORE ====================

class RestoreRequest(BaseModel):
    filename: str = Field(..., pattern=r'^observer_backup_\d{8}_\d{6}\.sql$')


@database_router.post("/restore")
async def restore_backup(req: RestoreRequest):
    """Restore database from a backup file."""
    # Sanitize
    if '/' in req.filename or '\\' in req.filename or '..' in req.filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = BACKUP_DIR / req.filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")

    try:
        dsn = _parse_dsn(config.DATABASE_URL)

        # Use psql to restore the SQL dump
        cmd = [
            'psql',
            '-h', dsn['host'],
            '-p', dsn['port'],
            '-d', dsn['dbname'],
            '-f', str(filepath),
            '--quiet',
            '--single-transaction',
        ]

        user_match = re.search(r'://([^:@]+)', config.DATABASE_URL)
        if user_match:
            cmd.extend(['-U', user_match.group(1)])

        with _pgpass_env(config.DATABASE_URL) as env:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=600
            )

        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error(f"Restore failed: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"Restore failed: {error_msg}",
            )

        logger.info(f"Database restored from: {req.filename}")

        return JSONResponse({
            "success": True,
            "filename": req.filename,
            "message": "Database restored successfully",
        })

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Restore timed out (10 min limit)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== HELPERS ====================

def _pretty_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size."""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
