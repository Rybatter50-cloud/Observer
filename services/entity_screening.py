"""
RYBAT Intelligence Platform - Entity Screening Service
=======================================================
Unified service wrapping FBI Wanted, Interpol Notices, and OpenSanctions
for entity screening against intelligence signals.

Clients:
  FBIClient          — FBI Most Wanted (free, no auth, API)
  InterpolClient     — Interpol Red/Yellow/UN notices (free, no auth, API)
  OpenSanctionsClient — PostgreSQL-backed sanctions database (pg_trgm fuzzy search)

Usage:
  service = get_screening_service()
  results = await service.screen_entity("Viktor Bout")

2026-02-12 | Mr Cat + Claude
"""

import asyncio
import aiohttp
import csv
import os
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

import config as app_config
from utils.logging import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ScreeningHit:
    """A single match from any screening source"""
    source: str            # 'fbi', 'interpol', 'opensanctions'
    name: str              # matched entity name
    score: float           # 0-100 match confidence
    category: str          # e.g. 'wanted', 'red_notice', 'sanction', 'pep'
    details: Dict[str, Any] = field(default_factory=dict)
    url: Optional[str] = None  # link to source record

@dataclass
class ScreeningResult:
    """Aggregated screening result across all sources"""
    query: str
    hits: List[ScreeningHit] = field(default_factory=list)
    sources_checked: List[str] = field(default_factory=list)
    sources_failed: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    @property
    def has_hits(self) -> bool:
        return len(self.hits) > 0

    @property
    def max_score(self) -> float:
        return max((h.score for h in self.hits), default=0.0)

    @property
    def hit_count(self) -> int:
        return len(self.hits)


# ─────────────────────────────────────────────────────────────────────
# FBI Client
# ─────────────────────────────────────────────────────────────────────

class FBIClient:
    """
    FBI Most Wanted API client.
    Free, no auth. ~1,060 records.
    https://api.fbi.gov/wanted/v1/list
    """

    BASE_URL = "https://api.fbi.gov/wanted/v1/list"
    CACHE_TTL = timedelta(hours=24)
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'application/json',
    }

    def __init__(self):
        self._cache: List[Dict[str, Any]] = []
        self._cache_time: Optional[datetime] = None
        self._loading = False

    async def refresh_cache(self) -> None:
        """Fetch full FBI wanted list into local cache."""
        if self._loading:
            return
        self._loading = True
        try:
            records = []
            page = 1
            page_size = 50
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(timeout=timeout, headers=self.HEADERS) as session:
                while True:
                    params = {'page': page, 'pageSize': page_size}
                    async with session.get(self.BASE_URL, params=params) as resp:
                        if resp.status != 200:
                            logger.warning(f"FBI API returned {resp.status}")
                            break
                        data = await resp.json()

                    items = data.get('items', [])
                    if not items:
                        break
                    records.extend(items)

                    total = data.get('total', 0)
                    if page * page_size >= total:
                        break
                    page += 1
                    await asyncio.sleep(0.3)  # polite delay

            self._cache = records
            self._cache_time = datetime.now()
            logger.info(f"FBI cache refreshed: {len(records)} records")
        except Exception as e:
            logger.error(f"FBI cache refresh failed: {e}")
        finally:
            self._loading = False

    def _needs_refresh(self) -> bool:
        if not self._cache_time:
            return True
        return datetime.now() - self._cache_time > self.CACHE_TTL

    async def search(self, name: str) -> List[ScreeningHit]:
        """Search cached FBI records by name (case-insensitive substring)."""
        if self._needs_refresh():
            await self.refresh_cache()

        if not self._cache:
            return []

        hits = []
        query_lower = name.lower().strip()
        query_parts = query_lower.split()

        for record in self._cache:
            title = (record.get('title') or '').lower()
            aliases = [a.lower() for a in (record.get('aliases') or []) if a]

            # Check title and aliases
            match_score = 0.0
            matched_name = ''

            # Exact match on title
            if query_lower == title:
                match_score = 100.0
                matched_name = record.get('title', '')
            # All query parts appear in title
            elif all(p in title for p in query_parts):
                match_score = 85.0
                matched_name = record.get('title', '')
            else:
                # Check aliases
                for alias in aliases:
                    if query_lower == alias:
                        match_score = 95.0
                        matched_name = alias
                        break
                    elif all(p in alias for p in query_parts):
                        match_score = 75.0
                        matched_name = alias
                        break

            if match_score > 0:
                classification = record.get('poster_classification', 'default')
                category_map = {
                    'ten': 'top_ten_wanted',
                    'terrorist': 'wanted_terrorist',
                    'default': 'wanted',
                    'missing': 'missing_person',
                    'information': 'seeking_info',
                    'ecap': 'ecap',
                }
                category = category_map.get(classification, 'wanted')

                details = {}
                for key in ('nationality', 'race', 'sex', 'dates_of_birth_used',
                            'place_of_birth', 'hair', 'eyes', 'height_min',
                            'weight', 'caution', 'reward_text', 'subjects',
                            'description', 'remarks', 'warning_message'):
                    val = record.get(key)
                    if val:
                        details[key] = val

                # Add charges (field_offices often map to case type)
                charges = record.get('description')
                if charges:
                    details['charges'] = charges

                hits.append(ScreeningHit(
                    source='fbi',
                    name=matched_name or record.get('title', 'Unknown'),
                    score=match_score,
                    category=category,
                    details=details,
                    url=record.get('url'),
                ))

        return hits

    def get_status(self) -> Dict[str, Any]:
        return {
            'records_cached': len(self._cache),
            'cache_age_minutes': round((datetime.now() - self._cache_time).total_seconds() / 60, 1) if self._cache_time else None,
            'available': True,
        }


