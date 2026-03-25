"""
Observer Lite - Entity Extraction Service (GLiNER)
==================================================
GLiNER-based NER for geopolitical entity extraction.
Runs on-demand via batch script (scripts/extract_entities.py).

Model: urchade/gliner_medium-v2.1 (~80MB, CPU)
Speed: ~30-50ms per article on CPU

2026-03-25 | Mr Cat + Claude | Entity extraction for Observer Lite
"""

import asyncio
import unicodedata
from typing import List, Dict, Optional

from utils.logging import get_logger

logger = get_logger(__name__)

# Entity type mapping from GLiNER labels to canonical types
_LABEL_MAP = {
    'person': 'PERSON',
    'organization': 'ORG',
    'location': 'GPE',
    'country': 'COUNTRY',
    'military unit': 'MILITARY',
    'weapon': 'WEAPON',
}

# GLiNER labels to extract
_LABELS = list(_LABEL_MAP.keys())

# Confidence threshold (favor recall; screening refines)
_THRESHOLD = 0.4


def _normalize_name(text: str) -> str:
    """NFKD + lowercase for canonical_name dedup."""
    normalized = unicodedata.normalize('NFKD', text)
    return normalized.lower().strip()


class EntityExtractionService:
    """GLiNER-based entity extraction service."""

    def __init__(self):
        self._model = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def load_model(self) -> bool:
        """Load GLiNER model (blocking)."""
        try:
            from gliner import GLiNER

            logger.info("Loading GLiNER model (urchade/gliner_medium-v2.1)...")
            self._model = GLiNER.from_pretrained(
                "urchade/gliner_medium-v2.1", map_location="cpu"
            )
            self._ready = True
            logger.info("GLiNER model loaded successfully")
            return True
        except Exception as e:
            logger.error(f"GLiNER model failed to load: {e}")
            self._ready = False
            return False

    def extract_sync(self, text: str) -> List[Dict]:
        """Synchronous extraction from text."""
        if not self._model or not text:
            return []

        try:
            entities = self._model.predict_entities(
                text, _LABELS, threshold=_THRESHOLD
            )
        except Exception as e:
            logger.debug(f"GLiNER prediction error: {e}")
            return []

        results = []
        seen = set()
        for ent in entities:
            text_span = ent.get('text', '').strip()
            label = ent.get('label', '').lower()
            score = ent.get('score', 0.0)

            if not text_span or len(text_span) < 2:
                continue

            canonical = _normalize_name(text_span)
            entity_type = _LABEL_MAP.get(label, 'UNKNOWN')

            # Dedup within same extraction
            dedup_key = (canonical, entity_type)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            results.append({
                'text': text_span,
                'type': entity_type,
                'canonical': canonical,
                'confidence': round(score, 4),
            })

        return results

    def extract_from_signal(self, title: str, description: str = "") -> List[Dict]:
        """
        Extract entities from title + description.
        Returns [{"text": "...", "type": "PERSON", "canonical": "...", "confidence": 0.87}, ...]
        """
        if not self._ready:
            return []

        # Combine title + truncated description
        text = title
        if description:
            text = f"{title}. {description[:500]}"

        return self.extract_sync(text)

    async def extract_entities_async(
        self, title: str, description: str = ""
    ) -> List[Dict]:
        """Async wrapper — runs extraction in executor."""
        if not self._ready:
            return []

        text = title
        if description:
            text = f"{title}. {description[:500]}"

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.extract_sync, text)


# Singleton
_entity_extraction_service: Optional[EntityExtractionService] = None


def get_entity_extraction_service() -> EntityExtractionService:
    """Get or create singleton entity extraction service."""
    global _entity_extraction_service
    if _entity_extraction_service is None:
        _entity_extraction_service = EntityExtractionService()
    return _entity_extraction_service
