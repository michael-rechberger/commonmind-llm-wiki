"""Migrate an Obsidian-style LLM wiki to Commonmind (SPEC Appendix A).

Decisions that need judgment come from two files prepared beforehand (by people or an agent):

- a migration map: for every file in `wiki/` the new path, the type and, for people, the relation
- a description map: one sentence per page (old path → description)

Everything else is mechanical. The run is all-or-nothing: it checks the map first and writes only
if every file is mapped. `--dry-run` computes the result without writing.
"""

import argparse
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

import yaml

from commonmind_lint.inventory import kebab
from commonmind_lint.lint import LINK, URI_SCHEME, _Loader, _mask_code

WIKILINK = re.compile(r"(!?)\[\[([^\]]+)\]\]")
CALLOUT = re.compile(r"^([ \t]*>[ \t]*)\[![A-Za-z-]+\][+-]?[ \t]*(.*)$", re.MULTILINE)
OLD_LOG_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2})[ \t]*(.*?)[ \t]*$", re.MULTILINE)
LOG_OP = re.compile(r"^(ingest|query|lint|review|promote|migrate|update)\s*:\s*(.+)$",
                    re.IGNORECASE)
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}[ _-]*")
FIELD_ORDER = ["type", "title", "description", "owner", "data_class", "status", "project_status",
               "relation", "tags", "sources", "generated", "verified", "stale_after"]
DROPPED = {"domain", "last_updated", "status", "type"}
INDEX_START, INDEX_END = "<!-- commonmind:index -->", "<!-- /commonmind:index -->"


class MigrationError(Exception):
    pass


@dataclass
class Report:
    files: int = 0
    wikilinks: int = 0
    unresolved: int = 0
    links_rewritten: int = 0
    callouts: int = 0
    embeds_removed: int = 0
    embeds_unsupported: int = 0
    base_files_removed: int = 0
    sources_missing: int = 0
    missing_descriptions: int = 0
    missing_owners: int = 0
    log_headings: int = 0


@dataclass
class Entry:
    old: str
    new: str
    type: str
    relation: str | None
    meta: dict
    body: str
    title: str


def _split(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    meta = yaml.load(text[4 : end + 1], Loader=_Loader) or {}
    return meta, text[end + 4 :].lstrip("\n")


FLOW_KEYS = {"tags", "generated"}


def _dump(meta: dict) -> str:
    def one(key: str, value: object) -> str:
        if key in FLOW_KEYS:
            flow = yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=1000,
                                  default_flow_style=True)
            return f"{key}: {flow}"
        return yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True, width=1000)

    parts = [one(key, value) for key, value in meta.items()]
    return "---\n" + "".join(parts) + "---\n"


def _slug(heading: str) -> str:
    return re.sub(r"[\s]+", "-", re.sub(r"[^\w\s-]", "", heading.strip().lower()))


def _domain(new: str) -> str:
    return PurePosixPath(new).parts[1]


def _url(new: str) -> str:
    return "/" + PurePosixPath(new).relative_to("wiki").as_posix()


