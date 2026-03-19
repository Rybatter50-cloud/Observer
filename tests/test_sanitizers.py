"""
Observer Test Suite - Sanitizer Unit Tests
========================================
Comprehensive tests for all functions in utils/sanitizers.py.

These are pure-function tests (no database, no async) — they run fast
and should be part of every pre-commit / CI check.

@created 2026-02-20 - C-3 remediation: security-critical test coverage
"""

import os
import sys

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.sanitizers import (
    strip_html_tags,
    sanitize_ai_field,
    normalize_text_input,
    sanitize_url,
    sanitize_json_string,
    extract_number,
    validate_time_window,
    sanitize_category,
)


# ======================================================================
# strip_html_tags
# ======================================================================

class TestStripHtmlTags:
    """Tests for the HTML tag stripping function used at collection time."""

    def test_plain_text_unchanged(self):
        assert strip_html_tags("Hello world") == "Hello world"

    def test_strips_simple_tags(self):
        assert strip_html_tags("<b>bold</b> text") == "bold text"

    def test_strips_nested_tags(self):
        assert strip_html_tags("<div><p>nested <b>content</b></p></div>") == "nested content"

    def test_strips_self_closing_tags(self):
        # Tag is removed but no space inserted — whitespace normalization
        # only collapses existing spaces, doesn't add new ones
        assert strip_html_tags("line one<br/>line two") == "line oneline two"
        # With surrounding space, it works as expected
        assert strip_html_tags("line one <br/> line two") == "line one line two"

    def test_strips_tags_with_attributes(self):
        assert strip_html_tags('<a href="http://evil.com">link</a>') == "link"

    def test_decodes_html_entities(self):
        # Entities are decoded FIRST, then tags stripped.
        # &lt;Corp&gt; decodes to <Corp> which is then stripped as a tag.
        assert strip_html_tags("AT&amp;T &lt;Corp&gt;") == "AT&T"
        # Entities that don't produce tags survive
        assert strip_html_tags("AT&amp;T rocks &amp; rolls") == "AT&T rocks & rolls"

    def test_decodes_numeric_entities(self):
        assert strip_html_tags("&#169; 2026") == "\u00a9 2026"

    def test_normalizes_whitespace(self):
        assert strip_html_tags("  lots   of   spaces  ") == "lots of spaces"

    def test_strips_tags_and_normalizes(self):
        assert strip_html_tags("<p>  spaced  </p>  <p> out </p>") == "spaced out"

    def test_empty_string(self):
        assert strip_html_tags("") == ""

    def test_none_returns_empty(self):
        assert strip_html_tags(None) == ""

    def test_non_string_returns_original_or_empty(self):
        # Non-string truthy values are returned as-is (guard clause: `not isinstance(text, str)`)
        assert strip_html_tags(42) == 42
        # Non-string falsy values return ''
        assert strip_html_tags([]) == ""
        assert strip_html_tags(0) == ""

    # --- XSS attack vectors ---

    def test_xss_script_tag(self):
        result = strip_html_tags('<script>alert("xss")</script>Safe text')
        assert "<script>" not in result
        assert "</script>" not in result
        # Tag stripping removes tags but preserves text content —
        # the output is plain text with no executable HTML structure
        assert "Safe text" in result

    def test_xss_img_onerror(self):
        result = strip_html_tags('<img src=x onerror="alert(1)">')
        assert "<img" not in result
        assert "onerror" not in result

    def test_xss_event_handler(self):
        result = strip_html_tags('<div onmouseover="evil()">hover</div>')
        assert "<div" not in result
        assert "hover" in result

    def test_xss_svg_onload(self):
        result = strip_html_tags('<svg onload="alert(1)"><circle/></svg>')
        assert "<svg" not in result
        assert "alert" not in result

    def test_rss_title_with_cdata_tags(self):
        """RSS feeds sometimes wrap titles in CDATA with embedded HTML."""
        result = strip_html_tags("<![CDATA[Breaking: <b>Explosion</b> reported]]>")
        # CDATA markers are text, not valid HTML tags — they remain after stripping
        # The important thing is <b> tags are stripped
        assert "<b>" not in result
        assert "Explosion" in result


# ======================================================================
# sanitize_ai_field
# ======================================================================

