"""
Observer Intelligence Platform - Feed Manager
============================================
Manages RSS feed registry and entry parsing with content filtering.

State (enabled_groups) is delegated to SourceStateManager.
Content filtering is provided by services/content_filter.py.

@updated 2026-02-09 by Mr Cat + Claude - Phase 2: extracted ContentFilter
"""

import re
import json
from pathlib import Path
from html import unescape
from datetime import datetime
from typing import Optional, List, Set, Dict, Any

from utils.logging import get_logger
from utils.sanitizers import sanitize_url
from services.source_state import get_source_state_manager
from services.content_filter import ContentFilter, get_content_filter

logger = get_logger(__name__)


# Re-export for any remaining consumers
__all__ = ['FeedManager', 'get_feed_manager', 'ContentFilter', 'get_content_filter']


def _parse_date_lenient(entry: dict) -> Optional[datetime]:
    """Parse publication date from feed entry, trying multiple formats."""
    for date_field in ['published_parsed', 'updated_parsed', 'created_parsed']:
        parsed = entry.get(date_field)
        if parsed:
            try:
                return datetime(*parsed[:6])
            except (TypeError, ValueError):
                continue

    for date_field in ['published', 'updated', 'created', 'pubDate']:
        date_str = entry.get(date_field)
        if not date_str:
            continue

        formats = [
            '%a, %d %b %Y %H:%M:%S %z',
            '%a, %d %b %Y %H:%M:%S %Z',
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

    return None


class FeedManager:
    """
    Manages RSS feed registry and entry parsing.

    State (enabled_groups) delegated to SourceStateManager.
    Content filtering delegated to ContentFilter.
    """

    def __init__(self):
        self.feed_registry: Dict[str, Any] = {}
        self.last_check: Dict[str, datetime] = {}
        self.min_check_interval: int = 300

        self._source_state = get_source_state_manager()
        self.content_filter = get_content_filter()
        self.rejection_stats: Dict[str, int] = {
            'blacklist_match': 0,
            'whitelist_fail': 0,
            'total_rejected': 0,
            'total_accepted': 0
        }
        self.feed_health: Dict[str, Dict[str, Any]] = {}

        logger.info(f"FeedManager initialized, enabled groups: {len(self._source_state.enabled_groups)}")

    def _count_feeds(self) -> int:
        """Count total feeds across all groups in the registry."""
        return sum(
            len(group.get('feeds', []))
            for key, group in self.feed_registry.items()
            if key != '_metadata' and isinstance(group, dict)
        )

    # -- Delegated properties --

    @property
    def enabled_groups(self) -> Set[str]:
        return self._source_state.enabled_groups

    @enabled_groups.setter
    def enabled_groups(self, value: Set[str]):
        self._source_state.enabled_groups = value

    # -- Delegated methods --

    def enable_group(self, group_name: str) -> bool:
        if group_name not in self.feed_registry or group_name == '_metadata':
            logger.warning(f"Feed group not found in registry: {group_name}")
            return False
        result = self._source_state.enable_group(group_name)
        if result:
            logger.info(f"Enabled feed group: {group_name} ({self._get_group_feed_count(group_name)} feeds)")
        return result

    def disable_group(self, group_name: str) -> bool:
        result = self._source_state.disable_group(group_name)
        if result:
            logger.info(f"Disabled feed group: {group_name}")
        return result

    def reset_to_defaults(self) -> None:
        self._source_state.reset_to_defaults()
        self.rejection_stats = {
            'blacklist_match': 0, 'whitelist_fail': 0,
            'total_rejected': 0, 'total_accepted': 0
        }

    # -- Registry operations --

    def _get_group_feed_count(self, group_name: str) -> int:
        group = self.feed_registry.get(group_name, {})
        if isinstance(group, dict):
            return len(group.get('feeds', []))
        return 0

    def get_enabled_feeds(self) -> List[Dict[str, Any]]:
        feeds = []
        for group_name in self.enabled_groups:
            group = self.feed_registry.get(group_name)
            if not group or not isinstance(group, dict):
                continue
            for feed in group.get('feeds', []):
                if feed.get('enabled', True):
                    feed_copy = dict(feed)
                    feed_copy['_group'] = group_name
                    feeds.append(feed_copy)
        return feeds

    def get_status(self) -> Dict[str, Any]:
        enabled_feeds = self.get_enabled_feeds()
        return {
            'enabled_groups': list(self.enabled_groups),
            'total_enabled_feeds': len(enabled_feeds),
            'rejection_stats': self.rejection_stats,
            'group_details': {
                group: {
                    'feed_count': self._get_group_feed_count(group),
                    'enabled': group in self.enabled_groups
                }
                for group in self.feed_registry.keys()
                if group != '_metadata'
            }
        }

    def _parse_entry(self, entry: Any, feed_name: str) -> Optional[Dict[str, Any]]:
        try:
            title = entry.get('title', '').strip()
            if not title:
                return None

            title = unescape(title)
            title = re.sub(r'<[^>]+>', '', title)
            title = re.sub(r'\s+', ' ', title).strip()

            description = entry.get('summary', entry.get('description', '')).strip()
            if description:
                description = unescape(description)
                description = re.sub(r'<[^>]+>', '', description)
                description = re.sub(r'\s+', ' ', description).strip()

            should_accept, reason = self.content_filter.should_accept(title, description, skip_whitelist=True)
            if not should_accept:
                self.rejection_stats['total_rejected'] += 1
                if reason == 'blacklist_match':
                    self.rejection_stats['blacklist_match'] += 1
                elif reason == 'whitelist_fail':
                    self.rejection_stats['whitelist_fail'] += 1
                if self.content_filter.log_rejected:
                    logger.debug(f"Rejected ({reason}): {title[:60]}... from {feed_name}")
                return None

            self.rejection_stats['total_accepted'] += 1

            url = entry.get('link', '').strip()
            url = sanitize_url(url)
            if not url:
                return None

            published = _parse_date_lenient(entry)
            if not published:
                published = datetime.now()

            return {
                'title': title,
                'url': url,
                'description': description[:1000] if description else '',
                'published': published.isoformat(),
                'source': feed_name,
                'collected_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.debug(f"Error parsing entry from {feed_name}: {e}")
            return None

    def enable_groups_by_keywords(self, keywords: List[str]) -> List[str]:
        enabled = []
        keywords_lower = [k.lower() for k in keywords]
        for group_name, group_data in self.feed_registry.items():
            if group_name == '_metadata':
                continue
            group_name_lower = group_name.lower()
            description = group_data.get('description', '').lower() if isinstance(group_data, dict) else ''
            for keyword in keywords_lower:
                if keyword in group_name_lower or keyword in description:
                    if self.enable_group(group_name):
                        enabled.append(group_name)
                    break
        return enabled


_feed_manager_instance: Optional[FeedManager] = None


def get_feed_manager() -> FeedManager:
    """Get or create singleton FeedManager instance."""
    global _feed_manager_instance
    if _feed_manager_instance is None:
        _feed_manager_instance = FeedManager()
    return _feed_manager_instance
