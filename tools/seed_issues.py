#!/usr/bin/env python3
"""Open a small, curated slice of the corpus as real GitHub issues.

Ground truth is STRIPPED — the NDJSON carries the answer key and live
issues must not. Throttled, ~10 issues, never the whole corpus (900
live issues is an API-abuse footgun; bulk work runs through replay.py).

Usage:
  python tools/seed_issues.py --dry-run       # show what would open
  python tools/seed_issues.py --expect        # predict the triage verdicts
  python tools/seed_issues.py                 # open them (needs gh auth)

--expect runs each curated ticket through the same classify path the
live workflow runs, no recent-issue window, solutions/rulebook.yaml
unless TRIAGE_RULEBOOK says otherwise, and prints the labels and gate
you should see land on the real issue. Open the tickets, then hold the
Actions run to these predictions.
"""

import argparse
import json
import os
import subprocess
import sys
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


def expect(picked):
    """Predict what the live workflow will do to each curated ticket.

    Mirrors triage/run.py's live path exactly: classify with no recent
    window, decide against THETA, the same rulebook the workflow env
    pins. Label assembly is restated here rather than imported, so the
    predictions work before you've written build_labels in layer 4.
    """
    sys.path.insert(0, str(ROOT))
    from triage.rulebook import classify, decide, load_rulebook

    rulebook_path = os.environ.get("TRIAGE_RULEBOOK",
                                   "solutions/rulebook.yaml")
    theta = float(os.environ.get("TRIAGE_THETA", "0.70"))
    rulebook = load_rulebook(rulebook_path)

    print(f"predictions against {rulebook_path}, theta {theta}\n")
    for kind, issue in picked:
        result, fired = classify(issue, rulebook)
        gate = decide(result, theta)
        sev, _ = result["severity"]
        svc, _ = result["service"]
        route, _ = result["routing"]
        labels = [f"sev:{sev}", f"route:{route}",
                  "triage:confident" if gate == "act"
                  else "triage:investigating"]
        if svc != "unknown":
            labels.append(f"service:{svc}")
        print(f"[{kind}] {issue['title']}")
        print(f"  expect labels: {' '.join(labels)}")
        print(f"  expect gate:   {gate}"
              + ("  (phase 2 will run)" if gate != "act" else ""))
    print("\nopen them, then compare: gh issue view <n> --json labels")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--expect", action="store_true",
                    help="print predicted labels + gate per ticket")
    ap.add_argument("--sleep", type=float, default=3.0,
                    help="seconds between issue creates")
    args = ap.parse_args()

    issues = []
    for f in sorted((ROOT / "data" / "issues").glob("*.ndjson")):
        issues += [json.loads(l) for l in f.read_text().splitlines()]

    picked = pick(issues)
    if not picked:
        raise SystemExit("no curated issues matched — regenerate the corpus?")

    if args.expect:
        expect(picked)
        return

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
