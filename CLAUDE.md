# CLAUDE.md – Commonmind

Specification and starter kit for team LLM wikis as an OKF v0.2 profile. Maintained by Michael
Rechberger (`michael-rechberger/commonmind-llm-wiki`).

## Commands

```bash
uv sync                                             # dependencies
scripts/check.sh                                    # everything CI checks; green before every commit
uv run pytest -q                                    # tests only
uv run commonmind-lint --strict examples/acme-wiki  # lint the example wiki only
```

## Rules

- **Scope rule:** what any organization needs to run an LLM wiki belongs here (normative in
  `SPEC.md`, or as non-normative kit). Values, systems and tools of a particular user do not.
- **English only**, field names and values included.
- **No company data:** no clients, people, hostnames or internal project names. Examples use
  fictional names (ACME, Globex).
- `SPEC.md` is normative; changes go into `CHANGELOG.md`.
- Keep `schema/page.schema.json`, templates and `examples/acme-wiki/` consistent with the spec.
- Python 3.13 with `uv`, `ruff`, `pytest`. Test first; a bug fix starts with a test that
  reproduces it, and every change brings regression tests.
- Conventional Commits, only with a green `scripts/check.sh`. No `git add -A`.
- New files need a licence entry in `REUSE.toml`; check with
  `uvx --from 'reuse[charset-normalizer]' reuse lint`.

## Workflow

- **Session start:** read `STATUS.md` if it exists (maintainer notes, not published).
