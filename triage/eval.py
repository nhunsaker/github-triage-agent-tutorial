"""Measure the rulebook against the corpus ground truth.

The training loop: baseline → mine → write a rule → re-eval → read the
misses → repeat. Tune on year 1. Unseal year 2 ONCE at the end.

Usage:
  python -m triage.eval --year 1
  python -m triage.eval --year 1 --show-misses
  python -m triage.eval --year 2 --rulebook solutions/rulebook.yaml
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from triage.rulebook import classify, decide, load_rulebook, recent_window

ROOT = Path(__file__).resolve().parents[1]


def load_issues(year):
    path = ROOT / "data" / "issues" / f"year{year}.ndjson"
    return [json.loads(l) for l in path.read_text().splitlines()]


def run(issues, rulebook, theta=0.70):
    rows = []
    for issue in issues:
        window = recent_window(issue, issues)
        result, fired = classify(issue, rulebook, recent_issues=window)
        rows.append({
            "number": issue["number"],
            "title": issue["title"],
            "gt": issue["ground_truth"],
            "pred": {dim: v for dim, (v, _) in result.items()},
            "conf": {dim: c for dim, (_, c) in result.items()},
            "gate": decide(result, theta),
            "fired": fired,
        })
    return rows


def report(rows, show_misses=False):
    n = len(rows)
    routing_hits = sum(1 for r in rows if r["pred"]["routing"] == r["gt"]["routing"])
    sev_hits = sum(1 for r in rows if r["pred"]["severity"] == r["gt"]["severity"])
    svc_hits = sum(1 for r in rows
                   if r["gt"]["service"] and r["pred"]["service"] == r["gt"]["service"])
    gated = sum(1 for r in rows if r["gate"] == "investigate")

    print(f"issues:          {n}")
    print(f"routing top-1:   {routing_hits/n:.1%}")
    print(f"severity:        {sev_hits/n:.1%}")
    print(f"service:         {svc_hits/n:.1%}")
    print(f"sent to phase 2: {gated/n:.1%}  (below theta)")

    # confusion matrix, routing
    print("\nrouting confusion (rows=truth, cols=pred):")
    labels = ["internal", "external", "human"]
    matrix = defaultdict(Counter)
    for r in rows:
        matrix[r["gt"]["routing"]][r["pred"]["routing"]] += 1
    print(f"{'':>10}" + "".join(f"{l:>10}" for l in labels))
    for gt in labels:
        print(f"{gt:>10}" + "".join(f"{matrix[gt][p]:>10}" for p in labels))

    # calibration: is confidence honest
    print("\nrouting calibration (bucket → accuracy in bucket):")
    buckets = defaultdict(list)
    for r in rows:
        b = round(r["conf"]["routing"] * 5) / 5
        buckets[b].append(r["pred"]["routing"] == r["gt"]["routing"])
    for b in sorted(buckets):
        hits = buckets[b]
        print(f"  conf ~{b:.1f}: {sum(hits)/len(hits):.1%}  (n={len(hits)})")

    if show_misses:
        print("\nmisses, grouped by (truth → predicted):")
        groups = defaultdict(list)
        for r in rows:
            if r["pred"]["routing"] != r["gt"]["routing"]:
                groups[(r["gt"]["routing"], r["pred"]["routing"])].append(r)
        for (gt, pred), items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            print(f"\n  {gt} → {pred}  ({len(items)} issues)")
            for r in items[:8]:
                cid = r["gt"]["catalog_id"] or "?"
                print(f"    #{r['number']:>4} [{cid}] {r['title'][:64]}")
            if len(items) > 8:
                print(f"    … {len(items)-8} more")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=1, choices=(1, 2))
    ap.add_argument("--rulebook", default=None)
    ap.add_argument("--theta", type=float, default=0.70)
    ap.add_argument("--show-misses", action="store_true")
    args = ap.parse_args()

    issues = load_issues(args.year)
    rulebook = load_rulebook(args.rulebook)
    rows = run(issues, rulebook, args.theta)
    name = args.rulebook or "triage/rulebook.yaml"
    print(f"rulebook: {name} · year {args.year} · theta {args.theta}\n")
    report(rows, show_misses=args.show_misses)


if __name__ == "__main__":
    main()
