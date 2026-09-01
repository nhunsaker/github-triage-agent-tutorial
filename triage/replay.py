"""Stream a corpus slice through the same path the Action runs.

Iterate on rules without opening a single live issue:
  python -m triage.replay --year 1 --limit 20
  python -m triage.replay --year 2 --only-gated
  python -m triage.replay --year 2 --number 612
"""

import argparse
import json
from pathlib import Path

from triage.rulebook import classify, decide, load_rulebook, recent_window

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=1, choices=(1, 2))
    ap.add_argument("--rulebook", default=None)
    ap.add_argument("--theta", type=float, default=0.70)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-gated", action="store_true",
                    help="show only issues sent to phase 2")
    ap.add_argument("--number", type=int, help="replay a single issue")
    args = ap.parse_args()

    path = ROOT / "data" / "issues" / f"year{args.year}.ndjson"
    issues = [json.loads(l) for l in path.read_text().splitlines()]
    rulebook = load_rulebook(args.rulebook)

    shown = 0
    for issue in issues:
        if args.number and issue["number"] != args.number:
            continue
        window = recent_window(issue, issues)
        result, fired = classify(issue, rulebook, recent_issues=window)
        gate = decide(result, args.theta)
        if args.only_gated and gate == "act":
            continue

        gt = issue["ground_truth"]
        mark = "✓" if result["routing"][0] == gt["routing"] else "✗"
        print(f"#{issue['number']:>4} {mark} "
              f"[{result['routing'][0]:<8} {result['routing'][1]:.2f}] "
              f"gate={gate:<11} gt={gt['routing']:<8} {issue['title'][:56]}")
        if args.number:
            print(f"\n  fired: {fired}")
            print(f"  full:  {result}")
        shown += 1
        if args.limit and shown >= args.limit:
            break


if __name__ == "__main__":
    main()
