"""Object encoder/decoder for Links Notation format.

Two output formats are available:

* :meth:`ObjectCodec.encode` -- the default. A readable, indented document where
  keys and values are written as they are, so it can be read and reviewed
  directly. See :mod:`link_notation_objects_codec.readable`.
* :meth:`ObjectCodec.encode_compact` -- the previous default. A single line where
  every value is type-tagged and every string is base64-encoded.

:meth:`ObjectCodec.decode` accepts both, so documents written by earlier versions
keep working and migrate to the readable form on the next write.
"""

import base64
import math
import re
from typing import Any

from links_notation import Link, Parser

from . import readable
from .debug import trace

#: Type markers that open a compact document, across all implementations.
#:
#: The languages historically disagreed on three of them -- Python writes
#: ``None``/``list``/``dict`` where JavaScript and Rust write
#: ``null``/``array``/``object`` -- so every implementation accepts the union and
#: can read a compact document written by any of the others.
_COMPACT_TYPE_MARKERS: frozenset[str] = frozenset(
    {
        "null",
        "None",
        "bool",
        "int",
        "float",
        "str",
        "array",
        "list",
        "object",
        "dict",
    }
)


#: Markers a compact document writes without a payload, so ``(null)`` is a
#: compact null while ``(null 1)`` is a readable line holding two values.
_EMPTY_BODY_MARKERS: frozenset[str] = frozenset({"null", "None", "undefined"})


def is_compact_notation(notation: str) -> bool:
    """Whether a document is in the compact (type-tagged, base64) format.

    The check looks at the first non-empty line: a compact document opens with
    ``(`` followed by a type marker, optionally preceded by an ``obj_N:``
    definition id. A readable document opens with ``(`` followed by a key, a
    value or a newline, so it is not mistaken for a compact one.

    Args:
        notation: The document to inspect.

    Returns:
        ``True`` when the document should be read by :func:`decode_compact`.
    """
    first_line = next((line.strip() for line in notation.splitlines() if line.strip()), None)
    if first_line is None or not first_line.startswith("("):
        return False

    # A compact document names the type of its value first, so a link that opens
    # another link straight away is the readable form, whose links nest.
    marker, rest = _split_token(first_line[1:].lstrip())

    # Skip the ``obj_N:`` definition id, if present.
    if marker.endswith(":"):
        if not marker[:-1].startswith("obj_"):
            return False
        marker, rest = _split_token(rest.lstrip())

    if marker not in _COMPACT_TYPE_MARKERS:
        return False

    # A compact null is the whole link: ``(null)``. A link that holds more than
    # the marker is a readable line whose first value happens to be null.
    if marker in _EMPTY_BODY_MARKERS:
        return rest.lstrip().startswith(")")

    return True


def _split_token(text: str) -> tuple[str, str]:
    """Split off the first token of a link body.

    The token is the text up to the next whitespace or parenthesis; a body that
    opens with a parenthesis has no token of its own.
    """
    match = re.search(r"[\s()]", text)
    return (text, "") if match is None else (text[: match.start()], text[match.start() :])


