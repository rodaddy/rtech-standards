#!/usr/bin/env zsh
# Point git at the tracked hooks directory.
#
# _githooks/ is tracked and visibly named (no hidden project folders), so the
# gate is reviewable in a PR instead of living only on one machine.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

git config core.hooksPath _githooks
chmod +x _githooks/*

print "hooks installed: core.hooksPath=_githooks"
print "  pre-push -> format, lint, types, conformance fixture (command-identical to CI)"
