# Changelog

## 1.1 – 2026-10-24 · first public release

The first published version of Commonmind. Earlier versions (0.1, 1.0) were not published.

- **Format:** repository layout, profile file `commonmind.yaml`, page frontmatter as a profile of
  OKF v0.2 (pinned to commit `ad30107`), core types, meeting files, file names, links within and
  between wikis.
- **Operation:** ingest, query, lint, review and promote; append-only `log.md`; owners are `human:`
  or `role:` actors; trust tiers as in OKF, plus a "changed since review" signal; no review of one's
  own changes.
- **Consumer duties:** data classes with an effective class per page, derived content and
  attachments carry the highest class of their inputs, applications that show only some pages do
  not reveal the others, the duties also bind agents.
- **Personal data:** person pages hold facts only, subjective notes stay in personal wikis, personal
  data may be redacted on a request for deletion.
- **Security considerations:** sources and pages are data, not instructions; no automatic loading
  of external resources; no secrets in sources or pages.
- **Starter kit (not normative):** JSON Schemas for pages and meeting files, templates, an example
  wiki, and the tools `commonmind-lint`, `commonmind-inventory` and `commonmind-migrate`.
