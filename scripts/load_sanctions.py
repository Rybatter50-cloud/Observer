#!/usr/bin/env python3
"""
RYBAT Intelligence Platform - Sanctions Database Loader
========================================================
Download the OpenSanctions CSV and bulk-load into PostgreSQL.

Usage:
    python scripts/load_sanctions.py                  # download + load
    python scripts/load_sanctions.py --skip-download   # load from cached CSV only
    python scripts/load_sanctions.py --status          # show DB stats
    python scripts/load_sanctions.py --prep            # pre-departure field prep

The --prep flag is designed for field deployments: it downloads the latest
OpenSanctions dataset, loads it into PostgreSQL, runs a verification search,
and confirms readiness for offline operation. Run this before departing for
environments with limited or no internet connectivity.

This is the same logic the app runs on startup, but as a standalone script
for initial loads or manual refreshes without restarting the server.

2026-02-12 | Mr Cat + Claude
"""

import os
import sys
import csv
import time
import asyncio
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

CSV_URL = "https://data.opensanctions.org/datasets/latest/default/targets.simple.csv"
HEADERS = {
    'User-Agent': 'RYBAT-Intelligence/1.0 (entity-screening)',
    'Accept': 'text/csv',
}


def get_data_dir() -> Path:
    return Path(os.getenv(
        'OPENSANCTIONS_DATA_DIR',
        str(Path(__file__).parent.parent / 'data')
    ))


def get_csv_path() -> Path:
    return get_data_dir() / 'opensanctions_default.csv'


async def download_csv(csv_path: Path) -> bool:
    """Download the OpenSanctions CSV."""
    import aiohttp

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=300)

    print(f"Downloading from {CSV_URL} ...")
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(CSV_URL, headers=HEADERS) as resp:
            if resp.status != 200:
                print(f"ERROR: HTTP {resp.status}")
                return False

            with open(csv_path, 'wb') as f:
                downloaded = 0
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    mb = downloaded / (1024 * 1024)
                    print(f"\r  Downloaded: {mb:.1f}MB", end='', flush=True)

    size_mb = csv_path.stat().st_size / (1024 * 1024)
    print(f"\n  Saved: {csv_path} ({size_mb:.1f}MB)")
    return True


def parse_csv(csv_path: Path) -> list:
    """Parse the CSV into record dicts."""
    records = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append({
                'id': row.get('id', ''),
                'schema': row.get('schema', ''),
                'name': row.get('name', ''),
                'aliases': row.get('aliases', ''),
                'birth_date': row.get('birth_date', ''),
                'countries': row.get('countries', ''),
                'sanctions': row.get('sanctions', ''),
                'dataset': row.get('dataset', ''),
                'identifiers': row.get('identifiers', ''),
            })
    return records


async def load_to_db(records: list) -> int:
    """Bulk-load records into PostgreSQL via ScreeningRepository."""
    import asyncpg
    from database.connection import Database

    db = Database(config.DATABASE_URL)
    await db.connect()

    try:
        # Check if sanctions tables exist
        exists = await db.screening.table_exists()
        if not exists:
            print("ERROR: sanctions_entities table does not exist.")
            print("Run the migration first (restart the server or apply migration 005).")
            return 0

        print(f"Bulk-loading {len(records)} entities to PostgreSQL...")
        start = time.monotonic()
        count = await db.screening.bulk_load(records)
        elapsed = time.monotonic() - start
        print(f"  Loaded {count} entities in {elapsed:.1f}s")

        name_count = await db.screening.get_name_count()
        print(f"  Name variants indexed: {name_count}")

        return count
    finally:
        await db.close()


async def show_status():
    """Show current DB stats."""
    import asyncpg
    from database.connection import Database

    db = Database(config.DATABASE_URL)
    await db.connect()

    try:
        exists = await db.screening.table_exists()
        if not exists:
            print("sanctions_entities table does not exist (migration 005 not applied)")
            return

        entity_count = await db.screening.get_entity_count()
        name_count = await db.screening.get_name_count()
        last_load = await db.screening.get_last_load_time()

        print(f"Sanctions Database Status:")
        print(f"  Entities:       {entity_count:,}")
        print(f"  Name variants:  {name_count:,}")
        print(f"  Last loaded:    {last_load or 'never'}")

        csv_path = get_csv_path()
        if csv_path.exists():
            size_mb = csv_path.stat().st_size / (1024 * 1024)
            print(f"  CSV on disk:    {csv_path} ({size_mb:.1f}MB)")
        else:
            print(f"  CSV on disk:    (not found)")
    finally:
        await db.close()


