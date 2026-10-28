# Observability Contract

**Version: 1.0.0**

Normative specification for structured logging across every rTech service, in
every language. This document is the law; the packages under `packages/` are
implementations of it, and `conformance/envelope-cases.json` is the executable
proof that an implementation obeys it.

If an implementation and this document disagree, this document wins and the
implementation is a bug.

## Why this exists

Before 2026-07-25 the fleet had no log ingestion at all: ~139 service processes
wrote to journald or nowhere, and Ansible wrote no on-disk record of any run.
Post-mortems were archaeology — "what broke at 03:14" was unanswerable because
the data never existed.

The fix is a single log envelope that both application code and infrastructure
tooling emit, so a service's logs and the Ansible run that changed it land on one
queryable timeline. That only works if every producer agrees on the field names.
A document telling nine repos to each build their own logger guarantees drift;
an installable package pinned by version does not.

## Normative language

MUST / MUST NOT / SHOULD / MAY carry their RFC 2119 meanings.

## 1. The envelope

Every log line MUST be a single-line JSON object (JSON Lines). Pretty-printing is
forbidden: a multi-line record breaks line-oriented collection.

### 1.1 Required fields

| Field | Type | Notes |
|-------|------|-------|
| `timestamp` | string | RFC 3339 / ISO 8601, UTC, millisecond precision, `Z` suffix. Example `2026-07-25T04:16:07.418Z`. |
| `level` | string | Lowercase, one of `debug` `info` `warning` `error` `critical`. |
| `service` | string | Catalog service name. Loki label. See §2. |
| `host` | string | Hostname of the emitting box. Loki label. See §2. |
| `message` | string | Human-readable, no trailing newline. |

### 1.2 Optional fields

| Field | Type | Notes |
|-------|------|-------|
| `correlation_id` | string | Ties related records together (request, run, job). High cardinality — body only, never a label. |
| `event` | string | Stable machine-readable event name, e.g. `service.start`, `identity.remap`. Prefer over parsing `message`. |
| `error` | object | `{type, message, stacktrace}` when the record describes a failure. |
| `duration_ms` | number | Elapsed milliseconds for a completed operation. |
| `context` | object | Arbitrary structured detail. Nested values allowed. Never secrets (§4). |

### 1.3 Reserved and forbidden

- Field names not listed above MUST go inside `context`, never at the top level.
  A flat namespace that anyone can extend is how field names fracture.
- The five required fields MUST be stamped by the implementation, NOT accepted
  from the caller. A caller that can pass `service` will spell it differently in
  five repos and fracture every query.
- `level` MUST NOT be abbreviated (`warn`, `err`, `crit` are non-conforming).
  One spelling per level, chosen because Loki queries are literal string matches.

## 2. Loki labels — exactly two

`service` and `host` are the ONLY fields promoted to Loki labels.

Everything else lives in the JSON body and is queried with a line filter or
`json` parser. This is not stylistic. Loki builds one index stream per unique
label-value combination; promoting a high-cardinality field such as
`correlation_id` produces an unbounded number of streams and makes the install
progressively unusable. At ~139 services this is the single mistake that would
take the system down.

```logql
{service="my-service"} | json | level="error"
{job="ansible"} | json | correlation_id="7f3c..."
```

Infrastructure producers MAY add a `job` label (`job="ansible"`), assigned by the
collector, not by the application.

## 3. The five log points

Derived from the rTech coding standards, which are normative for all rTech code.
Every code path MUST emit at these points:

| Point | Level | Purpose |
|-------|-------|---------|
| Entry | `debug` | Operation started, with identifying context. |
| Exit / result | `info` | Operation completed, with `duration_ms`. |
| Failure | `error` | Operation failed, with `error` populated. |
| Fallback / degraded | `warning` | A degraded path was taken. |
| Guard / limit trigger | `warning` | A guard, cap, or rail fired. |

**Silence is a signal.** Because every degraded path emits a `warning` or
`error`, the ABSENCE of a log line reliably means success. This inverts the
previous state, where absence meant "no idea". Implementations MUST NOT silently
swallow a degraded path.

