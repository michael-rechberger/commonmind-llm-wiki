"""Structural checks of a Commonmind wiki repository (SPEC sections 3-12).

`lint()` returns findings; `load_wiki()` exposes the parsed repository so that an organization
can add its own rules on top (e.g. a forbidden data class) without forking the linter.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

Level = Literal["error", "warning"]

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ACTOR = re.compile(
    r"^((human|role|agent|process):[a-z0-9]+(-[a-z0-9]+)*"
    r"|[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._+-]*)$"
)
ACCOUNTABLE = ("human:", "role:")
LOG_HEADING = re.compile(r"^## \[\d{4}-\d{2}-\d{2}\] [a-z][a-z-]* \| \S.*$")
MEETING_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(-[a-z0-9]+)*\.md$")
URI_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")

FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"!?\[[^\]]*\]\((?:<([^>]+)>|([^)\s]+))(?:\s+\"[^\"]*\")?\)")
WIKILINK = re.compile(r"!?\[\[[^\]]+\]\]")
CALLOUT = re.compile(r"^[ \t]*>[ \t]*\[![A-Za-z-]+\]", re.MULTILINE)
FOOTNOTE_REF = re.compile(r"\[\^([^\]\s]+)\](?!:)")

PROFILE_REQUIRED = ("commonmind_version", "wiki_id", "types", "data_classes")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    level: Level
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.level} {self.code}: {self.message}"


@dataclass
class Page:
    path: Path  # absolute
    rel: str  # relative to repository root, POSIX
    meta: dict | None  # None if frontmatter is missing or unparsable
    body: str
    body_line: int  # line number of the first body line
    error: str | None = None


@dataclass
class Wiki:
    root: Path
    profile: dict
    pages: list[Page] = field(default_factory=list)  # bundle pages, without index.md
    indexes: list[Page] = field(default_factory=list)  # index.md files in wiki/
    meetings: list[Page] = field(default_factory=list)

    @property
    def bundle(self) -> Path:
        return self.root / "wiki"

    def domain(self, page: Page) -> str | None:
        parts = page.path.relative_to(self.bundle).parts
        return parts[0] if len(parts) > 1 else None

    def class_rank(self, data_class: str | None) -> int | None:
        classes = self.profile.get("data_classes") or []
        if data_class is None:
            return None
        return classes.index(data_class) if data_class in classes else len(classes)


class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps timestamps as strings, so the schema can check their format."""


_Loader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _schema_dir() -> Path:
    packaged = Path(__file__).parent / "schema"
    return packaged if packaged.is_dir() else Path(__file__).resolve().parents[2] / "schema"


def _validators() -> tuple[Draft202012Validator, Draft202012Validator]:
    schemas = {
        name: json.loads((_schema_dir() / f"{name}.schema.json").read_text(encoding="utf-8"))
        for name in ("page", "meeting")
    }
    registry = Registry().with_resources(
        (s["$id"], Resource.from_contents(s)) for s in schemas.values()
    )
    return (
        Draft202012Validator(schemas["page"], registry=registry),
        Draft202012Validator(schemas["meeting"], registry=registry),
    )


def _read(path: Path, root: Path) -> Page:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(root).as_posix()
    if not text.startswith("---\n"):
        return Page(path, rel, None, text, 1)
    end = text.find("\n---", 4)
    if end == -1:
        return Page(path, rel, None, text, 1, "frontmatter is not closed")
    raw = text[4 : end + 1]
    after = text.find("\n", end + 4)
    body = text[after + 1 :] if after != -1 else ""
    body_line = raw.count("\n") + 3
    try:
        meta = yaml.load(raw, Loader=_Loader) or {}
    except yaml.YAMLError as exc:
        return Page(path, rel, None, body, body_line, f"frontmatter is not valid YAML: {exc}")
    if not isinstance(meta, dict):
        return Page(path, rel, None, body, body_line, "frontmatter is not a mapping")
    return Page(path, rel, meta, body, body_line)


