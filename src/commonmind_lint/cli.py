"""Command line: commonmind-lint [--strict] [--summary] [PATH]"""

import argparse
from collections import Counter

from commonmind_lint.lint import lint


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="commonmind-lint",
                                     description="Check a Commonmind wiki repository.")
    parser.add_argument("path", nargs="?", default=".", help="repository root (default: .)")
    parser.add_argument("--strict", action="store_true", help="fail on warnings too")
    parser.add_argument("--summary", action="store_true",
                        help="print counts per check only, without paths or messages")
    args = parser.parse_args(argv)

    findings = lint(args.path)
    errors = sum(f.level == "error" for f in findings)
    warnings = len(findings) - errors
    if args.summary:
        for (level, code), count in sorted(Counter((f.level, f.code) for f in findings).items()):
            print(f"{level} {code}: {count}")
    else:
        for finding in findings:
            print(finding)
    print(f"{errors} errors, {warnings} warnings")
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
