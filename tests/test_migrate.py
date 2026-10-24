from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from commonmind_lint import lint
from commonmind_lint.migrate import MigrationError, main, migrate

from .test_inventory import make

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)

PROFILE = """\
commonmind_version: "1.0"
wiki_id: test-wiki
title: Test Wiki
types: [organization, project, person, method, decision, policy, topic]
data_classes: [public, internal, confidential, restricted]
data_class_defaults:
  organizations: confidential
  projects: confidential
  people: internal
  methods: internal
  about: internal
self_domain: about
person_relations: [colleague, associate, contact]
domain_owners:
  organizations: human:jane-doe
  projects: human:jane-doe
  people: role:office
  methods: role:office
  about: role:office
tags: [client, agile-coaching, team]
"""

ORG = """\
---
title: Globex AG
domain: organizations
status: active
last_updated: 2026-09-01
data_class: confidential
tags: [client]
sources: [2026-03-02 Globex Kickoff.md]
---

# Globex AG

Project: [[Globex – Data Platform|the platform]]. Method: [[methods/Retro]].
Missing: [[Nowhere Page]]. Contact: [[Jane Doe#Role]].
Also a [markdown link](../projects/Globex%20–%20Data%20Platform.md).
"""

PROJECT = """\
---
title: Globex – Data Platform
domain: projects
status: active
last_updated: 2026-10-01
data_class: confidential
tags: [client]
sources: [2026-03-02 Globex Kickoff.md, Notes.md]
---

# Globex – Data Platform

For [[Globex AG]], led by [[Jane Doe]].
"""

PERSON = """\
---
title: Jane Doe
domain: company
status: active
last_updated: 2026-08-01
data_class: internal
tags: [team]
---

# Jane Doe

## Role

Works on [[Globex – Data Platform]].
"""

METHOD = """\
---
title: Retro
domain: methods
last_updated: 2026-07-01
data_class: internal
tags: [agile-coaching]
---

# Retro

Used in [[Globex – Data Platform]].
"""

MOC = """\
---
type: moc
domain: organizations
---

# Organizations

> [!abstract] Overview
> All clients we work with.

![[orgs.base#Active clients]]
"""

LOG = """\
# Log

## 2026-09-01 ingest: Globex kickoff

Created Globex.

## 2026-10-01 Lint run

Fixed links.
"""

MAP = """\
- {old: wiki/organizations/Globex AG.md, new: wiki/organizations/globex-ag.md, type: organization}
- {old: wiki/organizations/_MOC.md, new: wiki/organizations/index.md, type: index}
- old: wiki/projects/Globex – Data Platform.md
  new: wiki/projects/globex-data-platform.md
  type: project
- {old: wiki/company/Jane Doe.md, new: wiki/people/jane-doe.md, type: person, relation: colleague}
- {old: wiki/methods/Retro.md, new: wiki/methods/retro.md, type: method}
"""

DESCRIPTIONS = """\
wiki/organizations/Globex AG.md: Client in manufacturing.
wiki/projects/Globex – Data Platform.md: Data platform for Globex, 2026.
wiki/company/Jane Doe.md: Consultant at ACME.
wiki/methods/Retro.md: How we run retrospectives.
"""


def obsidian(root: Path, **overrides: str | None) -> Path:
    files = {
        "commonmind.yaml": PROFILE,
        "log.md": LOG,
        "wiki/organizations/Globex AG.md": ORG,
        "wiki/organizations/_MOC.md": MOC,
        "wiki/organizations/orgs.base": "views: []\n",
        "wiki/projects/Globex – Data Platform.md": PROJECT,
        "wiki/company/Jane Doe.md": PERSON,
        "wiki/methods/Retro.md": METHOD,
        "sources/inbox/2026-03-02 Globex Kickoff.md": "---\ntitle: Globex kick-off\n---\nraw\n",
        "sources/inbox/Notes.md": "raw\n",
        "tools/migration/migration-map.yaml": MAP,
        "tools/migration/description-map.yaml": DESCRIPTIONS,
    }
    files.update(overrides)
    return make(root, {k: v for k, v in files.items() if v is not None})


