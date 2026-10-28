"""Configuration gathering for the observability contract.

Every fact is read once at startup, validated, and frozen into an immutable
object that is passed down explicitly. Scattered environment reads elsewhere in
an application are non-conforming: they make the effective configuration
impossible to determine from one place.

See OBSERVABILITY_CONTRACT.md section 5.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class LogLevel(StrEnum):
    """The five conforming log levels.

    Spelled out in full because Loki matches level values literally; `warn`,
    `err`, and `crit` are non-conforming (contract section 1.3).
    """

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ConfigError(Exception):
    """Raised when configuration is missing or invalid.

    The contract fails closed rather than guessing: an unattributable record or a
    silently downgraded level is worse than a refusal to start (contract 5.1).
    """


DEFAULT_LOG_ROOT = Path("/mnt/logs/services")


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    """Resolved, validated, immutable logging configuration.

    Attributes:
        service: Catalog service name. Becomes a Loki label.
        level: Minimum level to emit.
        log_file: Destination for JSON Lines records, or None for stdout only.
        stdout: Whether to also emit to stdout (journald captures it).
    """

    service: str
    level: LogLevel
    log_file: Path | None
    stdout: bool


def _resolve_level(raw: str | None) -> LogLevel:
    """Parse a level name, failing closed on anything unrecognized.

    Args:
        raw: Candidate level name, or None to use the contract default.

    Returns:
        The matching LogLevel.

    Raises:
        ConfigError: If the value is not one of the five conforming levels.
    """
    if raw is None or raw == "":
        return LogLevel.INFO
    try:
        return LogLevel(raw.strip().lower())
    except ValueError:
        conforming = ", ".join(level.value for level in LogLevel)
        raise ConfigError(
            f"LOG_LEVEL={raw!r} is not a conforming level; "
            f"expected one of: {conforming}"
        ) from None


def _default_log_file(service: str, *, today: str) -> Path:
    """Build the contract's default per-service log path.

    A per-service default is what makes collection zero-config: Alloy discovers
    logs by path, so an app choosing its own location would require bespoke
    collector configuration (contract section 6).

    Args:
        service: Catalog service name.
        today: Date stamp in YYYY-MM-DD form.

    Returns:
        The default JSON Lines path for the service.
    """
    return DEFAULT_LOG_ROOT / service / f"{today}.jsonl"


def _resolve_bool(raw: str | None, *, default: bool) -> bool:
    """Interpret a boolean environment value.

    Args:
        raw: Candidate value, or None to use the default.
        default: Value to use when unset.

    Returns:
        The parsed boolean.
    """
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config(
    env: dict[str, str] | None = None,
    *,
    service: str | None = None,
    level: str | None = None,
    log_file: str | None = None,
    stdout: bool | None = None,
) -> ObservabilityConfig:
    """Gather and validate configuration from the environment and overrides.

    Programmatic arguments win over environment variables, which lets a host
    application own its configuration while still getting the contract's
    validation. Per-call overrides of envelope fields remain forbidden.

    Args:
        env: Environment mapping; defaults to os.environ.
        service: Overrides SERVICE_NAME.
        level: Overrides LOG_LEVEL.
        log_file: Overrides LOG_FILE.
        stdout: Overrides LOG_STDOUT.

    Returns:
        The frozen configuration.

    Raises:
        ConfigError: If SERVICE_NAME is absent or LOG_LEVEL is invalid.
    """
    source = os.environ if env is None else env

    resolved_service = (service or source.get("SERVICE_NAME") or "").strip()
    if not resolved_service:
        raise ConfigError(
            "SERVICE_NAME is required: an unattributable log record cannot be "
            "correlated to a service, so the contract fails closed"
        )

    resolved_level = _resolve_level(
        level if level is not None else source.get("LOG_LEVEL")
    )

    raw_file = log_file if log_file is not None else source.get("LOG_FILE")
    if raw_file is None or raw_file == "":
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        resolved_file: Path | None = _default_log_file(resolved_service, today=today)
    elif raw_file.strip().lower() == "none":
        resolved_file = None
    else:
        resolved_file = Path(raw_file)

    resolved_stdout = (
        stdout
        if stdout is not None
        else _resolve_bool(source.get("LOG_STDOUT"), default=True)
    )

    return ObservabilityConfig(
        service=resolved_service,
        level=resolved_level,
        log_file=resolved_file,
        stdout=resolved_stdout,
    )
