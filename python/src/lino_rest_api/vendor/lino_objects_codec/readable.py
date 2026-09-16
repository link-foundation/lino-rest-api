"""Readable, indented Links Notation representation.

This module implements the default output of :func:`link_notation_objects_codec.encode`:
a plain-text, indented projection where keys and values are written as they are,
so the document can be read, grepped and reviewed without decoding anything.

Shape
-----

One construct -- ``( )`` -- is used for both objects and arrays, at every level
including the root. What distinguishes them is the content of the lines:
``key value`` pairs make a dict, bare values make a list::

    (
      type "RouterState"
      server (
        host "127.0.0.1"
        port 18878
      )
      models (
        "claude-haiku"
        "claude-opus"
      )
    )

Value mapping
-------------

============================== ==========================================
Python value                   Readable form
============================== ==========================================
``dict``                       ``( )`` with one ``key value`` pair per line
``list`` / ``tuple``           ``( )`` with one value per line
``str``                        quoted text, never base64
``int`` / ``float`` / ``bool`` / ``None``  bare, so the type survives the round trip
============================== ==========================================

Empty containers keep their type: an empty list is ``()`` on one line, while an
empty dict is written as ``(`` and ``)`` on two lines.

Text is written as text. A string keeps every character a reader would grep
for, including newlines and tabs, and is quoted with a run of delimiters --
``\"\"\"say \"hi\"\"\"\"`` -- when it holds the delimiter itself. Only the characters a
form cannot carry are escaped, and only they: the value is then written as
``(escaped "...")``, where ``%XX`` stands for one escaped byte. The indented form
escapes the carriage return, which CRLF normalisation would otherwise rewrite,
and the other control characters; the single-line form escapes the newline as
well, because there a record ends at the end of the line. Nothing else is
encoded: base64 lives in :func:`link_notation_objects_codec.encode_compact`,
which a caller asks for by name.

Single-line form
----------------

:func:`encode_line` writes the same document on one line, so one record is one
line and an append-only log stays greppable, tailable and countable by ``wc -l``.
Rows can no longer be told apart by line breaks there, so a dict names itself
with the ``o`` link id the notation already has, and its pairs are written as
their own links::

    (o: (type "RouterState") (server (o: (host "127.0.0.1") (port 18878))))

================== ===============================
Value              Single-line form
================== ===============================
``dict``           ``(o: (key value) ...)``
empty ``dict``     ``(o:)``
``list``           ``(value ...)``
empty ``list``     ``()``
scalars            exactly as in the indented form
================== ===============================

The marker is what answers the ambiguity a flat layout otherwise has: without it
``((key value))`` reads both as the one-pair dict and as the list holding the
two-element list, and an empty key makes it worse. With it, a bare ``( )`` is
always a list and a marked one is always a dict, so every value -- empty key
included -- survives the round trip. Consequently a *hand-written* one-line link
such as ``(a 1)`` is the two-element list, not the one-pair dict: on one line,
dicts say so.
"""

import base64
import math
import re
import unicodedata
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from .debug import trace

#: Default indentation used by :func:`encode`.
DEFAULT_INDENT = "  "

#: Marker of a base64 payload, written by
#: :func:`link_notation_objects_codec.encode_compact` and by versions up to 0.6.0
#: of the readable form, which is still read back.
BASE64_MARKER = "base64"

#: Marker of a string whose unwritable characters are percent-escaped.
#:
#: It reads as ``(escaped "line one%0Aline two")``. Only those characters change;
#: the rest of the text is written as it is, so the value stays readable and
#: greppable.
ESCAPED_MARKER = "escaped"

#: Link id naming a dict in the single-line form, written as ``(o: ...)``.
OBJECT_MARKER = "o"

#: Quote characters that open a quoted reference.
_QUOTE_CHARS = ("'", '"', "`")

#: Characters that force an object key to be quoted.
_KEY_NEEDS_QUOTES = re.compile(r"[\s()':`\"\x00-\x1f\x7f-\x9f]")

#: The indented form, where a value may span several lines.
_FORM_INDENTED = "indented"

#: The single-line form, where a record ends at the end of the line.
_FORM_LINE = "line"

#: The two hexadecimal digits of a percent escape.
_HEX_ESCAPE = re.compile(r"^[0-9a-fA-F]{2}$")

_INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")
_FLOAT_PATTERN = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


class ReadableFormatError(ValueError):
    """Raised when a readable document cannot be parsed."""


class CircularReferenceError(ValueError):
    """Raised when a value cannot be written because it refers back to itself.

    The readable form writes a plain tree and has no place to put the ``obj_N``
    definition ids that name a shared node, so a cycle cannot be represented.
    :func:`link_notation_objects_codec.encode_compact` handles cycles.
    """


def encode(value: Any, indent: str = DEFAULT_INDENT) -> str:
    """Encode a value into the readable, indented Links Notation form.

    Args:
        value: The value to encode.
        indent: Indentation string used per nesting level.

    Returns:
        The readable Links Notation document.

    Raises:
        CircularReferenceError: If the value refers back to itself.
        TypeError: If the value holds a type this format cannot write.
    """
    out: list[str] = []
    _write_value(value, indent, 0, out, set())
    return "".join(out)


def encode_line(value: Any) -> str:
    """Encode a value into the readable, single-line Links Notation form.

    The result never contains a newline, so one value is one line of an
    append-only log. See the module documentation for the shape.

    Args:
        value: The value to encode.

    Returns:
        The readable Links Notation document, on one line.

    Raises:
        CircularReferenceError: If the value refers back to itself.
        TypeError: If the value holds a type this format cannot write.
    """
    out: list[str] = []
    _write_line_value(value, out, set())
    return "".join(out)


def decode_line(text: str) -> Any:
    """Decode the readable, single-line Links Notation form back into a value.

    This is the exact inverse of :func:`encode_line`. Input spanning more than
    one line is rejected: a line-based reader hands over one record at a time,
    and silently accepting several would merge two records into one value.

    Args:
        text: One line of a readable Links Notation document.

    Returns:
        The reconstructed value.

    Raises:
        ReadableFormatError: If the input holds more than one line.
    """
    line = text.strip("\n\r")
    if "\n" in line or "\r" in line:
        raise ReadableFormatError("a single-line document cannot contain a line break")
    return decode(line)


def decode(text: str) -> Any:
    """Decode the readable, indented Links Notation form back into a value.

    Args:
        text: The readable Links Notation document.

    Returns:
        The reconstructed value.

    Raises:
        ReadableFormatError: If the document is not well formed.
    """
    tokens = _tokenize(text)
    trace("readable.decode", lambda: f"{len(tokens)} tokens")
    cursor = _Cursor(tokens)
    rows = cursor.parse_rows(top_level=True)

    if cursor.pos < len(tokens):
        raise ReadableFormatError("unexpected ')' in readable notation")

    # A document holding a single value (for example ``42``) is that value.
    if len(rows) == 1 and len(rows[0]) == 1:
        return _node_to_value(rows[0][0])

    return _rows_to_value(rows, multiline=True, object_marker=False)


# === Encoding ===


def _write_value(value: Any, indent: str, level: int, out: list[str], path: set[int]) -> None:
    if isinstance(value, dict):
        with _on_path(value, path):
            items = list(value.items())
            if not items:
                # An empty dict spans two lines; ``()`` on one line is an empty list.
                out.append("(\n")
                _push_indent(indent, level, out)
                out.append(")")
                return

            def write_pair(pair: tuple[Any, Any]) -> None:
                key, child = pair
                out.append(_format_key(key, _FORM_INDENTED))
                out.append(" ")
                _write_value(child, indent, level + 1, out, path)

            _write_rows(items, indent, level, out, write_pair)
        return

    if isinstance(value, (list, tuple, set, frozenset)):
        with _on_path(value, path):
            items_seq: Sequence[Any] = list(value)

            def write_item(item: Any) -> None:
                _write_value(item, indent, level + 1, out, path)

            _write_rows(items_seq, indent, level, out, write_item)
        return

    out.append(_format_scalar(value, _FORM_INDENTED))


