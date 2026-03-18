#!/usr/bin/env python3
"""
Sync feed_registry_comprehensive.json → feed_sources table.

Reads every feed from the JSON registry and upserts into the DB.
Uses ON CONFLICT (url, feed_type) DO NOTHING so existing rows are untouched.

Usage:
    python scripts/sync_feed_registry.py          # dry-run (count only)
    python scripts/sync_feed_registry.py --apply   # actually insert
"""

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from config import config


def parse_feeds(registry: dict) -> list[dict]:
    """Extract all feeds from the JSON registry into flat dicts."""
    sources = []
    for group_key, group_data in registry.items():
        if group_key == "_metadata" or not isinstance(group_data, dict):
            continue

        group_label = group_data.get("description", group_key)

        for feed in group_data.get("feeds", []):
            url = feed.get("url", "").strip()
            if not url:
                continue
            parsed = urlparse(url)
            domain = (parsed.hostname or "").lower().removeprefix("www.")
            sources.append({
                "group_key": group_key,
                "group_label": group_label,
                "name": feed.get("name", domain),
                "url": url,
                "domain": domain,
                "feed_type": "rss",
                "language": feed.get("language", "en"),
                "city": feed.get("city", ""),
                "country": feed.get("country", ""),
                "enabled": feed.get("enabled", True),
                "lat": feed.get("lat"),
                "lon": feed.get("lon"),
            })

        for site in group_data.get("scraper_sites", []):
            url = site.get("url", "").strip()
            if not url:
                continue
            parsed = urlparse(url)
            domain = (parsed.hostname or "").lower().removeprefix("www.")
            sources.append({
                "group_key": group_key,
                "group_label": group_label,
                "name": site.get("name", domain),
                "url": url,
                "domain": domain,
                "feed_type": "scraper",
                "language": site.get("language", "en"),
                "city": site.get("city", ""),
                "country": site.get("country", ""),
                "enabled": site.get("enabled", True),
                "lat": site.get("lat"),
                "lon": site.get("lon"),
            })

    return sources


async def sync(apply: bool) -> None:
    json_path = Path(__file__).resolve().parent.parent / "data" / "feed_registry_comprehensive.json"
    with open(json_path) as f:
        registry = json.load(f)

    sources = parse_feeds(registry)
    print(f"Parsed {len(sources)} feeds from {json_path.name}")

    pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=2)

    try:
        # Check current count
        existing = await pool.fetchval("SELECT COUNT(*) FROM feed_sources")
        existing_urls = {
            r["url"]
            for r in await pool.fetch("SELECT url FROM feed_sources")
        }
        missing = [s for s in sources if s["url"] not in existing_urls]
        print(f"DB has {existing} feed_sources rows")
        print(f"Missing from DB: {len(missing)} feeds")

        if not missing:
            print("Nothing to do — all feeds already present.")
            return

        if not apply:
            print("\nMissing feeds:")
            for s in missing:
                print(f"  [{s['group_key']}] {s['name']} — {s['url']}")
            print(f"\nRe-run with --apply to insert these {len(missing)} feeds.")
            return

        inserted = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                for s in missing:
                    result = await conn.execute("""
                        INSERT INTO feed_sources
                            (group_key, group_label, name, url, domain, feed_type,
                             language, city, country, enabled, lat, lon, description)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                        ON CONFLICT (url, feed_type) DO NOTHING
                    """,
                        s["group_key"],
                        s["group_label"],
                        s["name"],
                        s["url"],
                        s["domain"],
                        s["feed_type"],
                        s["language"],
                        s["city"],
                        s["country"],
                        s["enabled"],
                        s["lat"],
                        s["lon"],
                        "",
                    )
                    if result and "INSERT 0 1" in result:
                        inserted += 1

        final = await pool.fetchval("SELECT COUNT(*) FROM feed_sources")
        print(f"Inserted {inserted} new feeds. DB now has {final} feed_sources rows.")
    finally:
        await pool.close()


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    asyncio.run(sync(apply))
