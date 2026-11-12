#!/usr/bin/env bash
# Single check for contributors and CI: lint, format, tests, example wiki.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run commonmind-lint --strict examples/acme-wiki
