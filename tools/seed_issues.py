#!/usr/bin/env python3
"""Open a small, curated slice of the corpus as real GitHub issues.

Ground truth is STRIPPED — the NDJSON carries the answer key and live
issues must not. Throttled, ~10 issues, never the whole corpus (900
live issues is an API-abuse footgun; bulk work runs through replay.py).

Usage:
  python tools/seed_issues.py --dry-run       # show what would open
  python tools/seed_issues.py                 # open them (needs gh auth)
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# hand-picked mix: confident signatures, one ambiguous, one vague,
# one webhook (always gates), one duplicate pair
CURATED_TITLES_HINTS = [
    ("sig-confident", "sold items we dont have in stock"),
    ("sig-confident", "500 on checkout"),
    ("sig-confident", "dead letter queue filling up"),
    ("sig-confident", "refund declined by vendor"),
    ("ambiguous", "order counts frozen"),
    ("ambiguous", "dashboard not showing new orders"),
    ("vague", "checkout is broken"),
    ("vague", "numbers look wrong"),
    ("hard", "webhook signature failures"),
    ("dupe", "same as an earlier report"),
]


def pick(issues):
    picked, used = [], set()
    for kind, hint in CURATED_TITLES_HINTS:
        for i in issues:
            if i["number"] in used:
                continue
            if hint.lower() in i["title"].lower():
                picked.append((kind, i))
                used.add(i["number"])
                break
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=3.0,
                    help="seconds between issue creates")
    args = ap.parse_args()

    issues = []
    for f in sorted((ROOT / "data" / "issues").glob("*.ndjson")):
        issues += [json.loads(l) for l in f.read_text().splitlines()]

    picked = pick(issues)
    if not picked:
        raise SystemExit("no curated issues matched — regenerate the corpus?")

    for kind, issue in picked:
        # strip the answer key
        title = issue["title"]
        body = issue["body"] + f"\n\n<sub>seeded from corpus #{issue['number']}</sub>"
        if args.dry_run:
            print(f"[{kind}] would open: {title}")
            continue
        subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body", body],
            check=True)
        print(f"[{kind}] opened: {title}")
        time.sleep(args.sleep)

    print(f"\n{len(picked)} issues {'previewed' if args.dry_run else 'opened'}. "
          "watch the Actions tab for the triage workflow.")


if __name__ == "__main__":
    main()
