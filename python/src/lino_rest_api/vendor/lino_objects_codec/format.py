"""
Formatting utilities for Links Notation.

These utilities provide functions for formatting and parsing indented Links Notation format.
Uses the links-notation library for parsing to ensure compatibility with the standard format.
"""

import re
from typing import Any

from links_notation import Parser

# Shared parser instance
_parser = Parser()


def escape_reference(value: Any) -> str:
    """
    Escape a reference for Links Notation.

    References need escaping when they contain spaces, quotes, parentheses, colons, or newlines.

    Args:
        value: The value to escape

    Returns:
        The escaped reference string
    """
    # Numbers and booleans don't need escaping
    if isinstance(value, (int, float, bool)):
        return str(value)

    s = str(value)

    # Check if escaping is needed
    needs_escaping = bool(re.search(r'[\s()\'":]', s)) or "\n" in s

    if not needs_escaping:
        return s

    # If contains single quotes but not double quotes, use double quotes
    if "'" in s and '"' not in s:
        return f'"{s}"'

    # If contains double quotes but not single quotes, use single quotes
    if '"' in s and "'" not in s:
        return f"'{s}'"

    # If contains both quotes, count which one appears more
    if "'" in s and '"' in s:
        single_count = s.count("'")
        double_count = s.count('"')

        if double_count < single_count:
            # Use double quotes, escape internal double quotes by doubling
            return f'"{s.replace(chr(34), chr(34) + chr(34))}"'
        else:
            # Use single quotes, escape internal single quotes by doubling
            return f"'{s.replace(chr(39), chr(39) + chr(39))}'"

    # Just spaces or other special characters, use single quotes by default
    return f"'{s}'"


def unescape_reference(s: str | None) -> str | None:
    """
    Unescape a reference from Links Notation format.

    Reverses the escaping done by escape_reference.

    Args:
        s: The escaped reference string

    Returns:
        The unescaped string
    """
    if s is None:
        return s

    # Unescape doubled quotes
    unescaped = s.replace('""', '"')
    unescaped = unescaped.replace("''", "'")

    return unescaped


def _format_indented_value(value: Any) -> str:
    """
    Format a value for display in indented Links Notation.
    Uses quoting strategy compatible with the links-notation parser:
    - If value contains double quotes, wrap in single quotes
    - Otherwise, wrap in double quotes

    Args:
        value: The value to format

    Returns:
        Formatted value with appropriate quotes
    """
    if value is None:
        return '"null"'

    s = str(value)

    # If contains double quotes but no single quotes, use single quotes
    if '"' in s and "'" not in s:
        return f"'{s}'"

    # If contains single quotes but no double quotes, use double quotes
    if "'" in s and '"' not in s:
        return f'"{s}"'

    # If contains both, use single quotes and escape internal single quotes
    if "'" in s and '"' in s:
        escaped = s.replace("'", "''")
        return f"'{escaped}'"

    # Default: use double quotes
    return f'"{s}"'


def format_indented(
    id: str,  # noqa: A002 - part of the public API since 0.1.0; renaming would break callers
    obj: dict[str, Any],
    indent: str = "  ",
) -> str:
    """
    Format an object in indented Links Notation format.

    This format is designed for human readability, displaying objects as:

        <identifier>
          <key> "<value>"
          <key> "<value>"
          ...

    Example:
        >>> format_indented(
        ...     '6dcf4c1b-ff3f-482c-95ab-711ea7d1b019',
        ...     {'uuid': '6dcf4c1b-ff3f-482c-95ab-711ea7d1b019', 'status': 'executed'}
        ... )
        '6dcf4c1b-ff3f-482c-95ab-711ea7d1b019\\n  uuid \\
"6dcf4c1b-ff3f-482c-95ab-711ea7d1b019"\\n  status "executed"'

    Args:
        id: The object identifier (displayed on first line)
        obj: The object (dict) with key-value pairs to format
        indent: The indentation string (default: 2 spaces)

    Returns:
        Formatted indented Links Notation string

    Raises:
        ValueError: If id is empty or obj is not a dict
    """
    if not id:
        raise ValueError("id is required for format_indented")

    if not isinstance(obj, dict):
        raise ValueError("obj must be a dict for format_indented")

    lines = [id]

    for key, value in obj.items():
        escaped_key = escape_reference(key)
        formatted_value = _format_indented_value(value)
        lines.append(f"{indent}{escaped_key} {formatted_value}")

    return "\n".join(lines)


def parse_indented(text: str) -> tuple[str, dict[str, Any]]:
    """
    Parse an indented Links Notation string back to an object.

    This function uses the links-notation parser for proper parsing,
    supporting the standard Links Notation indented syntax.

    Parses strings like:

        <identifier>
          <key> "<value>"
          <key> "<value>"
          ...

    The format with colon after identifier is also supported (standard lino):

        <identifier>:
          <key> "<value>"

    Args:
        text: The indented Links Notation string to parse

    Returns:
        A tuple of (id, obj) where id is the identifier and obj is the parsed dict

    Raises:
        ValueError: If text is empty or invalid
    """
    if not text:
        raise ValueError("text is required for parse_indented")

    lines = text.split("\n")
    if len(lines) == 0:
        raise ValueError("text must have at least one line (the identifier)")

    # Filter out empty lines to preserve indentation structure for the parser
    # Empty lines would break the indentation context in links-notation
    non_empty_lines = [line for line in lines if line.strip()]

    if len(non_empty_lines) == 0:
        raise ValueError("text must have at least one non-empty line (the identifier)")

    # Convert to standard lino format by adding colon after first line if not present
    # This allows the links-notation parser to properly parse the indented structure
    first_line = non_empty_lines[0].strip()
    if not first_line.endswith(":"):
        lino_text = first_line + ":\n" + "\n".join(non_empty_lines[1:])
    else:
        lino_text = "\n".join(non_empty_lines)

    # Use links-notation parser
    parsed = _parser.parse(lino_text)

    if not parsed or len(parsed) == 0:
        raise ValueError("Failed to parse indented Links Notation")

    # Extract id and key-value pairs from parsed result
    main_link = parsed[0]
    result_id = main_link.id or ""
    obj: dict[str, Any] = {}

    # Process the values array - each entry is a doublet (key value)
    for child in main_link.values or []:
        if hasattr(child, "values") and child.values and len(child.values) == 2:
            key_ref = child.values[0]
            value_ref = child.values[1]

            # Get key string
            key = key_ref.id or ""

            # Get value string, handling null
            value_str = value_ref.id
            if value_str == "null":
                obj[key] = None
            else:
                obj[key] = value_str

    return result_id, obj
