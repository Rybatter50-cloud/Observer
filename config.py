"""
Observer Lite v1.0.0 - Configuration Management
Loads and validates all configuration from environment variables.

Portable/field deployment: RSS feeds, NLLB translation, sanctions screening.
No LLMs, no embeddings, no heavy analysis services.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Project root — used to resolve relative model paths regardless of cwd
_PROJECT_ROOT = Path(__file__).parent

# Load .env file if it exists
env_path = _PROJECT_ROOT / '.env'
if env_path.exists():
    load_dotenv(env_path)


class ConfigurationError(Exception):
    """Raised when required configuration is missing"""
    pass


def _env_int(name: str, default: str) -> int:
    raw = os.getenv(name, default)
    try:
        return int(raw)
    except (ValueError, TypeError):
        raise ConfigurationError(
            f"Environment variable {name}='{raw}' is not a valid integer"
        )


def _env_float(name: str, default: str) -> float:
    raw = os.getenv(name, default)
    try:
        return float(raw)
    except (ValueError, TypeError):
        raise ConfigurationError(
            f"Environment variable {name}='{raw}' is not a valid number"
        )


class Config:
    """Application configuration for Observer Lite"""

    PROFILE: str = 'portable'

    # Database (PostgreSQL) — MUST be set via env var or .env file
    DATABASE_URL: str = os.getenv('DATABASE_URL', '')

    # Database Limits & Pool
    MAX_SIGNALS_LIMIT: int = _env_int('MAX_SIGNALS_LIMIT', '25000')
    DB_POOL_MIN_SIZE: int = _env_int('DB_POOL_MIN_SIZE', '1')
    DB_POOL_MAX_SIZE: int = _env_int('DB_POOL_MAX_SIZE', '3')

    # ==========================================================================
    # TRANSLATION (NLLB-200 only — no LLM fallback)
    # ==========================================================================
    AI_TRANSLATOR_MODE: str = os.getenv('AI_TRANSLATOR_MODE', 'nllb').lower()
    TRANSLATION_ENABLED: bool = (AI_TRANSLATOR_MODE != 'off')
    TRANSLATION_USE_LOCAL: bool = False  # No Ollama in Lite
    TRANSLATION_USE_NLLB: bool = (AI_TRANSLATOR_MODE == 'nllb')

    # NLLB Configuration (CTranslate2)
    NLLB_MODEL: str = os.getenv('NLLB_MODEL', str(_PROJECT_ROOT / 'models' / 'nllb-200-distilled-600M-ct2'))
    NLLB_SP_MODEL: str = os.getenv('NLLB_SP_MODEL', str(_PROJECT_ROOT / 'models' / 'nllb-200-distilled-600M-ct2' / 'sentencepiece.bpe.model'))
    NLLB_MAX_LENGTH: int = _env_int('NLLB_MAX_LENGTH', '512')
    NLLB_MAX_INPUT_LENGTH: int = _env_int('NLLB_MAX_INPUT_LENGTH', '0')
    NLLB_BATCH_SIZE: int = _env_int('NLLB_BATCH_SIZE', '8')
    NLLB_DEVICE: str = os.getenv('NLLB_DEVICE', 'cpu')
    NLLB_COMPUTE_TYPE: str = os.getenv('NLLB_COMPUTE_TYPE', 'int8')
    NLLB_INTER_THREADS: int = _env_int('NLLB_INTER_THREADS', '1')
    NLLB_INTRA_THREADS: int = _env_int('NLLB_INTRA_THREADS', '4')

    # CTranslate2 tuning parameters
    NLLB_BEAM_SIZE: int = _env_int('NLLB_BEAM_SIZE', '1')
    NLLB_LENGTH_PENALTY: float = _env_float('NLLB_LENGTH_PENALTY', '1.0')
    NLLB_REPETITION_PENALTY: float = _env_float('NLLB_REPETITION_PENALTY', '1.0')
    NLLB_NO_REPEAT_NGRAM: int = _env_int('NLLB_NO_REPEAT_NGRAM', '0')
    NLLB_BATCH_TYPE: str = os.getenv('NLLB_BATCH_TYPE', 'examples')
    NLLB_SAMPLING_TOPK: int = _env_int('NLLB_SAMPLING_TOPK', '1')
    NLLB_SAMPLING_TOPP: float = _env_float('NLLB_SAMPLING_TOPP', '1.0')
    NLLB_SAMPLING_TEMPERATURE: float = _env_float('NLLB_SAMPLING_TEMPERATURE', '1.0')

    # Translation cache sizing
    TRANSLATION_CACHE_MAX_SIZE: int = _env_int('TRANSLATION_CACHE_MAX_SIZE', '30000')

    # ==========================================================================
    # FEED COLLECTION
    # ==========================================================================
    FEED_COLLECTION_ENABLED: bool = os.getenv('FEED_COLLECTION_ENABLED', 'true').lower() == 'true'
    FEED_CHECK_INTERVAL: int = _env_int('FEED_CHECK_INTERVAL', '300')
    COLLECTOR_TIMEOUT: int = _env_int('COLLECTOR_TIMEOUT', '1200')
    FEED_MAX_ARTICLES_PER_SOURCE: int = _env_int('FEED_MAX_ARTICLES_PER_SOURCE', '5')
    FEED_CONCURRENCY: int = _env_int('FEED_CONCURRENCY', '5')

    # Content Filter Configuration
    CONTENT_FILTER_ENABLED: bool = os.getenv('CONTENT_FILTER_ENABLED', 'true').lower() == 'true'
    CONTENT_FILTER_MODE: str = os.getenv('CONTENT_FILTER_MODE', 'both')
    CONTENT_FILTER_LOG_REJECTED: bool = os.getenv('CONTENT_FILTER_LOG_REJECTED', 'false').lower() == 'true'
    CONTENT_FILTER_BL: str = os.getenv('CONTENT_FILTER_BL', 'BL_default')
    CONTENT_FILTER_WL: str = os.getenv('CONTENT_FILTER_WL', 'WL_geopolitical')

    # Scraper Configuration (trafilatura — on-demand full-text fetch)
    SCRAPER_COLLECTION_ENABLED: bool = os.getenv('SCRAPER_COLLECTION_ENABLED', 'false').lower() == 'true'
    SCRAPER_REQUEST_TIMEOUT: int = _env_int('SCRAPER_REQUEST_TIMEOUT', '30')
    SCRAPER_MIN_WORD_COUNT: int = _env_int('SCRAPER_MIN_WORD_COUNT', '100')
    SCRAPER_MAX_ARTICLES_PER_SITE: int = _env_int('SCRAPER_MAX_ARTICLES_PER_SITE', '20')
    SCRAPER_DEFAULT_LANGUAGE: str = os.getenv('SCRAPER_DEFAULT_LANGUAGE', 'en')
    SCRAPER_DELAY_BETWEEN_ARTICLES: float = _env_float('SCRAPER_DELAY_BETWEEN_ARTICLES', '2.0')
    SCRAPER_MAX_REQUESTS_PER_HOUR: int = _env_int('SCRAPER_MAX_REQUESTS_PER_HOUR', '100')
    SCRAPER_FAST_MODE: bool = os.getenv('SCRAPER_FAST_MODE', 'true').lower() == 'true'
    SCRAPER_FAVOR_PRECISION: bool = os.getenv('SCRAPER_FAVOR_PRECISION', 'false').lower() == 'true'
    SCRAPER_FAVOR_RECALL: bool = os.getenv('SCRAPER_FAVOR_RECALL', 'false').lower() == 'true'
    SCRAPER_INCLUDE_TABLES: bool = os.getenv('SCRAPER_INCLUDE_TABLES', 'false').lower() == 'true'
    SCRAPER_INCLUDE_LINKS: bool = os.getenv('SCRAPER_INCLUDE_LINKS', 'false').lower() == 'true'
    SCRAPER_INCLUDE_IMAGES: bool = os.getenv('SCRAPER_INCLUDE_IMAGES', 'false').lower() == 'true'
    SCRAPER_INCLUDE_COMMENTS: bool = os.getenv('SCRAPER_INCLUDE_COMMENTS', 'false').lower() == 'true'
    SCRAPER_DEDUPLICATE: bool = os.getenv('SCRAPER_DEDUPLICATE', 'true').lower() == 'true'
    SCRAPER_URL_BLACKLIST: str = os.getenv('SCRAPER_URL_BLACKLIST', '')

    # ==========================================================================
    # ENTITY SCREENING (OpenSanctions local + optional FBI/Interpol)
    # ==========================================================================
    SANCTIONS_NET_ENABLED: bool = os.getenv('SANCTIONS_NET_ENABLED', 'true').lower() == 'true'
    FBI_ENABLED: bool = os.getenv('FBI_ENABLED', 'false').lower() == 'true'
    INTERPOL_ENABLED: bool = os.getenv('INTERPOL_ENABLED', 'false').lower() == 'true'

    # Features permanently disabled in Lite
    EMBEDDINGS_ENABLED: bool = False
    WIKI_EVENTS_ENABLED: bool = False
    ENTITY_EXTRACTION_ENABLED: bool = os.getenv('ENTITY_EXTRACTION_ENABLED', 'true').lower() == 'true'
    ENTITY_ENRICHMENT_ENABLED: bool = False
    GEMINI_ENABLED: bool = False
    VIRUSTOTAL_ENABLED: bool = False
    URLSCAN_ENABLED: bool = False
    NEWSAPI_ENABLED: bool = False
    DVIDS_ENABLED: bool = False
    KOKORO_ENABLED: bool = False
    NP4K_ENABLED: bool = os.getenv('NP4K_ENABLED', 'false').lower() == 'true'
    VECTOR_TRANSLATION_ENABLED: bool = False
    ENTITY_AUTO_SCREEN: bool = os.getenv('ENTITY_AUTO_SCREEN', 'true').lower() == 'true'

    # Server Configuration
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = _env_int('PORT', '8999')
    DEBUG: bool = os.getenv('DEBUG', 'false').lower() == 'true'

    # CORS Configuration
    ALLOWED_ORIGINS: list = os.getenv('ALLOWED_ORIGINS', 'http://localhost:8999').split(',')

    # API Key Authentication
    API_KEY_ENABLED: bool = os.getenv('API_KEY_ENABLED', 'false').lower() == 'true'

    @classmethod
    def validate(cls) -> None:
        errors = []

        if cls.AI_TRANSLATOR_MODE not in ('nllb', 'off'):
            errors.append(f"Invalid AI_TRANSLATOR_MODE: '{cls.AI_TRANSLATOR_MODE}'. Must be 'nllb' or 'off'.")

        if not cls.DATABASE_URL:
            errors.append("DATABASE_URL not set. PostgreSQL connection string required.")

        if cls.FEED_COLLECTION_ENABLED:
            valid_content_modes = ['whitelist', 'blacklist', 'both']
            if cls.CONTENT_FILTER_MODE not in valid_content_modes:
                errors.append(f"Invalid CONTENT_FILTER_MODE: '{cls.CONTENT_FILTER_MODE}'")

        if errors:
            raise ConfigurationError("Configuration validation failed:\n" + "\n".join(errors))

    @classmethod
    def display(cls) -> None:
        print("\n" + "=" * 70)
        print("OBSERVER v1.0.0 - PORTABLE (Field)")
        print("=" * 70)
        print(f"\nTRANSLATION:")
        print(f"  Mode:               {cls.AI_TRANSLATOR_MODE.upper()}")
        if cls.TRANSLATION_USE_NLLB:
            print(f"  NLLB Model:         {cls.NLLB_MODEL}")
            print(f"  NLLB Device:        {cls.NLLB_DEVICE}")
            print(f"  NLLB Batch Size:    {cls.NLLB_BATCH_SIZE}")
        print(f"\nFEATURES:")
        print(f"  Feed Collection:    {'ENABLED' if cls.FEED_COLLECTION_ENABLED else 'DISABLED'}")
        print(f"  Scraper:            {'ENABLED' if cls.SCRAPER_COLLECTION_ENABLED else 'DISABLED'}")
        print(f"  Screening:")
        print(f"    OpenSanctions:    {'ENABLED' if cls.SANCTIONS_NET_ENABLED else 'DISABLED'}")
        print(f"    FBI:              {'ENABLED' if cls.FBI_ENABLED else 'DISABLED'}")
        print(f"    Interpol:         {'ENABLED' if cls.INTERPOL_ENABLED else 'DISABLED'}")
        print(f"\nDATABASE (PostgreSQL):")
        _dsn = cls.DATABASE_URL
        if '@' in _dsn and ':' in _dsn.split('@')[0]:
            _parts = _dsn.split('@')
            _user_part = _parts[0].rsplit(':', 1)[0]
            _dsn = f"{_user_part}:****@{'@'.join(_parts[1:])}"
        print(f"  Connection:         {_dsn}")
        print(f"  Max Signals:        {cls.MAX_SIGNALS_LIMIT:,}")
        print("=" * 70 + "\n")


config = Config()
