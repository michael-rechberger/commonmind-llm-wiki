from datetime import UTC, datetime
from pathlib import Path

import pytest

from commonmind_lint import lint

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "acme-wiki"

PROFILE = """\
commonmind_version: "1.0"
wiki_id: test-wiki
title: Test Wiki
types: [organization, project, person, method, decision, policy, topic, agenda, minutes]
data_classes: [public, internal, confidential]
data_class_defaults:
  organizations: confidential
  methods: internal
person_relations: [member, associate, contact]
"""


def page(type_="method", title="A", extra="", body="", data_class="internal"):
    dc = f"data_class: {data_class}\n" if data_class else ""
    return (
        f"---\ntype: {type_}\ntitle: {title}\ndescription: One sentence.\n"
        f"owner: human:jdoe\n{dc}{extra}---\n\n# {title}\n\n{body}\n"
    )


def make_wiki(root: Path, pages: dict[str, str] | None = None, profile: str | None = PROFILE,
              log: str | None = "# Log\n\n## [2026-10-18] ingest | Start\n") -> Path:
    files = {
        "wiki/index.md": '---\nokf_version: "0.2"\n---\n\n# Wiki\n\n- [Methods](/methods/index.md)\n',
        "wiki/methods/index.md": "# Methods\n\n- [A](/methods/a.md)\n- [B](/methods/b.md)\n",
        "wiki/methods/a.md": page(title="A", body="See [B](/methods/b.md)."),
        "wiki/methods/b.md": page(title="B", body="See [A](a.md)."),
    }
    if profile is not None:
        files["commonmind.yaml"] = profile
    if log is not None:
        files["log.md"] = log
    files.update(pages or {})
    for rel, content in files.items():
        if content is None:
            continue
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def codes(findings, level=None):
    return sorted(f.code for f in findings if level is None or f.level == level)


def test_minimal_wiki_is_clean(tmp_path):
    assert lint(make_wiki(tmp_path), now=NOW) == []


def test_index_title_missing_domain(tmp_path):
    wiki = make_wiki(tmp_path, {"wiki/methods/index.md": "> Quote first\n\n- [A](/methods/a.md)\n"})
    assert "index-title-missing" in codes(lint(wiki, now=NOW), "warning")


def test_index_title_missing_root(tmp_path):
    root = '---\nokf_version: "0.2"\n---\n\n- [Methods](/methods/index.md)\n'
    wiki = make_wiki(tmp_path, {"wiki/index.md": root})
    assert "index-title-missing" in codes(lint(wiki, now=NOW), "warning")


def test_index_title_h2_is_not_h1(tmp_path):
    wiki = make_wiki(tmp_path, {"wiki/methods/index.md": "## Methods\n\n- [A](/methods/a.md)\n"})
    assert "index-title-missing" in codes(lint(wiki, now=NOW), "warning")


def test_example_wiki_is_clean():
    assert lint(EXAMPLE, now=NOW) == []


# Profile and bundle structure


def test_missing_profile(tmp_path):
    assert "profile-missing" in codes(lint(make_wiki(tmp_path, profile=None), now=NOW))


@pytest.mark.parametrize("key", ["wiki_id", "types", "data_classes", "commonmind_version"])
def test_profile_required_keys(tmp_path, key):
    profile = "\n".join(line for line in PROFILE.splitlines() if not line.startswith(key))
    assert "profile-invalid" in codes(lint(make_wiki(tmp_path, profile=profile), now=NOW))


def test_profile_identifiers_kebab_case(tmp_path):
    profile = PROFILE.replace("[public, internal, confidential]", "[Public, internal]")
    assert "profile-invalid" in codes(lint(make_wiki(tmp_path, profile=profile), now=NOW))


def test_profile_folder_default_must_be_known_class(tmp_path):
    profile = PROFILE.replace("methods: internal", "methods: secret")
    assert "profile-invalid" in codes(lint(make_wiki(tmp_path, profile=profile), now=NOW))