# ─────────────────────────────────────────────────────────────────────
# Interpol Client
# ─────────────────────────────────────────────────────────────────────

class InterpolClient:
    """
    Interpol Notices API client (unofficial public endpoint).
    Free, no auth. Rate limit ~1000/hr.
    https://ws-public.interpol.int/notices/v1/red
    """

    BASE_URL = "https://ws-public.interpol.int/notices/v1"
    NOTICE_TYPES = ('red', 'yellow', 'un')
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'application/json',
    }

    def __init__(self):
        self._result_cache: Dict[str, tuple] = {}  # query -> (results, timestamp, was_success)
        self._cache_ttl = timedelta(hours=6)

    async def search(self, name: str, notice_types: Optional[List[str]] = None) -> List[ScreeningHit]:
        """
        Search Interpol notices by name.
        Queries Red, Yellow, and UN notice endpoints in parallel.
        """
        cache_key = name.lower().strip()
        if cache_key in self._result_cache:
            cached_hits, cached_time, was_success = self._result_cache[cache_key]
            if datetime.now() - cached_time < self._cache_ttl:
                # Only serve cached results if the original query actually succeeded
                if was_success:
                    return cached_hits
                # Stale failed result — retry

        types_to_check = notice_types or list(self.NOTICE_TYPES)
        hits = []
        any_success = False
        timeout = aiohttp.ClientTimeout(total=20)

        # Parse name — try surname-first (API expects name=surname, forename=firstname)
        parts = name.strip().split()
        if len(parts) >= 2:
            forename = parts[0]
            surname = ' '.join(parts[1:])  # preserve multi-word surnames
        else:
            forename = ''
            surname = parts[0] if parts else name.strip()

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=self.HEADERS) as session:
                tasks = []
                for ntype in types_to_check:
                    tasks.append(self._search_notice_type(session, ntype, forename, surname))

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for ntype, result in zip(types_to_check, results):
                    if isinstance(result, Exception):
                        logger.warning(f"Interpol {ntype} search failed: {result}")
                        continue
                    success, type_hits = result
                    if success:
                        any_success = True
                    hits.extend(type_hits)

                # If surname search found nothing and we have a multi-word name, try freeText
                if not hits and any_success and len(parts) >= 2:
                    free_tasks = []
                    for ntype in types_to_check:
                        free_tasks.append(
                            self._search_notice_freetext(session, ntype, name.strip())
                        )
                    free_results = await asyncio.gather(*free_tasks, return_exceptions=True)
                    for ntype, result in zip(types_to_check, free_results):
                        if isinstance(result, Exception):
                            continue
                        success, type_hits = result
                        if success:
                            any_success = True
                        hits.extend(type_hits)

        except Exception as e:
            logger.error(f"Interpol search connection error: {e}")

        # Cache results — but mark whether the API actually responded
        self._result_cache[cache_key] = (hits, datetime.now(), any_success)

        # Evict old cache entries
        cutoff = datetime.now() - self._cache_ttl
        self._result_cache = {
            k: v for k, v in self._result_cache.items() if v[1] > cutoff
        }

        return hits

    async def _search_notice_type(
        self, session: aiohttp.ClientSession,
        notice_type: str, forename: str, surname: str
    ) -> tuple:
        """Search a single Interpol notice type. Returns (success: bool, hits: list)."""
        url = f"{self.BASE_URL}/{notice_type}"
        params = {'name': surname, 'resultPerPage': 160}
        if forename and forename.lower() != surname.lower():
            params['forename'] = forename

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        f"Interpol {notice_type} returned HTTP {resp.status}: "
                        f"{body[:200] if body else '(empty)'}"
                    )
                    return (False, [])
                data = await resp.json()
        except Exception as e:
            logger.warning(f"Interpol {notice_type} request error: {e}")
            return (False, [])

        return (True, self._parse_notices(data, notice_type, forename, surname))

    async def _search_notice_freetext(
        self, session: aiohttp.ClientSession,
        notice_type: str, query: str
    ) -> tuple:
        """Fallback: search using freeText parameter."""
        url = f"{self.BASE_URL}/{notice_type}"
        params = {'freeText': query, 'resultPerPage': 20}

        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return (False, [])
                data = await resp.json()
        except Exception as e:
            logger.warning(f"Interpol {notice_type} freeText error: {e}")
            return (False, [])

        return (True, self._parse_notices(data, notice_type, query.split()[0] if query else '', query))

    def _parse_notices(
        self, data: dict, notice_type: str,
        forename: str, surname: str
    ) -> List[ScreeningHit]:
        """Parse Interpol API response into ScreeningHit list."""
        notices = data.get('_embedded', {}).get('notices', [])
        if not notices:
            return []

        hits = []
        query_lower = f"{forename} {surname}".lower().strip()
        query_parts = set(query_lower.split())

        for notice in notices:
            notice_name = notice.get('name', '')
            notice_forename = notice.get('forename', '')
            full_name = f"{notice_forename} {notice_name}".strip()
            full_lower = full_name.lower()

            # Score the match
            name_parts = set(full_lower.split())
            overlap = query_parts & name_parts
            if not overlap:
                continue

            # Calculate match score based on overlap
            score = (len(overlap) / max(len(query_parts), len(name_parts))) * 100

            # Boost exact matches
            if query_lower == full_lower:
                score = 100.0
            elif score < 40:
                continue  # too weak

            category_map = {
                'red': 'red_notice',
                'yellow': 'yellow_notice',
                'un': 'un_notice',
            }

            details = {}
            for key in ('date_of_birth', 'nationalities', 'sex_id',
                        'country_of_birth_id', 'weight', 'height'):
                val = notice.get(key)
                if val:
                    details[key] = val

            # Get arrest warrants / charges
            warrants = notice.get('arrest_warrants', [])
            if warrants:
                details['charges'] = [w.get('charge', '') for w in warrants if w.get('charge')]

            # Entity detail link
            entity_id = notice.get('entity_id', '')
            detail_url = f"https://www.interpol.int/en/How-we-work/Notices/View/{notice_type.capitalize()}-Notices#{entity_id}" if entity_id else None

            # Use the _links self href if available
            self_link = notice.get('_links', {}).get('self', {}).get('href')
            if self_link:
                detail_url = self_link

            hits.append(ScreeningHit(
                source='interpol',
                name=full_name,
                score=round(score, 1),
                category=category_map.get(notice_type, 'notice'),
                details=details,
                url=detail_url,
            ))

        return hits

    def get_status(self) -> Dict[str, Any]:
        return {
            'cached_queries': len(self._result_cache),
            'notice_types': list(self.NOTICE_TYPES),
            'available': True,
        }


