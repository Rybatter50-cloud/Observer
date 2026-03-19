#!/usr/bin/env python3
"""
Observer Intelligence Platform - UN Security Council Sanctions Loader
===================================================================
Download the UN SC Consolidated Sanctions List (XML) and load into
the existing sanctions_entities + sanctions_names tables with
source='un_sc' discriminator.

The UN publishes the consolidated list as XML at:
  https://scsanctions.un.org/resources/xml/en/consolidated.xml

This loader:
  1. Downloads the XML (redirects to Azure blob storage)
  2. Parses INDIVIDUAL and ENTITY records
  3. Inserts into sanctions_entities + sanctions_names with source='un_sc'
  4. Does NOT touch existing OpenSanctions data (source='opensanctions')

Usage:
    python scripts/load_un_sanctions.py               # download + load
    python scripts/load_un_sanctions.py --skip-download # load from cached XML
    python scripts/load_un_sanctions.py --status       # show DB stats

2026-02-25 | Mr Cat + Claude | Data Integration Plan - Phase 1
"""

import os
import sys
import time
import asyncio
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from xml.etree import ElementTree as ET

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

# ======================================================================
# UN SANCTIONS XML URL
# ======================================================================

UN_XML_URL = 'https://scsanctions.un.org/resources/xml/en/consolidated.xml'
# Fallback: direct Azure blob URL (the redirect target)
UN_XML_FALLBACK = 'https://unsolprodfiles.blob.core.windows.net/publiclegacyxmlfiles/EN/consolidatedLegacyByPRN.xml'

HEADERS = {
    'User-Agent': 'Observer-Intelligence/1.0 (sanctions-screening)',
    'Accept': 'application/xml',
}

SOURCE_TAG = 'un_sc'


def get_data_dir() -> Path:
    return Path(os.getenv(
        'UN_SANCTIONS_DATA_DIR',
        str(Path(__file__).parent.parent / 'data')
    ))


def get_xml_path() -> Path:
    return get_data_dir() / 'un_sc_consolidated.xml'


def _normalize_name(name: str) -> str:
    """NFKD decompose, strip accents, lowercase — same as screening.py."""
    decomposed = unicodedata.normalize('NFKD', name)
    stripped = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower().strip()


# ======================================================================
# DOWNLOAD
# ======================================================================

async def download_xml(xml_path: Path) -> bool:
    """Download the UN consolidated sanctions XML."""
    import aiohttp

    xml_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=120)

    for url in [UN_XML_URL, UN_XML_FALLBACK]:
        try:
            print(f"  Downloading from {url} ...")
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=HEADERS, allow_redirects=True) as resp:
                    if resp.status != 200:
                        print(f"  HTTP {resp.status}, trying fallback...")
                        continue

                    content = await resp.read()
                    with open(xml_path, 'wb') as f:
                        f.write(content)

                    size_kb = len(content) / 1024
                    print(f"  Saved: {xml_path} ({size_kb:.0f}KB)")
                    return True

        except Exception as e:
            print(f"  Error: {e}, trying fallback...")
            continue

    print("ERROR: Failed to download UN sanctions XML from all URLs")
    return False


# ======================================================================
# PARSE XML
# ======================================================================

def _get_text(elem, tag: str, default: str = '') -> str:
    """Get text content of a child element."""
    child = elem.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return default


def _get_nested_values(elem, tag: str, subtag: str = 'VALUE') -> List[str]:
    """Get list of values from nested elements like <NATIONALITY><VALUE>...</VALUE></NATIONALITY>."""
    values = []
    parent = elem.find(tag)
    if parent is not None:
        for child in parent.findall(subtag):
            if child.text:
                values.append(child.text.strip())
    # Also check for direct occurrences (multiple <NATIONALITY> elements)
    for parent in elem.findall(tag):
        for child in parent.findall(subtag):
            if child.text:
                values.append(child.text.strip())
    return list(set(values))  # dedupe


def _build_full_name(elem) -> str:
    """Build full name from FIRST_NAME through FOURTH_NAME."""
    parts = []
    for tag in ['FIRST_NAME', 'SECOND_NAME', 'THIRD_NAME', 'FOURTH_NAME']:
        text = _get_text(elem, tag)
        if text:
            parts.append(text)
    return ' '.join(parts)


def _get_aliases(elem, alias_tag: str) -> List[str]:
    """Extract aliases from INDIVIDUAL_ALIAS or ENTITY_ALIAS elements."""
    aliases = []
    for alias_elem in elem.findall(alias_tag):
        quality = _get_text(alias_elem, 'QUALITY')
        name = _get_text(alias_elem, 'ALIAS_NAME')
        if name:
            aliases.append(name)
    return aliases