def test_root_index_needs_okf_version(tmp_path):
    wiki = make_wiki(tmp_path, {"wiki/index.md": "# Wiki\n\n- [Methods](/methods/index.md)\n"})
    assert "root-index" in codes(lint(wiki, now=NOW))


def test_domain_index_without_frontmatter(tmp_path):
    wiki = make_wiki(tmp_path, {"wiki/methods/index.md": "---\ntype: topic\n---\n# Methods\n"})
    assert "domain-index-frontmatter" in codes(lint(wiki, now=NOW))


def test_domain_index_missing_is_warning(tmp_path):
    (make_wiki(tmp_path) / "wiki/methods/index.md").unlink()
    found = lint(tmp_path, now=NOW)
    assert "domain-index-missing" in codes(found, "warning")


# Frontmatter


def test_page_without_frontmatter(tmp_path):
    wiki = make_wiki(tmp_path, {"wiki/methods/c.md": "# C\n\nNo frontmatter. [A](/methods/a.md)\n"})
    assert "frontmatter" in codes(lint(wiki, now=NOW))


def test_unparsable_frontmatter(tmp_path):
    wiki = make_wiki(tmp_path, {"wiki/methods/a.md": "---\ntype: [method\n---\n# A\n"})
    assert "frontmatter" in codes(lint(wiki, now=NOW))


def test_required_field_missing(tmp_path):
    text = page(title="A", body="[B](/methods/b.md)").replace("description: One sentence.\n", "")
    assert "schema" in codes(lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW))


def test_unquoted_timestamp_is_accepted(tmp_path):
    text = page(title="A", body="[B](/methods/b.md)", extra="stale_after: 2027-01-01T00:00:00Z\n")
    assert lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW) == []


def test_project_status_only_on_projects(tmp_path):
    text = page(title="A", body="[B](/methods/b.md)", extra="project_status: active\n")
    assert "schema" in codes(lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW))


def test_unknown_type(tmp_path):
    text = page(type_="recipe", title="A", body="[B](/methods/b.md)")
    assert "unknown-type" in codes(lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW))


def test_meeting_type_not_allowed_in_bundle(tmp_path):
    text = page(type_="minutes", title="A", body="[B](/methods/b.md)")
    assert "schema" in codes(lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW))


def test_domain_field_not_allowed(tmp_path):
    text = page(title="A", body="[B](/methods/b.md)", extra="domain: methods\n")
    assert "domain-field" in codes(lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW))


def test_unknown_relation(tmp_path):
    pages = {
        "wiki/people/index.md": "# People\n\n- [P](/people/p.md)\n",
        "wiki/people/p.md": page(type_="person", title="P", extra="relation: friend\n",
                                 body="[A](/methods/a.md)"),
        "wiki/methods/a.md": page(title="A", body="[B](/methods/b.md) [P](/people/p.md)"),
    }
    assert "unknown-relation" in codes(lint(make_wiki(tmp_path, pages), now=NOW))


def test_missing_relation_and_project_status_are_warnings(tmp_path):
    pages = {
        "wiki/people/index.md": "# People\n\n- [P](/people/p.md)\n",
        "wiki/people/p.md": page(type_="person", title="P", body="[Q](/projects/q.md)"),
        "wiki/projects/index.md": "# Projects\n\n- [Q](/projects/q.md)\n",
        "wiki/projects/q.md": page(type_="project", title="Q", body="[P](/people/p.md)"),
    }
    found = codes(lint(make_wiki(tmp_path, pages), now=NOW), "warning")
    assert "relation-missing" in found
    assert "project-status-missing" in found


def test_unknown_tag_only_with_tag_list(tmp_path):
    text = page(title="A", body="[B](/methods/b.md)", extra="tags: [agile]\n")
    assert lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW) == []
    profile = PROFILE + "tags: [retrospective]\n"
    found = lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}, profile=profile), now=NOW)
    assert "unknown-tag" in codes(found)