def _timestamp(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return f"{text}T00:00:00Z" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else text


class _Migration:
    def __init__(self, root: Path, entries: list[Entry], descriptions: dict, profile: dict,
                 generated_by: str, report: Report):
        self.root, self.entries, self.descriptions = root, entries, descriptions
        self.profile, self.generated_by, self.report = profile, generated_by, report
        self.by_path = {e.old.removeprefix("wiki/").removesuffix(".md").lower(): e
                        for e in entries}
        stems: dict[str, list[Entry]] = {}
        for e in entries:
            stems.setdefault(PurePosixPath(e.old).stem.lower(), []).append(e)
        self.by_stem = {k: v[0] for k, v in stems.items() if len(v) == 1}
        sources = root / "sources"
        self.sources = {p.name.lower(): p for p in sources.rglob("*") if p.is_file()} \
            if sources.is_dir() else {}

    def find(self, target: str) -> Entry | None:
        key = target.strip().lower().removesuffix(".md")
        return self.by_path.get(key) or self.by_stem.get(key.rsplit("/", 1)[-1])

    def _replace(self, body: str, pattern: re.Pattern, convert) -> str:
        masked = _mask_code(body)
        for match in reversed(list(pattern.finditer(masked))):
            body = body[: match.start()] + convert(match) + body[match.end() :]
        return body

    def convert_body(self, entry: Entry) -> str:
        body = entry.body

        def wikilink(match: re.Match) -> str:
            embed, inner = match.group(1), match.group(2)
            target, _, alias = inner.partition("|")
            target, _, heading = target.partition("#")
            if embed:
                if target.lower().endswith(".base"):
                    self.report.embeds_removed += 1
                    return ""
                self.report.embeds_unsupported += 1
                return match.group(0)
            self.report.wikilinks += 1
            hit = self.find(target)
            anchor = f"#{_slug(heading)}" if heading else ""
            if hit is None:
                self.report.unresolved += 1
                return f"[{alias or target}](/unresolved/{kebab(target)}.md{anchor})"
            return f"[{alias or hit.title}]({_url(hit.new)}{anchor})"

        def mdlink(match: re.Match) -> str:
            target = match.group(1) or match.group(2)
            path, _, anchor = target.partition("#")
            if not path or URI_SCHEME.match(path):
                return match.group(0)
            base = PurePosixPath("wiki") if path.startswith("/") else PurePosixPath(
                entry.old).parent
            parts: list[str] = []
            for part in (base / unquote(path).lstrip("/")).parts:
                if part == ".." and parts:
                    parts.pop()
                elif part not in ("..", "."):
                    parts.append(part)
            hit = self.by_path.get("/".join(parts).removeprefix("wiki/").removesuffix(".md")
                                   .lower())
            if hit is None:
                return match.group(0)
            self.report.links_rewritten += 1
            new = _url(hit.new) + (f"#{anchor}" if anchor else "")
            text = match.group(0)
            return text[: text.index("](") + 2] + new + ")"

        def callout(match: re.Match) -> str:
            self.report.callouts += 1
            prefix, title = match.group(1), match.group(2).strip()
            return f"{prefix}**{title}**" if title else prefix.rstrip()

        # Markdown links first, so that links created from wiki links are not rewritten again
        body = self._replace(body, LINK, mdlink)
        body = self._replace(body, WIKILINK, wikilink)
        body = self._replace(body, CALLOUT, callout)
        return re.sub(r"\n{3,}", "\n\n", body).strip("\n") + "\n"

    def convert_meta(self, entry: Entry) -> dict:
        old = entry.meta
        meta: dict = {"type": entry.type, "title": entry.title}
        description = self.descriptions.get(entry.old)
        if description:
            meta["description"] = description
        else:
            self.report.missing_descriptions += 1
        owner = (self.profile.get("domain_owners") or {}).get(_domain(entry.new))
        if owner:
            meta["owner"] = owner
        else:
            self.report.missing_owners += 1
        if "data_class" in old:
            meta["data_class"] = old["data_class"]
        if entry.type == "project" and old.get("status"):
            meta["project_status"] = old["status"]
        if entry.relation:
            meta["relation"] = entry.relation
        if old.get("tags"):
            meta["tags"] = old["tags"]
        if old.get("sources"):
            meta["sources"] = [self.source(s) for s in old["sources"]]
        at = _timestamp(old.get("last_updated"))
        if at:
            meta["generated"] = {"by": self.generated_by, "at": at}
        rest = {k: v for k, v in old.items() if k not in DROPPED and k not in meta}
        ordered = {k: meta[k] for k in FIELD_ORDER if k in meta}
        return ordered | rest

    def source(self, value: object) -> object:
        if isinstance(value, dict):
            return value
        name = PurePosixPath(str(value)).name
        stem = PurePosixPath(name).stem
        entry: dict = {"id": kebab(DATE_PREFIX.sub("", stem)) or kebab(stem)}
        found = self.sources.get(name.lower())
        if found is None:
            self.report.sources_missing += 1
            entry["resource"] = str(value)
            entry["title"] = stem
            return entry
        entry["resource"] = found.relative_to(self.root).as_posix()
        meta, _ = _split(found.read_text(encoding="utf-8")) if found.suffix == ".md" else ({}, "")
        entry["title"] = (meta.get("title") if isinstance(meta, dict) else None) or stem
        return entry


def _index_list(pages: list[tuple[Entry, dict]]) -> str:
    lines = []
    for entry, meta in sorted(pages, key=lambda p: p[0].title.lower()):
        line = f"- [{entry.title}]({_url(entry.new)})"
        lines.append(f"{line}: {meta['description']}" if meta.get("description") else line)
    return "\n".join([INDEX_START, *lines, INDEX_END])


def _convert_log(text: str, report: Report) -> str:
    def heading(match: re.Match) -> str:
        report.log_headings += 1
        rest = match.group(2)
        op = LOG_OP.match(rest)
        op_name, title = (op.group(1).lower(), op.group(2)) if op else ("update", rest)
        # Old headings may carry only a date or a time; the title must not be empty
        return f"## [{match.group(1)}] {op_name} | {title.strip() or 'entry'}"

    return OLD_LOG_HEADING.sub(heading, text)


def _domain_title(domain: str, titles: dict[str, str]) -> str:
    return titles.get(domain) or domain.replace("-", " ").capitalize()


def migrate(root: Path | str, map_path: Path | str, descriptions_path: Path | str,
            generated_by: str, today: str | None = None, dry_run: bool = False,
            domain_titles: dict[str, str] | None = None) -> Report:
    root = Path(root)
    report = Report()
    titles = domain_titles or {}
    today = today or date.today().isoformat()
    profile = yaml.load((root / "commonmind.yaml").read_text(encoding="utf-8"), Loader=_Loader)
    mapping = yaml.load(Path(map_path).read_text(encoding="utf-8"), Loader=_Loader) or []
    descriptions = yaml.load(Path(descriptions_path).read_text(encoding="utf-8"),
                             Loader=_Loader) or {}

    files = {p.relative_to(root).as_posix() for p in (root / "wiki").rglob("*.md")}
    mapped = {m["old"] for m in mapping}
    if unmapped := sorted(files - mapped):
        raise MigrationError(f"{len(unmapped)} file(s) not in the migration map")
    if missing := sorted(mapped - files):
        raise MigrationError(f"{len(missing)} map entries point to missing files")
    news = [m["new"] for m in mapping]
    if len(news) != len(set(news)):
        raise MigrationError("two map entries have the same new path")

    entries = []
    for m in mapping:
        meta, body = _split((root / m["old"]).read_text(encoding="utf-8"))
        title = meta.get("title") or PurePosixPath(m["old"]).stem
        entries.append(Entry(m["old"], m["new"], m["type"], m.get("relation"), meta, body, title))
    report.files = len(entries)
    run = _Migration(root, entries, descriptions, profile, generated_by, report)

    outputs: dict[str, str] = {}
    pages_by_domain: dict[str, list[tuple[Entry, dict]]] = {}
    index_bodies: dict[str, str] = {}
    for entry in entries:
        body = run.convert_body(entry)
        if entry.type == "index":
            index_bodies[_domain(entry.new)] = body
            continue
        meta = run.convert_meta(entry)
        pages_by_domain.setdefault(_domain(entry.new), []).append((entry, meta))
        outputs[entry.new] = _dump(meta) + "\n" + body

    for domain, pages in pages_by_domain.items():
        title = f"# {_domain_title(domain, titles)}\n"
        head = index_bodies.get(domain) or title
        first = next((ln for ln in head.splitlines() if ln.strip()), "")
        if not first.startswith("# "):
            head = f"{title}\n{head.lstrip()}"
        outputs[f"wiki/{domain}/index.md"] = f"{head.rstrip()}\n\n{_index_list(pages)}\n"
    if not (root / "wiki/index.md").is_file():
        lines = [f"- [{_domain_title(d, titles)}](/{d}/index.md)"
                 for d in sorted(pages_by_domain)]
        title = profile.get("title") or "Wiki"
        outputs["wiki/index.md"] = ('---\nokf_version: "0.2"\n---\n\n'
                                    f"# {title}\n\n" + "\n".join(lines) + "\n")

    log_path = root / "log.md"
    log = _convert_log(log_path.read_text(encoding="utf-8"), report) if log_path.is_file() \
        else "# Log\n"
    version = profile.get("commonmind_version") or "1.1"
    log = (log.rstrip("\n") + f"\n\n## [{today}] migrate | Commonmind {version}\n\n"
           f"Migrated {report.files} files from Obsidian style (SPEC Appendix A); "
           "log headings reformatted once.\n")

    base_files = sorted((root / "wiki").rglob("*.base"))
    report.base_files_removed = len(base_files)
    if dry_run:
        return report
    for entry in entries:
        (root / entry.old).unlink()
    for path in base_files:
        path.unlink()
    for rel, text in outputs.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    log_path.write_text(log, encoding="utf-8")
    for folder in sorted((root / "wiki").rglob("*"), reverse=True):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="commonmind-migrate",
                                     description="Migrate an Obsidian-style wiki to Commonmind.")
    parser.add_argument("path", nargs="?", default=".", help="repository root (default: .)")
    parser.add_argument("--map", default="tools/migration/migration-map.yaml")
    parser.add_argument("--descriptions", default="tools/migration/description-map.yaml")
    parser.add_argument("--generated-by", required=True, help="actor for generated.by")
    parser.add_argument("--today", help="date for the log entry (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="compute, but write nothing")
    parser.add_argument("--domain-title", action="append", default=[], metavar="DOMAIN=TITLE",
                        help="display title of a domain in index pages (repeatable)")
    args = parser.parse_args(argv)
    root = Path(args.path)
    titles = dict(item.split("=", 1) for item in args.domain_title)
    try:
        report = migrate(root, root / args.map, root / args.descriptions, args.generated_by,
                         today=args.today, dry_run=args.dry_run, domain_titles=titles)
    except MigrationError as exc:
        print(f"aborted: {exc}")
        return 1
    for key, value in vars(report).items():
        print(f"{key}: {value}")
    if args.dry_run:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
