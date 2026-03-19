"""
Observer Intelligence Platform - Field Extraction Utilities
=========================================================
Regex-based extraction of location and casualty data from article titles.

Extracted from services/fallback_scorer.py during the backend simplification
(removal of AI scoring pipeline). These utilities are pure text extraction
with no scoring or AI dependency.

2026-02-13 | Backend audit refactor
"""

import re
from typing import List, Tuple

from utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# GEOGRAPHIC DATA
# =============================================================================

COUNTRY_PATTERNS: List[Tuple[str, str]] = [
    # Major conflict zones (prioritized)
    (r'\b(Ukraine|Ukrainian)\b', 'Ukraine'),
    (r'\b(Russia|Russian|Moscow)\b', 'Russia'),
    (r'\b(Israel|Israeli|Tel Aviv|Jerusalem)\b', 'Israel'),
    (r'\b(Palestine|Palestinian|Gaza|West Bank)\b', 'Palestine'),
    (r'\b(Iran|Iranian|Tehran)\b', 'Iran'),
    (r'\b(Syria|Syrian|Damascus)\b', 'Syria'),
    (r'\b(Yemen|Yemeni)\b', 'Yemen'),
    (r'\b(Taiwan|Taiwanese|Taipei)\b', 'Taiwan'),
    (r'\b(China|Chinese|Beijing)\b', 'China'),
    (r'\b(North Korea|DPRK|Pyongyang)\b', 'North Korea'),
    (r'\b(South Korea|Seoul)\b', 'South Korea'),

    # Other significant countries
    (r'\b(Afghanistan|Afghan|Kabul)\b', 'Afghanistan'),
    (r'\b(Iraq|Iraqi|Baghdad)\b', 'Iraq'),
    (r'\b(Lebanon|Lebanese|Beirut)\b', 'Lebanon'),
    (r'\b(Saudi Arabia|Saudi|Riyadh)\b', 'Saudi Arabia'),
    (r'\b(Turkey|Turkish|Ankara|Istanbul)\b', 'Turkey'),
    (r'\b(Egypt|Egyptian|Cairo)\b', 'Egypt'),
    (r'\b(Sudan|Sudanese|Khartoum)\b', 'Sudan'),
    (r'\b(Libya|Libyan|Tripoli)\b', 'Libya'),
    (r'\b(Somalia|Somali|Mogadishu)\b', 'Somalia'),
    (r'\b(Ethiopia|Ethiopian|Addis Ababa)\b', 'Ethiopia'),
    (r'\b(Nigeria|Nigerian|Lagos|Abuja)\b', 'Nigeria'),
    (r'\b(Myanmar|Burma|Burmese|Yangon)\b', 'Myanmar'),
    (r'\b(Pakistan|Pakistani|Islamabad|Karachi)\b', 'Pakistan'),
    (r'\b(India|Indian|New Delhi|Mumbai)\b', 'India'),
    (r'\b(Japan|Japanese|Tokyo)\b', 'Japan'),
    (r'\b(Venezuela|Venezuelan|Caracas)\b', 'Venezuela'),
    (r'\b(Mexico|Mexican|Mexico City)\b', 'Mexico'),

    # Major powers
    (r'\b(United States|USA|U\.S\.|US|American|Washington D\.?C\.?)\b', 'United States'),
    (r'\b(United Kingdom|UK|U\.K\.|British|Britain|London)\b', 'United Kingdom'),
    (r'\b(Germany|German|Berlin)\b', 'Germany'),
    (r'\b(France|French|Paris)\b', 'France'),
]

UKRAINE_CITIES = [
    'Kyiv', 'Kharkiv', 'Odesa', 'Odessa', 'Dnipro', 'Donetsk', 'Luhansk',
    'Zaporizhzhia', 'Lviv', 'Mariupol', 'Kherson', 'Crimea', 'Sevastopol',
    'Bakhmut', 'Avdiivka', 'Soledar', 'Kramatorsk', 'Sloviansk', 'Melitopol',
    'Donbas', 'Mykolaiv', 'Sumy', 'Chernihiv', 'Poltava', 'Vinnytsia',
]

MIDDLE_EAST_CITIES = [
    'Gaza', 'Rafah', 'Khan Younis', 'Ramallah', 'Nablus', 'Jenin',
    'Tel Aviv', 'Jerusalem', 'Haifa', 'Beirut', 'Damascus', 'Aleppo',
    'Tehran', 'Baghdad', 'Mosul', 'Basra', 'Riyadh', 'Jeddah',
    'Sanaa', 'Aden', 'Hodeida', 'Amman', 'Cairo', 'Alexandria',
]


# =============================================================================
# COMPILED PATTERNS (module-level, compiled once)
# =============================================================================

_compiled_countries = [
    (re.compile(pattern, re.IGNORECASE), country)
    for pattern, country in COUNTRY_PATTERNS
]

_ukraine_re = re.compile(
    r'\b(' + '|'.join(UKRAINE_CITIES) + r')\b', re.IGNORECASE
)

_middle_east_re = re.compile(
    r'\b(' + '|'.join(MIDDLE_EAST_CITIES) + r')\b', re.IGNORECASE
)


# =============================================================================
# EXTRACTION FUNCTIONS
# =============================================================================

def extract_location(title: str) -> str:
    """
    Extract geographic location from a headline using regex patterns.

    Returns:
        Location string (e.g. "Kyiv, Ukraine" or "Global")
    """
    # Try Ukraine cities first (common in current news)
    ukraine_match = _ukraine_re.search(title)
    if ukraine_match:
        return f"{ukraine_match.group(1)}, Ukraine"

    # Try Middle East cities
    me_match = _middle_east_re.search(title)
    if me_match:
        city = me_match.group(1)
        city_lower = city.lower()
        if city_lower in ('gaza', 'rafah', 'khan younis'):
            return f"{city}, Palestine"
        elif city_lower in ('tel aviv', 'jerusalem', 'haifa'):
            return f"{city}, Israel"
        elif city_lower in ('beirut',):
            return f"{city}, Lebanon"
        elif city_lower in ('damascus', 'aleppo'):
            return f"{city}, Syria"
        elif city_lower in ('tehran',):
            return f"{city}, Iran"
        elif city_lower in ('baghdad', 'mosul', 'basra'):
            return f"{city}, Iraq"
        elif city_lower in ('sanaa', 'aden', 'hodeida'):
            return f"{city}, Yemen"
        else:
            return city

    # Try country patterns
    for pattern, country in _compiled_countries:
        if pattern.search(title):
            return country

    return "Global"


def extract_casualties(title: str) -> int:
    """
    Extract casualty count from a headline.

    Returns:
        Casualty count (0 if none found)
    """
    text = title.lower()

    casualty_patterns = [
        r'(\d+)\s*(?:people\s+)?(?:killed|dead|died)',
        r'(\d+)\s*casualties',
        r'(\d+)\s*(?:people\s+)?(?:wounded|injured)',
        r'death toll[:\s]+(\d+)',
        r'(\d+)\s*(?:soldiers?|troops?|civilians?)\s+(?:killed|dead)',
    ]

    max_casualties = 0
    for pattern in casualty_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                num = int(match)
                max_casualties = max(max_casualties, num)
            except ValueError:
                continue

    return max_casualties