class ObjectCodec:
    """Codec for encoding/decoding Python objects to/from Links Notation."""

    # Type identifiers
    TYPE_NONE = "None"
    TYPE_BOOL = "bool"
    TYPE_INT = "int"
    TYPE_FLOAT = "float"
    TYPE_STR = "str"
    TYPE_LIST = "list"
    TYPE_DICT = "dict"

    def __init__(self) -> None:
        """Initialize the codec."""
        self.parser = Parser()
        # For tracking object identity during encoding
        self._encode_memo: dict[int, str] = {}
        self._encode_counter: int = 0
        # For tracking which objects need IDs (referenced multiple times or circularly)
        self._needs_id: set[int] = set()
        # For storing all definitions during encoding
        self._all_definitions: list[tuple[str, Link]] = []
        # For tracking references during decoding
        self._decode_memo: dict[str, Any] = {}
        # For storing all links during multi-link decoding
        self._all_links: list[Any] = []

    def _make_link(self, *parts: str) -> Link:
        """
        Create a Link from string parts.

        Args:
            *parts: String parts to include in the link

        Returns:
            Link object with parts as Link values
        """
        # Each part becomes a Link with that id
        values = [Link(link_id=part) for part in parts]
        return Link(values=values)

    def _find_objects_needing_ids(
        self,
        obj: Any,
        seen: dict[int, list[int]] | None = None,
        path: list[int] | None = None,
    ) -> None:
        """
        First pass: identify which objects need IDs (referenced multiple times or circularly).

        Args:
            obj: The object to analyze
            seen: Dict mapping object ID to list of parent IDs in the path
            path: Current path of object IDs from root
        """
        if seen is None:
            seen = {}
        if path is None:
            path = []

        # Only track mutable objects
        if not isinstance(obj, (list, dict)):
            return

        obj_id = id(obj)

        # If we've seen this object before, it's referenced multiple times or circularly
        if obj_id in seen:
            self._needs_id.add(obj_id)
            # Also mark all objects in the cycle as needing IDs
            if obj_id in path:
                # This is a circular reference - mark all objects in the cycle
                cycle_start = path.index(obj_id)
                for cycle_obj_id in path[cycle_start:]:
                    self._needs_id.add(cycle_obj_id)
            return  # Don't recurse again

        # Mark as seen with current path
        seen[obj_id] = list(path)
        # Add to current path
        new_path = path + [obj_id]

        # Recurse into structure
        if isinstance(obj, list):
            for item in obj:
                self._find_objects_needing_ids(item, seen, new_path)
        elif isinstance(obj, dict):
            for key, value in obj.items():
                self._find_objects_needing_ids(key, seen, new_path)
                self._find_objects_needing_ids(value, seen, new_path)

    def encode(self, obj: Any, indent: str = readable.DEFAULT_INDENT) -> str:
        """
        Encode a Python object to the readable, indented Links Notation format.

        Args:
            obj: The Python object to encode
            indent: Indentation string used per nesting level (for example ``"    "``)

        Returns:
            Readable Links Notation document
        """
        return readable.encode(obj, indent)

    def encode_line(self, obj: Any) -> str:
        """
        Encode a Python object to the readable, single-line Links Notation format.

        The result never contains a newline, so one value is one line: an
        append-only log written this way stays greppable, tailable and countable
        by ``wc -l``. See :mod:`link_notation_objects_codec.readable` for the shape.

        Args:
            obj: The Python object to encode

        Returns:
            One line of readable Links Notation
        """
        return readable.encode_line(obj)

    def decode_line(self, notation: str) -> Any:
        """
        Decode one line of the readable, single-line Links Notation format.

        This is the exact inverse of :meth:`encode_line`. Input spanning more
        than one line is rejected, so two log records never merge into one value.

        Args:
            notation: One line of readable Links Notation

        Returns:
            Reconstructed Python object
        """
        return readable.decode_line(notation)

    def encode_compact(self, obj: Any) -> str:
        """
        Encode a Python object to the compact, single-line Links Notation format.

        Every value is tagged with its type and every string is base64-encoded, so
        the whole document fits on one line and carries no readable text. This was
        the default before the readable format; callers now opt into it explicitly.

        Uses multi-link format to avoid parser bugs with nested self-references.
        Each self-referenced object is defined at the top level.

        Args:
            obj: The Python object to encode

        Returns:
            String representation in compact Links Notation format
        """
        # Reset state for each encode operation
        self._encode_memo = {}
        self._encode_counter = 0
        self._needs_id = set()
        self._all_definitions = []

        # First pass: identify which objects need IDs (referenced multiple times or circularly)
        self._find_objects_needing_ids(obj)

        # Encode the object (this populates _all_definitions)
        main_link = self._encode_value(obj, depth=0)

        # If we have additional definitions, output them all as multi-link format
        if self._all_definitions:
            # The main link should be first
            all_links = [main_link]
            # Add all other definitions
            for ref_id, link in self._all_definitions:
                # Only add if not the main link (avoid duplicates)
                if not (main_link.id and main_link.id == ref_id):
                    all_links.append(link)

            # Format as multi-link (newline separated)
            return "\n".join(link.format() for link in all_links)

        # Single link output
        return main_link.format()

    def encode_obfuscated(self, obj: Any) -> str:
        """
        Encode a Python object to the compact format.

        Deprecated alias of :meth:`encode_compact`, kept for callers written
        against the earlier name.

        Args:
            obj: The Python object to encode

        Returns:
            String representation in compact Links Notation format
        """
        return self.encode_compact(obj)

    def decode(self, notation: str) -> Any:
        """
        Decode Links Notation format to a Python object.

        Both the readable format and the compact (base64) format are accepted, so
        files written by earlier versions keep working and migrate on next write.

        Args:
            notation: String in Links Notation format

        Returns:
            Reconstructed Python object
        """
        if notation is None or not notation.strip():
            return None

        if is_compact_notation(notation):
            trace("codec.decode", lambda: "compact notation detected")
            return self.decode_compact(notation)

        trace("codec.decode", lambda: "readable notation detected")
        return readable.decode(notation)

    def decode_compact(self, notation: str) -> Any:
        """
        Decode the compact (type-tagged, base64) Links Notation format.

        Args:
            notation: String in compact Links Notation format

        Returns:
            Reconstructed Python object
        """
        # Reset state for each decode operation
        self._decode_memo = {}
        self._all_links = []

        links = self.parser.parse(notation)
        if not links:
            return None

        # If there are multiple links, store them all for forward reference resolution
        if len(links) > 1:
            self._all_links = links
            # Decode the first link (this will be the main result)
            # Forward references will be resolved automatically
            result = self._decode_link(links[0])
            return result

        link = links[0]

        # Handle case where format() creates output like (obj_0) which parser wraps
        # The parser returns a wrapper Link with no ID, containing the actual Link as first value
        if (
            not link.id
            and link.values
            and len(link.values) == 1
            and hasattr(link.values[0], "id")
            and link.values[0].id
            and link.values[0].id.startswith("obj_")
        ):
            # Extract the actual Link
            link = link.values[0]

        return self._decode_link(link)

    def _encode_value(self, obj: Any, visited: set[int] | None = None, depth: int = 0) -> Link:
        """
        Encode a value into a Link.

        Args:
            obj: The value to encode
            visited: Set of object IDs currently being processed (for cycle detection)
            depth: Current nesting depth (0 = top level)

        Returns:
            Link object
        """
        if visited is None:
            visited = set()

        obj_id = id(obj)

        # Check if we've seen this object before (for circular references and shared objects)
        # Only track mutable objects (lists, dicts)
        if isinstance(obj, (list, dict)) and obj_id in self._encode_memo:
            # Return a reference to the previously defined object
            ref_id = self._encode_memo[obj_id]
            return Link(link_id=ref_id)

        # For mutable objects that need IDs, assign them
        if isinstance(obj, (list, dict)) and obj_id in self._needs_id:
            # Assign an ID if not already assigned
            if obj_id not in self._encode_memo:
                ref_id = f"obj_{self._encode_counter}"
                self._encode_counter += 1
                self._encode_memo[obj_id] = ref_id

            if obj_id in visited:
                # We're in a cycle, create a direct reference
                ref_id = self._encode_memo[obj_id]
                return Link(link_id=ref_id)

            # Add to visited set
            visited = visited | {obj_id}

        # Encode based on type
        if obj is None:
            return self._make_link(self.TYPE_NONE)

        elif isinstance(obj, bool):
            # Must check bool before int because bool is a subclass of int
            return self._make_link(self.TYPE_BOOL, "true" if obj else "false")

        elif isinstance(obj, int):
            return self._make_link(self.TYPE_INT, str(obj))

        elif isinstance(obj, float):
            # Handle special float values
            if math.isnan(obj):
                return self._make_link(self.TYPE_FLOAT, "NaN")
            elif math.isinf(obj):
                if obj > 0:
                    return self._make_link(self.TYPE_FLOAT, "Infinity")
                else:
                    return self._make_link(self.TYPE_FLOAT, "-Infinity")
            else:
                return self._make_link(self.TYPE_FLOAT, str(obj))

        elif isinstance(obj, str):
            # Encode strings as base64 to handle special characters, newlines, etc.
            b64_encoded = base64.b64encode(obj.encode("utf-8")).decode("ascii")
            return self._make_link(self.TYPE_STR, b64_encoded)

        elif isinstance(obj, list):
            parts = []
            for item in obj:
                # Encode each item with increased depth
                item_link = self._encode_value(item, visited, depth + 1)
                parts.append(item_link)

            # If this list has an ID, use self-reference format: (obj_id: list item1 item2 ...)
            if obj_id in self._encode_memo:
                ref_id = self._encode_memo[obj_id]
                # Create the definition with self-reference ID
                definition = Link(link_id=ref_id, values=[Link(link_id=self.TYPE_LIST)] + parts)
                # Store for multi-link output if not at top level
                if depth > 0:
                    self._all_definitions.append((ref_id, definition))
                    # Return a reference instead of the full definition
                    return Link(link_id=ref_id)
                return definition
            else:
                # Wrap in a type marker for lists without IDs: (list item1 item2 ...)
                return Link(values=[Link(link_id=self.TYPE_LIST)] + parts)

        elif isinstance(obj, dict):
            parts = []
            for key, value in obj.items():
                # Encode key and value with increased depth
                key_link = self._encode_value(key, visited, depth + 1)
                value_link = self._encode_value(value, visited, depth + 1)
                # Create a pair link
                pair = Link(values=[key_link, value_link])
                parts.append(pair)

            # If this dict has an ID, use self-reference format: (obj_id: dict (key val) ...)
            if obj_id in self._encode_memo:
                ref_id = self._encode_memo[obj_id]
                # Create the definition with self-reference ID
                definition = Link(link_id=ref_id, values=[Link(link_id=self.TYPE_DICT)] + parts)
                # Store for multi-link output if not at top level
                if depth > 0:
                    self._all_definitions.append((ref_id, definition))
                    # Return a reference instead of the full definition
                    return Link(link_id=ref_id)
                return definition
            else:
                # Wrap in a type marker for dicts without IDs: (dict (key val) ...)
                return Link(values=[Link(link_id=self.TYPE_DICT)] + parts)

        else:
            raise TypeError(f"Unsupported type: {type(obj)}")

    def _decode_link(self, link: Link) -> Any:
        """
        Decode a Link into a Python value.

        Args:
            link: Link object to decode

        Returns:
            Decoded Python value
        """
        # Check if this is a direct reference to a previously decoded object
        # Direct references have an id but no values, or the id refers to an existing object
        if link.id and link.id in self._decode_memo:
            return self._decode_memo[link.id]

        if not link.values:
            # Empty link - this might be a simple id, reference, or empty collection
            if link.id:
                # If it's in memo, return the cached object
                if link.id in self._decode_memo:
                    return self._decode_memo[link.id]

                # If it starts with obj_, check if we have a forward reference in _all_links
                if link.id.startswith("obj_") and self._all_links:
                    # Look for this ID in the remaining links
                    for other_link in self._all_links:
                        if hasattr(other_link, "id") and other_link.id == link.id:
                            # Found it! Decode it now
                            return self._decode_link(other_link)

                    # Not found in links - create empty list as fallback
                    result: list[Any] = []
                    self._decode_memo[link.id] = result
                    return result

                # Otherwise it's just a string ID
                return link.id
            return None

        # Check if this link has a self-reference ID (format: obj_0: type ...)
        self_ref_id = None
        if link.id and link.id.startswith("obj_"):
            self_ref_id = link.id
            # If this is a back-reference (already in memo), return it
            if self_ref_id in self._decode_memo:
                return self._decode_memo[self_ref_id]

        # Get the type marker from the first value
        first_value = link.values[0]
        if not hasattr(first_value, "id") or not first_value.id:
            # Not a type marker we recognize
            return None

        type_marker = first_value.id

        if type_marker == self.TYPE_NONE:
            return None

        elif type_marker == self.TYPE_BOOL:
            if len(link.values) > 1:
                bool_value = link.values[1]
                if hasattr(bool_value, "id"):
                    return bool_value.id.lower() == "true"
            return False

        elif type_marker == self.TYPE_INT:
            if len(link.values) > 1:
                int_value = link.values[1]
                if hasattr(int_value, "id"):
                    return int(int_value.id)
            return 0

        elif type_marker == self.TYPE_FLOAT:
            if len(link.values) > 1:
                float_value = link.values[1]
                if hasattr(float_value, "id"):
                    value_str = float_value.id
                    if value_str == "NaN":
                        return math.nan
                    elif value_str == "Infinity":
                        return math.inf
                    elif value_str == "-Infinity":
                        return -math.inf
                    else:
                        return float(value_str)
            return 0.0

        elif type_marker == self.TYPE_STR:
            if len(link.values) > 1:
                str_value = link.values[1]
                if hasattr(str_value, "id"):
                    b64_str = str_value.id
                    # Decode from base64
                    try:
                        decoded_bytes = base64.b64decode(b64_str)
                        return decoded_bytes.decode("utf-8")
                    except Exception:
                        # If decode fails, return the raw value
                        return b64_str
            return ""

        elif type_marker == self.TYPE_LIST:
            # New format with self-reference: (obj_0: list item1 item2 ...)
            start_idx = 1
            list_id = self_ref_id  # Use self-reference ID from link.id if present

            result_list: list[Any] = []
            if list_id:
                self._decode_memo[list_id] = result_list

            for item_link in link.values[start_idx:]:
                decoded_item = self._decode_link(item_link)
                result_list.append(decoded_item)
            return result_list

        elif type_marker == self.TYPE_DICT:
            # New format with self-reference: (obj_0: dict (key val) ...)
            start_idx = 1
            dict_id = self_ref_id  # Use self-reference ID from link.id if present

            result_dict: dict[Any, Any] = {}
            if dict_id:
                self._decode_memo[dict_id] = result_dict

            for pair_link in link.values[start_idx:]:
                if hasattr(pair_link, "values") and len(pair_link.values) >= 2:
                    key_link = pair_link.values[0]
                    value_link = pair_link.values[1]

                    decoded_key = self._decode_link(key_link)
                    decoded_value = self._decode_link(value_link)

                    result_dict[decoded_key] = decoded_value
            return result_dict

        else:
            # Unknown type marker
            raise ValueError(f"Unknown type marker: {type_marker}")


