"""
RYBAT Intelligence Platform - Content Filter
=============================================
Filters RSS/scraped articles by blacklist/whitelist regex patterns
loaded from external text files in the filters/ directory.

File naming convention:
  BL_*.txt  — blacklist filter files
  WL_*.txt  — whitelist filter files

Users select one BL file + one WL file via the dashboard.
The app combines them at runtime. Hardcoded defaults are used as
fallback if files are missing or corrupt.

2026-02-09 | Mr Cat + Claude | Extracted from feed_manager.py
2026-02-10 | Mr Cat + Claude | External file loading + multi-filter selection
"""

import os
import re
from pathlib import Path
from typing import Tuple, Optional, List, Dict

from utils.logging import get_logger

logger = get_logger(__name__)

# Default filters directory (relative to project root)
FILTERS_DIR = Path(os.getenv('FILTERS_DIR', './filters'))


# ==================================================================
# FILE I/O — load patterns from text files
# ==================================================================

def _load_patterns_from_file(filepath: Path) -> List[str]:
    """
    Load regex patterns from a text file.

    - One pattern per line
    - Lines starting with # are comments
    - Blank lines are ignored
    - Invalid regex patterns are skipped with a warning

    Returns:
        List of validated regex pattern strings
    """
    patterns = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, raw_line in enumerate(f, 1):
                line = raw_line.strip()
                if not line or line.startswith('#'):
                    continue
                # Validate regex
                try:
                    re.compile(line, re.IGNORECASE)
                    patterns.append(line)
                except re.error as e:
                    logger.warning(
                        f"Invalid regex in {filepath.name}:{line_num}: "
                        f"'{line}' — {e} (skipped)"
                    )
    except FileNotFoundError:
        logger.warning(f"Filter file not found: {filepath}")
    except Exception as e:
        logger.error(f"Error reading filter file {filepath}: {e}")

    return patterns


def list_filter_files() -> Dict[str, List[str]]:
    """
    Scan the filters directory for BL_*.txt and WL_*.txt files.

    Returns:
        {"blacklist": ["BL_default", ...], "whitelist": ["WL_geopolitical", ...]}
        Names are returned without the .txt extension.
    """
    result = {"blacklist": [], "whitelist": []}
    if not FILTERS_DIR.is_dir():
        logger.warning(f"Filters directory not found: {FILTERS_DIR}")
        return result

    for f in sorted(FILTERS_DIR.glob('*.txt')):
        name = f.stem  # e.g. "BL_default"
        if name.startswith('BL_'):
            result["blacklist"].append(name)
        elif name.startswith('WL_'):
            result["whitelist"].append(name)

    return result


# ==================================================================
# HARDCODED FALLBACK PATTERNS
# ==================================================================

_FALLBACK_BLACKLIST = [
    r'\bsponsored\b', r'\badvertisement\b', r'\bpromotional\b',
    r'\bsubscribe now\b', r'\bsign up free\b', r'\bfree trial\b',
    r'\blottery\b', r'\bsweepstakes\b', r'\bgiveaway\b',
    r'\bhoroscope\b', r'\bzodiac\b', r'\bcrossword\b', r'\bsudoku\b',
    r'\brecipe of\b', r'\bcooking tips\b', r'\bfashion trends\b',
    r'\bnfl draft\b', r'\bnba playoffs\b', r'\bworld cup qualif\b',
    r'\btransfer news\b', r'\bfantasy football\b',
    r'\bcelebrity gossip\b', r'\bred carpet\b', r'\baward show\b',
    r'\breality tv\b', r'\bkardashians?\b',
    r"you won't believe", r'shocking reveal', r'this one trick',
    r'\d+ things you', r'what happened next',
]

_FALLBACK_WHITELIST = [
    r'\bmilitary\b', r'\bairstrikes?\b', r'\bbombing\b', r'\bmissiles?\b',
    r'\bwar\b', r'\bconflict\b', r'\binvasion\b', r'\boffensive\b',
    r'\bescalation\b', r'\binsurgency\b', r'\btroops?\b', r'\bmilitia\b',
    r'\bnuclear\b', r'\bartillery\b', r'\bshelling\b', r'\bdrone strike\b',
    r'\bcasualt(y|ies)\b', r'\bkilled\b', r'\bdeath toll\b', r'\bexplosion\b',
    r'\bterroris[mt]\b', r'\bhostage\b', r'\bassassination\b',
    r'\bceasefire\b', r'\bsanctions?\b', r'\bmartial law\b',
    r'\bukraine\b', r'\brussia\b', r'\bgaza\b', r'\bisrael\b',
    r'\biran\b', r'\bsyria\b', r'\byemen\b', r'\btaiwan\b',
    r'\bnorth korea\b', r'\bsudan\b', r'\bafghanistan\b',
    r'\bputin\b', r'\bzelensky\b', r'\bnato\b', r'\bunited nations\b',
    r'\bpentagon\b', r'\bcia\b', r'\bmossad\b', r'\bisis\b',
    r'\bcyber attack\b', r'\bransomware\b', r'\bdata breach\b',
    r'\bpipeline\b', r'\bpower grid\b', r'\binfrastructure attack\b',
    r'\brefugee\b', r'\bhumanitarian\b', r'\bearthquake\b', r'\btsunami\b',
]


# ==================================================================
# CONTENT FILTER CLASS
# ==================================================================