class TestSanitizeAiField:
    """Tests for AI output sanitization (used before database storage)."""

    # --- String mode ---

    def test_str_from_string(self):
        assert sanitize_ai_field("  Paris  ", "str") == "Paris"

    def test_str_from_int(self):
        assert sanitize_ai_field(42, "str") == "42"

    def test_str_from_none(self):
        assert sanitize_ai_field(None, "str") == "Unknown"

    def test_str_from_empty(self):
        assert sanitize_ai_field("", "str") == "Unknown"

    def test_str_from_list(self):
        assert sanitize_ai_field(["Paris", "France"], "str") == "Paris, France"

    def test_str_from_empty_list(self):
        assert sanitize_ai_field([], "str") == "Unknown"

    def test_str_from_list_with_empty_values(self):
        result = sanitize_ai_field(["", None, "Valid"], "str")
        assert "Valid" in result

    def test_str_from_dict(self):
        result = sanitize_ai_field({"key": "val"}, "str")
        assert isinstance(result, str)
        assert "key" in result

    # --- Integer mode ---

    def test_int_from_int(self):
        assert sanitize_ai_field(42, "int") == 42

    def test_int_from_float(self):
        assert sanitize_ai_field(3.7, "int") == 3

    def test_int_from_string_number(self):
        assert sanitize_ai_field("85", "int") == 85

    def test_int_from_string_with_text(self):
        assert sanitize_ai_field("about 75 people", "int") == 75

    def test_int_from_negative_string(self):
        assert sanitize_ai_field("-10 degrees", "int") == -10

    def test_int_from_none(self):
        assert sanitize_ai_field(None, "int") == 0

    def test_int_from_empty(self):
        assert sanitize_ai_field("", "int") == 0

    def test_int_from_no_numbers(self):
        assert sanitize_ai_field("no numbers here", "int") == 0

    def test_int_from_list(self):
        assert sanitize_ai_field([42, 10], "int") == 42

    def test_int_from_empty_list(self):
        assert sanitize_ai_field([], "int") == 0

    def test_int_from_list_non_numeric(self):
        assert sanitize_ai_field(["abc", "def"], "int") == 0

    # --- Default target_type is 'str' ---

    def test_default_type_is_str(self):
        assert sanitize_ai_field("test") == "test"


# ======================================================================
# normalize_text_input
# ======================================================================

class TestNormalizeTextInput:
    """Tests for text input normalization (null bytes, length, type coercion)."""

    def test_normal_string(self):
        assert normalize_text_input("hello") == "hello"

    def test_strips_whitespace(self):
        assert normalize_text_input("  padded  ") == "padded"

    def test_removes_null_bytes(self):
        assert normalize_text_input("abc\x00def") == "abcdef"

    def test_truncates_to_max_length(self):
        long = "a" * 2000
        result = normalize_text_input(long, max_length=100)
        assert len(result) == 100

    def test_default_max_length_is_1000(self):
        long = "b" * 1500
        result = normalize_text_input(long)
        assert len(result) == 1000

    def test_non_string_converted(self):
        assert normalize_text_input(42) == "42"
        assert normalize_text_input(None) == "None"

    def test_preserves_special_chars(self):
        """This is input hygiene, not SQL escaping — quotes pass through unchanged."""
        assert normalize_text_input("O'Brien") == "O'Brien"

    def test_multiple_null_bytes(self):
        assert normalize_text_input("\x00\x00\x00") == ""


# ======================================================================
# sanitize_url
# ======================================================================

class TestSanitizeUrl:
    """Tests for URL validation and sanitization."""

    # --- Valid URLs pass through ---

    def test_valid_https(self):
        assert sanitize_url("https://example.com/page") == "https://example.com/page"

    def test_valid_http(self):
        assert sanitize_url("http://example.com") == "http://example.com"

    def test_url_with_query_params(self):
        url = "https://example.com/search?q=test&page=1"
        assert sanitize_url(url) == url

    def test_url_with_fragment(self):
        url = "https://example.com/page#section"
        assert sanitize_url(url) == url

    def test_url_with_port(self):
        url = "https://example.com:8080/api"
        assert sanitize_url(url) == url

    def test_preserves_single_quotes(self):
        """Single quotes are RFC 3986 legal."""
        assert sanitize_url("https://example.com/it's") == "https://example.com/it's"

    def test_strips_leading_trailing_whitespace(self):
        assert sanitize_url("  https://example.com  ") == "https://example.com"

    def test_unicode_path(self):
        url = "https://example.com/ürlaub"
        assert sanitize_url(url) == url

    # --- Scheme rejection ---

    def test_rejects_no_scheme(self):
        assert sanitize_url("example.com") == ""

    def test_rejects_ftp(self):
        assert sanitize_url("ftp://example.com") == ""

    def test_rejects_javascript(self):
        assert sanitize_url("javascript:alert(1)") == ""

    def test_rejects_data_uri(self):
        assert sanitize_url("data:text/html,<h1>evil</h1>") == ""

    def test_rejects_file_scheme(self):
        assert sanitize_url("file:///etc/passwd") == ""

    # --- Hostname validation ---

    def test_rejects_scheme_only(self):
        assert sanitize_url("http://") == ""

    # --- Dangerous character stripping ---

    def test_strips_angle_brackets(self):
        assert sanitize_url("https://example.com/<script>") == "https://example.com/script"

    def test_strips_double_quotes(self):
        assert sanitize_url('https://example.com/"test"') == "https://example.com/test"

    def test_strips_backticks(self):
        assert sanitize_url("https://example.com/`onerror=alert(1)`") == "https://example.com/onerror=alert(1)"

    def test_strips_control_chars(self):
        assert sanitize_url("https://example.com/\x00path") == "https://example.com/path"
        assert sanitize_url("https://example.com/\x0apath") == "https://example.com/path"

    # --- Length enforcement ---

    def test_rejects_overly_long_url(self):
        url = "https://example.com/" + "a" * 2100
        assert sanitize_url(url) == ""

    def test_custom_max_length(self):
        url = "https://example.com/" + "a" * 200
        assert sanitize_url(url, max_length=100) == ""

    # --- Edge cases ---

    def test_none_returns_empty(self):
        assert sanitize_url(None) == ""

    def test_empty_returns_empty(self):
        assert sanitize_url("") == ""

    def test_non_string_returns_empty(self):
        assert sanitize_url(42) == ""