def _write_line_value(value: Any, out: list[str], path: set[int]) -> None:
    """Write a value on one line.

    Dicts name themselves with the ``o`` link id and write each pair as its own
    link, so nothing depends on where lines break.
    """
    if isinstance(value, dict):
        with _on_path(value, path):
            items = list(value.items())
            if not items:
                # ``()`` is the empty list, so the empty dict keeps its marker.
                out.append(f"({OBJECT_MARKER}:)")
                return

            out.append(f"({OBJECT_MARKER}:")
            for key, child in items:
                out.append(f" ({_format_key(key, _FORM_LINE)} ")
                _write_line_value(child, out, path)
                out.append(")")
            out.append(")")
        return

    if isinstance(value, (list, tuple, set, frozenset)):
        with _on_path(value, path):
            out.append("(")
            for index, item in enumerate(value):
                if index:
                    out.append(" ")
                _write_line_value(item, out, path)
            out.append(")")
        return

    out.append(_format_scalar(value, _FORM_LINE))


@contextmanager
def _on_path(value: Any, path: set[int]) -> Iterator[None]:
    """Mark a container as being written, so a reference back to it is caught.

    Only the containers on the way down are tracked: the same object appearing
    twice side by side is written twice, which reads back as two equal values.
    """
    marker = id(value)
    if marker in path:
        raise CircularReferenceError(
            "Cannot write a circular reference in the readable format; "
            "use encode_compact, which names shared nodes with obj_N ids"
        )
    path.add(marker)
    try:
        yield
    finally:
        path.discard(marker)


def _write_rows(
    items: Sequence[Any], indent: str, level: int, out: list[str], write_item: Any
) -> None:
    """Write a container as ``(``, one indented line per item, then ``)``.

    An empty container collapses to ``()``, which reads back as an empty list.
    """
    if not items:
        out.append("()")
        return

    out.append("(")
    for item in items:
        out.append("\n")
        _push_indent(indent, level + 1, out)
        write_item(item)
    out.append("\n")
    _push_indent(indent, level, out)
    out.append(")")


def _push_indent(indent: str, level: int, out: list[str]) -> None:
    for _ in range(level):
        out.append(indent)