# ─────────────────────────────────────────────────────────────────────
# Sanctions.network Client
# ─────────────────────────────────────────────────────────────────────

class SanctionsNetworkClient:
    """
    sanctions.network API client.
    Free, no auth. PostgREST-backed, pg_trgm fuzzy search.
    Sources: OFAC SDN, UN Security Council, EU Financial Sanctions.
    https://api.sanctions.network/rpc/search_sanctions
    """

    API_URL = "https://api.sanctions.network/rpc/search_sanctions"
    HEADERS = {
        'User-Agent': 'RYBAT-Intelligence/1.0 (entity-screening)',
        'Accept': 'application/json',
    }

    def __init__(self):
        self._result_cache: Dict[str, tuple] = {}  # query -> (results, timestamp)
        self._cache_ttl = timedelta(hours=6)

    async def search(self, name: str, entity_type: str = 'Person') -> List[ScreeningHit]:
        """
        Fuzzy search via /rpc/search_sanctions.
        Returns ScreeningHit list sorted by name similarity.
        """
        cache_key = name.lower().strip()
        if cache_key in self._result_cache:
            cached_hits, cached_time = self._result_cache[cache_key]
            if datetime.now() - cached_time < self._cache_ttl:
                return cached_hits

        hits = []
        timeout = aiohttp.ClientTimeout(total=15)

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=self.HEADERS) as session:
                async with session.post(
                    self.API_URL,
                    json={"name": name},
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"sanctions.network returned {resp.status}")
                        return []
                    records = await resp.json()

        except Exception as e:
            logger.error(f"sanctions.network search error: {e}")
            return []

        if not records or not isinstance(records, list):
            self._result_cache[cache_key] = ([], datetime.now())
            return []

        query_lower = name.lower().strip()
        query_parts = set(query_lower.split())

        for record in records[:50]:
            names_list = record.get('names', [])
            if not names_list:
                continue

            # Score based on name overlap
            best_score = 0.0
            best_name = names_list[0] if names_list else ''

            for candidate in names_list:
                cand_lower = candidate.lower()
                cand_parts = set(cand_lower.split())

                if query_lower == cand_lower:
                    best_score = 100.0
                    best_name = candidate
                    break

                overlap = query_parts & cand_parts
                if overlap:
                    score = (len(overlap) / max(len(query_parts), len(cand_parts))) * 100
                    if score > best_score:
                        best_score = score
                        best_name = candidate

            if best_score < 30:
                continue

            # Map source to category
            source_val = (record.get('source') or '').lower()
            category_map = {
                'ofac': 'sanction_ofac',
                'unsc': 'sanction_unsc',
                'eu': 'sanction_eu',
            }
            category = category_map.get(source_val, 'sanction')

            details = {}
            if record.get('target_type'):
                details['target_type'] = record['target_type']
            if record.get('source_id'):
                details['source_id'] = record['source_id']
            if record.get('remarks'):
                details['remarks'] = record['remarks']
            if record.get('positions'):
                details['positions'] = record['positions']
            if record.get('listed_on'):
                details['listed_on'] = record['listed_on']
            if len(names_list) > 1:
                details['aliases'] = names_list[1:]

            hits.append(ScreeningHit(
                source='sanctions_network',
                name=best_name,
                score=round(best_score, 1),
                category=category,
                details=details,
                url=None,
            ))

        self._result_cache[cache_key] = (hits, datetime.now())
        return hits

    def get_status(self) -> Dict[str, Any]:
        return {
            'cached_queries': len(self._result_cache),
            'sources': ['ofac', 'unsc', 'eu'],
            'available': True,
        }


