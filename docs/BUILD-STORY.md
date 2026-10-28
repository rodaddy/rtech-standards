# How rtech-standards was built

Sources: the private development repository's git history (13 commits,
2026-07-25 to 2026-10-23, including one unmerged feature branch), its issues
and pull requests, `docs/decisions.md`, the contract, and the tests. This
public repository started as a one-commit snapshot of the `main` branch.

## The problem

A set of self-hosted services, spread over several machines and about nine
code repositories, had no log ingestion. Services wrote to journald or
nowhere, and the Ansible runs that changed them left no on-disk record, so
after an incident there was nothing to read. The commit that started the
repository puts it as "not a discipline problem -- the data never existed."
The goal was one envelope that application code and infrastructure tooling
both emit, so a service's logs and the change that broke it land on one
timeline.

## Timeline

| Date | What happened |
|------|---------------|
| 2026-07-25 01:18 | **Bootstrap.** Contract 1.0.0, a conformance fixture of 16 language-agnostic cases, and the Python reference package, with a measured cost of about 50 µs per record (about 20,000 records a second) on an M4 Pro. The commit states the claim precisely: the background writer means the caller "does not block on I/O", not that logging is free, because serialisation and redaction still run inline. |
| 2026-07-25 01:42 | **First hook run fails.** The pre-push hook blocked the very first push: ruff formats Python inside Markdown code fences, so an aligned comment in the README counted as unformatted code. Fix: Markdown is excluded from ruff, because a documentation edit must never gate code. 18/18 conformance tests green. |
| 2026-07-25 03:15 | **Metrics** (on a feature branch). Prometheus counters in the same package, so metrics and logs share one `service` value as their join key. Two transports: an HTTP scrape endpoint for daemons and a node_exporter textfile for jobs that exit before a scrape. Off by default, because binding a port on import is hostile to the host application. Contract 1.1.0, 40 tests. |
| 2026-07-25 10:45 | **Versioning split** (same branch). Package version and contract version were decoupled: the contract version means "the wire format", the package version means "this implementation". Packages declare the contract they target and the range they interoperate with, and refuse a revision they cannot parse. Contract 1.2.0, 59 tests. |
| 2026-07-27 to 2026-10-01 | Housekeeping on `main`: search index settings, agent instruction files, secret scanner change, formatting. |
| 2026-10-06 | Issue #2 / PR #3: CI ran the full suite on every PR, even for docs-only changes. PRs now run only the tests affected by the diff, with a full-suite fallback when lockfiles, config, fixtures or CI change; `main` keeps the full suite. |
| 2026-10-23 | PR #5: removed workflow `permissions` blocks that Forgejo ignores. |

The metrics and versioning commits sit on a branch that has not been merged
into `main`, so this snapshot carries contract 1.0.0 and 18 tests.

## Key design decisions

All recorded with their reasons in `docs/decisions.md`:

- **A package, not a document.** A document cannot be a dependency; a
  version-pinned package can, and one bump reaches every consumer.
- **Exactly two Loki labels.** `service` and `host` only. Each unique label
  combination is an index stream, and one high-cardinality label (such as a
  correlation id) would make the log store unusable.
- **The package stamps required fields.** If callers could pass `service`,
  it would be spelled five ways across five repositories.
- **Redaction keeps the key.** `"password": "[REDACTED]"` tells a
  post-mortem that credentials were present without leaking them.
- **Fail closed on config, degrade on the log file.** A missing service
  name stops start-up; a missing log mount falls back to stdout with one
  loud warning, because a service must not fail to boot over logging.
- **Python first; Rust and Swift on paper only.** Untested bindings nobody
  imports are a liability. The TypeScript transport for Bun is held until a
  measured spike shows it does not block.
- **Pin by version tag.** A tag survives a move between git hosts as a
  single remote change.

## How AI was used

The repository was written with an AI coding agent; one commit carries a
Claude (Opus) co-author line and the commit messages read as agent work
logs with stated evidence. The working rule visible throughout is
"measured, not assumed": the logging cost was benchmarked rather than
estimated, the metrics output was checked with the real `promtool check
metrics` rather than only with self-written assertions, and the decisions
log records that the Bun transport question must be settled by a
measurement because "three reasoning-only conclusions about adjacent
library behavior were wrong the same day this repo was created." Later CI
maintenance was proposed through issues and pull requests by automated
agents.

## Testing

`packages/python/tests/test_conformance.py` runs every fixture case against
the package: 18 tests on `main` (59 on the metrics branch). Ruff, ruff
format and strict mypy run in the same pre-push hook and CI workflow, and
CI runs pytest as an unprivileged user so file-permission tests are real.

## What did not work

- **Letting the linter read docs.** The hook's first run was blocked by a
  README; fixed by scoping the linter to source.
- **Trusting a library's bind.** The Prometheus HTTP server sets
  `SO_REUSEADDR`, so starting it on a port already in use silently created
  a second server. Caught by a failing test; the port is now probed first.
- **Counting in the formatter.** loguru runs a format function once per
  sink, so with two sinks every record was counted twice. Caught by a
  failing test; counting moved to a once-per-call hook.
- **One version number for two things.** Tests asserted the contract
  version literally, so the first package patch release would have failed
  its own suite. Fixed by the version split.

## Current state

Contract 1.0.0 and `rtech-obs` 1.0.0 on `main`, passing the fixture. The
metrics extension and version split are written and tested on a branch and
not merged.