def load_wiki(root: Path | str) -> tuple[Wiki | None, list[Finding]]:
    root = Path(root).resolve()
    profile_path = root / "commonmind.yaml"
    if not profile_path.is_file():
        return None, [Finding("commonmind.yaml", 1, "error", "profile-missing",
                              "profile file commonmind.yaml is missing")]
    try:
        profile = yaml.load(profile_path.read_text(encoding="utf-8"), Loader=_Loader) or {}
    except yaml.YAMLError as exc:
        return None, [Finding("commonmind.yaml", 1, "error", "profile-invalid", str(exc))]
    if not isinstance(profile, dict):
        return None, [Finding("commonmind.yaml", 1, "error", "profile-invalid",
                              "profile is not a mapping")]
    wiki = Wiki(root, profile)
    if wiki.bundle.is_dir():
        for path in sorted(wiki.bundle.rglob("*.md")):
            target = wiki.indexes if path.name == "index.md" else wiki.pages
            target.append(_read(path, root))
    meetings = root / "sources" / "meetings"
    if meetings.is_dir():
        wiki.meetings = [_read(p, root) for p in sorted(meetings.glob("*.md"))]
    return wiki, []


def _mask_code(body: str) -> str:
    """Blank out code so that examples in code are not checked; keeps line numbers."""

    def blank(match: re.Match) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return INLINE_CODE.sub(blank, FENCE.sub(blank, body))


def _line(page: Page, text: str, offset: int) -> int:
    return page.body_line + text.count("\n", 0, offset)


def _check_profile(profile: dict) -> list[Finding]:
    problems = [f"'{key}' is missing" for key in PROFILE_REQUIRED if not profile.get(key)]
    classes = profile.get("data_classes") or []
    for key in ("types", "data_classes", "tags", "person_relations"):
        for value in profile.get(key) or []:
            if not isinstance(value, str) or not KEBAB.match(value):
                problems.append(f"'{key}' value '{value}' is not lowercase kebab-case")
    for folder, value in (profile.get("data_class_defaults") or {}).items():
        if value not in classes:
            problems.append(f"data_class_defaults.{folder} '{value}' is not in data_classes")
    default = profile.get("default_data_class")
    if default is not None and default not in classes:
        problems.append(f"default_data_class '{default}' is not in data_classes")
    for folder, actor in (profile.get("domain_owners") or {}).items():
        if not isinstance(actor, str) or not ACTOR.match(actor):
            problems.append(f"domain_owners.{folder} '{actor}' is not an actor")
    return [Finding("commonmind.yaml", 1, "error", "profile-invalid", p) for p in problems]


def _check_indexes(wiki: Wiki) -> list[Finding]:
    found = []
    root_index = wiki.bundle / "index.md"
    root_page = next((p for p in wiki.indexes if p.path == root_index), None)
    meta = root_page.meta if root_page else None
    if root_page is None:
        found.append(Finding("wiki/index.md", 1, "error", "root-index", "wiki/index.md is missing"))
    elif meta is None or set(meta) != {"okf_version"} or str(meta["okf_version"]) != "0.2":
        found.append(Finding(root_page.rel, 1, "error", "root-index",
                             'frontmatter must be only okf_version: "0.2"'))
    for index in wiki.indexes:
        first = next((ln for ln in index.body.splitlines() if ln.strip()), "")
        if not first.startswith("# "):
            found.append(Finding(index.rel, index.body_line, "warning", "index-title-missing",
                                 "index.md should begin with a level-1 heading"))
        if index.path != root_index and (index.meta is not None or index.error):
            found.append(Finding(index.rel, 1, "error", "domain-index-frontmatter",
                                 "domain index.md must not have frontmatter"))
    if wiki.bundle.is_dir():
        for domain in sorted(d for d in wiki.bundle.iterdir() if d.is_dir()):
            if not (domain / "index.md").is_file():
                rel = (domain / "index.md").relative_to(wiki.root).as_posix()
                found.append(Finding(rel, 1, "warning", "domain-index-missing",
                                     f"domain '{domain.name}' has no index.md"))
    return found