def parse_xml(xml_path: Path) -> List[Dict[str, Any]]:
    """Parse the UN SC consolidated sanctions XML into entity records."""
    records = []

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Parse date generated
    date_generated = root.attrib.get('dateGenerated', 'unknown')
    print(f"  XML generated: {date_generated}")

    # Parse INDIVIDUALS
    individuals_elem = root.find('INDIVIDUALS')
    if individuals_elem is not None:
        for ind in individuals_elem.findall('INDIVIDUAL'):
            dataid = _get_text(ind, 'DATAID')
            ref_num = _get_text(ind, 'REFERENCE_NUMBER')
            entity_id = f"un_sc_{ref_num}" if ref_num else f"un_sc_ind_{dataid}"

            full_name = _build_full_name(ind)
            if not full_name:
                continue

            aliases = _get_aliases(ind, 'INDIVIDUAL_ALIAS')
            nationalities = _get_nested_values(ind, 'NATIONALITY')
            listed_on = _get_text(ind, 'LISTED_ON')
            un_list_type = _get_text(ind, 'UN_LIST_TYPE')
            comments = _get_text(ind, 'COMMENTS1')
            designation = _get_text(ind, 'DESIGNATION')

            # Build identifiers from documents
            identifiers = []
            for doc in ind.findall('INDIVIDUAL_DOCUMENT'):
                doc_type = _get_text(doc, 'TYPE_OF_DOCUMENT')
                doc_num = _get_text(doc, 'NUMBER')
                if doc_num:
                    identifiers.append(f"{doc_type}: {doc_num}" if doc_type else doc_num)

            # Build birth_date
            birth_dates = []
            for dob in ind.findall('INDIVIDUAL_DATE_OF_BIRTH'):
                date_val = _get_text(dob, 'DATE')
                year_val = _get_text(dob, 'YEAR')
                if date_val:
                    birth_dates.append(date_val)
                elif year_val:
                    birth_dates.append(year_val)

            records.append({
                'id': entity_id,
                'schema_type': 'Person',
                'name': full_name,
                'aliases': ';'.join(aliases) if aliases else '',
                'birth_date': ';'.join(birth_dates) if birth_dates else '',
                'countries': ';'.join(nationalities) if nationalities else '',
                'sanctions': f"UN SC {un_list_type}" if un_list_type else 'UN SC',
                'dataset': 'un_sc_consolidated',
                'identifiers': ';'.join(identifiers) if identifiers else '',
                'source': SOURCE_TAG,
            })

    # Parse ENTITIES
    entities_elem = root.find('ENTITIES')
    if entities_elem is not None:
        for ent in entities_elem.findall('ENTITY'):
            dataid = _get_text(ent, 'DATAID')
            ref_num = _get_text(ent, 'REFERENCE_NUMBER')
            entity_id = f"un_sc_{ref_num}" if ref_num else f"un_sc_ent_{dataid}"

            name = _get_text(ent, 'FIRST_NAME')
            if not name:
                continue

            aliases = _get_aliases(ent, 'ENTITY_ALIAS')
            listed_on = _get_text(ent, 'LISTED_ON')
            un_list_type = _get_text(ent, 'UN_LIST_TYPE')
            comments = _get_text(ent, 'COMMENTS1')

            # Entity addresses for country extraction
            countries = []
            for addr in ent.findall('ENTITY_ADDRESS'):
                country = _get_text(addr, 'COUNTRY')
                if country:
                    countries.append(country)

            records.append({
                'id': entity_id,
                'schema_type': 'Organization',
                'name': name,
                'aliases': ';'.join(aliases) if aliases else '',
                'birth_date': '',
                'countries': ';'.join(list(set(countries))) if countries else '',
                'sanctions': f"UN SC {un_list_type}" if un_list_type else 'UN SC',
                'dataset': 'un_sc_consolidated',
                'identifiers': '',
                'source': SOURCE_TAG,
            })

    return records


# ======================================================================
# LOAD TO DB
# ======================================================================

async def load_to_db(records: List[Dict[str, Any]]) -> int:
    """Load UN sanctions records into PostgreSQL."""
    import asyncpg

    pool = await asyncpg.create_pool(
        config.DATABASE_URL, min_size=2, max_size=4
    )

    try:
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'sanctions_entities'"
            )
            if not exists:
                print("ERROR: sanctions_entities table does not exist.")
                return 0

            # Check source column exists (migration 017)
            has_source = await conn.fetchval("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'sanctions_entities' AND column_name = 'source'
            """)
            if not has_source:
                print("ERROR: 'source' column not found on sanctions_entities.")
                print("Apply migration 017 first.")
                return 0

            async with conn.transaction():
                # Delete existing UN SC data only (preserve OpenSanctions)
                deleted = await conn.fetchval(
                    "DELETE FROM sanctions_entities WHERE source = $1 RETURNING COUNT(*)",
                    SOURCE_TAG,
                )
                if deleted:
                    print(f"  Removed {deleted} existing UN SC records")

                # Bulk insert entities
                batch_size = 500
                entity_count = 0
                name_rows = []

                for i in range(0, len(records), batch_size):
                    batch = records[i:i + batch_size]

                    entity_tuples = [
                        (
                            r['id'], r['schema_type'], r['name'], r['aliases'],
                            r['birth_date'], r['countries'], r['sanctions'],
                            r['dataset'], r['identifiers'], r['source'],
                        )
                        for r in batch
                    ]
                    await conn.executemany(
                        """INSERT INTO sanctions_entities
                           (id, schema_type, name, aliases, birth_date,
                            countries, sanctions, dataset, identifiers, source)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                           ON CONFLICT (id) DO UPDATE SET
                               name = EXCLUDED.name,
                               aliases = EXCLUDED.aliases,
                               sanctions = EXCLUDED.sanctions,
                               source = EXCLUDED.source,
                               loaded_at = NOW()""",
                        entity_tuples,
                    )
                    entity_count += len(batch)

                    # Build name index rows
                    for r in batch:
                        eid = r['id']
                        primary = r['name'].strip()
                        if primary:
                            name_rows.append((eid, _normalize_name(primary), primary))

                        if r['aliases']:
                            for alias in r['aliases'].split(';'):
                                alias = alias.strip()
                                if alias and len(alias) > 1:
                                    name_rows.append((eid, _normalize_name(alias), alias))

                # Insert name variants
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
                       WHERE key = 'un_sanctions_last_load'""",
                    datetime.now().isoformat(),
                )

            # ANALYZE
            await conn.execute("ANALYZE sanctions_entities")
            await conn.execute("ANALYZE sanctions_names")

        return entity_count
    finally:
        await pool.close()


