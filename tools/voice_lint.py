#!/usr/bin/env python3
"""Lint the tutorial prose for banned moves. Keeps the voice honest
through edits.

Usage: python tools/voice_lint.py [docs/tutorial]
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BANNED = [
    (re.compile(r"—"), "em dash (restructure with commas or periods)"),
    (re.compile(r"\s-\s"), "hyphen as punctuation"),
    (re.compile(r"\b(Additionally|Furthermore|Moreover)\b"), "AI transition word"),
    (re.compile(r"It'?s worth noting", re.I), "AI hedge"),
    (re.compile(r"I'?d be happy to", re.I), "AI servility"),
    (re.compile(r"\b(awesome|fantastic|amazing|incredible)\b", re.I), "enthusiasm inflation"),
    (re.compile(r"!(?!\[)"), "exclamation point"),
    (re.compile(r";\s"), "semicolon"),
    (re.compile(r"In this (section|layer|tutorial), (we|you) will", re.I), "restating the ask"),
    (re.compile(r"(In summary|To summarize|Let'?s recap)", re.I), "wrap-up summary"),
]


def lint_file(path):
    problems = []
    in_code = False
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or line.strip().startswith("|"):
            continue  # code and tables get a pass
        for pat, why in BANNED:
            if pat.search(line):
                problems.append((n, why, line.strip()[:70]))
    return problems


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "tutorial"
    files = sorted(target.glob("*.md")) if target.is_dir() else [target]
    total = 0
    for f in files:
        problems = lint_file(f)
        if problems:
            try:
                shown = f.resolve().relative_to(ROOT)
            except ValueError:
                shown = f
            print(f"\n{shown}")
            for n, why, line in problems:
                print(f"  {n:>4}: {why}\n        {line}")
            total += len(problems)
    if total:
        print(f"\n{total} voice violations")
        sys.exit(1)
    print("voice clean")


if __name__ == "__main__":
    main()