def _check_frontmatter(wiki: Wiki, page: Page, validator: Draft202012Validator,
                       now: datetime) -> list[Finding]:
    def finding(level: Level, code: str, message: str) -> Finding:
        return Finding(page.rel, 1, level, code, message)

    if page.meta is None:
        return [finding("error", "frontmatter", page.error or "page has no YAML frontmatter")]
    meta, profile = page.meta, wiki.profile
    found = [finding("error", "schema", f"{'.'.join(map(str, e.path)) or 'page'}: {e.message}")
             for e in sorted(validator.iter_errors(meta), key=lambda e: list(e.path))]
    if "domain" in meta:
        found.append(finding("error", "domain-field", "'domain' follows from the folder"))
    owner = meta.get("owner")
    if isinstance(owner, str) and ACTOR.match(owner) and not owner.startswith(ACCOUNTABLE):
        found.append(finding("warning", "owner-not-accountable",
                             f"owner '{owner}' should be a human: or role: actor"))
    type_ = meta.get("type")
    if isinstance(type_, str) and type_ not in (profile.get("types") or []):
        found.append(finding("error", "unknown-type", f"type '{type_}' is not in the profile"))

    data_class = meta.get("data_class")
    classes = profile.get("data_classes") or []
    if data_class is None:
        found.append(finding("warning", "data-class-missing", "data_class is not set"))
    elif data_class not in classes:
        found.append(finding("error", "unknown-data-class",
                             f"data_class '{data_class}' is not in the profile"))
    else:
        folder_default = (profile.get("data_class_defaults") or {}).get(wiki.domain(page))
        if folder_default in classes and wiki.class_rank(data_class) < wiki.class_rank(
                folder_default):
            found.append(finding("error", "class-below-default",
                                 f"data_class '{data_class}' is below the folder default "
                                 f"'{folder_default}'"))

    if type_ == "project" and "project_status" not in meta:
        found.append(finding("warning", "project-status-missing", "project without project_status"))
    if type_ == "person":
        relation = meta.get("relation")
        relations = profile.get("person_relations")
        if relation is None:
            found.append(finding("warning", "relation-missing", "person without relation"))
        elif relations is not None and relation not in relations:
            found.append(finding("error", "unknown-relation",
                                 f"relation '{relation}' is not in the profile"))
    if "tags" in profile and isinstance(meta.get("tags"), list):
        for tag in meta["tags"]:
            if tag not in (profile.get("tags") or []):
                found.append(finding("error", "unknown-tag", f"tag '{tag}' is not in the profile"))

    generated = meta.get("generated")
    author = generated.get("by") if isinstance(generated, dict) else None
    verified = meta.get("verified")
    stamps = [verified] if isinstance(verified, dict) else verified or []
    if author and any(isinstance(v, dict) and v.get("by") == author for v in stamps):
        found.append(finding("warning", "self-verified",
                             f"'{author}' verified its own content; review by another actor"))

    stale_after = meta.get("stale_after")
    if isinstance(stale_after, str):
        try:
            due = datetime.fromisoformat(stale_after)
        except ValueError:
            due = None
        if due is not None and due < now:
            found.append(finding("warning", "stale",
                                 f"stale since {stale_after}, owner {meta.get('owner')}"))

    for source in meta.get("sources") or []:
        resource = source.get("resource") if isinstance(source, dict) else None
        local = isinstance(resource, str) and not URI_SCHEME.match(resource)
        if local and not (wiki.root / resource).exists():
            found.append(finding("warning", "source-missing",
                                 f"source '{resource}' does not exist"))
    return found


def _resolve(wiki: Wiki, page: Page, target: str) -> Path | None:
    """Return the local file a link points to, or None for external and anchor-only links."""
    target = unquote(target.split("#", 1)[0])
    if not target or URI_SCHEME.match(target):
        return None
    base = wiki.bundle if target.startswith("/") else page.path.parent
    return (base / target.lstrip("/")).resolve()