async def show_status():
    """Show UN sanctions DB stats."""
    import asyncpg

    pool = await asyncpg.create_pool(
        config.DATABASE_URL, min_size=1, max_size=2
    )

    try:
        async with pool.acquire() as conn:
            # Check source column exists
            has_source = await conn.fetchval("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'sanctions_entities' AND column_name = 'source'
            """)

            if has_source:
                un_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM sanctions_entities WHERE source = $1",
                    SOURCE_TAG,
                )
                os_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM sanctions_entities WHERE source = 'opensanctions'"
                )
                total = await conn.fetchval("SELECT COUNT(*) FROM sanctions_entities")
                print(f"Sanctions Database Status:")
                print(f"  OpenSanctions:      {os_count:,}")
                print(f"  UN SC Consolidated: {un_count:,}")
                print(f"  Total:              {total:,}")

                # UN breakdown
                if un_count > 0:
                    persons = await conn.fetchval(
                        "SELECT COUNT(*) FROM sanctions_entities WHERE source = $1 AND schema_type = 'Person'",
                        SOURCE_TAG,
                    )
                    orgs = await conn.fetchval(
                        "SELECT COUNT(*) FROM sanctions_entities WHERE source = $1 AND schema_type = 'Organization'",
                        SOURCE_TAG,
                    )
                    print(f"    UN Individuals:   {persons:,}")
                    print(f"    UN Entities:      {orgs:,}")
            else:
                total = await conn.fetchval("SELECT COUNT(*) FROM sanctions_entities")
                print(f"Sanctions entities: {total:,}")
                print(f"(source column not yet added — run migration 017)")

            last_load = await conn.fetchval(
                "SELECT value FROM metadata WHERE key = 'un_sanctions_last_load'"
            )
            print(f"\n  Last UN load: {last_load or 'never'}")

            last_os = await conn.fetchval(
                "SELECT value FROM metadata WHERE key = 'sanctions_last_load'"
            )
            print(f"  Last OpenSanctions load: {last_os or 'never'}")
    finally:
        await pool.close()


async def main():
    parser = argparse.ArgumentParser(
        description='Download and load UN SC consolidated sanctions into PostgreSQL',
    )
    parser.add_argument('--skip-download', action='store_true',
                        help='Skip download, load from cached XML')
    parser.add_argument('--status', action='store_true',
                        help='Show current DB stats')
    args = parser.parse_args()

    if args.status:
        await show_status()
        return

    xml_path = get_xml_path()

    print("=" * 65)
    print("  Observer — UN Security Council Sanctions Loader")
    print("=" * 65)

    if not args.skip_download:
        print("\n[1/3] Downloading UN SC Consolidated List (XML)...")
        ok = await download_xml(xml_path)
        if not ok:
            sys.exit(1)
    else:
        if not xml_path.exists():
            print(f"ERROR: XML not found at {xml_path}")
            sys.exit(1)
        size_kb = xml_path.stat().st_size / 1024
        print(f"  Using cached XML: {xml_path} ({size_kb:.0f}KB)")

    print("\n[2/3] Parsing XML...")
    records = parse_xml(xml_path)
    persons = sum(1 for r in records if r['schema_type'] == 'Person')
    orgs = sum(1 for r in records if r['schema_type'] == 'Organization')
    print(f"  Parsed {len(records)} entities ({persons} individuals, {orgs} organizations)")

    print("\n[3/3] Loading into PostgreSQL...")
    start = time.monotonic()
    count = await load_to_db(records)
    elapsed = time.monotonic() - start

    print("\n" + "=" * 65)
    print("  UN SANCTIONS LOAD COMPLETE")
    print(f"  Entities loaded: {count:,}")
    print(f"  Time: {elapsed:.1f}s")
    print("=" * 65)


if __name__ == '__main__':
    asyncio.run(main())