class ContentFilter:
    """
    Content filtering for RSS/scraped articles.

    Modes:
    - 'blacklist': Only reject blacklisted content
    - 'whitelist': Only accept whitelisted content
    - 'both': Apply both filters (whitelist overrides blacklist)

    Filter patterns are loaded from external files (BL_*.txt / WL_*.txt)
    in the filters/ directory. Falls back to hardcoded defaults if files
    are missing or corrupt.
    """

    def __init__(self, enabled: bool = True, mode: str = 'both',
                 log_rejected: bool = False,
                 bl_file: str = 'BL_default', wl_file: str = 'WL_geopolitical'):
        self.enabled = enabled
        self.mode = mode
        self.log_rejected = log_rejected

        # Track active file names
        self.active_bl_file = bl_file
        self.active_wl_file = wl_file

        # Load patterns and compile
        self._load_and_compile(bl_file, wl_file)

    def _load_and_compile(self, bl_file: str, wl_file: str) -> None:
        """Load patterns from files (with fallback) and compile regexes."""
        # Load blacklist
        bl_path = FILTERS_DIR / f"{bl_file}.txt"
        bl_patterns = _load_patterns_from_file(bl_path)
        if not bl_patterns:
            logger.warning(
                f"No valid patterns from {bl_file}.txt — using fallback blacklist "
                f"({len(_FALLBACK_BLACKLIST)} patterns)"
            )
            bl_patterns = _FALLBACK_BLACKLIST

        # Load whitelist
        wl_path = FILTERS_DIR / f"{wl_file}.txt"
        wl_patterns = _load_patterns_from_file(wl_path)
        if not wl_patterns:
            logger.warning(
                f"No valid patterns from {wl_file}.txt — using fallback whitelist "
                f"({len(_FALLBACK_WHITELIST)} patterns)"
            )
            wl_patterns = _FALLBACK_WHITELIST

        # Store counts for diagnostics
        self.bl_count = len(bl_patterns)
        self.wl_count = len(wl_patterns)

        # Compile regexes
        self.blacklist_regex = re.compile(
            '|'.join(bl_patterns), re.IGNORECASE
        )
        self.whitelist_regex = re.compile(
            '|'.join(wl_patterns), re.IGNORECASE
        )

        self.active_bl_file = bl_file
        self.active_wl_file = wl_file

        logger.info(
            f"Content filter: mode={self.mode}, "
            f"BL={bl_file} ({self.bl_count}), WL={wl_file} ({self.wl_count})"
        )

    def set_mode(self, mode: str) -> bool:
        """Change filter mode at runtime."""
        if mode not in ('blacklist', 'whitelist', 'both'):
            return False
        self.mode = mode
        logger.info(f"Content filter mode changed to: {mode}")
        return True

    def set_filters(self, bl_file: str = None, wl_file: str = None) -> bool:
        """
        Switch active filter files at runtime. Recompiles regexes.

        Args:
            bl_file: New blacklist file name (without .txt), or None to keep current
            wl_file: New whitelist file name (without .txt), or None to keep current

        Returns:
            True if recompilation succeeded
        """
        bl = bl_file or self.active_bl_file
        wl = wl_file or self.active_wl_file

        # Validate files exist before switching
        bl_path = FILTERS_DIR / f"{bl}.txt"
        wl_path = FILTERS_DIR / f"{wl}.txt"

        if bl_file and not bl_path.exists():
            logger.warning(f"Blacklist file not found: {bl_path}")
            return False
        if wl_file and not wl_path.exists():
            logger.warning(f"Whitelist file not found: {wl_path}")
            return False

        self._load_and_compile(bl, wl)
        return True

    def get_status(self) -> Dict:
        """Get current filter status for API/dashboard."""
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "active_bl": self.active_bl_file,
            "active_wl": self.active_wl_file,
            "bl_count": self.bl_count,
            "wl_count": self.wl_count,
        }

    def should_accept(self, title: str, description: str = '',
                      skip_whitelist: bool = False) -> Tuple[bool, str]:
        if not self.enabled:
            return True, 'filter_disabled'

        text = f"{title} {description}".lower()

        bl_hit = self.mode in ('blacklist', 'both') and self.blacklist_regex.search(text)
        wl_hit = (not skip_whitelist and self.mode in ('whitelist', 'both')
                  and self.whitelist_regex.search(text))

        if self.mode == 'blacklist':
            if bl_hit:
                return False, 'blacklist_match'
        elif self.mode == 'whitelist':
            if not skip_whitelist and not wl_hit:
                return False, 'whitelist_fail'
        elif self.mode == 'both':
            if skip_whitelist:
                if bl_hit:
                    return False, 'blacklist_match'
            elif wl_hit:
                return True, 'whitelist_override'
            elif bl_hit:
                return False, 'blacklist_match'

        return True, 'accepted'

    def matches_whitelist(self, text: str) -> bool:
        return bool(self.whitelist_regex.search(text))


_content_filter: Optional[ContentFilter] = None


def get_content_filter() -> ContentFilter:
    """Get or create singleton content filter instance."""
    global _content_filter
    if _content_filter is None:
        from config import config
        _content_filter = ContentFilter(
            enabled=getattr(config, 'CONTENT_FILTER_ENABLED', True),
            mode=getattr(config, 'CONTENT_FILTER_MODE', 'both'),
            log_rejected=getattr(config, 'CONTENT_FILTER_LOG_REJECTED', False),
            bl_file=getattr(config, 'CONTENT_FILTER_BL', 'BL_default'),
            wl_file=getattr(config, 'CONTENT_FILTER_WL', 'WL_geopolitical'),
        )
    return _content_filter