async def test_search(name: str):
    """Test a fuzzy search against the loaded DB."""
    import asyncpg
    from database.connection import Database

    db = Database(config.DATABASE_URL)
    await db.connect()

    try:
        print(f"\nSearching for: '{name}'")
        start = time.monotonic()
        results = await db.screening.search_by_name(name, threshold=0.3, limit=10)
        elapsed = (time.monotonic() - start) * 1000

        if not results:
            print(f"  No matches found ({elapsed:.0f}ms)")
        else:
            print(f"  {len(results)} matches ({elapsed:.0f}ms):")
            for r in results:
                countries = r.get('countries', '') or ''
                datasets = r.get('dataset', '') or ''
                print(f"    [{r['score']:5.1f}%] {r['name']} | {countries} | {datasets[:60]}")
    finally:
        await db.close()


async def field_prep():
    """Pre-departure field prep: download latest data, load, verify, report."""
    print("=" * 65)
    print("  RYBAT — OpenSanctions Field Prep")
    print("  Updating sanctions database for offline / field deployment")
    print("=" * 65)
    print()

    csv_path = get_csv_path()

    # Step 1: Download latest
    print("[1/4] Downloading latest OpenSanctions dataset...")
    ok = await download_csv(csv_path)
    if not ok:
        print("\nERROR: Download failed. Check internet connectivity.")
        print("If you have a cached CSV, run with --skip-download instead.")
        sys.exit(1)

    # Step 2: Parse
    print("\n[2/4] Parsing CSV...")
    records = parse_csv(csv_path)
    print(f"  Parsed {len(records):,} entities")

    # Step 3: Load into PostgreSQL
    print(f"\n[3/4] Loading into PostgreSQL...")
    count = await load_to_db(records)
    if count == 0:
        sys.exit(1)

    # Step 4: Verify with a known entity
    print(f"\n[4/4] Verification search...")
    await test_search("Viktor Bout")

    # Summary
    csv_size_mb = csv_path.stat().st_size / (1024 * 1024)
    print()
    print("=" * 65)
    print("  FIELD PREP COMPLETE")
    print(f"  Entities loaded:  {count:,}")
    print(f"  CSV cached at:    {csv_path} ({csv_size_mb:.1f}MB)")
    print(f"  Data timestamp:   {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()
    print("  Sanctions screening will work offline — all data is in")
    print("  PostgreSQL with local pg_trgm matching. No internet needed.")
    print("=" * 65)


async def main():
    parser = argparse.ArgumentParser(
        description='Load OpenSanctions data into PostgreSQL',
        epilog='Field prep:  python scripts/load_sanctions.py --prep'
    )
    parser.add_argument('--skip-download', action='store_true',
                        help='Skip download, load from cached CSV only')
    parser.add_argument('--status', action='store_true',
                        help='Show current DB stats and exit')
    parser.add_argument('--test', type=str, default=None,
                        help='Test search after loading (e.g. --test "Viktor Bout")')
    parser.add_argument('--prep', action='store_true',
                        help='Pre-departure field prep: download, load, verify')
    args = parser.parse_args()

    if args.status:
        await show_status()
        return

    if args.prep:
        await field_prep()
        return

    csv_path = get_csv_path()

    if not args.skip_download:
        ok = await download_csv(csv_path)
        if not ok:
            sys.exit(1)
    else:
        if not csv_path.exists():
            print(f"ERROR: CSV not found at {csv_path}")
            print("Run without --skip-download to fetch it first.")
            sys.exit(1)
        size_mb = csv_path.stat().st_size / (1024 * 1024)
        print(f"Using cached CSV: {csv_path} ({size_mb:.1f}MB)")

    print("Parsing CSV...")
    records = parse_csv(csv_path)
    print(f"  Parsed {len(records)} entities")

    count = await load_to_db(records)
    if count == 0:
        sys.exit(1)

    await show_status()

    if args.test:
        await test_search(args.test)


if __name__ == '__main__':
    asyncio.run(main())