def _check_body(wiki: Wiki, page: Page, incoming: dict[Path, int]) -> list[Finding]:
    found = []
    text = _mask_code(page.body)
    for match in WIKILINK.finditer(text):
        found.append(Finding(page.rel, _line(page, text, match.start()), "error", "editor-syntax",
                             f"wiki link or embed {match.group(0)}"))
    for match in CALLOUT.finditer(text):
        found.append(Finding(page.rel, _line(page, text, match.start()), "error", "editor-syntax",
                             "callout; use a plain blockquote"))
    for match in LINK.finditer(text):
        target = match.group(1) or match.group(2)
        path = _resolve(wiki, page, target)
        if path is None:
            continue
        if not path.is_file():
            found.append(Finding(page.rel, _line(page, text, match.start()), "error",
                                 "broken-link", f"link target '{target}' does not exist"))
        elif path != page.path.resolve():
            incoming[path] = incoming.get(path, 0) + 1
    if page.meta is not None and page.path.name != "index.md":
        ids = {s.get("id") for s in page.meta.get("sources") or [] if isinstance(s, dict)}
        for ref in sorted({m.group(1) for m in FOOTNOTE_REF.finditer(text)} - ids):
            found.append(Finding(page.rel, page.body_line, "warning", "footnote-unknown",
                                 f"footnote [^{ref}] has no entry in sources"))
    return found


def _check_names(wiki: Wiki) -> list[Finding]:
    found = []
    for page in wiki.pages:
        parts = page.path.relative_to(wiki.bundle).with_suffix("").parts
        bad = [part for part in parts if not KEBAB.match(part)]
        if bad:
            found.append(Finding(page.rel, 1, "warning", "file-name",
                                 "file and folder names must be lowercase kebab-case"))
        if len(parts) == 1:
            found.append(Finding(page.rel, 1, "warning", "no-domain",
                                 "page is not inside a domain folder"))
    return found


def _check_log(wiki: Wiki) -> list[Finding]:
    log = wiki.root / "log.md"
    if not log.is_file():
        return [Finding("log.md", 1, "warning", "log-missing", "log.md is missing")]
    found = []
    for number, line in enumerate(log.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("## ") and not LOG_HEADING.match(line):
            found.append(Finding("log.md", number, "error", "log-heading",
                                 "entry heading must be '## [YYYY-MM-DD] <operation> | <title>'"))
    return found


def _check_meetings(wiki: Wiki, validator: Draft202012Validator) -> list[Finding]:
    found = []
    types = wiki.profile.get("types") or []
    for meeting in wiki.meetings:
        if not MEETING_NAME.match(meeting.path.name):
            found.append(Finding(meeting.rel, 1, "error", "meeting-file-name",
                                 "name must be YYYY-MM-DD-<kebab-title>.md"))
        if meeting.meta is None:
            found.append(Finding(meeting.rel, 1, "error", "frontmatter",
                                 meeting.error or "meeting file has no YAML frontmatter"))
            continue
        for error in validator.iter_errors(meeting.meta):
            where = ".".join(map(str, error.path)) or "meeting"
            found.append(Finding(meeting.rel, 1, "error", "schema", f"{where}: {error.message}"))
        type_ = meeting.meta.get("type")
        if isinstance(type_, str) and type_ not in types:
            found.append(Finding(meeting.rel, 1, "error", "unknown-type",
                                 f"type '{type_}' is not in the profile"))
        for target in meeting.meta.get("related") or []:
            if isinstance(target, str) and not (wiki.bundle / target.lstrip("/")).is_file():
                found.append(Finding(meeting.rel, 1, "error", "broken-link",
                                     f"related page '{target}' does not exist"))
    return found


def lint(root: Path | str, now: datetime | None = None) -> list[Finding]:
    """Check a Commonmind wiki repository and return all findings."""
    now = now or datetime.now(UTC)
    wiki, found = load_wiki(root)
    if wiki is None:
        return found
    page_validator, meeting_validator = _validators()
    found += _check_profile(wiki.profile)
    found += _check_indexes(wiki)
    found += _check_names(wiki)
    incoming: dict[Path, int] = {}
    for page in wiki.pages:
        found += _check_frontmatter(wiki, page, page_validator, now)
        found += _check_body(wiki, page, incoming)
    index_links: dict[Path, int] = {}
    for index in wiki.indexes:
        found += _check_body(wiki, index, index_links)
    for page in wiki.pages:
        if page.path.resolve() not in incoming:
            found.append(Finding(page.rel, 1, "warning", "orphan",
                                 "no other page links here (index.md does not count)"))
    found += _check_log(wiki)
    found += _check_meetings(wiki, meeting_validator)
    return sorted(found, key=lambda f: (f.path, f.line, f.code))
