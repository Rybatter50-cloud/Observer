"""
RYBAT Intelligence Platform - Data Sanitization Utilities
Provides safe data cleaning and validation functions
"""

import re
from html import unescape
from typing import Any, Union
from urllib.parse import urlparse


def strip_html_tags(text: str) -> str:
    """
    Strip HTML tags from text and normalize whitespace.

    Used at collection time to ensure only plain text is stored in the database.
    Decodes HTML entities (e.g. &amp; -> &) and removes all tags.

    Args:
        text: Input text that may contain HTML tags/entities

    Returns:
        Plain text with tags removed and entities decoded
    """
    if not text or not isinstance(text, str):
        return text or ''
    text = unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def sanitize_ai_field(value: Any, target_type: str = 'str') -> Union[str, int]:
    """
    Ensures AI output is safe for database storage and prevents injection
    
    Args:
        value: Raw value from AI or external source
        target_type: Expected type ('str' or 'int')
        
    Returns:
        Sanitized value of the specified type
    """
    try:
        # Handle list inputs
        if isinstance(value, list):
            if not value:
                return 0 if target_type == 'int' else "Unknown"
            if target_type == 'str':
                # Filter and join valid string values
                clean_values = [str(v).strip() for v in value if v]
                return ", ".join(clean_values) if clean_values else "Unknown"
            # For int, take first numeric value
            for item in value:
                try:
                    return int(float(item))
                except (ValueError, TypeError):
                    continue
            return 0
        
        # Handle dict inputs
        if isinstance(value, dict):
            return str(value)
        
        # Handle None or empty
        if value is None or value == "":
            return 0 if target_type == 'int' else "Unknown"
        
        # Handle integer conversion
        if target_type == 'int':
            # Extract first number from string if present
            if isinstance(value, str):
                numbers = re.findall(r'-?\d+(?:\.\d+)?', value)
                return int(float(numbers[0])) if numbers else 0
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return 0
        
        # Handle string conversion
        return str(value).strip()
        
    except Exception:
        return 0 if target_type == 'int' else "Unknown"


def normalize_text_input(value: str, max_length: int = 1000) -> str:
    """
    Normalize text input: coerce to str, strip null bytes, and enforce max length.

    NOTE: This is NOT a SQL injection defense.  All database queries MUST use
    parameterized statements ($1, $2, …) via asyncpg — never string formatting.
    This function is for general input hygiene only.

    Args:
        value: Input string
        max_length: Maximum allowed length

    Returns:
        Cleaned string
    """
    if not isinstance(value, str):
        value = str(value)
    
    # Remove any null bytes
    value = value.replace('\x00', '')
    
    # Limit length
    if len(value) > max_length:
        value = value[:max_length]
    
    return value.strip()


def sanitize_url(url: str, max_length: int = 2048) -> str:
    """
    Validate and sanitize URLs using proper URL parsing.

    Rejects non-HTTP(S) schemes, URLs without a valid hostname, and strips
    characters that are unsafe in HTML attribute contexts.

    Args:
        url: Input URL
        max_length: Maximum allowed URL length (default 2048)

    Returns:
        Sanitized URL or empty string if invalid
    """
    if not url or not isinstance(url, str):
        return ""

    url = url.strip()

    if len(url) > max_length:
        return ""

    # Structural validation via urllib.parse
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return ""
    if not parsed.hostname:
        return ""

    # Strip characters that are dangerous in HTML href/src contexts.
    # Covers <, >, ", backtick, and ASCII control chars (0x00-0x1F, 0x7F).
    url = re.sub(r'[<>"`\x00-\x1f\x7f]', '', url)

    return url


def sanitize_json_string(value: str) -> str:
    """
    Clean JSON strings from AI responses
    
    Args:
        value: Raw JSON string potentially with markdown formatting
        
    Returns:
        Clean JSON string
    """
    if not value:
        return "{}"
    
    # Remove markdown code fences
    value = re.sub(r'```json\s*', '', value)
    value = re.sub(r'```\s*', '', value)
    
    # Remove any leading/trailing whitespace
    value = value.strip()
    
    return value


def extract_number(text: str, default: int = 0) -> int:
    """
    Extract first number from text
    
    Args:
        text: Input text
        default: Default value if no number found
        
    Returns:
        Extracted integer or default
    """
    if not text:
        return default
    
    # Find all numbers in text
    numbers = re.findall(r'\d+', str(text))
    
    if numbers:
        return int(numbers[0])
    
    return default


def validate_time_window(window: str) -> str:
    """
    Validate and sanitize time window parameter
    
    Args:
        window: Time window string
        
    Returns:
        Valid time window or 'all'
    """
    valid_windows = ['4h', '24h', '72h', '7d', 'all']
    
    if window in valid_windows:
        return window
    
    return 'all'


def sanitize_category(category: str) -> str:
    """
    Validate intelligence category
    
    Args:
        category: Category string
        
    Returns:
        Valid category or 'UNKNOWN'
    """
    valid_categories = [
        'CONFLICT', 'TERRORISM', 'POLITICAL', 'ECONOMIC',
        'HUMANITARIAN', 'CYBER', 'ENVIRONMENTAL', 'UNKNOWN'
    ]
    
    category = category.upper().strip()
    
    if category in valid_categories:
        return category
    
    return 'UNKNOWN'