# Convenience functions
_default_codec = ObjectCodec()


def encode(obj: Any, indent: str = readable.DEFAULT_INDENT) -> str:
    """
    Encode a Python object to the readable, indented Links Notation format.

    Args:
        obj: The Python object to encode
        indent: Indentation string used per nesting level

    Returns:
        Readable Links Notation document

    Example:
        >>> encode({"age": 30})
        '(\n  age 30\n)'
    """
    return _default_codec.encode(obj, indent)


def encode_line(obj: Any) -> str:
    """
    Encode a Python object to the readable, single-line Links Notation format.

    The result never contains a newline, so one value is one line of an
    append-only log.

    Args:
        obj: The Python object to encode

    Returns:
        One line of readable Links Notation

    Example:
        >>> encode_line({"age": 30})
        '(o: (age 30))'
    """
    return _default_codec.encode_line(obj)


def decode_line(notation: str) -> Any:
    """
    Decode one line of the readable, single-line Links Notation format.

    The exact inverse of :func:`encode_line`.

    Args:
        notation: One line of readable Links Notation

    Returns:
        Reconstructed Python object

    Example:
        >>> decode_line('(o: (age 30))')
        {'age': 30}
    """
    return _default_codec.decode_line(notation)


def encode_compact(obj: Any) -> str:
    """
    Encode a Python object to the compact, single-line Links Notation format.

    Every string is base64-encoded and the whole document is written on one line.
    :func:`decode` reads this form as well, so stored documents remain readable by
    the current version.

    Args:
        obj: The Python object to encode

    Returns:
        String representation in compact Links Notation format
    """
    return _default_codec.encode_compact(obj)


def encode_obfuscated(obj: Any) -> str:
    """
    Encode a Python object to the compact format.

    Deprecated alias of :func:`encode_compact`.

    Args:
        obj: The Python object to encode

    Returns:
        String representation in compact Links Notation format
    """
    return _default_codec.encode_obfuscated(obj)


def decode(notation: str) -> Any:
    """
    Decode Links Notation format to a Python object.

    Both the readable format and the compact (base64) format are accepted.

    Args:
        notation: String in Links Notation format

    Returns:
        Reconstructed Python object
    """
    return _default_codec.decode(notation)


def decode_compact(notation: str) -> Any:
    """
    Decode the compact (type-tagged, base64) Links Notation format.

    Args:
        notation: String in compact Links Notation format

    Returns:
        Reconstructed Python object
    """
    return _default_codec.decode_compact(notation)
