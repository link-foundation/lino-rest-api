"""Opt-in tracing for the codec.

Tracing is off by default and writes nothing. It is turned on either by setting
the ``LINO_CODEC_DEBUG`` environment variable to a truthy value (``1``, ``true``,
``yes``, ``on``) or by calling :func:`set_debug_enabled` from code.

The same switch and the same environment variable exist in the JavaScript, Rust
and C# implementations, so a problem can be traced the same way in every
language.
"""

import os
import sys
from collections.abc import Callable

#: Name of the environment variable that turns tracing on.
DEBUG_ENV_VAR = "LINO_CODEC_DEBUG"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

_overridden: bool | None = None


def is_debug_enabled() -> bool:
    """Return whether tracing is currently on."""
    if _overridden is not None:
        return _overridden
    raw = os.environ.get(DEBUG_ENV_VAR)
    return raw is not None and raw.strip().lower() in _TRUTHY


def set_debug_enabled(enabled: bool | None) -> None:
    """Turn tracing on or off from code, overriding the environment variable.

    Args:
        enabled: ``True``/``False`` to force, ``None`` to follow the environment.
    """
    global _overridden
    _overridden = None if enabled is None else bool(enabled)


def trace(scope: str, message: Callable[[], str]) -> None:
    """Emit a trace message when tracing is on.

    The message is passed as a callable so that building it costs nothing while
    tracing is off, which is the normal case.

    Args:
        scope: Where the message comes from, for example ``readable.decode``.
        message: Builds the message text.
    """
    if not is_debug_enabled():
        return
    print(f"[lino-codec] {scope}: {message()}", file=sys.stderr)
