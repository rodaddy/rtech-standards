"""Secret redaction for log records.

The key is retained and only the value is replaced, so a post-mortem can still
see that an auth payload was present without the payload leaking. Dropping the
key entirely would lose information that matters when reconstructing an incident.

See OBSERVABILITY_CONTRACT.md section 4.
"""

from __future__ import annotations

from typing import Any

REDACTED = "[REDACTED]"

#: Key fragments that mark a value as secret. Matched case-insensitively against
#: the whole key, as a substring, so `db_password` and `X-Api-Key` both match.
SECRET_KEY_FRAGMENTS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "credential",
        "private_key",
        "session",
        "cookie",
    }
)


def is_secret_key(key: str) -> bool:
    """Report whether a field name marks its value as secret.

    Args:
        key: Field name to test.

    Returns:
        True when the value must be redacted.
    """
    lowered = key.lower()
    return any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS)


def redact(value: Any) -> Any:
    """Return a copy of a value with secret-valued keys replaced.

    Recurses into mappings, lists, and tuples, because a nested secret is still a
    secret. The caller's object is never mutated: redaction applies to the record
    being emitted, and callers are not trusted to have pre-redacted.

    Args:
        value: Arbitrary structure to sanitize.

    Returns:
        A sanitized copy, structurally identical apart from redacted values.
    """
    if isinstance(value, dict):
        return {
            key: (REDACTED if is_secret_key(str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        rebuilt = [redact(item) for item in value]
        return type(value)(rebuilt) if isinstance(value, tuple) else rebuilt
    return value
