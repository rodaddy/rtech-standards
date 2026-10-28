"""Construction of the contract's log envelope.

The five required fields are stamped here rather than accepted from callers. If
callers could supply `service`, it would be spelled differently across repos and
every cross-service Loki query would fracture.

See OBSERVABILITY_CONTRACT.md sections 1 and 2.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from typing import Any

from .config import LogLevel
from .redaction import redact

#: Fields the contract defines at the top level. Anything else a caller passes is
#: relocated into `context`, because a flat namespace anyone can extend is how
#: field names diverge between services (contract 1.3).
TOP_LEVEL_FIELDS: frozenset[str] = frozenset(
    {
        "timestamp",
        "level",
        "service",
        "host",
        "message",
        "correlation_id",
        "event",
        "error",
        "duration_ms",
        "context",
    }
)

#: The only two fields promoted to Loki labels. Everything else stays in the body:
#: Loki builds one index stream per unique label combination, so a
#: high-cardinality label produces unbounded streams (contract section 2).
LABEL_FIELDS: tuple[str, str] = ("service", "host")

_CACHED_HOST: str | None = None


def hostname() -> str:
    """Return this host's name, resolved once and cached.

    Returns:
        The short hostname used as the `host` label.
    """
    global _CACHED_HOST
    if _CACHED_HOST is None:
        _CACHED_HOST = socket.gethostname()
    return _CACHED_HOST


def utc_timestamp() -> str:
    """Return the current time as an RFC 3339 UTC stamp with millisecond precision.

    Returns:
        A timestamp such as `2026-07-25T04:16:07.418Z`.
    """
    now = datetime.now(UTC)
    return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}.{now.microsecond // 1000:03d}Z"


def build_envelope(
    *,
    service: str,
    level: LogLevel,
    message: str,
    correlation_id: str | None = None,
    event: str | None = None,
    error: dict[str, Any] | None = None,
    duration_ms: float | None = None,
    context: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble one conforming envelope.

    Args:
        service: Catalog service name, stamped from configuration.
        level: Severity of this record.
        message: Human-readable text, without a trailing newline.
        correlation_id: Optional identifier tying related records together.
        event: Optional stable machine-readable event name.
        error: Optional `{type, message, stacktrace}` describing a failure.
        duration_ms: Optional elapsed milliseconds for a completed operation.
        context: Optional structured detail.
        extra: Non-contract fields, relocated into `context`.

    Returns:
        The envelope as a plain dict, with secrets already redacted.
    """
    merged_context: dict[str, Any] = {}
    if context:
        merged_context.update(context)
    if extra:
        merged_context.update(extra)

    envelope: dict[str, Any] = {
        "timestamp": utc_timestamp(),
        "level": level.value,
        "service": service,
        "host": hostname(),
        "message": message.rstrip("\n"),
    }

    if correlation_id is not None:
        envelope["correlation_id"] = correlation_id
    if event is not None:
        envelope["event"] = event
    if error is not None:
        envelope["error"] = redact(error)
    if duration_ms is not None:
        envelope["duration_ms"] = duration_ms
    if merged_context:
        envelope["context"] = redact(merged_context)

    return envelope
