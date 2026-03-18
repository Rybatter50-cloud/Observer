#!/usr/bin/env python3
"""
RYBAT Intelligence Platform - Paywall / Subscriber Wall Scanner
================================================================
Scan all feed registry URLs for Schema.org isAccessibleForFree metadata.
Flags domains with subscriber walls or paywalls in the source_fetch_flags table.

Usage:
    python scripts/scan_paywalls.py              # scan all feeds
    python scripts/scan_paywalls.py --status     # show current flags
    python scripts/scan_paywalls.py --clear      # clear all flags and re-scan
    python scripts/scan_paywalls.py --dry-run    # scan but don't write to DB

This check is purely local (download HTML, parse metadata) — no API keys
or rate limits. Paces requests at ~1/sec to be polite to feed servers.

2026-02-21 | Mr Cat + Claude | Standalone paywall detection scanner
"""

import os
import sys
import json
import re
import asyncio
import argparse
import time
from pathlib import Path
from urllib.parse import urlparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

# Pace between HTTP requests (seconds) — be polite to feed servers
REQUEST_PACE = 1.0
# HTTP timeout per request
REQUEST_TIMEOUT = 15


def load_feed_urls() -> list:
    """Load all feed URLs from the registry JSON."""
    registry_path = Path(config.FEED_REGISTRY_PATH)
    if not registry_path.exists():
        print(f"ERROR: Feed registry not found: {registry_path}")
        sys.exit(1)

    with open(registry_path, 'r', encoding='utf-8') as f:
        registry = json.load(f)

    feeds = []
    for group_name, group_data in registry.items():
        if group_name.startswith('_'):
            continue
        for feed in group_data.get('feeds', []):
            url = feed.get('url')
            if url:
                feeds.append({
                    'url': url,
                    'name': feed.get('name', 'Unknown'),
                    'group': group_name,
                })
    return feeds


def detect_paywall_schema(html: str) -> str | None:
    """
    Check HTML for Schema.org paywall / subscriber-wall indicators.

    Returns 'subscriber_wall' if isAccessibleForFree is False,
    'paywall' if explicit paywall meta tag found, or None.
    """
    html_lower = html.lower()

    # Check JSON-LD script blocks for isAccessibleForFree
    try:
        for match in re.finditer(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE,
        ):
            try:
                ld = json.loads(match.group(1))
                items = ld if isinstance(ld, list) else [ld]
                for item in items:
                    if isinstance(item, dict):
                        accessible = item.get('isAccessibleForFree')
                        if accessible is not None:
                            if str(accessible).lower() in ('false', '0', 'no'):
                                return 'subscriber_wall'
                        for node in item.get('@graph', []):
                            if isinstance(node, dict):
                                accessible = node.get('isAccessibleForFree')
                                if accessible is not None:
                                    if str(accessible).lower() in ('false', '0', 'no'):
                                        return 'subscriber_wall'
            except (json.JSONDecodeError, TypeError):
                continue
    except Exception:
        pass

    # Check meta tags
    if re.search(
        r'<meta[^>]*name=["\']accessible.for.free["\'][^>]*content=["\']false["\']',
        html_lower,
    ):
        return 'subscriber_wall'

    if re.search(
        r'<meta[^>]*name=["\']paywall["\'][^>]*content=["\']true["\']',
        html_lower,
    ):
        return 'paywall'

    return None


