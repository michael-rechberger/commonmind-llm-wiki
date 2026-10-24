# Contributing

Thank you for helping. Commonmind is a specification with a starter kit, maintained by one person,
so a short note on how changes work.

## Changes to the specification

- **Open an issue first**, with the template "Spec change proposal". Describe the problem, where it
  occurs in a real wiki, and what you propose. Please do not open a pull request on `SPEC.md`
  before the change is agreed.
- **Rules are published once they run in a real wiki.** A proposal is ready when it is in use
  somewhere, in your wiki or in the maintainer's.
- **New fields are expensive.** Section 4.3 applies: a field is added only if a consumer actually
  uses it and it cannot be expressed with `type`, `tags` or links in the text.
- Accepted changes go into `SPEC.md` and `CHANGELOG.md`; the schema, the templates, the example
  wiki and the linter stay consistent with them.

## Linter, schema, templates and examples

Pull requests are welcome. Before you open one:

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run commonmind-lint --strict examples/acme-wiki
```

Examples use fictional organizations and people only (ACME, Globex, John Doe).

## Questions and ideas

Use [Discussions](https://github.com/michael-rechberger/commonmind-llm-wiki/discussions) for
questions, ideas and experiences with running a wiki. Issues are for concrete changes and bugs.

## License of contributions

A contribution is licensed like the part it changes (see `REUSE.toml`): CC BY 4.0 for the
specification and documentation, MIT for the linter and the schema, CC0 1.0 for templates and
examples.
