"""
RYBAT Lite - Intelligence Ingestion Service
=============================================
Core article preparation and field extraction for the collection pipeline.

No AI scoring at collection time. Signals are collected, translated,
and persisted with extracted metadata (location, casualties). Scoring
fields (relevance_score, risk_indicators, source_confidence, author_confidence)
are populated later via offline Claude re-scoring and sentence-transformer
inference.

Pipeline: RSS -> Validate -> Translate -> Extract Fields -> Persist -> Broadcast

@updated 2026-02-13 | Backend audit: removed AI analysis cascade, Groq/Gemini,
                       fallback scorer, confidence engine. Kept translation +
                       field extraction at collection time.
"""

from datetime import datetime
from typing import Optional, Dict, Any

from config import config
from database.models import IntelligenceDB
from services.field_extraction import extract_location, extract_casualties
from utils.logging import get_logger
from utils.sanitizers import sanitize_ai_field, sanitize_url

logger = get_logger(__name__)


class IntelligenceService:
    """
    Article preparation and field extraction.

    Handles:
    - Article validation, translation, field extraction (_prepare_article)
    - Finalization with extracted metadata (finalize_article)

    Scoring is NOT performed at collection time. Signals are persisted
    with default/empty scoring fields, to be populated later by:
    - Claude re-scoring (offline batch)
    - Sentence-transformer inference (production)
    - Curated lookup tables (source/author confidence)
    """

    def __init__(self, db: IntelligenceDB):
        self.db = db

    # =========================================================================
    # ARTICLE PREPARATION
    # =========================================================================

    async def _prepare_article(self, article: dict, translator, context=None):
        """
        Prepare a single article for insertion.
        Handles validation, pg_trgm deduplication, and translation.

        Args:
            article: Raw article dict from collector
            translator: TranslationService instance (or None)
            context: Unused (kept for API compatibility with pipeline)

        Returns:
            dict with prepared INSERT values, 'duplicate' string, or None on error
        """
        title = article.get('title', '').strip()
        url = article.get('url', '').strip()
        source = article.get('source', 'Unknown')
        description = article.get('description', '').strip()
        full_text = article.get('full_text', '').strip() or None
        collector_name = article.get('collector', 'rss')
        method = article.get('collection_method', collector_name)
        author = article.get('author', '').strip() or None

        if not title or not url:
            return None

        # pg_trgm fuzzy title dedup (GIN-indexed)
        if await self.db.find_similar_title(title):
            return 'duplicate'

        url = sanitize_url(url)
        if not url:
            return None

        # Parse published timestamp
        published_at = datetime.now()
        if 'published' in article:
            try:
                published_at = datetime.fromisoformat(article['published'].replace('Z', '+00:00'))
            except (ValueError, TypeError, KeyError):
                pass

        # Source label — identify scraper/NP4K articles
        if method in ('scraper', 'newspaper4k', 'trafilatura') or collector_name == 'np4k':
            source_label = f"Scraper:{source}"
        else:
            source_label = source

        # Handle translation
        display_title = title
        display_description = description or None
        display_full_text = full_text
        is_translated = False
        source_language = None
        translation_source = None

        if translator and translator.enabled:
            if translator.needs_translation(title):
                tr_result = await translator.translate_with_metadata(title)
                # Always capture detected language, even if translation failed
                if tr_result.source_language:
                    source_language = tr_result.source_language
                if tr_result.was_translated:
                    display_title = tr_result.text
                    is_translated = True
                    translation_source = tr_result.translation_source
                    logger.debug(f"Translated via {translation_source}: {source_language} -> EN")

                    # Also translate description and full_text
                    if description:
                        desc_result = await translator.translate_with_metadata(
                            description, source_lang=source_language
                        )
                        if desc_result.was_translated:
                            display_description = desc_result.text

                    if full_text:
                        display_full_text = await translator.translate_long_text(
                            full_text, source_lang=source_language
                        )

        # Post-translation dedup: if the translated title closely matches an
        # existing signal, this is a cross-source duplicate (same story from
        # multiple feeds, different URLs, different original-language titles,
        # but identical English translation).  Use a lower threshold (0.80)
        # than the pre-translation check because NLLB can produce slightly
        # different phrasings for the same headline.
        if is_translated and display_title != title:
            if await self.db.find_similar_title(display_title, threshold=0.80):
                logger.debug(
                    f"Post-translation duplicate: '{display_title[:60]}...' "
                    f"(original: '{title[:40]}...')"
                )
                return 'duplicate'

        return {
            'title': display_title,
            'original_title': title,
            'description': display_description,
            'full_text': display_full_text,
            'url': url,
            'published_at': published_at,
            'source_label': source_label,
            'collector_name': collector_name,
            'source_group': article.get('_group'),
            'source_tier': article.get('_tier', 3),
            'is_translated': is_translated,
            'source_language': source_language,
            'translation_source': translation_source,
            'author': author,
        }

    # =========================================================================
    # ARTICLE FINALIZATION (replaces analyze_article)
    # =========================================================================

    async def finalize_article(self, prepared: dict) -> dict:
        """
        Finalize a prepared article with extracted metadata.
        No AI scoring — just field extraction and default values.

        Args:
            prepared: Article dict from _prepare_article

        Returns:
            prepared dict updated with location, casualties, and default
            scoring fields ready for DB insertion.
        """
        title = prepared['title']
        source_name = prepared.get('source_label', 'Unknown')
        author_name = prepared.get('author') or ''

        # Extract location from headline; fall back to feed-level metadata
        loc_str = extract_location(title)
        if not loc_str or loc_str == 'Global':
            feed_city = prepared.get('city', '')
            feed_country = prepared.get('country', '')
            if feed_city and feed_country:
                loc_str = f"{feed_city}, {feed_country}"
            elif feed_country:
                loc_str = feed_country
        loc_str = sanitize_ai_field(loc_str or 'Unknown', 'str')
        casualties = extract_casualties(title)

        # Derive source confidence from feed registry tier
        # Tier 1 (global/osint) = 80, Tier 2 (regional) = 60, Tier 3+ (discovered/unknown) = 40
        source_tier = prepared.get('source_tier', 3)
        tier_confidence = {1: 80, 2: 60}.get(source_tier, 40)

        # Merge extracted fields + scoring defaults
        prepared.update({
            'location': loc_str,
            'casualties': casualties,
            'risk_indicators': [],
            'relevance_score': 0,
            'source_confidence': tier_confidence,
            'author_confidence': 0,
            'analysis_mode': 'SKIPPED',
            'source_name': source_name,
            'author_name': author_name,
            'processed': True,
        })

        return prepared
