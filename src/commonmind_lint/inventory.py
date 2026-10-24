"""Inventory of an Obsidian-style LLM wiki before migrating it to Commonmind (SPEC Appendix B).

The output holds counts only, no file names, titles or text, so that it can be shared from a
run on a confidential wiki.
"""

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import yaml

from commonmind_lint.lint import KEBAB, _Loader, _mask_code

WIKILINK = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")
EMBED = re.compile(r"!\[\[([^\]]+)\]\]")
CALLOUT = re.compile(r"^[ \t]*>[ \t]*\[!([A-Za-z-]+)\]", re.MULTILINE)
DATAVIEW = re.compile(r"^```dataview", re.MULTILINE)
MD_LINK = re.compile(r"(?<!!)\[[^\]]*\]\([^)]+\)")
UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue",
                         "ß": "ss"})


def kebab(name: str) -> str:
    """File name stem to lowercase kebab-case ASCII (German umlauts transliterated)."""
    ascii_ = unicodedata.normalize("NFKD", name.translate(UMLAUTS))
    ascii_ = ascii_.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-")


def _split(text: str) -> tuple[dict | None, str, bool]:
    """Return (frontmatter, body, parsable)."""
    if not text.startswith("---\n"):
        return None, text, True
    end = text.find("\n---", 4)
    if end == -1:
        return None, text, False
    body = text[end + 4 :]
    try:
        meta = yaml.load(text[4 : end + 1], Loader=_Loader)
    except yaml.YAMLError:
        return None, body, False
    return (meta if isinstance(meta, dict) else None), body, isinstance(meta, dict)


def inventory(root: Path | str) -> dict:
    root = Path(root)
    bundle, sources = root / "wiki", root / "sources"
    files = sorted(bundle.rglob("*.md"))
    page_stems = {p.relative_to(bundle).with_suffix("").as_posix().lower() for p in files}
    source_files = [p for p in sources.rglob("*") if p.is_file()] if sources.is_dir() else []
    source_names = {p.name.lower() for p in source_files} | {p.stem.lower() for p in source_files}

    per_folder: Counter = Counter()
    fields: Counter = Counter()
    values: dict[str, Counter] = {"status": Counter(), "type": Counter()}
    tags: set[str] = set()
    missing = unparsable = 0
    src = Counter()
    links = Counter()
    embeds: Counter = Counter()
    callouts: Counter = Counter()
    other = Counter()

    def resolve(target: str) -> str:
        target = target.split("|", 1)[0].split("#", 1)[0].strip().lower().removesuffix(".md")
        if any(s == target or s.endswith("/" + target) for s in page_stems):
            return "to_pages"
        if target.rsplit("/", 1)[-1] in source_names:
            return "to_sources"
        return "unresolved"

    for path in files:
        rel = path.relative_to(bundle)
        per_folder[rel.parts[0] if len(rel.parts) > 1 else "."] += 1
        meta, body, ok = _split(path.read_text(encoding="utf-8"))
        if not ok:
            unparsable += 1
        elif meta is None:
            missing += 1
        else:
            fields.update(meta.keys())
            for key, counter in values.items():
                if isinstance(meta.get(key), str):
                    counter[meta[key]] += 1
            tags.update(t for t in meta.get("tags") or [] if isinstance(t, str))
            for entry in meta.get("sources") or []:
                src["entries"] += 1
                if isinstance(entry, dict):
                    src["as_object"] += 1
                    name = str(entry.get("resource", ""))
                else:
                    src["as_text"] += 1
                    name = str(entry)
                if Path(name).name.lower() in source_names:
                    src["found"] += 1
        other["dataview_blocks"] += len(DATAVIEW.findall(body))
        text = _mask_code(body)
        for match in WIKILINK.finditer(text):
            inner = match.group(1)
            links["total"] += 1
            links["with_alias"] += "|" in inner
            links["with_path"] += "/" in inner.split("|", 1)[0]
            links["with_heading"] += "#" in inner.split("|", 1)[0]
            links[resolve(inner)] += 1
        for match in EMBED.finditer(text):
            suffix = Path(match.group(1).split("|", 1)[0].split("#", 1)[0]).suffix.lower()
            embeds[suffix or "page"] += 1
        callouts.update(m.group(1).lower() for m in CALLOUT.finditer(text))
        other["markdown_links"] += len(MD_LINK.findall(text))

    stems = [p for p in files if p.name != "_MOC.md"]
    by_folder: dict[Path, Counter] = {}
    for p in stems:
        by_folder.setdefault(p.parent, Counter())[kebab(p.stem)] += 1
    log = root / "log.md"
    headings = [line for line in log.read_text(encoding="utf-8").splitlines()
                if line.startswith("## ")] if log.is_file() else []

    return {
        "pages": {"total": len(files), "per_folder": dict(sorted(per_folder.items()))},
        "frontmatter": {
            "missing": missing,
            "unparsable": unparsable,
            "fields": dict(sorted(fields.items())),
            "values": {k: dict(sorted(v.items())) for k, v in values.items()},
        },
        "tags": {"distinct": len(tags), "not_kebab_case": sum(not KEBAB.match(t) for t in tags)},
        "sources": {k: src[k] for k in ("entries", "as_text", "as_object", "found")},
        "wikilinks": {k: links[k] for k in ("total", "with_alias", "with_path", "with_heading",
                                            "to_pages", "to_sources", "unresolved")},
        "embeds": dict(sorted(embeds.items())),
        "callouts": dict(sorted(callouts.items())),
        "other_syntax": dict(sorted(other.items())),
        "file_names": {
            "not_kebab_case": sum(not KEBAB.match(p.stem) for p in stems),
            "non_ascii": sum(not p.stem.isascii() for p in stems),
            "duplicate_basenames": sum(
                c - 1 for c in Counter(p.stem.lower() for p in stems).values() if c > 1),
            "kebab_collisions": sum(c - 1 for f in by_folder.values() for c in f.values() if c > 1),
        },
        "log": {
            "exists": log.is_file(),
            "headings": len(headings),
            "commonmind_format": sum(bool(re.match(r"^## \[\d{4}-\d{2}-\d{2}\] \S+ \| ", h))
                                     for h in headings),
            "date_first": sum(bool(re.match(r"^## \d{4}-\d{2}-\d{2}", h)) for h in headings),
            "other": sum(not re.match(r"^## \[?\d{4}-\d{2}-\d{2}", h) for h in headings),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="commonmind-inventory",
                                     description="Count Obsidian-style constructs (no content).")
    parser.add_argument("path", nargs="?", default=".", help="repository root (default: .)")
    parser.add_argument("-o", "--output", help="write JSON to this file instead of stdout")
    args = parser.parse_args(argv)
    text = json.dumps(inventory(args.path), indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