# ======================================================================
# sanitize_json_string
# ======================================================================

class TestSanitizeJsonString:
    """Tests for JSON string cleanup from AI responses."""

    def test_clean_json_unchanged(self):
        assert sanitize_json_string('{"key": "value"}') == '{"key": "value"}'

    def test_strips_json_code_fence(self):
        result = sanitize_json_string('```json\n{"key": "val"}\n```')
        assert result == '{"key": "val"}'

    def test_strips_plain_code_fence(self):
        result = sanitize_json_string('```\n{"key": "val"}\n```')
        assert result == '{"key": "val"}'

    def test_strips_whitespace(self):
        assert sanitize_json_string("  {}\n  ") == "{}"

    def test_empty_returns_braces(self):
        assert sanitize_json_string("") == "{}"

    def test_none_returns_braces(self):
        assert sanitize_json_string(None) == "{}"

    def test_preserves_nested_json(self):
        inp = '```json\n{"a": {"b": [1, 2]}}\n```'
        result = sanitize_json_string(inp)
        assert '"a"' in result
        assert '"b"' in result


# ======================================================================
# extract_number
# ======================================================================

class TestExtractNumber:
    """Tests for number extraction from free text."""

    def test_simple_number(self):
        assert extract_number("42") == 42

    def test_number_in_text(self):
        assert extract_number("about 150 casualties") == 150

    def test_first_number_wins(self):
        assert extract_number("3 dead, 17 injured") == 3

    def test_no_number_returns_default(self):
        assert extract_number("no numbers") == 0

    def test_custom_default(self):
        assert extract_number("nothing", default=-1) == -1

    def test_empty_returns_default(self):
        assert extract_number("") == 0

    def test_none_returns_default(self):
        assert extract_number(None) == 0

    def test_non_string_converted(self):
        assert extract_number(42) == 42

    def test_large_number(self):
        assert extract_number("population 1000000") == 1000000


# ======================================================================
# validate_time_window
# ======================================================================

class TestValidateTimeWindow:
    """Tests for time window parameter validation."""

    def test_valid_4h(self):
        assert validate_time_window("4h") == "4h"

    def test_valid_24h(self):
        assert validate_time_window("24h") == "24h"

    def test_valid_72h(self):
        assert validate_time_window("72h") == "72h"

    def test_valid_7d(self):
        assert validate_time_window("7d") == "7d"

    def test_valid_all(self):
        assert validate_time_window("all") == "all"

    def test_invalid_returns_all(self):
        assert validate_time_window("bogus") == "all"

    def test_empty_returns_all(self):
        assert validate_time_window("") == "all"

    def test_sql_injection_attempt(self):
        assert validate_time_window("'; DROP TABLE intel_signals;--") == "all"

    def test_case_sensitive(self):
        """The allowlist is lowercase — uppercase should be rejected."""
        assert validate_time_window("4H") == "all"
        assert validate_time_window("ALL") == "all"


# ======================================================================
# sanitize_category
# ======================================================================

class TestSanitizeCategory:
    """Tests for intelligence category validation."""

    def test_valid_categories(self):
        for cat in ['CONFLICT', 'TERRORISM', 'POLITICAL', 'ECONOMIC',
                     'HUMANITARIAN', 'CYBER', 'ENVIRONMENTAL', 'UNKNOWN']:
            assert sanitize_category(cat) == cat

    def test_lowercase_normalized(self):
        assert sanitize_category("conflict") == "CONFLICT"

    def test_mixed_case(self):
        assert sanitize_category("Terrorism") == "TERRORISM"

    def test_strips_whitespace(self):
        assert sanitize_category("  CYBER  ") == "CYBER"

    def test_invalid_returns_unknown(self):
        assert sanitize_category("INVALID") == "UNKNOWN"

    def test_empty_returns_unknown(self):
        # Note: empty string .upper().strip() == "" which is not in valid list
        assert sanitize_category("") == "UNKNOWN"

    def test_sql_injection_attempt(self):
        assert sanitize_category("'; DROP TABLE--") == "UNKNOWN"