# Data classes (section 11)


def test_unknown_data_class(tmp_path):
    text = page(title="A", body="[B](/methods/b.md)", data_class="secret")
    found = lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW)
    assert "unknown-data-class" in codes(found)


def test_class_below_folder_default(tmp_path):
    pages = {
        "wiki/organizations/index.md": "# Orgs\n\n- [O](/organizations/o.md)\n",
        "wiki/organizations/o.md": page(type_="organization", title="O", data_class="internal",
                                        body="[A](/methods/a.md)"),
        "wiki/methods/a.md": page(title="A", body="[B](/methods/b.md) [O](/organizations/o.md)"),
    }
    assert "class-below-default" in codes(lint(make_wiki(tmp_path, pages), now=NOW))


def test_class_above_folder_default_is_fine(tmp_path):
    text = page(title="A", body="[B](/methods/b.md)", data_class="confidential")
    assert lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW) == []


def test_missing_data_class_is_warning(tmp_path):
    text = page(title="A", body="[B](/methods/b.md)", data_class=None)
    found = lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW)
    assert codes(found) == ["data-class-missing"]
    assert found[0].level == "warning"


# Names and links


def test_file_name_not_kebab_case_is_warning(tmp_path):
    pages = {
        "wiki/methods/index.md": "# M\n\n- [A](/methods/a.md)\n- [B](/methods/B%20Two.md)\n",
        "wiki/methods/B Two.md": page(title="B", body="[A](/methods/a.md)"),
        "wiki/methods/b.md": None,
        "wiki/methods/a.md": page(title="A", body="[B](</methods/B Two.md>)"),
    }
    (tmp_path / "wiki/methods").mkdir(parents=True)
    found = lint(make_wiki(tmp_path, pages), now=NOW)
    assert codes(found) == ["file-name"]
    assert found[0].level == "warning"


@pytest.mark.parametrize("syntax", ["[[B]]", "![[view.base]]", "> [!note] Hint"])
def test_editor_syntax(tmp_path, syntax):
    text = page(title="A", body=f"[B](/methods/b.md)\n\n{syntax}\n")
    found = lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW)
    assert codes(found) == ["editor-syntax"]
    assert found[0].line == 13


def test_editor_syntax_in_code_is_ignored(tmp_path):
    body = "[B](/methods/b.md)\n\n```\n[[B]]\n> [!note]\n[x](/nowhere.md)\n```\n\nInline `[[B]]`.\n"
    text = page(title="A", body=body)
    assert lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW) == []


def test_broken_links(tmp_path):
    body = "[B](/methods/b.md) [X](/methods/x.md) [Y](y.md) [Z](/methods/b.md#section)"
    text = page(title="A", body=body)
    found = lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW)
    assert codes(found) == ["broken-link", "broken-link"]


def test_external_and_wiki_links_are_not_checked(tmp_path):
    body = "[B](/methods/b.md) [W](https://example.com) [O](wiki://other/x) [M](mailto:a@b.c) [S](#s)"
    text = page(title="A", body=body)
    assert lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW) == []


def test_orphan_page(tmp_path):
    pages = {
        "wiki/methods/index.md": "# M\n\n- [A](/methods/a.md)\n- [B](/methods/b.md)\n- [C](/methods/c.md)\n",
        "wiki/methods/c.md": page(title="C", body="[A](/methods/a.md)"),
    }
    found = lint(make_wiki(tmp_path, pages), now=NOW)
    assert codes(found) == ["orphan"]
    assert found[0].path == "wiki/methods/c.md"


# Review, sources


def test_stale_page(tmp_path):
    text = page(title="A", body="[B](/methods/b.md)", extra='stale_after: "2026-10-01T00:00:00Z"\n')
    found = lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW)
    assert codes(found) == ["stale"]
    assert "human:jdoe" in found[0].message