# ─────────────────────────────────────────────────────────────────────
# OpenSanctions PostgreSQL Client
# ─────────────────────────────────────────────────────────────────────

class OpenSanctionsClient:
    """
    OpenSanctions client backed by PostgreSQL with pg_trgm fuzzy matching.

    Downloads the 'default' dataset targets.simple.csv from OpenSanctions,
    bulk-loads into sanctions_entities + sanctions_names tables, then queries
    via pg_trgm similarity() with GIN index.

    Data source: https://data.opensanctions.org/datasets/latest/default/
    ~300K+ entities (sanctions + PEPs + criminals + debarred), ~200MB CSV,
    refreshed daily by OpenSanctions. All queries hit PostgreSQL — zero
    memory cost beyond the connection pool.
    """

    CSV_URL = "https://data.opensanctions.org/datasets/latest/default/targets.simple.csv"
    ENTITY_URL_PREFIX = "https://www.opensanctions.org/entities/"
    HEADERS = {
        'User-Agent': 'RYBAT-Intelligence/1.0 (entity-screening)',
        'Accept': 'text/csv',
    }

    def __init__(self, screening_repo=None, data_dir: Optional[str] = None, refresh_hours: int = 24):
        self._repo = screening_repo  # ScreeningRepository, set later if not provided
        self._data_dir = Path(data_dir or os.getenv(
            'OPENSANCTIONS_DATA_DIR',
            str(Path(__file__).parent.parent / 'data')
        ))
        self._csv_path = self._data_dir / 'opensanctions_default.csv'
        self._refresh_interval = timedelta(hours=refresh_hours)

        self._last_modified: Optional[str] = None  # HTTP Last-Modified for delta
        self._load_time: Optional[datetime] = None
        self._entity_count: int = 0
        self._loading = False
        self.enabled = True

    def set_repo(self, screening_repo) -> None:
        """Set the screening repository (called after DB init)."""
        self._repo = screening_repo

    async def refresh_cache(self) -> None:
        """Download CSV (if newer) and bulk-load into PostgreSQL."""
        if self._loading:
            return
        if not self._repo:
            logger.warning("OpenSanctions: no DB repository available, skipping refresh")
            return

        self._loading = True
        try:
            # Hydrate in-memory state from DB on first run (survives restarts)
            await self._hydrate_from_db()

            # Check if DB already has data and is fresh enough
            if not self._needs_refresh():
                logger.debug("OpenSanctions DB data still fresh, skipping refresh")
                return

            logger.info("OpenSanctions: downloading latest dataset...")
            downloaded = await self._download_csv()
            if downloaded or self._entity_count == 0:
                count = await self._load_csv_to_db()
                self._entity_count = count
                self._load_time = datetime.now()
            elif self._csv_path.exists() and self._entity_count == 0:
                # DB empty but CSV on disk — load it
                count = await self._load_csv_to_db()
                self._entity_count = count
                self._load_time = datetime.now()
        except Exception as e:
            logger.error(f"OpenSanctions refresh failed: {e}")
            # Try loading from disk if DB is empty
            if self._entity_count == 0 and self._csv_path.exists():
                try:
                    count = await self._load_csv_to_db()
                    self._entity_count = count
                    self._load_time = datetime.now()
                    logger.info("OpenSanctions loaded from cached CSV on disk")
                except Exception as e2:
                    logger.error(f"OpenSanctions disk fallback failed: {e2}")
        finally:
            self._loading = False

    async def _download_csv(self) -> bool:
        """Download CSV with If-Modified-Since delta check. Returns True if new data downloaded."""
        self._data_dir.mkdir(parents=True, exist_ok=True)

        headers = dict(self.HEADERS)
        if self._last_modified and self._csv_path.exists():
            headers['If-Modified-Since'] = self._last_modified

        timeout = aiohttp.ClientTimeout(total=600)  # 10min — default dataset is ~200MB

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(self.CSV_URL, headers=headers) as resp:
                if resp.status == 304:
                    logger.info("OpenSanctions CSV not modified, skipping download")
                    return False
                if resp.status != 200:
                    raise RuntimeError(f"OpenSanctions download failed: HTTP {resp.status}")

                lm = resp.headers.get('Last-Modified')
                if lm:
                    self._last_modified = lm
                    # Persist so If-Modified-Since works across restarts
                    if self._repo:
                        await self._repo.set_csv_last_modified(lm)

                with open(self._csv_path, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        f.write(chunk)

                size_mb = self._csv_path.stat().st_size / (1024 * 1024)
                logger.info(f"OpenSanctions CSV downloaded: {size_mb:.1f}MB")
                return True

    async def _load_csv_to_db(self) -> int:
        """Parse CSV and bulk-load into PostgreSQL via ScreeningRepository."""
        if not self._csv_path.exists():
            logger.warning("OpenSanctions CSV not found on disk")
            return 0
        if not self._repo:
            logger.warning("OpenSanctions: no DB repository, cannot load")
            return 0

        size_mb = self._csv_path.stat().st_size / (1024 * 1024)
        logger.info(f"OpenSanctions: loading CSV ({size_mb:.1f}MB) into database...")
        records = []
        with open(self._csv_path, 'r', encoding='utf-8') as f:
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

        logger.info(f"OpenSanctions CSV parsed: {len(records)} records, loading to PostgreSQL...")
        count = await self._repo.bulk_load(records)
        logger.info(f"OpenSanctions DB loaded: {count} entities")
        return count

    async def _hydrate_from_db(self) -> None:
        """Load persisted state from DB so cold starts can skip redundant downloads."""
        if self._load_time or not self._repo:
            return
        try:
            last_load = await self._repo.get_last_load_time()
            if last_load:
                self._load_time = datetime.fromisoformat(last_load)
            last_modified = await self._repo.get_csv_last_modified()
            if last_modified:
                self._last_modified = last_modified
            count = await self._repo.get_entity_count()
            self._entity_count = count
        except Exception as e:
            logger.debug(f"OpenSanctions: could not hydrate from DB: {e}")

    def _needs_refresh(self) -> bool:
        if not self._load_time:
            return True
        return datetime.now() - self._load_time > self._refresh_interval

    async def search(self, name: str, entity_type: str = 'Person') -> List[ScreeningHit]:
        """
        Search sanctions entities via PostgreSQL pg_trgm similarity().
        """
        if not self._repo:
            logger.warning("OpenSanctions search skipped: no DB repository connected")
            return []

        # Auto-refresh if needed
        if self._needs_refresh():
            await self.refresh_cache()

        # Check if DB has data
        if self._entity_count == 0:
            count = await self._repo.get_entity_count()
            self._entity_count = count
            if count == 0:
                if self._loading:
                    logger.warning("OpenSanctions search skipped: DB empty (initial load still in progress)")
                else:
                    logger.warning("OpenSanctions search skipped: DB empty (run scripts/load_sanctions.py or restart server)")
                return []

        schema_type = None
        if entity_type == 'Person':
            schema_type = 'Person'

        rows = await self._repo.search_by_name(
            name=name,
            threshold=0.3,
            schema_type=schema_type,
            limit=50,
        )

        hits = []
        for row in rows:
            dataset = (row.get('dataset') or '').lower()
            category = 'sanction'
            if 'pep' in dataset:
                category = 'pep'
            elif 'crime' in dataset or 'wanted' in dataset:
                category = 'criminal'
            elif 'debarment' in dataset:
                category = 'debarment'

            details: Dict[str, Any] = {
                'schema': row.get('schema_type', ''),
                'datasets': row['dataset'].split(';') if row.get('dataset') else [],
            }
            if row.get('countries'):
                details['countries'] = row['countries'].split(';')
            if row.get('birth_date'):
                details['birth_date'] = row['birth_date']
            if row.get('sanctions'):
                sanctions = row['sanctions']
                if len(sanctions) > 300:
                    sanctions = sanctions[:300] + '...'
                details['sanctions'] = sanctions
            if row.get('identifiers'):
                details['identifiers'] = row['identifiers']
            if row.get('matched_name') and row['matched_name'] != row.get('name'):
                details['matched_alias'] = row['matched_name']

            entity_url = f"{self.ENTITY_URL_PREFIX}{row['id']}/" if row.get('id') else None

            hits.append(ScreeningHit(
                source='opensanctions',
                name=row.get('name', ''),
                score=row.get('score', 0.0),
                category=category,
                details=details,
                url=entity_url,
            ))

        return hits

    async def get_status(self) -> Dict[str, Any]:
        entity_count = 0
        name_count = 0
        last_load = None
        if self._repo:
            try:
                entity_count = await self._repo.get_entity_count()
                name_count = await self._repo.get_name_count()
                last_load = await self._repo.get_last_load_time()
            except Exception:
                pass

        csv_size = None
        if self._csv_path.exists():
            csv_size = f"{self._csv_path.stat().st_size / (1024*1024):.1f}MB"

        return {
            'enabled': True,
            'mode': 'postgresql',
            'entities_in_db': entity_count,
            'name_variants_indexed': name_count,
            'csv_file': str(self._csv_path),
            'csv_size': csv_size,
            'last_modified': self._last_modified,
            'last_db_load': last_load,
            'cache_age_minutes': round(
                (datetime.now() - self._load_time).total_seconds() / 60, 1
            ) if self._load_time else None,
        }


# ─────────────────────────────────────────────────────────────────────
# Unified Screening Service
# ─────────────────────────────────────────────────────────────────────

class EntityScreeningService:
    """
    Orchestrates screening queries across FBI, Interpol, and OpenSanctions.
    All sources are queried in parallel.
    """

    def __init__(self):
        self.fbi = FBIClient()
        self.interpol = InterpolClient()
        self.opensanctions = OpenSanctionsClient()
        self.sanctions_network = SanctionsNetworkClient()
        self._total_screens = 0
        self._total_hits = 0

    def connect_db(self, screening_repo) -> None:
        """Wire the PostgreSQL screening repository to OpenSanctions client."""
        self.opensanctions.set_repo(screening_repo)

    async def screen_entity(
        self,
        name: str,
        sources: Optional[List[str]] = None,
        entity_type: str = 'Person',
    ) -> ScreeningResult:
        """
        Screen a name against all (or selected) sources in parallel.
        """
        start = time.monotonic()
        all_sources = sources or ['fbi', 'interpol', 'opensanctions', 'sanctions_network']
        result = ScreeningResult(query=name)

        tasks = {}
        if 'fbi' in all_sources and app_config.Config.FBI_ENABLED:
            tasks['fbi'] = asyncio.create_task(self.fbi.search(name))
        elif 'fbi' in all_sources:
            result.sources_failed.append('fbi (disabled)')
        if 'interpol' in all_sources and app_config.Config.INTERPOL_ENABLED:
            tasks['interpol'] = asyncio.create_task(self.interpol.search(name))
        elif 'interpol' in all_sources:
            result.sources_failed.append('interpol (disabled)')
        if 'opensanctions' in all_sources and self.opensanctions.enabled:
            tasks['opensanctions'] = asyncio.create_task(
                self.opensanctions.search(name, entity_type)
            )
        if 'sanctions_network' in all_sources and app_config.Config.SANCTIONS_NET_ENABLED:
            tasks['sanctions_network'] = asyncio.create_task(
                self.sanctions_network.search(name, entity_type)
            )
        elif 'sanctions_network' in all_sources:
            result.sources_failed.append('sanctions_network (disabled)')

        for source, task in tasks.items():
            try:
                hits = await task
                result.hits.extend(hits)
                result.sources_checked.append(source)
            except Exception as e:
                logger.error(f"Screening source {source} failed: {e}")
                result.sources_failed.append(source)

        # Sort hits by score descending
        result.hits.sort(key=lambda h: h.score, reverse=True)
        result.elapsed_ms = round((time.monotonic() - start) * 1000, 1)

        self._total_screens += 1
        if result.has_hits:
            self._total_hits += 1

        log_level = logger.warning if result.has_hits else logger.info
        log_level(
            f"Screening '{name}': {result.hit_count} hits from "
            f"{', '.join(result.sources_checked)} ({result.elapsed_ms}ms)"
        )

        return result

    async def warm_cache(self) -> None:
        """Pre-load FBI + OpenSanctions caches on startup (in parallel).

        Respects API toggle flags — skips disabled sources.
        """
        tasks = []
        labels = []
        if app_config.Config.FBI_ENABLED:
            tasks.append(self.fbi.refresh_cache())
            labels.append('FBI')
        else:
            logger.info("FBI cache warm skipped (FBI_ENABLED=false)")
        tasks.append(self.opensanctions.refresh_cache())
        labels.append('OpenSanctions')

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for source, result in zip(labels, results):
            if isinstance(result, Exception):
                logger.error(f"{source} cache warm failed: {result}")

    async def get_status(self) -> Dict[str, Any]:
        opensanctions_status = await self.opensanctions.get_status()
        interpol_status = self.interpol.get_status()
        interpol_status['enabled'] = app_config.Config.INTERPOL_ENABLED
        if not app_config.Config.INTERPOL_ENABLED:
            interpol_status['available'] = False
        fbi_status = self.fbi.get_status()
        fbi_status['enabled'] = app_config.Config.FBI_ENABLED
        if not app_config.Config.FBI_ENABLED:
            fbi_status['available'] = False
        sanctions_net_status = self.sanctions_network.get_status()
        sanctions_net_status['enabled'] = app_config.Config.SANCTIONS_NET_ENABLED
        if not app_config.Config.SANCTIONS_NET_ENABLED:
            sanctions_net_status['available'] = False
        return {
            'total_screens': self._total_screens,
            'total_with_hits': self._total_hits,
            'sources': {
                'fbi': fbi_status,
                'interpol': interpol_status,
                'opensanctions': opensanctions_status,
                'sanctions_network': sanctions_net_status,
            }
        }


# ─────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────

_screening_service: Optional[EntityScreeningService] = None


def get_screening_service() -> EntityScreeningService:
    """Get or create singleton screening service."""
    global _screening_service
    if _screening_service is None:
        _screening_service = EntityScreeningService()
    return _screening_service
