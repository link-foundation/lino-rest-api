"""
Object encoder/decoder for Links Notation format.

Vendored from https://github.com/link-foundation/link-notation-objects-codec
until the package is published to PyPI.
"""

import base64
import math
from typing import Any

from links_notation import Link, Parser, format_links


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
    TYPE_REF = "ref"

    def __init__(self) -> None:
        """Initialize the codec."""
        self.parser = Parser()
        # For tracking object identity during encoding
        self._encode_memo: dict[int, str] = {}
        self._encode_counter: int = 0
        # For tracking references during decoding
        self._decode_memo: dict[str, Any] = {}

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

    def encode(self, obj: Any) -> str:
        """
        Encode a Python object to Links Notation format.

        Args:
            obj: The Python object to encode

        Returns:
            String representation in Links Notation format
        """
        # Reset memo for each encode operation
        self._encode_memo = {}
        self._encode_counter = 0

        link = self._encode_value(obj)
        return format_links([link])

    def decode(self, notation: str) -> Any:
        """
        Decode Links Notation format to a Python object.

        Args:
            notation: String in Links Notation format

        Returns:
            Reconstructed Python object
        """
        # Reset memo for each decode operation
        self._decode_memo = {}

        links = self.parser.parse(notation)
        if not links:
            return None

        return self._decode_link(links[0])

    def _encode_value(self, obj: Any, visited: set[int] | None = None) -> Link:
        """
        Encode a value into a Link.

        Args:
            obj: The value to encode
            visited: Set of object IDs currently being processed (for cycle detection)

        Returns:
            Link object
        """
        if visited is None:
            visited = set()

        obj_id = id(obj)

        # Check if we've seen this object before (for circular references and shared objects)
        # Only track mutable objects (lists, dicts)
        if isinstance(obj, (list, dict)) and obj_id in self._encode_memo:
            # Return a reference to the previously encoded object
            ref_id = self._encode_memo[obj_id]
            return self._make_link(self.TYPE_REF, ref_id)

        # For mutable objects, check if we're in a cycle
        if isinstance(obj, (list, dict)):
            if obj_id in visited:
                # We're in a cycle, create a reference
                if obj_id not in self._encode_memo:
                    # Assign an ID for this object
                    ref_id = f"obj_{self._encode_counter}"
                    self._encode_counter += 1
                    self._encode_memo[obj_id] = ref_id
                ref_id = self._encode_memo[obj_id]
                return self._make_link(self.TYPE_REF, ref_id)

            # Add to visited set
            visited = visited | {obj_id}

            # Assign an ID to this object
            ref_id = f"obj_{self._encode_counter}"
            self._encode_counter += 1
            self._encode_memo[obj_id] = ref_id

        # Encode based on type
        if obj is None:
            return self._make_link(self.TYPE_NONE)

        elif isinstance(obj, bool):
            # Must check bool before int because bool is a subclass of int
            return self._make_link(self.TYPE_BOOL, str(obj))

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
            ref_id = self._encode_memo[obj_id]
            # Encode as: (list ref_id item0 item1 item2 ...)
            parts = [Link(link_id=self.TYPE_LIST), Link(link_id=ref_id)]
            for item in obj:
                # Encode each item
                item_link = self._encode_value(item, visited)
                parts.append(item_link)
            return Link(values=parts)

        elif isinstance(obj, dict):
            ref_id = self._encode_memo[obj_id]
            # Encode as: (dict ref_id (key0 value0) (key1 value1) ...)
            parts = [Link(link_id=self.TYPE_DICT), Link(link_id=ref_id)]
            for key, value in obj.items():
                # Encode key and value
                key_link = self._encode_value(key, visited)
                value_link = self._encode_value(value, visited)
                # Create a pair link
                pair = Link(values=[key_link, value_link])
                parts.append(pair)
            return Link(values=parts)

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
        if not link.values:
            # Empty link - this might be a simple id
            if link.id:
                return link.id
            return None

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
                    return bool_value.id == "True"
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

        elif type_marker == self.TYPE_REF:
            # This is a reference to a previously decoded object
            if len(link.values) > 1:
                ref_value = link.values[1]
                if hasattr(ref_value, "id"):
                    ref_id = ref_value.id
                    if ref_id in self._decode_memo:
                        return self._decode_memo[ref_id]
            raise ValueError("Unknown reference in link")

        elif type_marker == self.TYPE_LIST:
            if len(link.values) < 2:
                return []

            ref_value = link.values[1]
            ref_id = ref_value.id if hasattr(ref_value, "id") else None

            # Create the list object first (to handle circular references)
            result: list[Any] = []
            if ref_id:
                self._decode_memo[ref_id] = result

            # Decode items
            for i in range(2, len(link.values)):
                item_link = link.values[i]
                decoded_item = self._decode_link(item_link)
                result.append(decoded_item)

            return result

        elif type_marker == self.TYPE_DICT:
            if len(link.values) < 2:
                return {}

            ref_value = link.values[1]
            ref_id = ref_value.id if hasattr(ref_value, "id") else None

            # Create the dict object first (to handle circular references)
            result_dict: dict[Any, Any] = {}
            if ref_id:
                self._decode_memo[ref_id] = result_dict

            # Decode key-value pairs
            for i in range(2, len(link.values)):
                pair_link = link.values[i]
                if hasattr(pair_link, "values") and len(pair_link.values) >= 2:
                    # This should be a link with 2 values: key and value
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


def encode(obj: Any) -> str:
    """
    Encode a Python object to Links Notation format.

    Args:
        obj: The Python object to encode

    Returns:
        String representation in Links Notation format
    """
    return _default_codec.encode(obj)


def decode(notation: str) -> Any:
    """
    Decode Links Notation format to a Python object.

    Args:
        notation: String in Links Notation format

    Returns:
        Reconstructed Python object
    """
    return _default_codec.decode(notation)