This rule has teeth: a hook that crashed silently on 2026-07-25 was
indistinguishable from a hook that approved, because it emitted nothing on its
failure path. A crash that logs nothing is a correctness bug, not a cosmetic one.

## 4. Redaction — never log secrets

Implementations MUST NOT emit secrets, tokens, credentials, auth payloads, or
private user content.

- A field whose key matches (case-insensitive) `password`, `passwd`, `secret`,
  `token`, `api_key`, `apikey`, `authorization`, `auth`, `credential`,
  `private_key`, `session`, or `cookie` MUST have its VALUE replaced with the
  literal string `[REDACTED]`.
- Redaction MUST recurse into nested objects and arrays inside `context`.
- The key MUST be retained. Metadata without the value keeps the audit trail
  ("an auth payload was present") without leaking the payload. Dropping the key
  entirely loses information that matters in a post-mortem.
- Redaction applies to the emitted record. Callers are not trusted to pre-redact.

Infrastructure note: Ansible's `no_log` blanks an entire task result. The Ansible
producer MUST still emit the record's metadata (host, task, changed, duration)
with values stripped, rather than emitting nothing — otherwise a `no_log` task
becomes an unexplained gap in the timeline.

## 5. Configuration contract

Configuration is owned by the implementation and read ONCE at initialization into
an immutable object. This mirrors the `config.py` pattern that is already the
Python standard: gather every fact at startup, validate, then pass the frozen
result down. Scattered environment reads are non-conforming.

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `SERVICE_NAME` | yes | none | Catalog service name. Absent → fail closed (§5.1). |
| `LOG_LEVEL` | no | `info` | One of the five levels. Invalid → fail closed. |
| `LOG_FILE` | no | `/mnt/logs/services/${SERVICE_NAME}/${YYYY-MM-DD}.jsonl` | See §6. |
| `LOG_STDOUT` | no | `true` | Also emit to stdout (journald captures it). |

Callers MAY override any resolved value programmatically at init. Per-call
overrides of the five required envelope fields are forbidden (§1.3).

### 5.1 Fail closed

Missing `SERVICE_NAME` or an unrecognized `LOG_LEVEL` MUST raise at
initialization. Defaulting a bad level to `info` silently discards the operator's
intent, and the same fail-closed rule already governs auth configuration in the
rTech coding standards.

Being unable to open `LOG_FILE` is NOT fatal: it MUST fall back to stdout and
emit one `warning` naming the path and the reason (§3, degraded path). A service
must not fail to boot because a log mount is absent.

## 6. File path convention

```
/mnt/logs/
  ansible/<YYYY-MM-DD>/<run-uuid>.json    # Ansible run receipts + diffs
  hosts/<hostname>/<unit>/<YYYY-MM-DD>.log
  services/<service>/<YYYY-MM-DD>.jsonl   # application logs (this contract)
  loki/                                   # Loki archive target
```

`<service>` MUST be the catalog service name, so the tree matches the service
manifests and can be validated against them.

`/mnt/logs` is an NFS share mounted fleet-wide. Application logs are written
there as the durable raw archive; Loki ingests from it. Loki's own chunk and
index store MUST remain on local disk — it performs read-modify-write with file
locking, and NFSv4 lock semantics corrupt it.

## 7. Conformance

An implementation is conforming when it passes every case in
`conformance/envelope-cases.json`. Each case supplies an input and the expected
emitted envelope, with volatile fields (`timestamp`, `host`) matched by pattern
rather than equality.

A new language binding is not "done" when it compiles. It is done when the
fixture passes.

## 8. Versioning

This contract is semver'd, and the version above is authoritative.

- **Patch** — clarification, no wire change.
- **Minor** — new optional field, or a new conformance case that existing
  conforming implementations already satisfy.
- **Major** — any change to required fields, label promotion, or redaction
  behavior.

Consumers MUST pin by version tag, never by branch or commit URL. This repo is
moving from GitHub to Forgejo; a tag-pinned dependency survives the move as a
remote swap, while nine URL-pinned dependencies do not.
