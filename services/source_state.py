"""
RYBAT Intelligence Platform - Source State Manager
===================================================
Single source of truth for all data source configuration.

@created 2026-02-03 by Claude - v1.5.0 Collector Architecture Refactor

Manages:
- Which geographic/topic groups are enabled
- Which collectors (RSS, NewsAPI, etc.) are enabled
- Per-collector configuration
- Geographic region filtering
- State persistence to JSON

This replaces the old FeedStateManager with a more generic design
that supports multiple collector types.

Usage:
    from services.source_state import get_source_state_manager
    
    state = get_source_state_manager()
    
    # Check enabled groups
    groups = state.enabled_groups
    
    # Check enabled collectors
    collectors = state.enabled_collectors
    
    # Enable/disable
    state.enable_group('ukraine')
    state.enable_collector('newsapi')
    state.save_state()

Environment Variables:
    SOURCE_STARTUP_ALL=true     - Enable ALL groups at startup
    SOURCE_STATE_RESTORE=true   - Restore state from JSON on startup
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Set, Optional

from utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# GEOGRAPHIC REGION DEFINITIONS
# =============================================================================
# Maps regions to feed groups for geographic filtering

REGION_DEFINITIONS = {
    "ukraine_conflict": {
        "bounds": {"north": 52.4, "south": 44.3, "east": 40.2, "west": 22.1},
        "groups": ["ukraine", "russia"],
        "tier": 1
    },
    "middle_east": {
        "bounds": {"north": 42.0, "south": 12.0, "east": 63.0, "west": 25.0},
        "groups": [
            "bahrain", "iran", "iraq", "israel", "jordan", "kuwait",
            "lebanon", "oman", "qatar", "saudi_arabia", "syria",
            "turkey", "uae", "yemen"
        ],
        "tier": 1
    },
    "europe": {
        "bounds": {"north": 71.0, "south": 35.0, "east": 40.0, "west": -10.0},
        "groups": [
            "albania", "andorra", "austria", "belarus", "belgium", "bosnia",
            "bulgaria", "croatia", "cyprus", "czechia", "denmark", "estonia",
            "finland", "france", "germany", "greece", "hungary", "iceland",
            "ireland", "italy", "latvia", "liechtenstein", "lithuania",
            "luxembourg", "malta", "moldova", "monaco", "montenegro",
            "netherlands", "north_macedonia", "norway", "poland", "portugal",
            "romania", "russia", "san_marino", "serbia", "slovakia",
            "slovenia", "spain", "sweden", "switzerland", "uk", "ukraine"
        ],
        "tier": 2
    },
    "asia_pacific": {
        "bounds": {"north": 53.0, "south": -10.0, "east": 180.0, "west": 73.0},
        "groups": [
            "australia", "bangladesh", "bhutan", "brunei", "cambodia",
            "china", "fiji", "hong_kong", "india", "indonesia", "japan",
            "kiribati", "laos", "malaysia", "maldives", "marshall_islands",
            "micronesia", "mongolia", "myanmar", "nauru", "nepal",
            "new_zealand", "north_korea", "pakistan", "palau",
            "papua_new_guinea", "philippines", "samoa", "singapore",
            "solomon_islands", "south_korea", "sri_lanka", "taiwan",
            "thailand", "timor_leste", "tonga", "tuvalu", "vanuatu",
            "vietnam"
        ],
        "tier": 2
    },
    "africa": {
        "bounds": {"north": 37.0, "south": -35.0, "east": 52.0, "west": -18.0},
        "groups": [
            "algeria", "angola", "benin", "botswana", "burkina_faso",
            "burundi", "cabo_verde", "cameroon", "central_african_republic",
            "chad", "comoros", "congo_dr", "congo_republic", "cote_d_ivoire",
            "djibouti", "egypt", "equatorial_guinea", "eritrea", "eswatini",
            "ethiopia", "gabon", "gambia", "ghana", "guinea", "guinea_bissau",
            "kenya", "lesotho", "liberia", "libya", "madagascar", "malawi",
            "mali", "mauritania", "mauritius", "morocco", "mozambique",
            "namibia", "niger", "nigeria", "rwanda", "sao_tome_and_principe",
            "senegal", "seychelles", "sierra_leone", "somalia", "south_africa",
            "south_sudan", "sudan", "tanzania", "togo", "tunisia", "uganda",
            "zambia", "zimbabwe"
        ],
        "tier": 2
    },
    "americas": {
        "bounds": {"north": 72.0, "south": -56.0, "east": -34.0, "west": -170.0},
        "groups": [
            "antigua_and_barbuda", "argentina", "bahamas", "barbados",
            "belize", "bolivia", "brazil", "canada", "chile", "colombia",
            "costa_rica", "cuba", "dominica", "dominican_republic", "ecuador",
            "el_salvador", "grenada", "guatemala", "guyana", "haiti",
            "honduras", "jamaica", "mexico", "nicaragua", "panama",
            "paraguay", "peru", "saint_kitts_and_nevis", "saint_lucia",
            "saint_vincent_and_the_grenadines", "suriname",
            "trinidad_and_tobago", "uruguay", "usa", "venezuela"
        ],
        "tier": 2
    },
    "caucasus_central_asia": {
        "bounds": {"north": 55.0, "south": 35.0, "east": 80.0, "west": 40.0},
        "groups": [
            "afghanistan", "armenia", "azerbaijan", "georgia",
            "kazakhstan", "kyrgyzstan", "tajikistan", "turkmenistan",
            "uzbekistan"
        ],
        "tier": 2
    }
}


# =============================================================================
# SOURCE STATE MANAGER
# =============================================================================

class SourceStateManager:
    """
    Single source of truth for all data source configuration
    
    Responsibilities:
    - Track which geographic/topic groups are enabled
    - Track which collectors are enabled
    - Store per-collector configuration
    - Persist state to JSON file
    This is the ONLY place that tracks what's enabled.
    All collectors and services read from here.
    """
    
    # Default collectors to enable on fresh install
    # NP4K is a specialist tool (default off, enable via dashboard or NP4K_ENABLED=true)
    DEFAULT_COLLECTORS = {'rss'}
    
    # Tier 1 groups that are always available (can't be disabled)
    TIER1_GROUPS = {'global', 'osint'}
    
    def __init__(self, state_file: str = './data/source_state.json'):
        """
        Initialize source state manager
        
        Args:
            state_file: Path to state persistence file
        """
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # === CORE STATE ===
        self.enabled_groups: Set[str] = set()
        self.enabled_collectors: Set[str] = set()
        self.collector_configs: Dict[str, Dict[str, Any]] = {}
        
        # === METADATA ===
        self.last_updated: Optional[datetime] = None
        
        # === STATISTICS (runtime only, not persisted) ===
        self.articles_24h: Dict[str, int] = {}  # group -> article count
        
        # === INITIALIZE ===
        self._initialize_state()
        
        logger.info(
            f"SourceStateManager initialized: "
            f"{len(self.enabled_groups)} groups, "
            f"{len(self.enabled_collectors)} collectors"
        )
    
    def _initialize_state(self):
        """
        Initialize state based on environment configuration
        
        Behavior:
        1. If SOURCE_STATE_RESTORE=true and state file exists, load it
        2. Otherwise, set defaults based on SOURCE_STARTUP_ALL
        """
        restore_state = os.getenv('SOURCE_STATE_RESTORE', 'true').lower() == 'true'
        
        if restore_state and self.state_file.exists():
            self._load_state()
        else:
            self._set_defaults()
    
    def _set_defaults(self):
        """
        Set default state for fresh install
        
        Controlled by environment:
        - SOURCE_STARTUP_ALL=true: Enable ALL groups
        - SOURCE_STARTUP_ALL=false (default): Enable only Tier 1
        """
        startup_all = os.getenv('SOURCE_STARTUP_ALL', 'false').lower() == 'true'
        
        if startup_all:
            # Get all available groups from feed registry
            self.enabled_groups = self._get_all_groups_from_registry()
            logger.info(f"SOURCE_STARTUP_ALL=true: Enabled ALL {len(self.enabled_groups)} groups")
        else:
            # Tier 1 only
            self.enabled_groups = self.TIER1_GROUPS.copy()
            logger.info(f"Default startup: Enabled Tier 1 groups only ({', '.join(self.TIER1_GROUPS)})")
        
        # Default collectors
        self.enabled_collectors = self.DEFAULT_COLLECTORS.copy()
        
    def _get_all_groups_from_registry(self) -> Set[str]:
        """
        Get all group names from the feed registry
        
        Returns:
            Set of all group names
        """
        try:
            # Try to load from feed registry
            registry_path = os.getenv('FEED_REGISTRY_PATH', 'feed_registry_comprehensive.json')
            
            if Path(registry_path).exists():
                with open(registry_path, 'r', encoding='utf-8') as f:
                    registry = json.load(f)
                
                groups = set()
                for key in registry.keys():
                    if key != '_metadata':
                        groups.add(key)
                
                return groups
            else:
                logger.warning(f"Feed registry not found: {registry_path}")
                return self.TIER1_GROUPS.copy()
                
        except Exception as e:
            logger.error(f"Error loading feed registry for groups: {e}")
            return self.TIER1_GROUPS.copy()
    
    def _load_state(self):
        """Load state from persistence file"""
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            
            self.enabled_groups = set(data.get('enabled_groups', list(self.TIER1_GROUPS)))
            self.enabled_collectors = set(data.get('enabled_collectors', list(self.DEFAULT_COLLECTORS)))
            self.collector_configs = data.get('collector_configs', {})
            if data.get('last_updated'):
                self.last_updated = datetime.fromisoformat(data['last_updated'])
            
            logger.info(f"Loaded source state from {self.state_file}")
            
        except Exception as e:
            logger.error(f"Error loading source state: {e}")
            self._set_defaults()
    
    def save_state(self) -> bool:
        """
        Save current state to persistence file
        
        Returns:
            True if successful
        """
        try:
            self.last_updated = datetime.now()
            
            data = {
                'enabled_groups': list(self.enabled_groups),
                'enabled_collectors': list(self.enabled_collectors),
                'collector_configs': self.collector_configs,
                'last_updated': self.last_updated.isoformat()
            }
            
            # Atomic write
            temp_path = self.state_file.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self.state_file)
            
            logger.debug(f"Saved source state to {self.state_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving source state: {e}")
            return False
    
    # === GROUP MANAGEMENT ===
    
    def enable_group(self, group_name: str) -> bool:
        """Enable a feed group"""
        self.enabled_groups.add(group_name)
        logger.info(f"Enabled group: {group_name}")
        return True
    
    def disable_group(self, group_name: str) -> bool:
        """Disable a feed group (except Tier 1)"""
        if group_name in self.TIER1_GROUPS:
            logger.warning(f"Cannot disable Tier 1 group: {group_name}")
            return False
        
        self.enabled_groups.discard(group_name)
        logger.info(f"Disabled group: {group_name}")
        return True
    
    def enable_groups(self, groups: List[str]) -> List[str]:
        """Enable multiple groups"""
        enabled = []
        for group in groups:
            if self.enable_group(group):
                enabled.append(group)
        return enabled
    
    def disable_groups(self, groups: List[str]) -> List[str]:
        """Disable multiple groups"""
        disabled = []
        for group in groups:
            if self.disable_group(group):
                disabled.append(group)
        return disabled
    
    def set_enabled_groups(self, groups: Set[str]):
        """Set exactly which groups are enabled"""
        # Always include Tier 1
        self.enabled_groups = groups | self.TIER1_GROUPS
    
    def enable_all_groups(self):
        """Enable all available groups"""
        self.enabled_groups = self._get_all_groups_from_registry()
        logger.info(f"Enabled ALL {len(self.enabled_groups)} groups")
    
    # === COLLECTOR MANAGEMENT ===
    
    def enable_collector(self, collector_name: str) -> bool:
        """Enable a collector"""
        self.enabled_collectors.add(collector_name)
        logger.info(f"Enabled collector: {collector_name}")
        return True
    
    def disable_collector(self, collector_name: str) -> bool:
        """Disable a collector"""
        self.enabled_collectors.discard(collector_name)
        logger.info(f"Disabled collector: {collector_name}")
        return True
    
    def set_collector_config(self, collector_name: str, config: Dict[str, Any]):
        """Set configuration for a specific collector"""
        self.collector_configs[collector_name] = config
    
    def get_collector_config(self, collector_name: str) -> Dict[str, Any]:
        """Get configuration for a specific collector"""
        return self.collector_configs.get(collector_name, {})
    
    # === STATUS ===
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive state status"""
        return {
            'enabled_groups': list(self.enabled_groups),
            'enabled_collectors': list(self.enabled_collectors),
            'collector_configs': self.collector_configs,
            'tier1_groups': list(self.TIER1_GROUPS),
            'tier2_enabled': [g for g in self.enabled_groups if g not in self.TIER1_GROUPS],
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }
    
    def reset_to_defaults(self):
        """Reset everything to defaults"""
        self._set_defaults()
        self.save_state()
        logger.info("Source state reset to defaults")


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_source_state_manager: Optional[SourceStateManager] = None


def get_source_state_manager(state_file: str = './data/source_state.json') -> SourceStateManager:
    """
    Get or create singleton source state manager
    
    Args:
        state_file: Path to state persistence file
    
    Returns:
        SourceStateManager instance
    """
    global _source_state_manager
    
    if _source_state_manager is None:
        _source_state_manager = SourceStateManager(state_file)
    
    return _source_state_manager