def test_local_source_must_exist(tmp_path):
    extra = (
        "sources:\n  - {id: k, resource: sources/inbox/missing.md}\n"
        "  - {id: w, resource: https://example.com/x}\n"
    )
    text = page(title="A", body="[B](/methods/b.md)", extra=extra)
    found = lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW)
    assert codes(found) == ["source-missing"]


def test_footnote_without_source(tmp_path):
    extra = "sources:\n  - {id: k, resource: https://example.com/x}\n"
    body = "[B](/methods/b.md) Claim.[^k] Other.[^x]\n\n[^k]: K\n[^x]: X\n"
    text = page(title="A", body=body, extra=extra)
    found = lint(make_wiki(tmp_path, {"wiki/methods/a.md": text}), now=NOW)
    assert codes(found) == ["footnote-unknown"]


# Log and meetings


def test_log_heading_format(tmp_path):
    log = "# Log\n\n## [2026-10-18] ingest | Start\n\n## 2026-10-19 ingest Start\n"
    found = lint(make_wiki(tmp_path, log=log), now=NOW)
    assert codes(found) == ["log-heading"]
    assert found[0].line == 5


def test_missing_log_is_warning(tmp_path):
    found = lint(make_wiki(tmp_path, log=None), now=NOW)
    assert codes(found, "warning") == ["log-missing"]


MEETING = """\
---
type: minutes
title: Steering
date: "2026-04-13T08:00:00Z"
owner: human:jdoe
related: [/methods/a.md]
verified:
  - {by: "human:jdoe", at: "2026-04-14T07:30:00Z"}
---

# Steering

## Agenda

## Minutes
"""


def test_valid_meeting_file(tmp_path):
    wiki = make_wiki(tmp_path, {"sources/meetings/2026-04-13-steering.md": MEETING})
    assert lint(wiki, now=NOW) == []


def test_meeting_file_name_and_schema(tmp_path):
    bad = MEETING.replace('date: "2026-04-13T08:00:00Z"\n', "")
    wiki = make_wiki(tmp_path, {"sources/meetings/Steering.md": bad})
    assert codes(lint(wiki, now=NOW)) == ["meeting-file-name", "schema"]


def test_meeting_related_must_exist(tmp_path):
    text = MEETING.replace("/methods/a.md", "/methods/x.md")
    wiki = make_wiki(tmp_path, {"sources/meetings/2026-04-13-steering.md": text})
    assert codes(lint(wiki, now=NOW)) == ["broken-link"]


CORE_PROFILE = """\
commonmind_version: "1.0"
wiki_id: core-wiki
types: [method]
data_classes: [internal]
"""


def test_core_only_wiki_has_no_errors(tmp_path):
    """Section 1.1: a wiki that uses only the core parts conforms. Optional parts (meetings,
    several wikis, folder defaults, stale_after, further profile keys) and the SHOULD files
    may be missing; the linter warns at most about SHOULD rules."""
    core_page = "---\ntype: method\ntitle: {t}\ndescription: One sentence.\nowner: human:jdoe\n---\n\n# {t}\n\nSee [{o}](/methods/{lo}.md).\n"
    wiki = make_wiki(tmp_path, {
        "wiki/methods/a.md": core_page.format(t="A", o="B", lo="b"),
        "wiki/methods/b.md": core_page.format(t="B", o="A", lo="a"),
    }, profile=CORE_PROFILE, log=None)
    assert not (wiki / "sources").exists() and not (wiki / "AGENTS.md").exists()
    findings = lint(wiki, now=NOW)
    assert codes(findings, "error") == []
    assert set(codes(findings)) <= {"data-class-missing", "log-missing"}


# K1: actors and trust fields as in OKF v0.2 (sections 5.2, 5.5)

def _with(extra):
    return {"wiki/methods/a.md": page(title="A", body="See [B](/methods/b.md).", extra=extra)}


