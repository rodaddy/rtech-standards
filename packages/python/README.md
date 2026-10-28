# rtech-obs (Python)

Reference implementation of the [observability contract](../../OBSERVABILITY_CONTRACT.md).

Python is the reference: other language bindings are checked against the same
`conformance/envelope-cases.json` fixture this package passes.

## Pinning

Consumers pin by version tag, never branch or commit URL, so a remote move is a
single URL swap.

## Use

```python
from rtech_obs import init_observability, logger

init_observability()  # once, at startup
logger.info("service started")
```

Four exports, deliberately:

| Export | Purpose |
|--------|---------|
| `init_observability()` | Read + validate config, install sinks. Call once. |
| `logger` | The loguru logger, emitting conforming envelopes. |
| `with_context(**fields)` | Bind fields to every record inside the block. |
| `with_logging(event)` | Decorator emitting entry/exit/failure with `duration_ms`. |

## Configuration

Read once at init into a frozen dataclass, mirroring the `config.py` pattern.

| Variable | Required | Default |
|----------|----------|---------|
| `SERVICE_NAME` | yes | — (fails closed) |
| `LOG_LEVEL` | no | `info` |
| `LOG_FILE` | no | `/mnt/logs/services/<service>/<date>.jsonl` |
| `LOG_STDOUT` | no | `true` |

Any value can be overridden programmatically: `init_observability(service="x")`.

Missing `SERVICE_NAME` or an invalid `LOG_LEVEL` raises `ConfigError` at startup —
silently defaulting would discard operator intent. An unwritable `LOG_FILE` is
**not** fatal: it degrades to stdout and emits one loud warning, because a service
must not fail to boot over an absent log mount.

## Performance

Measured on an M4 Pro, 20k records: **~50 µs per record** caller-visible, with
flush adding effectively nothing.

`enqueue=True` moves the disk write to a background thread, but serialization and
redaction run inline — so the caller doesn't block on I/O, though it does pay for
building the envelope. Roughly 20k records/second.

## Development

```bash
uv sync
uv run pytest          # conformance fixture -- the acceptance gate
uv run ruff check .
uv run ruff format --check .
uv run mypy src        # strict
```

All four must pass. The fixture is what makes conformance a fact rather than a
claim: a change that breaks the envelope fails here, not in production.