async def fetch_html(url: str) -> str | None:
    """Download HTML from a URL using aiohttp."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                headers={'User-Agent': 'RYBAT-Intelligence/1.0 (paywall-check)'},
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    return None
                # Only read HTML content
                ct = resp.headers.get('Content-Type', '')
                if 'xml' in ct or 'rss' in ct or 'atom' in ct:
                    # This is the RSS feed itself, not an article page.
                    # We need the site's homepage to check for paywall metadata.
                    return None
                return await resp.text(errors='replace')
    except Exception:
        return None


def get_site_url(feed_url: str) -> str:
    """Extract the site homepage URL from a feed URL."""
    parsed = urlparse(feed_url)
    return f"{parsed.scheme}://{parsed.netloc}/"


async def scan_all_feeds(dry_run: bool = False):
    """Scan all feed registry URLs for paywall metadata."""
    import asyncpg
    from database.connection import Database

    feeds = load_feed_urls()
    print(f"\nLoaded {len(feeds)} feeds from registry")

    # Deduplicate by domain — only need to check each domain once
    domain_feeds = {}
    for feed in feeds:
        domain = urlparse(feed['url']).netloc.lower()
        if domain and domain not in domain_feeds:
            domain_feeds[domain] = feed

    print(f"Unique domains to check: {len(domain_feeds)}")

    # Connect to DB (unless dry-run)
    db = None
    if not dry_run:
        db = Database(config.DATABASE_URL)
        await db.connect()
        # Run migration if table doesn't exist
        try:
            await db.pool.execute(
                "SELECT 1 FROM source_fetch_flags LIMIT 1"
            )
        except asyncpg.UndefinedTableError:
            print("Creating source_fetch_flags table...")
            await db.pool.execute("""
                CREATE TABLE IF NOT EXISTS source_fetch_flags (
                    domain              TEXT PRIMARY KEY,
                    has_subscriber_wall BOOLEAN NOT NULL DEFAULT FALSE,
                    has_paywall         BOOLEAN NOT NULL DEFAULT FALSE,
                    source_name         TEXT,
                    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

    flagged = []
    errors = 0
    skipped_rss = 0
    checked = 0
    total = len(domain_feeds)

    print(f"\nScanning {total} domains for paywall metadata...\n")
    start_time = time.time()

    for i, (domain, feed) in enumerate(domain_feeds.items(), 1):
        site_url = get_site_url(feed['url'])
        progress = f"[{i}/{total}]"

        html = await fetch_html(site_url)

        if html is None:
            # Try the feed URL directly (some sites serve HTML at feed URLs)
            html = await fetch_html(feed['url'])

        if html is None:
            print(f"  {progress} SKIP  {domain} (could not fetch)")
            errors += 1
            await asyncio.sleep(REQUEST_PACE)
            continue

        if len(html) < 200:
            print(f"  {progress} SKIP  {domain} (response too short)")
            errors += 1
            await asyncio.sleep(REQUEST_PACE)
            continue

        result = detect_paywall_schema(html)
        checked += 1

        if result:
            flag_label = 'SUBSCRIBER WALL' if result == 'subscriber_wall' else 'PAYWALL'
            print(f"  {progress} FLAG  {domain} -> {flag_label}  ({feed['name']})")
            flagged.append({
                'domain': domain,
                'type': result,
                'name': feed['name'],
                'group': feed['group'],
            })

            if db and not dry_run:
                from database.repositories.source_flags import SourceFlagsRepository
                repo = SourceFlagsRepository(db.pool)
                await repo.flag_domain(domain, result, feed['name'])
        else:
            print(f"  {progress} OK    {domain}  ({feed['name']})")

        await asyncio.sleep(REQUEST_PACE)

    elapsed = time.time() - start_time

    # Summary
    print(f"\n{'=' * 60}")
    print(f"SCAN COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Domains checked:  {checked}")
    print(f"  Fetch errors:     {errors}")
    print(f"  Flagged:          {len(flagged)}")
    print(f"  Clean:            {checked - len(flagged)}")
    print(f"  Time:             {elapsed:.0f}s")

    if flagged:
        print(f"\n  Flagged domains:")
        for f in flagged:
            label = 'subscriber_wall' if f['type'] == 'subscriber_wall' else 'paywall'
            print(f"    - {f['domain']} ({label}) — {f['name']}")

    if dry_run:
        print(f"\n  DRY RUN — no changes written to database")

    if db:
        await db.close()


async def show_status():
    """Show current flagged domains from the database."""
    from database.connection import Database

    db = Database(config.DATABASE_URL)
    await db.connect()

    try:
        rows = await db.pool.fetch(
            "SELECT * FROM source_fetch_flags ORDER BY detected_at DESC"
        )
    except Exception:
        print("No source_fetch_flags table found. Run the scan first.")
        await db.close()
        return

    if not rows:
        print("No domains currently flagged.")
        await db.close()
        return

    print(f"\nFlagged domains: {len(rows)}\n")
    print(f"  {'Domain':<40} {'Type':<20} {'Source':<30} {'Detected'}")
    print(f"  {'-'*40} {'-'*20} {'-'*30} {'-'*20}")

    for r in rows:
        flag_type = 'paywall' if r['has_paywall'] else 'subscriber_wall'
        print(f"  {r['domain']:<40} {flag_type:<20} {(r['source_name'] or ''):<30} {r['detected_at']}")

    await db.close()


async def clear_flags():
    """Clear all flags from the database."""
    from database.connection import Database

    db = Database(config.DATABASE_URL)
    await db.connect()

    try:
        result = await db.pool.execute("DELETE FROM source_fetch_flags")
        count = int(result.split()[-1])
        print(f"Cleared {count} flagged domain(s).")
    except Exception as e:
        print(f"Error clearing flags: {e}")

    await db.close()


def main():
    parser = argparse.ArgumentParser(
        description='Scan feed registry for paywalls / subscriber walls'
    )
    parser.add_argument(
        '--status', action='store_true',
        help='Show currently flagged domains'
    )
    parser.add_argument(
        '--clear', action='store_true',
        help='Clear all flags, then re-scan'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Scan but do not write to database'
    )
    args = parser.parse_args()

    if args.status:
        asyncio.run(show_status())
    elif args.clear:
        asyncio.run(clear_flags())
        print("\nStarting fresh scan...\n")
        asyncio.run(scan_all_feeds(dry_run=False))
    else:
        asyncio.run(scan_all_feeds(dry_run=args.dry_run))


if __name__ == '__main__':
    main()