@pytest.mark.parametrize("actor", ["wiki-update/1.2", "reference_agent/gemini-2.5-pro",
                                   "process:nightly-check", "agent:wiki-update", "human:jdoe"])
@pytest.mark.parametrize("field", ["generated", "verified"])
def test_okf_actor_forms_are_accepted_in_stamps(tmp_path, actor, field):
    author = actor if field == "generated" else "agent:other"
    verifier = actor if field == "verified" else "human:reviewer"
    extra = f'generated: {{by: "{author}", at: "2026-10-16T09:00:00Z"}}\n'
    extra += f'verified:\n  - {{by: "{verifier}", at: "2026-10-16T10:00:00Z"}}\n'
    assert lint(make_wiki(tmp_path, _with(extra)), now=NOW) == []


@pytest.mark.parametrize("field", ["generated", "verified"])
def test_role_cannot_write_or_verify(tmp_path, field):
    stamp = '{by: "role:delivery-lead", at: "2026-10-16T09:00:00Z"}'
    extra = f"generated: {stamp}\n" if field == "generated" else f"verified:\n  - {stamp}\n"
    findings = lint(make_wiki(tmp_path, _with(extra)), now=NOW)
    assert "schema" in codes(findings, "error")


def test_verified_as_single_mapping_is_accepted(tmp_path):
    extra = 'verified: {by: "human:jdoe", at: "2026-10-16T10:00:00Z"}\n'
    assert lint(make_wiki(tmp_path, _with(extra)), now=NOW) == []


@pytest.mark.parametrize("owner", ["agent:wiki-update", "process:nightly", "wiki-update/1.2"])
def test_owner_should_be_accountable(tmp_path, owner):
    content = page(title="A", body="See [B](/methods/b.md).").replace(
        "owner: human:jdoe", f'owner: "{owner}"')
    findings = lint(make_wiki(tmp_path, {"wiki/methods/a.md": content}), now=NOW)
    assert codes(findings) == ["owner-not-accountable"]
    assert codes(findings, "warning") == ["owner-not-accountable"]


def test_role_owner_is_accountable(tmp_path):
    content = page(title="A", body="See [B](/methods/b.md).").replace(
        "owner: human:jdoe", "owner: role:delivery-lead")
    assert lint(make_wiki(tmp_path, {"wiki/methods/a.md": content}), now=NOW) == []


def test_meeting_verified_as_single_mapping_is_accepted(tmp_path):
    meeting = (
        '---\ntype: minutes\ntitle: Steering\ndate: "2026-10-20T08:00:00Z"\nowner: human:jdoe\n'
        'data_class: internal\nverified: {by: "human:jdoe", at: "2026-10-21T08:00:00Z"}\n---\n\n'
        "## Minutes\n"
    )
    wiki = make_wiki(tmp_path, {"sources/meetings/2026-10-20-steering.md": meeting})
    assert lint(wiki, now=NOW) == []


# K2: no self-approval (section 5.5)

@pytest.mark.parametrize("actor", ["human:jdoe", "wiki-update/1.2"])
def test_self_verified_warns(tmp_path, actor):
    extra = (f'generated: {{by: "{actor}", at: "2026-10-16T09:00:00Z"}}\n'
             f'verified:\n  - {{by: "{actor}", at: "2026-10-16T10:00:00Z"}}\n')
    findings = lint(make_wiki(tmp_path, _with(extra)), now=NOW)
    assert codes(findings) == ["self-verified"]
    assert codes(findings, "warning") == ["self-verified"]


def test_verified_by_someone_else_is_clean(tmp_path):
    extra = ('generated: {by: "wiki-update/1.2", at: "2026-10-16T09:00:00Z"}\n'
             'verified: {by: "human:jdoe", at: "2026-10-16T10:00:00Z"}\n')
    assert lint(make_wiki(tmp_path, _with(extra)), now=NOW) == []
