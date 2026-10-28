#!/usr/bin/env bash
# Pick the Python tests a pull request needs.
#
# Usage: select-tests.sh <base-sha> <head-sha>   (or: select-tests.sh --files < list)
# Prints one of:
#   FULL            run the whole suite (fail-safe)
#   NONE            docs-only change, no tests needed
#   <test paths>    test files relative to packages/python, one per line
#
# FULL wins whenever a change could affect every test: lockfile, manifest,
# tool config, test helpers/fixtures, the shared conformance fixture, a CI
# workflow, or a code change that maps to no test file.
set -euo pipefail

pkg="packages/python"

if [ "${1:-}" = "--files" ]; then
  changed="$(cat)"
else
  changed="$(git diff --name-only "$1...$2")"
fi

[ -z "${changed}" ] && { echo NONE; exit 0; }

full=0
code=0
selected=""

while IFS= read -r f; do
  [ -z "${f}" ] && continue
  case "${f}" in
    *.lock|*/uv.lock|*package-lock.json|*bun.lock*|*pnpm-lock.yaml|*yarn.lock \
    |*/package.json|package.json|*/pyproject.toml|pyproject.toml|*/go.mod|*/Cargo.toml \
    |*tsconfig*.json|*biome.json*|*eslint*|*pytest.ini|*vitest.config.*|setup.cfg|*/setup.cfg \
    |*/conftest.py|conftest.py|*/fixtures/*|*/tests/support/*|*/tests/helpers/* \
    |conformance/*|.github/workflows/*|.forgejo/workflows/*|.gitea/workflows/*|scripts/ci/* \
    |*/migrations/*|*schema.sql)
      full=1 ;;
    *.md|docs/*) ;;
    "${pkg}"/tests/test_*.py|"${pkg}"/tests/*/test_*.py)
      code=1
      selected="${selected}${f#"${pkg}"/}"$'\n' ;;
    *)
      code=1
      if [ "${f#"${pkg}"/}" != "${f}" ]; then
        stem="$(basename "${f}")"; stem="${stem%.*}"
        dir="$(dirname "${f#"${pkg}"/}")"
        while IFS= read -r t; do
          [ -z "${t}" ] && continue
          rel="${t#"${pkg}"/}"
          case "${rel}" in
            *"${stem}"*|"${dir}"/*) selected="${selected}${rel}"$'\n' ;;
          esac
        done < <(cd "$(git rev-parse --show-toplevel)" && ls "${pkg}"/tests/test_*.py "${pkg}"/tests/*/test_*.py 2>/dev/null)
      fi ;;
  esac
done <<< "${changed}"

if [ "${full}" -eq 1 ]; then echo FULL; exit 0; fi
selected="$(printf '%s' "${selected}" | sed '/^$/d' | sort -u)"
if [ -n "${selected}" ]; then echo "${selected}"; exit 0; fi
if [ "${code}" -eq 1 ]; then echo FULL; else echo NONE; fi
