"""
Observer Lite - Translation Service
Backend: NLLB-200 via CTranslate2 (no PyTorch dependency)

Features:
- NLLB-200 seq2seq translation (purpose-built, 200 languages)
- CTranslate2 inference: fast CPU/GPU, int8/float16 quantization
- Native batch translation for throughput
- Automatic language detection (via langdetect library)
- Translation to English
- Caching to avoid re-translating
- Async batch translation
- PERSISTENT JSON CACHE (survives restarts)

===============================================================================
CHANGELOG:
-------------------------------------------------------------------------------
2026-02-17 | Mr Cat + Claude | Migrate NLLB from HuggingFace to CTranslate2
    - Changed: Replaced transformers + torch with ctranslate2 + sentencepiece
    - Benefit: Drops ~2GB PyTorch dependency, faster inference, int8 support
    - Changed: NLLB_MODEL now points to CTranslate2-converted model directory
    - New: NLLB_SP_MODEL config for sentencepiece model path
    - New: NLLB_DEVICE (cpu/cuda/auto) and NLLB_COMPUTE_TYPE (int8/float16/auto)
    - Kept: All public API, caching, batch logic, FLORES codes unchanged
-------------------------------------------------------------------------------
2026-02-15 | Mr Cat + Claude | NLLB-200 translation backend
    - New: facebook/nllb-200-distilled-600M as primary translation model
    - New: FLORES-200 language code mapping (ISO 639-1 → NLLB codes)
    - New: Lazy model loading with thread-safe initialization
    - New: True GPU batch translation via NLLB pipeline
    - Changed: AI_TRANSLATOR_MODE default 'local' → 'nllb'
    - Removed: Ollama fallback (Lite uses NLLB only)
    - Removed: Groq API (no longer used)
-------------------------------------------------------------------------------
2026-02-12 | Mr Cat + Claude | Translation cache optimization
    - Changed: TTL 72 hours → 30 days (translated text never changes)
    - Changed: Max size 3,000 → 30,000 (global multi-country collection)
    - Changed: Dict → OrderedDict for O(1) LRU eviction (was O(n) scan)
    - New: Language detection LRU cache (10,000 entries, avoids re-running langdetect)
    - New: Cache loads sorted by timestamp to preserve LRU order across restarts
    - New: Stats report cache capacity and detection cache size
-------------------------------------------------------------------------------
2026-02-01 | Mr Cat + Claude | Added persistent JSON cache
    - New: Cache persists to data/translation_cache.json
    - New: Auto-loads cache on startup
    - New: Auto-saves every 50 new translations or 5 minutes
    - New: Graceful save on shutdown via save_cache()
    - Benefit: Saves API costs across restarts
-------------------------------------------------------------------------------
2026-02-01 | Mr Cat + Claude | Replaced heuristic detection with langdetect
    - New: Uses langdetect library for 55+ language support
    - New: Detects ALL Latin-based languages (Spanish, French, German, etc.)
    - New: Falls back to character heuristics if langdetect fails
    - Requires: pip install langdetect
===============================================================================
"""

import json
import re
import asyncio
import aiohttp
import hashlib
import atexit
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta


# =============================================================================
# TRANSLATION RESULT
# @added 2026-02-05 by Mr Cat + Claude - Structured translation metadata
# =============================================================================
@dataclass
class TranslationResult:
    """Result of a translation operation with metadata"""
    text: str  # The translated text (or original if not translated)
    was_translated: bool  # Whether translation actually occurred
    source_language: str  # Detected source language code (e.g., 'ru', 'en')
    translation_source: Optional[str] = None  # 'cache', 'nllb', or None if not translated

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# NLLB SUPPORT via CTranslate2 (facebook/nllb-200-distilled-600M)
# =============================================================================
HAS_NLLB = False
try:
    import ctranslate2
    import sentencepiece as spm
    HAS_NLLB = True
except ImportError:
    logger.debug("ctranslate2/sentencepiece not installed - NLLB translation unavailable")

# =============================================================================
# LANGUAGE DETECTION - using langdetect library
# =============================================================================
HAS_LANGDETECT = False
try:
    from langdetect import detect, detect_langs, DetectorFactory, LangDetectException
    # Make detection deterministic (same result for same input)
    DetectorFactory.seed = 0
    HAS_LANGDETECT = True
    logger.info("langdetect library loaded - comprehensive language detection enabled")
except ImportError:
    logger.warning("langdetect not installed - using fallback character detection")
    logger.warning("Install with: pip install langdetect")

# =============================================================================
# CACHE PERSISTENCE CONFIG
# =============================================================================
CACHE_FILE_PATH = Path("data/translation_cache.json")
CACHE_SAVE_INTERVAL = 50  # Save after this many new translations
CACHE_SAVE_TIMEOUT = 300  # Or save after 5 minutes of changes