def run(root: Path, **kwargs):
    kwargs.setdefault("domain_titles", {})
    return migrate(root, root / "tools/migration/migration-map.yaml",
                   root / "tools/migration/description-map.yaml",
                   generated_by="agent:wiki-update", today="2026-10-18", **kwargs)


def front(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n", 2)[1])


def test_files_are_moved(tmp_path):
    run(obsidian(tmp_path))
    wiki = tmp_path / "wiki"
    assert sorted(p.relative_to(wiki).as_posix() for p in wiki.rglob("*") if p.is_file()) == [
        "index.md",
        "methods/index.md",
        "methods/retro.md",
        "organizations/globex-ag.md",
        "organizations/index.md",
        "people/index.md",
        "people/jane-doe.md",
        "projects/globex-data-platform.md",
        "projects/index.md",
    ]


def test_project_frontmatter(tmp_path):
    run(obsidian(tmp_path))
    meta = front(tmp_path / "wiki/projects/globex-data-platform.md")
    assert list(meta) == ["type", "title", "description", "owner", "data_class",
                          "project_status", "tags", "sources", "generated"]
    assert meta["type"] == "project"
    assert meta["project_status"] == "active"
    assert meta["owner"] == "human:jane-doe"
    assert meta["description"] == "Data platform for Globex, 2026."
    assert meta["generated"] == {"by": "agent:wiki-update", "at": "2026-10-01T00:00:00Z"}
    assert meta["sources"] == [
        {"id": "globex-kickoff", "resource": "sources/inbox/2026-03-02 Globex Kickoff.md",
         "title": "Globex kick-off"},
        {"id": "notes", "resource": "sources/inbox/Notes.md", "title": "Notes"},
    ]


def test_status_dropped_outside_projects_and_relation_set(tmp_path):
    run(obsidian(tmp_path))
    org = front(tmp_path / "wiki/organizations/globex-ag.md")
    person = front(tmp_path / "wiki/people/jane-doe.md")
    assert "status" not in org and "domain" not in org and "last_updated" not in org
    assert person["type"] == "person"
    assert person["relation"] == "colleague"
    assert person["owner"] == "role:office"
    assert "status" not in person


def test_links_are_converted(tmp_path):
    run(obsidian(tmp_path))
    body = (tmp_path / "wiki/organizations/globex-ag.md").read_text(encoding="utf-8")
    assert "Project: [the platform](/projects/globex-data-platform.md)." in body
    assert "Method: [Retro](/methods/retro.md)." in body
    assert "Missing: [Nowhere Page](/unresolved/nowhere-page.md)." in body
    assert "Contact: [Jane Doe](/people/jane-doe.md#role)." in body
    assert "[markdown link](/projects/globex-data-platform.md)" in body
    assert "[[" not in body


def test_domain_index_is_generated(tmp_path):
    run(obsidian(tmp_path))
    index = (tmp_path / "wiki/organizations/index.md").read_text(encoding="utf-8")
    assert not index.startswith("---")
    assert index.startswith("# Organizations\n\n> **Overview**")
    assert "> **Overview**\n> All clients we work with." in index
    assert "![[" not in index and "[!abstract]" not in index
    assert ("<!-- commonmind:index -->\n- [Globex AG](/organizations/globex-ag.md): "
            "Client in manufacturing.\n<!-- /commonmind:index -->") in index
    assert (tmp_path / "wiki/people/index.md").read_text(encoding="utf-8").startswith("# People")


def test_old_index_without_h1_gets_title(tmp_path):
    moc = MOC.replace("# Organizations\n\n", "", 1)
    run(obsidian(tmp_path, **{"wiki/organizations/_MOC.md": moc}))
    index = (tmp_path / "wiki/organizations/index.md").read_text(encoding="utf-8")
    assert index.startswith("# Organizations\n\n> **Overview**")


def test_old_index_with_h1_gets_no_second_h1(tmp_path):
    run(obsidian(tmp_path))
    index = (tmp_path / "wiki/organizations/index.md").read_text(encoding="utf-8")
    assert [ln for ln in index.splitlines() if ln.startswith("# ")] == ["# Organizations"]


def test_root_index(tmp_path):
    run(obsidian(tmp_path))
    root = (tmp_path / "wiki/index.md").read_text(encoding="utf-8")
    assert root.startswith('---\nokf_version: "0.2"\n---\n')
    assert "- [Organizations](/organizations/index.md)" in root
    assert "- [About](/about/index.md)" not in root  # no pages there


def test_log_headings_and_entry(tmp_path):
    run(obsidian(tmp_path))
    log = (tmp_path / "log.md").read_text(encoding="utf-8")
    assert "## [2026-09-01] ingest | Globex kickoff\n\nCreated Globex." in log
    assert "## [2026-10-01] update | Lint run\n" in log
    assert log.rstrip().endswith("## [2026-10-18] migrate | Commonmind 1.0\n\n"
                                 "Migrated 5 files from Obsidian style (SPEC Appendix A); "
                                 "log headings reformatted once.")


def test_result_passes_linter(tmp_path):
    run(obsidian(tmp_path))
    errors = [f for f in lint(tmp_path, now=NOW) if f.level == "error"]
    assert [f.code for f in errors] == ["broken-link"]  # the unresolved link, on purpose


def test_dry_run_changes_nothing(tmp_path):
    root = obsidian(tmp_path)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    report = run(root, dry_run=True)
    after = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert report.files == 5


def test_report_counts(tmp_path):
    report = run(obsidian(tmp_path))
    assert report.files == 5
    assert report.wikilinks == 8
    assert report.unresolved == 1
    assert report.links_rewritten == 1
    assert report.callouts == 1
    assert report.embeds_removed == 1
    assert report.missing_descriptions == 0


def test_unmapped_page_aborts(tmp_path):
    root = obsidian(tmp_path, **{"wiki/methods/Extra.md": "---\ntitle: X\n---\n"})
    with pytest.raises(MigrationError, match="not in the migration map"):
        run(root)
    assert (root / "wiki/methods/Retro.md").exists()


def test_missing_description_is_reported(tmp_path):
    descriptions = DESCRIPTIONS.replace("wiki/methods/Retro.md: How we run retrospectives.\n", "")
    report = run(obsidian(tmp_path, **{"tools/migration/description-map.yaml": descriptions}))
    assert report.missing_descriptions == 1


def test_cli_summary_has_no_names(tmp_path, capsys):
    root = obsidian(tmp_path)
    assert main([str(root), "--generated-by", "agent:wiki-update", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "files: 5" in out
    assert "Globex" not in out


def test_domain_titles(tmp_path):
    run(obsidian(tmp_path), domain_titles={"people": "Personen", "organizations": "Organisationen"})
    root = (tmp_path / "wiki/index.md").read_text(encoding="utf-8")
    assert "- [Personen](/people/index.md)" in root
    assert "- [Organisationen](/organizations/index.md)" in root
    assert "- [Methods](/methods/index.md)" in root
    people = (tmp_path / "wiki/people/index.md").read_text(encoding="utf-8")
    assert people.startswith("# Personen\n")
    organizations = (tmp_path / "wiki/organizations/index.md").read_text(encoding="utf-8")
    assert organizations.startswith("# Organizations\n")  # heading of the old MOC stays


def test_sources_in_block_style(tmp_path):
    run(obsidian(tmp_path))
    text = (tmp_path / "wiki/projects/globex-data-platform.md").read_text(encoding="utf-8")
    assert "tags: [client]\n" in text
    assert "generated: {by: " in text
    assert "sources:\n- id: globex-kickoff\n  resource: " in text


def test_cli_domain_title(tmp_path, capsys):
    root = obsidian(tmp_path)
    assert main([str(root), "--generated-by", "agent:wiki-update",
                 "--domain-title", "people=Personen"]) == 0
    assert "- [Personen](/people/index.md)" in (root / "wiki/index.md").read_text()


def test_log_headings_with_date_or_time_only(tmp_path):
    log = "# Log\n\n## 2026-06-23\n\nFirst.\n\n## 2026-06-24 14:30\n\nSecond.\n"
    report = run(obsidian(tmp_path, **{"log.md": log}))
    text = (tmp_path / "log.md").read_text(encoding="utf-8")
    assert "## [2026-06-23] update | entry\n\nFirst." in text
    assert "## [2026-06-24] update | 14:30\n\nSecond." in text
    assert report.log_headings == 2
