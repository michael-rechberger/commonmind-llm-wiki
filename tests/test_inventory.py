import json
from pathlib import Path

from commonmind_lint.inventory import inventory, main

PAGE = """\
---
title: Some Page
domain: organizations
status: active
last_updated: 2026-01-01
tags: [Kunde, agile-coaching]
sources: [2026-01-01 Kickoff.md, missing.md]
---

# Some Page

See [[Other Page]] and [[methods/Retro|the retro]] and [[Other Page#Goals]].
Raw source: [[2026-01-01 Kickoff]]. Broken: [[Nowhere]].

![[orgs.base#Active clients]]
![[diagram.png]]

> [!note] Hint
> text

> [!warning]

A [markdown link](/methods/retro.md).

```dataview
TABLE x
```

```
[[Not counted]]
```
"""


def make(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def obsidian_wiki(root: Path) -> Path:
    return make(root, {
        "wiki/organizations/Some Page.md": PAGE,
        "wiki/organizations/Other Page.md": "---\ntitle: Other\nstatus: archived\n---\n# Other\n",
        "wiki/organizations/_MOC.md": "---\ntype: moc\n---\n![[orgs.base]]\n",
        "wiki/methods/Retro.md": "# Retro without frontmatter\n",
        "wiki/methods/Über uns – Team.md": "---\ntitle: [broken\n---\n",
        "wiki/methods/ueber-uns-team.md": "---\ntitle: X\n---\n",
        "wiki/company/team.md": "---\ntitle: T\n---\n",
        "sources/inbox/2026-01-01 Kickoff.md": "raw\n",
        "log.md": "# Log\n\n## [2026-01-01] ingest | A\n## 2026-01-02 lint\n## Something\n",
    })


def test_pages_per_folder(tmp_path):
    inv = inventory(obsidian_wiki(tmp_path))
    assert inv["pages"] == {"total": 7, "per_folder": {"company": 1, "methods": 3,
                                                       "organizations": 3}}


def test_frontmatter(tmp_path):
    fm = inventory(obsidian_wiki(tmp_path))["frontmatter"]
    assert fm["missing"] == 1
    assert fm["unparsable"] == 1
    assert fm["fields"]["title"] == 4
    assert fm["fields"]["domain"] == 1
    assert fm["values"]["status"] == {"active": 1, "archived": 1}
    assert fm["values"]["type"] == {"moc": 1}


def test_tags_and_sources(tmp_path):
    inv = inventory(obsidian_wiki(tmp_path))
    assert inv["tags"] == {"distinct": 2, "not_kebab_case": 1}
    assert inv["sources"] == {"entries": 2, "as_text": 2, "as_object": 0, "found": 1}


def test_wikilinks(tmp_path):
    links = inventory(obsidian_wiki(tmp_path))["wikilinks"]
    assert links == {"total": 5, "with_alias": 1, "with_path": 1, "with_heading": 1,
                     "to_pages": 3, "to_sources": 1, "unresolved": 1}


def test_embeds_callouts_and_other_syntax(tmp_path):
    inv = inventory(obsidian_wiki(tmp_path))
    assert inv["embeds"] == {".base": 2, ".png": 1}
    assert inv["callouts"] == {"note": 1, "warning": 1}
    assert inv["other_syntax"] == {"dataview_blocks": 1, "markdown_links": 1}


def test_file_names(tmp_path):
    names = inventory(obsidian_wiki(tmp_path))["file_names"]
    assert names == {"not_kebab_case": 4, "non_ascii": 1, "duplicate_basenames": 0,
                     "kebab_collisions": 1}


def test_log_headings(tmp_path):
    assert inventory(obsidian_wiki(tmp_path))["log"] == {
        "exists": True, "headings": 3, "commonmind_format": 1, "date_first": 1, "other": 1}


def test_cli_writes_json_without_names(tmp_path, capsys):
    out = tmp_path / "inv.json"
    assert main([str(obsidian_wiki(tmp_path / "w")), "-o", str(out)]) == 0
    text = out.read_text()
    assert json.loads(text)["pages"]["total"] == 7
    assert "Some Page" not in text
    assert "Kickoff" not in text