class TranslationService:
    """Handles translation of non-English content via NLLB-200."""

    # Languages we support translating (ISO 639-1 codes)
    SUPPORTED_LANGUAGES = {
        # Cyrillic
        'ru': 'Russian',
        'uk': 'Ukrainian',
        'bg': 'Bulgarian',
        'sr': 'Serbian',
        'mk': 'Macedonian',
        'be': 'Belarusian',
        
        # Middle East / North Africa
        'ar': 'Arabic',
        'he': 'Hebrew',
        'fa': 'Persian',
        'ur': 'Urdu',
        
        # East Asia
        'zh-cn': 'Chinese (Simplified)',
        'zh-tw': 'Chinese (Traditional)',
        'zh': 'Chinese',  # Generic
        'ja': 'Japanese',
        'ko': 'Korean',
        'vi': 'Vietnamese',
        'th': 'Thai',
        
        # Europe (Latin-based)
        'es': 'Spanish',
        'fr': 'French',
        'de': 'German',
        'pt': 'Portuguese',
        'it': 'Italian',
        'pl': 'Polish',
        'nl': 'Dutch',
        'ro': 'Romanian',
        'cs': 'Czech',
        'sk': 'Slovak',
        'hu': 'Hungarian',
        'el': 'Greek',
        'tr': 'Turkish',
        'sv': 'Swedish',
        'da': 'Danish',
        'no': 'Norwegian',
        'fi': 'Finnish',
        'hr': 'Croatian',
        'sl': 'Slovenian',
        'et': 'Estonian',
        'lv': 'Latvian',
        'lt': 'Lithuanian',
        
        # South Asia
        'hi': 'Hindi',
        'bn': 'Bengali',
        'ta': 'Tamil',
        'te': 'Telugu',
        'mr': 'Marathi',
        'gu': 'Gujarati',
        'kn': 'Kannada',
        'ml': 'Malayalam',
        'ne': 'Nepali',
        'pa': 'Punjabi',

        # Caucasus / Southeast Asia
        'hy': 'Armenian',
        'km': 'Khmer',

        # Europe (other)
        'ca': 'Catalan',
        'sq': 'Albanian',
        'cy': 'Welsh',

        # Africa
        'so': 'Somali',

        # Other
        'id': 'Indonesian',
        'ms': 'Malay',
        'tl': 'Tagalog',
        'sw': 'Swahili',
        'af': 'Afrikaans',
    }

    # ISO 639-1 → FLORES-200 language codes for NLLB
    # NLLB uses {lang}_{script} format (e.g., 'rus_Cyrl')
    FLORES_CODES = {
        # Cyrillic
        'ru': 'rus_Cyrl', 'uk': 'ukr_Cyrl', 'bg': 'bul_Cyrl',
        'sr': 'srp_Cyrl', 'mk': 'mkd_Cyrl', 'be': 'bel_Cyrl',
        # Middle East / North Africa
        'ar': 'arb_Arab', 'he': 'heb_Hebr', 'fa': 'pes_Arab', 'ur': 'urd_Arab',
        # East Asia
        'zh-cn': 'zho_Hans', 'zh-tw': 'zho_Hant', 'zh': 'zho_Hans',
        'ja': 'jpn_Jpan', 'ko': 'kor_Hang', 'vi': 'vie_Latn', 'th': 'tha_Thai',
        # Europe (Latin-based)
        'es': 'spa_Latn', 'fr': 'fra_Latn', 'de': 'deu_Latn', 'pt': 'por_Latn',
        'it': 'ita_Latn', 'pl': 'pol_Latn', 'nl': 'nld_Latn', 'ro': 'ron_Latn',
        'cs': 'ces_Latn', 'sk': 'slk_Latn', 'hu': 'hun_Latn', 'el': 'ell_Grek',
        'tr': 'tur_Latn', 'sv': 'swe_Latn', 'da': 'dan_Latn', 'no': 'nob_Latn',
        'fi': 'fin_Latn', 'hr': 'hrv_Latn', 'sl': 'slv_Latn', 'et': 'est_Latn',
        'lv': 'lvs_Latn', 'lt': 'lit_Latn',
        # South Asia
        'hi': 'hin_Deva', 'bn': 'ben_Beng', 'ta': 'tam_Taml',
        'te': 'tel_Telu', 'mr': 'mar_Deva',
        'gu': 'guj_Gujr', 'kn': 'kan_Knda', 'ml': 'mal_Mlym',
        'ne': 'npi_Deva', 'pa': 'pan_Guru',
        # Caucasus / Southeast Asia
        'hy': 'hye_Armn', 'km': 'khm_Khmr',
        # Europe (other)
        'ca': 'cat_Latn', 'sq': 'als_Latn', 'cy': 'cym_Latn',
        # Africa
        'so': 'som_Latn',
        # Other
        'id': 'ind_Latn', 'ms': 'zsm_Latn', 'tl': 'tgl_Latn',
        'sw': 'swh_Latn', 'af': 'afr_Latn',
    }

    NLLB_TARGET_LANG = 'eng_Latn'

    def __init__(self):
        """Initialize translation service"""
        self._use_nllb = getattr(config, 'TRANSLATION_USE_NLLB', False)

        # Determine if we can enable based on NLLB availability
        self.enabled = self._use_nllb and getattr(config, 'TRANSLATION_ENABLED', True) and HAS_NLLB

        # NLLB model state (lazy-loaded on first translate call)
        self._nllb_translator = None   # ctranslate2.Translator
        self._nllb_sp = None           # sentencepiece.SentencePieceProcessor
        self._nllb_lock = threading.Lock()
        self._nllb_load_time_ms = 0

        # CTranslate2 runtime-tunable translation parameters (persisted to .env)
        self.nllb_beam_size: int = getattr(config, 'NLLB_BEAM_SIZE', 1)
        self.nllb_length_penalty: float = getattr(config, 'NLLB_LENGTH_PENALTY', 1.0)
        self.nllb_repetition_penalty: float = getattr(config, 'NLLB_REPETITION_PENALTY', 1.0)
        self.nllb_no_repeat_ngram_size: int = getattr(config, 'NLLB_NO_REPEAT_NGRAM', 0)
        self.nllb_max_batch_size: int = getattr(config, 'NLLB_BATCH_SIZE', 16)
        self.nllb_batch_type: str = getattr(config, 'NLLB_BATCH_TYPE', 'examples')
        self.nllb_max_decoding_length: int = getattr(config, 'NLLB_MAX_LENGTH', 512)
        _max_input = getattr(config, 'NLLB_MAX_INPUT_LENGTH', 0)
        self.nllb_max_input_length: int = _max_input if _max_input > 0 else self.nllb_max_decoding_length
        self.nllb_sampling_topk: int = getattr(config, 'NLLB_SAMPLING_TOPK', 1)
        self.nllb_sampling_topp: float = getattr(config, 'NLLB_SAMPLING_TOPP', 1.0)
        self.nllb_sampling_temperature: float = getattr(config, 'NLLB_SAMPLING_TEMPERATURE', 1.0)

        # In-memory cache: hash -> (translation, source_lang, timestamp_iso)
        # OrderedDict maintains insertion order for O(1) LRU eviction
        self._cache: OrderedDict[str, Tuple[str, str, str]] = OrderedDict()
        self._cache_ttl = timedelta(days=30)
        self._cache_max_size = getattr(config, 'TRANSLATION_CACHE_MAX_SIZE', 30_000)

        # Language detection cache: hash -> detected_lang_code
        # Avoids re-running langdetect on the same text (CPU-intensive)
        self._lang_cache: OrderedDict[str, str] = OrderedDict()
        self._lang_cache_max_size = 10_000

        # Persistence tracking
        self._unsaved_count = 0
        self._last_save_time = datetime.now()
        self._cache_file = CACHE_FILE_PATH

        # Statistics
        self.stats = {
            'translations': 0,
            'cache_hits': 0,
            'errors': 0,
            'chars_translated': 0,
            'cache_loaded_from_disk': 0,
            'batch_translations': 0,
            'languages_detected': {}  # Track which languages we see
        }

        # Load persistent cache on startup
        self._load_cache()

        # Register save on exit
        atexit.register(self._save_cache_sync)

        if self.enabled:
            nllb_model = getattr(config, 'NLLB_MODEL', 'facebook/nllb-200-distilled-600M')
            logger.info(f"Translation service initialized: mode=nllb ({nllb_model}), cache={len(self._cache)} entries")
            logger.info("NLLB model will be lazy-loaded on first translation request")
            logger.info(f"Supported languages: {len(self.SUPPORTED_LANGUAGES)} ({len(self.FLORES_CODES)} with NLLB codes)")
        else:
            if not getattr(config, 'TRANSLATION_ENABLED', True):
                logger.info("Translation service disabled (AI_TRANSLATOR_MODE=off)")
            elif self._use_nllb and not HAS_NLLB:
                logger.warning("Translation disabled: ctranslate2/sentencepiece not installed (pip install ctranslate2 sentencepiece)")
            else:
                logger.info("Translation service disabled")
    
    # =========================================================================
    # CACHE PERSISTENCE
    # =========================================================================
    
    def _load_cache(self) -> None:
        """Load cache from JSON file on startup"""
        try:
            if not self._cache_file.exists():
                logger.debug("No translation cache file found, starting fresh")
                return
            
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate structure
            if not isinstance(data, dict) or 'entries' not in data:
                logger.warning("Invalid cache file format, starting fresh")
                return
            
            # Load entries, filtering expired ones
            now = datetime.now()
            loaded = 0
            expired = 0
            
            # Sort by timestamp so oldest entries are first in OrderedDict
            # This preserves correct LRU eviction order after restart
            entries_with_ts = []
            for key, entry in data.get('entries', {}).items():
                try:
                    translation = entry.get('translation', '')
                    source_lang = entry.get('source_lang', 'unknown')
                    timestamp_str = entry.get('timestamp', '')

                    # Check if expired
                    if timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str)
                        if now - timestamp > self._cache_ttl:
                            expired += 1
                            continue
                    else:
                        timestamp = datetime.min

                    entries_with_ts.append((timestamp, key, translation, source_lang, timestamp_str))
                    loaded += 1

                except Exception as e:
                    logger.debug(f"Skipping invalid cache entry: {e}")

            # Insert oldest first so newest are at end (LRU order)
            entries_with_ts.sort(key=lambda x: x[0])
            for _, key, translation, source_lang, timestamp_str in entries_with_ts:
                self._cache[key] = (translation, source_lang, timestamp_str)
            
            self.stats['cache_loaded_from_disk'] = loaded
            logger.info(f"Loaded {loaded} translations from cache ({expired} expired, skipped)")
            
        except json.JSONDecodeError as e:
            logger.warning(f"Cache file corrupted, starting fresh: {e}")
        except Exception as e:
            logger.error(f"Error loading translation cache: {e}")
    
    def _save_cache(self) -> None:
        """Save cache to JSON file"""
        try:
            # Ensure directory exists
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Build cache structure
            entries = {}
            for key, (translation, source_lang, timestamp_str) in self._cache.items():
                entries[key] = {
                    'translation': translation,
                    'source_lang': source_lang,
                    'timestamp': timestamp_str
                }
            
            data = {
                'version': '1.0',
                'saved_at': datetime.now().isoformat(),
                'entry_count': len(entries),
                'entries': entries
            }
            
            # Write atomically (write to temp, then rename)
            temp_file = self._cache_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            temp_file.replace(self._cache_file)
            
            self._unsaved_count = 0
            self._last_save_time = datetime.now()
            logger.debug(f"Saved {len(entries)} translations to cache file")
            
        except Exception as e:
            logger.error(f"Error saving translation cache: {e}")
    
    def _save_cache_sync(self) -> None:
        """Synchronous save for atexit handler"""
        if self._unsaved_count > 0:
            logger.info(f"Saving {self._unsaved_count} unsaved translations on shutdown...")
            self._save_cache()
    
    def _maybe_save_cache(self) -> None:
        """Check if cache should be saved (called after adding entries)"""
        # Save if we have enough unsaved entries
        if self._unsaved_count >= CACHE_SAVE_INTERVAL:
            self._save_cache()
            return
        
        # Or if enough time has passed since last save
        if (datetime.now() - self._last_save_time).total_seconds() > CACHE_SAVE_TIMEOUT:
            if self._unsaved_count > 0:
                self._save_cache()
    
    def save_cache(self) -> None:
        """Public method to force cache save (call on graceful shutdown)"""
        if self._unsaved_count > 0:
            self._save_cache()
            logger.info(f"Translation cache saved: {len(self._cache)} entries")
    
    # =========================================================================
    # CACHE OPERATIONS
    # =========================================================================
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _check_cache(self, text: str) -> Optional[Tuple[str, str]]:
        """
        Check if translation is cached

        Returns:
            Tuple of (translation, source_lang) or None
        """
        key = self._get_cache_key(text)
        if key in self._cache:
            translation, source_lang, timestamp_str = self._cache[key]

            # Check TTL
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    if datetime.now() - timestamp > self._cache_ttl:
                        del self._cache[key]
                        return None
                except (ValueError, TypeError):
                    pass  # Keep entry if timestamp parsing fails

            # Move to end (most recently used) for LRU ordering
            self._cache.move_to_end(key)
            self.stats['cache_hits'] += 1
            return translation, source_lang

        return None
    
    def _add_to_cache(self, text: str, translation: str, source_lang: str) -> None:
        """Add translation to cache"""
        key = self._get_cache_key(text)

        # If key already exists, remove it first so it moves to end
        if key in self._cache:
            del self._cache[key]

        # Evict oldest (front of OrderedDict) if cache is full — O(1)
        while len(self._cache) >= self._cache_max_size:
            self._cache.popitem(last=False)

        timestamp_str = datetime.now().isoformat()
        self._cache[key] = (translation, source_lang, timestamp_str)

        # Track unsaved changes and maybe save
        self._unsaved_count += 1
        self._maybe_save_cache()
    
    # =========================================================================
    # LANGUAGE DETECTION
    # =========================================================================
    
    def detect_language(self, text: str) -> str:
        """
        Detect the language of text

        Uses an in-memory LRU cache (10,000 entries) to avoid redundant
        langdetect calls. Falls back to character heuristics if langdetect
        is unavailable.

        Args:
            text: Text to analyze

        Returns:
            ISO 639-1 language code (e.g., 'en', 'ru', 'es', 'ar')
        """
        if not text or not text.strip():
            return 'en'

        # Check language detection cache first
        cache_key = hashlib.md5(text.encode('utf-8')).hexdigest()
        if cache_key in self._lang_cache:
            self._lang_cache.move_to_end(cache_key)
            return self._lang_cache[cache_key]

        # Run actual detection
        detected = self._detect_language_uncached(text)

        # Store in LRU cache — evict oldest if full
        if len(self._lang_cache) >= self._lang_cache_max_size:
            self._lang_cache.popitem(last=False)
        self._lang_cache[cache_key] = detected

        return detected

    def _detect_language_uncached(self, text: str) -> str:
        """Run language detection without cache (langdetect → fallback)"""
        # Try langdetect first (if available)
        if HAS_LANGDETECT:
            try:
                detected = detect(text)

                # Track what we're seeing
                self.stats['languages_detected'][detected] = \
                    self.stats['languages_detected'].get(detected, 0) + 1

                # Check if it's a supported language
                if detected in self.SUPPORTED_LANGUAGES:
                    return detected

                # Handle Chinese variants
                if detected.startswith('zh'):
                    return 'zh'

                # English or other language we don't translate from — just pass through
                if detected != 'en':
                    logger.debug(f"Detected unsupported language: {detected}")
                return detected

            except LangDetectException as e:
                logger.debug(f"langdetect failed, using fallback: {e}")
            except Exception as e:
                logger.debug(f"langdetect error: {e}")

        # Fallback: character-based heuristics
        return self._detect_language_fallback(text)
    
    def _detect_language_fallback(self, text: str) -> str:
        """
        Fallback language detection using character analysis
        
        Used when langdetect is unavailable or fails.
        """
        if not text or not text.strip():
            return 'en'
        
        text_sample = text[:500]
        sample_len = len(text_sample)
        
        if sample_len == 0:
            return 'en'
        
        # Cyrillic (Russian, Ukrainian, etc.)
        cyrillic_chars = sum(1 for c in text_sample if '\u0400' <= c <= '\u04FF')
        if cyrillic_chars > sample_len * 0.3:
            # Try to distinguish Russian vs Ukrainian
            ukrainian_chars = sum(1 for c in text_sample if c in 'іїєґІЇЄҐ')
            return 'uk' if ukrainian_chars > 2 else 'ru'
        
        # Arabic script
        arabic_chars = sum(1 for c in text_sample if '\u0600' <= c <= '\u06FF')
        if arabic_chars > sample_len * 0.3:
            # Check for Persian-specific characters
            persian_chars = sum(1 for c in text_sample if c in 'پچژگک')
            if persian_chars > 2:
                return 'fa'
            return 'ar'
        
        # Hebrew
        hebrew_chars = sum(1 for c in text_sample if '\u0590' <= c <= '\u05FF')
        if hebrew_chars > sample_len * 0.3:
            return 'he'
        
        # Chinese
        chinese_chars = sum(1 for c in text_sample if '\u4e00' <= c <= '\u9fff')
        if chinese_chars > sample_len * 0.2:
            return 'zh'
        
        # Japanese (Hiragana/Katakana)
        japanese_chars = sum(1 for c in text_sample if '\u3040' <= c <= '\u30FF')
        if japanese_chars > sample_len * 0.1:
            return 'ja'
        
        # Korean
        korean_chars = sum(1 for c in text_sample if '\uAC00' <= c <= '\uD7AF')
        if korean_chars > sample_len * 0.2:
            return 'ko'
        
        # Thai
        thai_chars = sum(1 for c in text_sample if '\u0E00' <= c <= '\u0E7F')
        if thai_chars > sample_len * 0.2:
            return 'th'
        
        # Armenian
        armenian_chars = sum(1 for c in text_sample if '\u0530' <= c <= '\u058F')
        if armenian_chars > sample_len * 0.3:
            return 'hy'

        # Khmer (Cambodian)
        khmer_chars = sum(1 for c in text_sample if '\u1780' <= c <= '\u17FF')
        if khmer_chars > sample_len * 0.2:
            return 'km'

        # Gujarati
        gujarati_chars = sum(1 for c in text_sample if '\u0A80' <= c <= '\u0AFF')
        if gujarati_chars > sample_len * 0.3:
            return 'gu'

        # Kannada
        kannada_chars = sum(1 for c in text_sample if '\u0C80' <= c <= '\u0CFF')
        if kannada_chars > sample_len * 0.3:
            return 'kn'

        # Malayalam
        malayalam_chars = sum(1 for c in text_sample if '\u0D00' <= c <= '\u0D7F')
        if malayalam_chars > sample_len * 0.3:
            return 'ml'

        # Gurmukhi (Punjabi)
        gurmukhi_chars = sum(1 for c in text_sample if '\u0A00' <= c <= '\u0A7F')
        if gurmukhi_chars > sample_len * 0.3:
            return 'pa'

        # Greek
        greek_chars = sum(1 for c in text_sample if '\u0370' <= c <= '\u03FF')
        if greek_chars > sample_len * 0.3:
            return 'el'

        # Default to English for Latin scripts
        # (langdetect handles Latin differentiation much better)
        return 'en'

    def _get_detection_confidence(self, text: str, expected_lang: str) -> float:
        """Return langdetect's probability for a specific language on the given text."""
        if not HAS_LANGDETECT:
            return 0.0
        try:
            results = detect_langs(text)
            for r in results:
                if r.lang == expected_lang:
                    return r.prob
        except Exception:
            pass
        return 0.0

    # Latin-script languages that langdetect often confuses with English on
    # short text. For these, we require high detection confidence (>= 0.85)
    # rather than blanket-skipping them.
    # @added 2026-02-05 by Mr Cat + Claude - Fix false positive translations
    # @changed 2026-02-26 by Mr Cat + Claude - Use confidence threshold
    #   instead of blanket skip (was blocking real Swedish/Norwegian/etc.)
    CONFUSABLE_LANGUAGES = {'da', 'nl', 'no', 'sv', 'af', 'cy', 'id', 'so', 'sw', 'tl'}
    CONFUSABLE_MIN_CONFIDENCE = 0.85

    def needs_translation(self, text: str) -> bool:
        """
        Quick check if text likely needs translation

        Args:
            text: Text to check

        Returns:
            True if text appears to be non-English
        """
        if not text or len(text) < 10:
            return False

        detected = self.detect_language(text)

        if detected == 'en':
            return False

        # For confusable Latin-script languages, require high confidence
        # to avoid false-positive translations of English text
        if detected in self.CONFUSABLE_LANGUAGES:
            confidence = self._get_detection_confidence(text, detected)
            if confidence < self.CONFUSABLE_MIN_CONFIDENCE:
                logger.debug(
                    f"Skipping translation: {detected} confidence {confidence:.2f} "
                    f"< {self.CONFUSABLE_MIN_CONFIDENCE} threshold"
                )
                return False

        return True
    
    # =========================================================================
    # TRANSLATION
    # =========================================================================
    
    async def translate(self, text: str, source_lang: Optional[str] = None) -> Tuple[str, str]:
        """
        Translate text to English
        
        Args:
            text: Text to translate
            source_lang: Source language code (auto-detected if None)
            
        Returns:
            Tuple of (translated_text, detected_source_language)
        """
        # Check runtime mode (supports live switching via dashboard)
        if not getattr(config, 'TRANSLATION_ENABLED', True):
            return text, 'en'

        if not text or not text.strip():
            return text, 'en'

        # Detect source language if not provided
        if not source_lang:
            source_lang = self.detect_language(text)

        # Skip if already English
        if source_lang == 'en':
            return text, 'en'

        # Check cache
        cached = self._check_cache(text)
        if cached:
            translation, cached_lang = cached
            # Record cache hit for telemetry
            try:
                from services.metrics import metrics_collector
                metrics_collector.record_cache_hit()
            except ImportError:
                pass
            logger.debug(f"Translation cache hit for {len(text)} chars ({cached_lang})")
            return translation, cached_lang

        # Route to NLLB backend
        use_nllb = getattr(config, 'TRANSLATION_USE_NLLB', False)

        try:
            if use_nllb:
                translation = await self._call_nllb_translate(text, source_lang)
                backend = "NLLB"
            else:
                logger.debug("Translation skipped: no backend configured (set AI_TRANSLATOR_MODE to nllb)")
                return text, source_lang

            # Cache result (now includes source_lang)
            self._add_to_cache(text, translation, source_lang)

            # Update stats
            self.stats['translations'] += 1
            self.stats['chars_translated'] += len(text)

            # Record successful call for telemetry
            try:
                from services.metrics import metrics_collector
                metrics_collector.record_translator_call()
            except ImportError:
                pass

            logger.info(f"Translated {len(text)} chars from {source_lang} ({backend})")
            return translation, source_lang

        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"Translation error: {e}")
            return text, source_lang

    async def translate_with_metadata(self, text: str, source_lang: Optional[str] = None) -> TranslationResult:
        """
        Translate text to English with full metadata.

        Translation priority:
          1. Skip if already English
          2. Check in-memory LRU cache (30-day TTL)
          3. NLLB seq2seq translation

        @added 2026-02-05 by Mr Cat + Claude - Translation tracking for badges

        Args:
            text: Text to translate
            source_lang: Source language code (auto-detected if None)

        Returns:
            TranslationResult with text, was_translated, source_language, translation_source
        """
        # Check runtime mode (supports live switching via dashboard)
        if not getattr(config, 'TRANSLATION_ENABLED', True):
            return TranslationResult(text=text, was_translated=False, source_language='en', translation_source=None)

        if not text or not text.strip():
            return TranslationResult(text=text, was_translated=False, source_language='en', translation_source=None)

        # Detect source language if not provided
        if not source_lang:
            source_lang = self.detect_language(text)

        # Skip if already English
        if source_lang == 'en':
            return TranslationResult(text=text, was_translated=False, source_language='en', translation_source=None)

        # Check in-memory cache (fast path — O(1) hash lookup)
        cached = self._check_cache(text)
        if cached:
            translation, cached_lang = cached
            # Record cache hit for telemetry
            try:
                from services.metrics import metrics_collector
                metrics_collector.record_cache_hit()
            except ImportError:
                pass
            logger.debug(f"Translation cache hit for {len(text)} chars ({cached_lang})")
            return TranslationResult(
                text=translation,
                was_translated=True,
                source_language=cached_lang,
                translation_source='cache'
            )

        # Route to NLLB translation backend
        use_nllb = getattr(config, 'TRANSLATION_USE_NLLB', False)

        try:
            if use_nllb:
                translation = await self._call_nllb_translate(text, source_lang)
                backend = 'nllb'
            else:
                logger.debug("Translation skipped: no backend configured")
                return TranslationResult(text=text, was_translated=False, source_language=source_lang, translation_source=None)

            # Cache result in the in-memory LRU cache
            self._add_to_cache(text, translation, source_lang)

            # Update stats
            self.stats['translations'] += 1
            self.stats['chars_translated'] += len(text)

            # Record successful call for telemetry
            try:
                from services.metrics import metrics_collector
                metrics_collector.record_translator_call()
            except ImportError:
                pass

            logger.info(f"Translated {len(text)} chars from {source_lang} ({backend})")
            return TranslationResult(
                text=translation,
                was_translated=True,
                source_language=source_lang,
                translation_source=backend
            )

        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"Translation error: {e}")
            return TranslationResult(text=text, was_translated=False, source_language=source_lang, translation_source=None)

    # =========================================================================
    # NLLB TRANSLATION
    # =========================================================================

    def _load_nllb_model(self) -> bool:
        """
        Lazy-load CTranslate2 translator and sentencepiece tokenizer (thread-safe, called once).

        Returns True if model loaded successfully.
        """
        if self._nllb_translator is not None:
            return True

        with self._nllb_lock:
            # Double-check after acquiring lock
            if self._nllb_translator is not None:
                return True

            if not HAS_NLLB:
                logger.error("Cannot load NLLB: ctranslate2/sentencepiece not installed")
                return False

            model_path = getattr(config, 'NLLB_MODEL', 'models/nllb-200-distilled-600M-ct2')
            sp_model_path = getattr(config, 'NLLB_SP_MODEL', f'{model_path}/sentencepiece.bpe.model')
            device = getattr(config, 'NLLB_DEVICE', 'auto')
            compute_type = getattr(config, 'NLLB_COMPUTE_TYPE', 'auto')
            inter_threads = getattr(config, 'NLLB_INTER_THREADS', 1)
            intra_threads = getattr(config, 'NLLB_INTRA_THREADS', 4)
            logger.info(
                f"Loading NLLB CTranslate2 model: {model_path} "
                f"(device={device}, compute={compute_type}, "
                f"inter_threads={inter_threads}, intra_threads={intra_threads})"
            )
            start = time.monotonic()

            try:
                self._nllb_sp = spm.SentencePieceProcessor()
                self._nllb_sp.Load(sp_model_path)
                self._nllb_translator = ctranslate2.Translator(
                    model_path,
                    device=device,
                    compute_type=compute_type,
                    inter_threads=inter_threads,
                    intra_threads=intra_threads,
                )
                self._nllb_load_time_ms = int((time.monotonic() - start) * 1000)
                logger.info(f"NLLB CTranslate2 model loaded in {self._nllb_load_time_ms}ms")
                return True
            except Exception as e:
                logger.error(f"Failed to load NLLB model: {e}")
                self._nllb_translator = None
                self._nllb_sp = None
                return False

    def _get_flores_code(self, iso_code: str) -> Optional[str]:
        """Map ISO 639-1 language code to FLORES-200 code for NLLB."""
        return self.FLORES_CODES.get(iso_code)

    def _tokenize(self, text: str, src_lang: str) -> List[str]:
        """Tokenize text with sentencepiece for CTranslate2 NLLB input.

        Format: [src_lang] + bpe_tokens + [</s>]
        The </s> end-of-sentence token is required for Transformers-converted
        models — CTranslate2 does NOT add it implicitly.
        """
        pieces = self._nllb_sp.Encode(text, out_type=str)
        return [src_lang] + pieces + ['</s>']

    def _detokenize(self, tokens: List[str]) -> str:
        """Detokenize CTranslate2 output tokens back to text.

        CTranslate2 returns the target_prefix (language tag) as the first
        token and </s> as the last. Strip only those, then decode the rest
        with sentencepiece.
        """
        if not tokens:
            return ''
        # Strip leading language tag (e.g. 'eng_Latn') if present
        start = 1 if tokens[0] == self.NLLB_TARGET_LANG else 0
        # Strip trailing </s>
        end = len(tokens)
        while end > start and tokens[end - 1] in ('</s>', '<s>'):
            end -= 1
        return self._nllb_sp.DecodePieces(tokens[start:end])

    def _build_translate_kwargs(self) -> dict:
        """Build CTranslate2 translate_batch kwargs from current tuning params."""
        kwargs = {
            'max_decoding_length': self.nllb_max_decoding_length,
            'max_input_length': self.nllb_max_input_length,
            'beam_size': self.nllb_beam_size,
            'length_penalty': self.nllb_length_penalty,
            'repetition_penalty': self.nllb_repetition_penalty,
            'no_repeat_ngram_size': self.nllb_no_repeat_ngram_size,
        }
        # Sampling params only apply when beam_size == 1
        if self.nllb_beam_size == 1:
            kwargs['sampling_topk'] = self.nllb_sampling_topk
            kwargs['sampling_topp'] = self.nllb_sampling_topp
            kwargs['sampling_temperature'] = self.nllb_sampling_temperature
        return kwargs

    def _nllb_translate_sync(self, text: str, source_lang: str) -> str:
        """Run NLLB translation synchronously (called from executor)."""
        flores_src = self._get_flores_code(source_lang)
        if not flores_src:
            raise ValueError(f"No FLORES-200 code for language: {source_lang}")

        tokens = self._tokenize(text, flores_src)

        results = self._nllb_translator.translate_batch(
            [tokens],
            target_prefix=[[self.NLLB_TARGET_LANG]],
            **self._build_translate_kwargs(),
        )

        output_tokens = results[0].hypotheses[0]
        return self._detokenize(output_tokens)

    def _nllb_translate_batch_sync(self, texts: List[str], source_langs: List[str]) -> List[str]:
        """
        Batch-translate multiple texts via CTranslate2.

        Groups texts by source language for correct source-language token,
        then processes each group as a batch.
        """
        batch_size = self.nllb_max_batch_size
        translate_kwargs = self._build_translate_kwargs()
        translate_kwargs['batch_type'] = self.nllb_batch_type

        # Group by source language for correct language prefix
        lang_groups: Dict[str, List[Tuple[int, str]]] = {}
        for i, (text, lang) in enumerate(zip(texts, source_langs)):
            flores = self._get_flores_code(lang)
            if flores:
                lang_groups.setdefault(flores, []).append((i, text))

        results = [''] * len(texts)

        for flores_code, items in lang_groups.items():
            # Process in sub-batches of batch_size
            for batch_start in range(0, len(items), batch_size):
                batch_items = items[batch_start:batch_start + batch_size]
                batch_indices = [idx for idx, _ in batch_items]
                batch_texts = [txt for _, txt in batch_items]

                batch_tokens = [self._tokenize(t, flores_code) for t in batch_texts]
                target_prefixes = [[self.NLLB_TARGET_LANG]] * len(batch_tokens)

                batch_results = self._nllb_translator.translate_batch(
                    batch_tokens,
                    target_prefix=target_prefixes,
                    max_batch_size=batch_size,
                    **translate_kwargs,
                )

                for j, idx in enumerate(batch_indices):
                    output_tokens = batch_results[j].hypotheses[0]
                    results[idx] = self._detokenize(output_tokens)

        return results

    async def _call_nllb_translate(self, text: str, source_lang: str) -> str:
        """Translate a single text using NLLB-200 (runs in thread executor)."""
        if not self._load_nllb_model():
            raise Exception("NLLB model not available")

        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._nllb_translate_sync, text, source_lang),
            timeout=60,
        )

    async def _call_nllb_translate_batch(
        self, texts: List[str], source_langs: List[str]
    ) -> List[str]:
        """Batch-translate using NLLB-200 (runs in thread executor)."""
        if not self._load_nllb_model():
            raise Exception("NLLB model not available")

        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._nllb_translate_batch_sync, texts, source_langs),
            timeout=120,
        )

    # =========================================================================
    # LONG TEXT TRANSLATION (paragraph chunking for full_text)
    # =========================================================================

    async def translate_long_text(self, text: str, source_lang: str) -> str:
        """Translate text that may exceed NLLB's token limit by paragraph chunking.

        Short texts (<=500 chars) go through translate_with_metadata for caching.
        Longer texts are split into paragraphs (and sentences if needed), batch-
        translated in a single CTranslate2 call, and reassembled.

        Args:
            text: The text to translate.
            source_lang: ISO 639-1 language code (e.g. 'ru', 'zh').

        Returns:
            Translated text with original paragraph structure preserved.
        """
        if not text or not text.strip():
            return text

        MAX_CHUNK_CHARS = 500  # ~300 tokens, safely under the 512-token limit

        # Short text: use normal path (benefits from cache)
        if len(text) <= MAX_CHUNK_CHARS:
            result = await self.translate_with_metadata(text, source_lang=source_lang)
            return result.text if result.was_translated else text

        # Split into paragraphs, then chunk long paragraphs by sentence
        chunks = []
        for para in text.split('\n'):
            if not para.strip():
                chunks.append('')  # preserve blank lines
                continue
            if len(para) <= MAX_CHUNK_CHARS:
                chunks.append(para)
            else:
                # Split oversized paragraph by sentence boundaries
                sentences = re.split(r'(?<=[.!?。！？])\s+', para)
                current = ''
                for sent in sentences:
                    if current and len(current) + len(sent) + 1 > MAX_CHUNK_CHARS:
                        chunks.append(current)
                        current = sent
                    else:
                        current = f"{current} {sent}" if current else sent
                if current:
                    chunks.append(current)

        # Identify non-empty chunks that need translation
        to_translate = [(i, c) for i, c in enumerate(chunks) if c.strip()]
        if not to_translate:
            return text

        try:
            texts = [c for _, c in to_translate]
            langs = [source_lang] * len(texts)
            translations = await self._call_nllb_translate_batch(texts, langs)

            for (idx, _), translated in zip(to_translate, translations):
                chunks[idx] = translated

            return '\n'.join(chunks)
        except Exception as e:
            logger.info(f"NLLB batch failed, falling back to per-chunk translation: {e}")

        # Fallback: translate each chunk individually via translate_with_metadata
        # (can use cache or NLLB as backend)
        try:
            for idx, chunk_text in to_translate:
                result = await self.translate_with_metadata(chunk_text, source_lang=source_lang)
                if result.was_translated:
                    chunks[idx] = result.text
            return '\n'.join(chunks)
        except Exception as e2:
            logger.warning(f"Long text translation failed entirely: {e2}")
            return text

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================
    
    async def translate_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translate article title and description if non-English

        @updated 2026-02-05 by Mr Cat + Claude - Now tracks translation_source

        Args:
            article: Article dictionary with 'title' and optionally 'description'

        Returns:
            Article dict with translations added:
            - translated: bool - whether any translation occurred
            - source_language: str - detected source language
            - translation_source: str - 'cache', 'nllb', or None
            - original_title: str - original title if translated
        """
        result = article.copy()
        result['translated'] = False
        result['translation_source'] = None

        # Check and translate title
        title = article.get('title', '')
        if title and self.needs_translation(title):
            tr = await self.translate_with_metadata(title)
            if tr.was_translated:
                result['original_title'] = title
                result['title'] = tr.text
                result['source_language'] = tr.source_language
                result['translation_source'] = tr.translation_source
                result['translated'] = True
                logger.debug(f"Translated title from {tr.source_language} via {tr.translation_source}: '{title[:40]}...'")

        # Check and translate description
        description = article.get('description', '')
        if description and self.needs_translation(description):
            tr = await self.translate_with_metadata(description)
            if tr.was_translated:
                result['original_description'] = description
                result['description'] = tr.text
                # Don't overwrite source_language/translation_source if title was already translated
                if not result['translated']:
                    result['source_language'] = tr.source_language
                    result['translation_source'] = tr.translation_source
                result['translated'] = True

        return result
    
    async def translate_batch(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Translate a batch of articles using NLLB batched translation.

        Collects all titles needing translation and processes them in a
        single batched forward pass.

        Args:
            articles: List of article dictionaries

        Returns:
            List of articles with translations
        """
        if not self.enabled:
            return articles

        return await self._translate_batch_nllb(articles)

        if translate_count > 0:
            logger.info(f"Translated {translate_count}/{len(articles)} articles")

        return translated

    async def _translate_batch_nllb(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Batch-translate articles using NLLB's native batching.

        Collects all titles/descriptions needing translation, checks cache,
        then sends uncached texts through NLLB in one batched call.
        """
        results = [article.copy() for article in articles]
        for r in results:
            r['translated'] = False
            r['translation_source'] = None

        # Phase 1: Detect languages and check caches, collect uncached texts
        uncached_title_indices = []   # index into results
        uncached_title_texts = []
        uncached_title_langs = []

        uncached_desc_indices = []
        uncached_desc_texts = []
        uncached_desc_langs = []

        for i, article in enumerate(results):
            title = article.get('title', '')
            if title and self.needs_translation(title):
                lang = self.detect_language(title)
                if lang != 'en' and self._get_flores_code(lang):
                    cached = self._check_cache(title)
                    if cached:
                        translation, cached_lang = cached
                        results[i]['original_title'] = title
                        results[i]['title'] = translation
                        results[i]['source_language'] = cached_lang
                        results[i]['translation_source'] = 'cache'
                        results[i]['translated'] = True
                    else:
                        uncached_title_indices.append(i)
                        uncached_title_texts.append(title)
                        uncached_title_langs.append(lang)

            desc = article.get('description', '')
            if desc and self.needs_translation(desc):
                lang = self.detect_language(desc)
                if lang != 'en' and self._get_flores_code(lang):
                    cached = self._check_cache(desc)
                    if cached:
                        translation, cached_lang = cached
                        results[i]['original_description'] = desc
                        results[i]['description'] = translation
                        results[i]['translated'] = True
                        if not results[i].get('source_language'):
                            results[i]['source_language'] = cached_lang
                            results[i]['translation_source'] = 'cache'
                    else:
                        uncached_desc_indices.append(i)
                        uncached_desc_texts.append(desc)
                        uncached_desc_langs.append(lang)

        # Phase 2: Batch-translate all uncached texts in one call
        all_texts = uncached_title_texts + uncached_desc_texts
        all_langs = uncached_title_langs + uncached_desc_langs

        if all_texts:
            try:
                translations = await self._call_nllb_translate_batch(all_texts, all_langs)

                # Apply title translations
                for j, idx in enumerate(uncached_title_indices):
                    translation = translations[j]
                    original = uncached_title_texts[j]
                    lang = uncached_title_langs[j]
                    results[idx]['original_title'] = original
                    results[idx]['title'] = translation
                    results[idx]['source_language'] = lang
                    results[idx]['translation_source'] = 'nllb'
                    results[idx]['translated'] = True
                    self._add_to_cache(original, translation, lang)

                # Apply description translations
                offset = len(uncached_title_texts)
                for j, idx in enumerate(uncached_desc_indices):
                    translation = translations[offset + j]
                    original = uncached_desc_texts[j]
                    lang = uncached_desc_langs[j]
                    results[idx]['original_description'] = original
                    results[idx]['description'] = translation
                    results[idx]['translated'] = True
                    if not results[idx].get('source_language'):
                        results[idx]['source_language'] = lang
                        results[idx]['translation_source'] = 'nllb'
                    self._add_to_cache(original, translation, lang)

                self.stats['translations'] += len(all_texts)
                self.stats['batch_translations'] += 1
                self.stats['chars_translated'] += sum(len(t) for t in all_texts)

            except Exception as e:
                logger.error(f"NLLB batch translation failed: {e}")
                self.stats['errors'] += 1

        translate_count = sum(1 for r in results if r.get('translated'))
        if translate_count > 0:
            cached_count = translate_count - len(all_texts) if all_texts else translate_count
            logger.info(
                f"Batch translated {translate_count}/{len(articles)} articles "
                f"({len(all_texts)} via NLLB, {cached_count} from cache)"
            )

        return results
    
    # =========================================================================
    # STATS
    # =========================================================================
    
    def get_nllb_params(self) -> Dict[str, Any]:
        """Get current CTranslate2 tuning parameters."""
        return {
            'beam_size': self.nllb_beam_size,
            'length_penalty': self.nllb_length_penalty,
            'repetition_penalty': self.nllb_repetition_penalty,
            'no_repeat_ngram_size': self.nllb_no_repeat_ngram_size,
            'max_batch_size': self.nllb_max_batch_size,
            'batch_type': self.nllb_batch_type,
            'max_decoding_length': self.nllb_max_decoding_length,
            'max_input_length': self.nllb_max_input_length,
            'sampling_topk': self.nllb_sampling_topk,
            'sampling_topp': self.nllb_sampling_topp,
            'sampling_temperature': self.nllb_sampling_temperature,
        }

    def set_nllb_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update CTranslate2 tuning parameters at runtime. Returns the updated params."""
        PARAM_SPEC = {
            'beam_size':             (int,   1, 10),
            'length_penalty':        (float, 0.0, 3.0),
            'repetition_penalty':    (float, 1.0, 3.0),
            'no_repeat_ngram_size':  (int,   0, 20),
            'max_batch_size':        (int,   1, 4096),
            'max_decoding_length':   (int,   32, 2048),
            'max_input_length':      (int,   32, 2048),
            'sampling_topk':         (int,   1, 100),
            'sampling_topp':         (float, 0.0, 1.0),
            'sampling_temperature':  (float, 0.1, 5.0),
        }
        applied = {}
        for key, value in params.items():
            if key == 'batch_type':
                if value in ('examples', 'tokens'):
                    self.nllb_batch_type = value
                    applied[key] = value
                continue
            if key in PARAM_SPEC:
                typ, lo, hi = PARAM_SPEC[key]
                casted = typ(value)
                clamped = max(lo, min(hi, casted))
                setattr(self, f'nllb_{key}', clamped)
                applied[key] = clamped
        return applied

    def get_stats(self) -> Dict[str, Any]:
        """Get translation statistics"""
        mode = config.AI_TRANSLATOR_MODE
        if self._use_nllb:
            model_name = getattr(config, 'NLLB_MODEL', 'models/nllb-200-distilled-600M-ct2')
        else:
            model_name = 'none'

        device = getattr(config, 'NLLB_DEVICE', 'auto')
        compute_type = getattr(config, 'NLLB_COMPUTE_TYPE', 'auto')
        inter_threads = getattr(config, 'NLLB_INTER_THREADS', 1)
        intra_threads = getattr(config, 'NLLB_INTRA_THREADS', 4)

        return {
            **self.stats,
            'cache_size': len(self._cache),
            'cache_max_size': self._cache_max_size,
            'cache_ttl_days': self._cache_ttl.days,
            'cache_unsaved': self._unsaved_count,
            'cache_file': str(self._cache_file),
            'lang_cache_size': len(self._lang_cache),
            'lang_cache_max_size': self._lang_cache_max_size,
            'enabled': self.enabled,
            'mode': mode,
            'model': model_name,
            'nllb_loaded': self._nllb_translator is not None,
            'nllb_load_time_ms': self._nllb_load_time_ms,
            'nllb_device': device,
            'nllb_compute_type': compute_type,
            'nllb_inter_threads': inter_threads,
            'nllb_intra_threads': intra_threads,
            'nllb_params': self.get_nllb_params(),
            'supported_language_count': len(self.SUPPORTED_LANGUAGES),
            'nllb_language_count': len(self.FLORES_CODES),
            'langdetect_available': HAS_LANGDETECT,
            'nllb_available': HAS_NLLB,
        }


# =============================================================================
# SINGLETON
# =============================================================================

_translation_service: Optional[TranslationService] = None


def get_translation_service() -> TranslationService:
    """Get or create singleton translation service"""
    global _translation_service
    if _translation_service is None:
        _translation_service = TranslationService()
    return _translation_service
