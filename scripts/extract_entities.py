#!/usr/bin/env python3
"""
Observer Lite - Batch Entity Extraction
=======================================
Extracts entities from intel_signals using GLiNER and optionally
auto-screens Person entities against sanctions/watchlists.

Usage:
    python scripts/extract_entities.py                     # Process 500 signals
    python scripts/extract_entities.py --limit 100         # Process 100 signals
    python scripts/extract_entities.py --auto-screen       # Extract + screen persons
    python scripts/extract_entities.py --reprocess         # Re-extract all (reset tier)

2026-03-25 | Mr Cat + Claude
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

import asyncpg
from services.entity_extraction import EntityExtractionService
from utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def get_pool() -> asyncpg.Pool:
    """Create asyncpg connection pool from DATABASE_URL."""
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL not set in .env")
        sys.exit(1)
    return await asyncpg.create_pool(db_url, min_size=1, max_size=3)


async def fetch_unprocessed(pool: asyncpg.Pool, limit: int, reprocess: bool) -> list:
    """Fetch signals needing entity extraction."""
    if reprocess:
        query = """
            SELECT id, title, description
            FROM intel_signals
            ORDER BY created_at DESC
            LIMIT $1
        """
    else:
        query = """
            SELECT id, title, description
            FROM intel_signals
            WHERE entities_tier = 0 OR entities_tier IS NULL
            ORDER BY created_at DESC
            LIMIT $1
        """
    async with pool.acquire() as conn:
        return await conn.fetch(query, limit)


async def update_signal_entities(
    pool: asyncpg.Pool, signal_id: int, entities: list, tier: int = 1
):
    """Write entities_json and entities_tier to signal."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE intel_signals
            SET entities_json = $1::jsonb, entities_tier = $2
            WHERE id = $3
            """,
            json.dumps(entities),
            tier,
            signal_id,
        )


async def update_screening_hits(
    pool: asyncpg.Pool, signal_id: int, screening_data: dict
):
    """Write screening_hits JSONB to signal."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE intel_signals SET screening_hits = $1::jsonb WHERE id = $2",
            json.dumps(screening_data),
            signal_id,
        )


async def screen_person_entities(
    pool: asyncpg.Pool, signal_id: int, entities: list
) -> dict:
    """Screen PERSON entities against sanctions/watchlists."""
    from services.entity_screening import get_screening_service

    service = get_screening_service()

    # Wire DB repo if sanctions enabled
    import config as app_config
    if app_config.Config.SANCTIONS_NET_ENABLED:
        from database.repositories.screening import ScreeningRepository
        repo = ScreeningRepository(pool)
        service.connect_db(repo)

    persons = [
        e for e in entities
        if e['type'] == 'PERSON' and e.get('confidence', 0) >= 0.6
    ]

    if not persons:
        return {}

    all_hits = []
    for person in persons:
        result = await service.screen_entity(person['text'], entity_type='Person')
        if result.has_hits:
            for hit in result.hits:
                all_hits.append({
                    'entity': person['text'],
                    'source': hit.source,
                    'score': hit.score,
                    'category': hit.category,
                    'name': hit.name,
                    'url': hit.url,
                    'details': hit.details,
                })

    if not all_hits:
        return {}

    max_score = max(h['score'] for h in all_hits)
    screening_data = {
        'hit_count': len(all_hits),
        'max_score': max_score,
        'entities_screened': len(persons),
        'hits': all_hits,
    }

    await update_screening_hits(pool, signal_id, screening_data)
    return screening_data


async def main():
    parser = argparse.ArgumentParser(description='Batch entity extraction via GLiNER')
    parser.add_argument('--limit', type=int, default=500,
                        help='Max signals to process (default: 500)')
    parser.add_argument('--batch-size', type=int, default=50,
                        help='Signals per progress update (default: 50)')
    parser.add_argument('--auto-screen', action='store_true',
                        help='Screen PERSON entities against sanctions/watchlists')
    parser.add_argument('--reprocess', action='store_true',
                        help='Re-extract entities for all signals (ignore tier)')
    args = parser.parse_args()

    setup_logging(debug=False)

    print("=" * 60)
    print("Observer Lite - Batch Entity Extraction")
    print("=" * 60)

    # Load GLiNER model
    print("\nLoading GLiNER model...")
    t0 = time.monotonic()
    extractor = EntityExtractionService()
    if not extractor.load_model():
        print("ERROR: Failed to load GLiNER model")
        sys.exit(1)
    print(f"Model loaded in {time.monotonic() - t0:.1f}s")

    # Connect to database
    print("Connecting to database...")
    pool = await get_pool()

    # Fetch signals
    signals = await fetch_unprocessed(pool, args.limit, args.reprocess)
    total = len(signals)
    if total == 0:
        print("\nNo signals to process. All signals already have entities extracted.")
        await pool.close()
        return

    print(f"\nProcessing {total} signals (auto-screen: {'ON' if args.auto_screen else 'OFF'})")
    print("-" * 60)

    # Stats
    total_entities = 0
    total_persons_screened = 0
    total_screening_hits = 0
    errors = 0
    t_start = time.monotonic()

    for i, row in enumerate(signals, 1):
        signal_id = row['id']
        title = row['title'] or ''
        description = row['description'] or ''

        try:
            # Extract entities
            entities = extractor.extract_from_signal(title, description)
            total_entities += len(entities)

            # Save to DB
            await update_signal_entities(pool, signal_id, entities)

            # Auto-screen
            screening_info = ""
            if args.auto_screen and entities:
                persons = [e for e in entities if e['type'] == 'PERSON' and e.get('confidence', 0) >= 0.6]
                if persons:
                    total_persons_screened += len(persons)
                    result = await screen_person_entities(pool, signal_id, entities)
                    if result:
                        hits = result.get('hit_count', 0)
                        total_screening_hits += hits
                        max_s = result.get('max_score', 0)
                        screening_info = f", {len(persons)} screened, {hits} hits (max: {max_s}%)"
                    else:
                        screening_info = f", {len(persons)} screened, 0 hits"

            # Progress
            entity_types = {}
            for e in entities:
                entity_types[e['type']] = entity_types.get(e['type'], 0) + 1
            type_str = " ".join(f"{v}{k[0]}" for k, v in sorted(entity_types.items()))

            if i % 10 == 0 or i == total or i <= 3:
                print(f"  [{i}/{total}] Signal #{signal_id}: {len(entities)} entities ({type_str}){screening_info}")

        except Exception as e:
            errors += 1
            print(f"  [{i}/{total}] Signal #{signal_id}: ERROR - {e}")

    elapsed = time.monotonic() - t_start

    # Summary
    print("\n" + "=" * 60)
    print("EXTRACTION COMPLETE")
    print("=" * 60)
    print(f"  Signals processed:  {total - errors} / {total}")
    print(f"  Total entities:     {total_entities}")
    print(f"  Avg per signal:     {total_entities / max(total - errors, 1):.1f}")
    if args.auto_screen:
        print(f"  Persons screened:   {total_persons_screened}")
        print(f"  Screening hits:     {total_screening_hits}")
    if errors:
        print(f"  Errors:             {errors}")
    print(f"  Time:               {elapsed:.1f}s ({(total - errors) / max(elapsed, 0.1):.1f} signals/sec)")
    print()

    await pool.close()


if __name__ == '__main__':
    asyncio.run(main())