def _format_scalar(value: Any, form: str) -> str:
    """Format a scalar value.

    Strings are quoted, everything else stays bare so that its type is
    recoverable when reading the document back.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, str):
        return _format_string(value, form)
    if isinstance(value, (bytes, bytearray)):
        return f"({BASE64_MARKER} {_quote(base64.b64encode(bytes(value)).decode('ascii'))})"
    raise TypeError(f"Unsupported type: {type(value).__name__}")


def _format_float(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    # ``repr`` keeps the decimal point for whole floats (``1.0``), which is what
    # tells a float apart from an int when reading the document back.
    return repr(value)


def _format_string(value: str, form: str) -> str:
    """Format a string value.

    The text is written as text; when it holds characters this form cannot carry,
    those characters -- and only those -- are percent-escaped and the value is
    marked, so the rest of it stays readable and greppable.
    """
    escaped = _escape_unwritable(value, form)
    if escaped is None:
        return _quote(value)
    return f"({ESCAPED_MARKER} {_quote(escaped)})"


def _escape_unwritable(value: str, form: str) -> str | None:
    """Percent-escape the characters this form cannot carry.

    Returns ``None`` when the text can be written as it is. ``%`` is escaped too,
    so escaping is reversible.
    """
    if not any(_is_unwritable(char, form) for char in value):
        return None

    parts: list[str] = []
    for char in value:
        if char == "%" or _is_unwritable(char, form):
            parts.extend(f"%{byte:02X}" for byte in char.encode("utf-8"))
        else:
            parts.append(char)
    return "".join(parts)


def _is_unwritable(char: str, form: str) -> bool:
    """Whether a character has to be escaped in this form.

    A tab is text a reader can see, and so is a newline in the indented form,
    where a value may span lines. A carriage return is escaped because CRLF
    normalisation rewrites it, and the remaining control characters because they
    are not text at all.
    """
    if unicodedata.category(char) != "Cc":
        return False
    if char == "\t":
        return False
    if char == "\n":
        return form == _FORM_LINE
    return True


def _quote(value: str) -> str:
    """Quote a value so that both this reader and the notation's own parser read
    it back unchanged.

    One delimiter is enough while the text holds none of that kind; when it holds
    both kinds, a run of at least three opens the notation's n-quote form, where
    the text is literal and only a run at least as long closes it. A value
    starting with the delimiter would lengthen the opening run, so the other
    delimiter is used for it.
    """
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"

    delimiter = "'" if value.startswith('"') else '"'
    # A run of two delimiters is the empty value, so the n-quote form starts at
    # three; beyond that the run only has to outrun the longest one inside.
    run = delimiter * max(_longest_run(value, delimiter) + 1, 3)
    return f"{run}{value}{run}"


def _longest_run(value: str, char: str) -> int:
    """The length of the longest run of ``char`` in ``value``."""
    longest = 0
    current = 0
    for candidate in value:
        if candidate == char:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _format_key(key: Any, form: str) -> str:
    """Format an object key. Keys are bare when they read as plain identifiers.

    The readable form has string keys, like JSON: a non-string key is written as
    the text it formats to, and reads back as that text.
    """
    if isinstance(key, str):
        text = key
    elif key is None or isinstance(key, (bool, int, float)):
        text = _format_scalar(key, form)
    else:
        raise TypeError(f"Unsupported key type: {type(key).__name__}")

    plain = (
        bool(text)
        and text != BASE64_MARKER
        and text != ESCAPED_MARKER
        and not _KEY_NEEDS_QUOTES.search(text)
    )
    return text if plain else _format_string(text, form)


# === Decoding ===

_TOKEN_OPEN = "open"
_TOKEN_CLOSE = "close"
_TOKEN_NEWLINE = "newline"
_TOKEN_REF = "ref"


class _Token:
    """One token of a readable document."""

    __slots__ = ("kind", "value", "quoted")

    def __init__(self, kind: str, value: str = "", quoted: bool = False) -> None:
        self.kind = kind
        self.value = value
        self.quoted = quoted


class _Node:
    """A parsed element: a reference (remembering whether it was quoted, which is
    what distinguishes a string from a number) or a link."""

    __slots__ = ("is_ref", "value", "quoted", "rows", "multiline", "is_object")

    def __init__(
        self,
        is_ref: bool,
        value: str = "",
        quoted: bool = False,
        rows: list[list["_Node"]] | None = None,
        multiline: bool = False,
        is_object: bool = False,
    ) -> None:
        self.is_ref = is_ref
        self.value = value
        self.quoted = quoted
        self.rows = rows if rows is not None else []
        self.multiline = multiline
        self.is_object = is_object


def _tokenize(text: str) -> list[_Token]:
    """Split a document into parentheses, newlines and references."""
    tokens: list[_Token] = []
    i = 0
    length = len(text)

    while i < length:
        char = text[i]

        if char == "\n":
            tokens.append(_Token(_TOKEN_NEWLINE))
            i += 1
        elif char.isspace():
            i += 1
        elif char == "(":
            tokens.append(_Token(_TOKEN_OPEN))
            i += 1
        elif char == ")":
            tokens.append(_Token(_TOKEN_CLOSE))
            i += 1
        elif char in _QUOTE_CHARS:
            value, i = _read_quoted(text, i, char)
            tokens.append(_Token(_TOKEN_REF, value, quoted=True))
        else:
            start = i
            while (
                i < length
                and not text[i].isspace()
                and text[i] not in "()"
                and text[i] not in _QUOTE_CHARS
            ):
                i += 1
            tokens.append(_Token(_TOKEN_REF, text[start:i], quoted=False))

    return tokens


def _read_quoted(text: str, start: int, quote_char: str) -> tuple[str, int]:
    """Read a quoted reference.

    The opening run of delimiters says how it is read, which is what the
    notation's own parser does:

    * one delimiter -- the text is literal and a doubled delimiter is one literal
      delimiter, which is how versions up to 0.6.0 wrote such values;
    * two -- the empty value;
    * three or more -- the n-quote form: the text is literal, and the value ends
      at the first run at least as long, whose last delimiters close it. A longer
      run therefore belongs to the text, so a value may end with a delimiter.
    """
    opening = _run_length(text, start, quote_char)

    if opening == 2:
        return "", start + 2

    if opening == 1:
        return _read_doubled_quoted(text, start, quote_char)

    length = len(text)
    i = start + opening
    while i < length:
        if text[i] != quote_char:
            i += 1
            continue

        run = _run_length(text, i, quote_char)
        if run >= opening:
            return text[start + opening : i + run - opening], i + run
        i += run

    raise _unterminated_quote(start)


def _read_doubled_quoted(text: str, start: int, quote_char: str) -> tuple[str, int]:
    """Read a value opened by a single delimiter, where a doubled delimiter means
    one literal delimiter."""
    parts: list[str] = []
    i = start + 1
    length = len(text)

    while i < length:
        if text[i] == quote_char:
            if i + 1 < length and text[i + 1] == quote_char:
                parts.append(quote_char)
                i += 2
                continue
            return "".join(parts), i + 1
        parts.append(text[i])
        i += 1

    raise _unterminated_quote(start)


def _run_length(text: str, start: int, char: str) -> int:
    """The length of the run of ``char`` that starts at ``start``."""
    i = start
    while i < len(text) and text[i] == char:
        i += 1
    return i - start


def _unterminated_quote(start: int) -> ReadableFormatError:
    return ReadableFormatError(f"unterminated quoted value starting at character {start}")


class _Cursor:
    """Cursor over the token stream, turning tokens into nodes and rows."""

    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def parse_rows(self, top_level: bool) -> list[list[_Node]]:
        """Parse rows until the matching ``)`` (or the end of input at the top level).

        A row is one line: the values written between two newlines.
        """
        rows: list[list[_Node]] = []
        row: list[_Node] = []

        while self.pos < len(self.tokens):
            token = self.tokens[self.pos]

            if token.kind == _TOKEN_CLOSE:
                if top_level:
                    break
                self.pos += 1
                if row:
                    rows.append(row)
                return rows

            if token.kind == _TOKEN_NEWLINE:
                self.pos += 1
                if row:
                    rows.append(row)
                    row = []
                continue

            row.append(self.parse_node())

        if not top_level:
            raise ReadableFormatError("unterminated '(' in readable notation")

        if row:
            rows.append(row)
        return rows

    def parse_node(self) -> _Node:
        """Parse a single node: a reference or a parenthesised link."""
        token = self.tokens[self.pos]

        if token.kind == _TOKEN_REF:
            self.pos += 1
            return _Node(True, token.value, token.quoted)

        if token.kind == _TOKEN_OPEN:
            self.pos += 1
            is_object = self._take_object_marker()
            multiline = self._link_is_multiline()
            rows = self.parse_rows(top_level=False)
            return _Node(False, rows=rows, multiline=multiline, is_object=is_object)

        raise ReadableFormatError("unexpected token in readable notation")

    def _take_object_marker(self) -> bool:
        """Consume the ``o:`` marker if the link that just opened carries one,
        which is how the single-line form says "this link is a dict, not a list"."""
        if self.pos >= len(self.tokens):
            return False
        token = self.tokens[self.pos]
        is_marker = (
            token.kind == _TOKEN_REF and not token.quoted and token.value == f"{OBJECT_MARKER}:"
        )
        if is_marker:
            self.pos += 1
        return is_marker

    def _link_is_multiline(self) -> bool:
        """Whether the link that just opened spans more than one line, which is
        what tells an empty dict (``(\\n)``) from an empty list (``()``)."""
        for token in self.tokens[self.pos :]:
            if token.kind == _TOKEN_CLOSE:
                return False
            if token.kind == _TOKEN_NEWLINE:
                return True
        return False


def _node_to_value(node: _Node) -> Any:
    if node.is_ref:
        return _ref_to_value(node.value, node.quoted)
    return _rows_to_value(node.rows, node.multiline, node.is_object)


def _rows_to_value(rows: list[list[_Node]], multiline: bool, object_marker: bool) -> Any:
    if object_marker:
        return _marked_object_to_value(rows)

    if not rows:
        return {} if multiline else []

    marked = _decode_marked_value(rows)
    if marked is not None:
        return marked[0]

    # Written on one line, a link is a list of values: a dict on one line says so
    # with the ``o:`` marker, which is what keeps ``(key value)`` unambiguous.
    if not multiline:
        return [_node_to_value(node) for row in rows for node in row]

    # ``key value`` on every line makes a dict; anything else is a list of values.
    is_dict = all(len(row) == 2 and _node_to_key(row[0]) is not None for row in rows)

    if is_dict:
        result: dict[str, Any] = {}
        for row in rows:
            key = _node_to_key(row[0])
            assert key is not None  # checked by is_dict
            result[key] = _node_to_value(row[1])
        return result

    items: list[Any] = []
    for row in rows:
        for node in row:
            items.append(_node_to_value(node))
    return items


def _marked_object_to_value(rows: list[list[_Node]]) -> dict[str, Any]:
    """Build the dict a ``(o: (key value) ...)`` link describes.

    Every value in it is a pair, so anything else is a malformed document rather
    than a silent list.
    """
    result: dict[str, Any] = {}

    for node in (node for row in rows for node in row):
        if node.is_ref or node.is_object:
            raise ReadableFormatError(
                f"an object marked '{OBJECT_MARKER}:' holds (key value) pairs, "
                "found a value that is not a pair"
            )
        if len(node.rows) != 1:
            raise ReadableFormatError(
                f"an object marked '{OBJECT_MARKER}:' holds (key value) pairs, "
                f"found a link of {len(node.rows)} lines"
            )
        row = node.rows[0]
        if len(row) != 2:
            raise ReadableFormatError(
                f"an object marked '{OBJECT_MARKER}:' holds (key value) pairs, "
                f"found a link of {len(row)} values"
            )
        key = _node_to_key(row[0])
        if key is None:
            raise ReadableFormatError(
                f"an object marked '{OBJECT_MARKER}:' holds (key value) pairs, "
                "found a pair whose key is not text"
            )
        result[key] = _node_to_value(row[1])

    return result


def _node_to_key(node: _Node) -> str | None:
    """The key a node in key position spells.

    A reference is the key itself, and a marked link is the text its marker
    escapes, which is how a key holding a character the form cannot carry stays a
    key instead of turning its dict into a list.
    """
    if node.is_ref:
        return node.value
    if node.is_object:
        return None
    try:
        marked = _decode_marked_value(node.rows)
    except ReadableFormatError:
        return None
    return None if marked is None else marked[0]


def _decode_marked_value(rows: list[list[_Node]]) -> tuple[str] | None:
    """Recognise a marked value.

    ``(escaped "...")`` holds text written as it is except for the
    percent-escaped characters the form cannot carry; ``(base64 "...")`` is what
    versions up to 0.6.0 wrote, and is still read. A quoted marker is an ordinary
    dict key, not a marker. The result is wrapped in a tuple so that an empty
    string is still distinguishable from "not a marker".
    """
    if len(rows) != 1 or len(rows[0]) != 2:
        return None

    marker, payload = rows[0]
    if not marker.is_ref or marker.quoted:
        return None
    if marker.value not in (ESCAPED_MARKER, BASE64_MARKER):
        return None
    if not payload.is_ref or not payload.quoted:
        return None

    if marker.value == ESCAPED_MARKER:
        return (_unescape(payload.value),)

    try:
        decoded = base64.b64decode(payload.value, validate=True).decode("utf-8")
    except Exception as error:  # noqa: BLE001 - reported as a format error
        raise ReadableFormatError(f"invalid base64 value: {error}") from error
    return (decoded,)


def _unescape(payload: str) -> str:
    """Undo the percent-escaping of an ``(escaped "...")`` payload.

    Escapes stand for bytes, so a character outside ASCII is written as its UTF-8
    bytes and read back from them.
    """
    out = bytearray()
    i = 0
    length = len(payload)

    while i < length:
        if payload[i] != "%":
            out.extend(payload[i].encode("utf-8"))
            i += 1
            continue

        escape = payload[i + 1 : i + 3]
        if len(escape) != 2:
            raise ReadableFormatError(f"truncated escape at character {i} of an escaped value")
        if not _HEX_ESCAPE.match(escape):
            raise ReadableFormatError(f"invalid escape '%{escape}' in an escaped value")
        out.append(int(escape, 16))
        i += 3

    try:
        return out.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReadableFormatError(f"invalid UTF-8 escaped value: {error}") from error


def _ref_to_value(value: str, quoted: bool) -> None | bool | int | float | str:
    """Convert a reference to a value.

    Quoted references are always strings; bare references keep the type they were
    written with.
    """
    if quoted:
        return value

    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "NaN":
        return math.nan
    if value == "Infinity":
        return math.inf
    if value == "-Infinity":
        return -math.inf

    if _INTEGER_PATTERN.match(value):
        return int(value)
    if _FLOAT_PATTERN.match(value):
        return float(value)

    return value
