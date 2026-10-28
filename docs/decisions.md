# Ratified Decisions

Append-only log. Each entry records what was decided, when, and **why** — so the
reasoning survives and the decision is not re-litigated by the next session.

## 2026-07-25 — Repo exists at all, and is named `rtech-standards`

A shared package beats a document. A standards document cannot be a dependency; a
repo pinned by version tag can, and that pin is the enforcement lever — when the
envelope changes, one bump propagates to every consumer.

Named with the `rtech-` prefix to match the other rTech infrastructure repos. Bare
`standards` was the initial suggestion but is too generic for something that
appears as a dependency URL in ~9 repos.

Originally private, matching sibling visibility; later published as a portfolio
piece.

## 2026-07-25 — Exactly two Loki labels: `service` and `host`

Loki builds one index stream per unique label-value combination. Promoting a
high-cardinality field such as `correlation_id` produces an unbounded number of
streams and progressively destroys query performance. With well over a hundred
service processes to cover, this is the single decision that determines whether the install stays
usable.

Everything except `service` and `host` therefore lives in the JSON body, queried
with a line filter or the `json` parser. Collectors may add a `job` label; that is
assigned by infrastructure, not by application code.

## 2026-07-25 — Required envelope fields are stamped by the package

`timestamp`, `level`, `service`, `host`, `message` are set by the implementation
and cannot be supplied per-call. If callers can pass `service`, it will be spelled
five different ways across five repos and every cross-service query fractures —
which is the same drift problem the package exists to prevent, one layer down.

Unknown top-level fields are moved into `context` rather than accepted, because a
flat namespace anyone can extend is how field names diverge.

## 2026-07-25 — Redaction retains the key, replaces the value

A secret-valued key becomes `"password": "[REDACTED]"`, not removed. Dropping the
key loses information a post-mortem needs — that an auth payload was present at
all. Redaction recurses into nested objects and arrays, and applies to the emitted
record because callers are not trusted to pre-redact.

Ansible's `no_log` blanks a whole task result, so the infra producer still emits
host/task/changed/duration with values stripped. Emitting nothing would turn every
`no_log` task into an unexplained gap in the timeline.

## 2026-07-25 — Config is package-owned, read once, fail closed

Mirrors the `config.py` pattern already standard for rTech Python: gather every
fact at startup, validate, freeze, pass down. Scattered environment reads are
non-conforming.

Missing `SERVICE_NAME` or an unrecognized `LOG_LEVEL` raises at init — silently
defaulting a bad level to `info` discards operator intent, and the same fail-closed
rule already governs auth config in the rTech coding standards.

An unwritable `LOG_FILE` is explicitly **not** fatal: it degrades to stdout and
emits one loud warning. A service must not fail to boot because a log mount is
absent, but the degradation must be visible — silence is a signal.

## 2026-07-25 — Default log path follows the share convention

`/mnt/logs/services/<service>/<YYYY-MM-DD>.jsonl`, keyed to the catalog service
name. A per-service default is what makes collection zero-config: Alloy discovers
logs by path, so if each app chose its own location, every service would need
bespoke collector config and the enforcement story collapses.

Loki's own chunk and index store stays on **local disk**, never the NFS share.
Loki does read-modify-write with file locking, and NFSv4 lock semantics corrupt
it. Earlier NFS problems point the same way: a shared runners
directory became unreadable by every identity including root under `sec=sys`
squash, NFS default ACLs override `umask`, and `chattr +i` is unsupported on NFS.

## 2026-07-25 — Pin by version tag, never branch or commit URL

This repo is moving from GitHub to Forgejo. A tag-pinned dependency survives that
migration as a single remote swap; nine URL-pinned dependencies would each need
rewriting. Avoid `git+ssh` URLs baked into manifests for the same reason.

## 2026-07-25 — Python is the reference; Rust and Swift stay spec-only

Python already has the established `config.py` + loguru pattern and a reference
service, so it is the implementation other languages are checked
against.

No current service is written in Rust or Swift. Those bindings are specified but
deliberately unimplemented until a consumer exists — untested bindings that nobody
imports are liability, not coverage.

## 2026-07-25 — The Bun transport needs a proven spike, not a review

The TypeScript binding's async transport must be demonstrated non-blocking under
Bun 1.3.13 in a real service before it becomes a dependency in nine repos. This is
a measurement, not an opinion, and it is explicitly not to be settled by reading
the code — three reasoning-only conclusions about adjacent library behavior were
wrong the same day this repo was created.
