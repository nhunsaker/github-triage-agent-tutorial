#!/usr/bin/env python3
"""Mine year-1 issues + resolutions for the signals that become rules.

The rulebook must not appear by magic. Run this, read the tables, write
the rule yourself. Each table answers one question:

  1. signature → routing        which quoted errors predict which routing
  2. keyword → routing          what plain words in vague reports predict
  3. external share by service  where do vendor problems live
  4. burst windows              when do many reports share one cause

Usage: python tools/mine_patterns.py
"""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

KEYWORDS = [
    "payflow", "webhook", "refund", "charge", "checkout", "stock",
    "dashboard", "stale", "frozen", "queue", "stream", "schema",
    "duplicate", "return", "503", "deprecated", "lag", "dead-letter",
]


def load():
    issues = [json.loads(l) for l in
              (ROOT / "data" / "issues" / "year1.ndjson").read_text().splitlines()]
    res = [json.loads(l) for l in
           (ROOT / "data" / "resolutions" / "year1.ndjson").read_text().splitlines()]
    res_by_issue = {r["issue_number"]: r for r in res}
    with open(ROOT / "data" / "error_catalog.yaml") as f:
        catalog = yaml.safe_load(f)["catalog"]
    return issues, res_by_issue, catalog


def sig_pattern(entry):
    pat = re.escape(entry["message"])
    return re.compile(re.sub(r"\\\{[a-z_]+\\\}", ".+?", pat), re.S)


def main():
    issues, res_by_issue, catalog = load()
    print(f"mining {len(issues)} year-1 issues against {len(res_by_issue)} resolutions\n")

    # 1 ── signature → routing
    print("=" * 70)
    print("1. quoted signature → final routing (write signature rules from this)")
    print("=" * 70)
    pats = [(e, sig_pattern(e)) for e in catalog]
    table = defaultdict(Counter)
    for i in issues:
        r = res_by_issue.get(i["number"])
        if not r:
            continue
        for e, p in pats:
            if p.search(i["body"]):
                table[e["id"]][r["routing"]] += 1
                break
    for cid in sorted(table):
        c = table[cid]
        total = sum(c.values())
        top, top_n = c.most_common(1)[0]
        e = next(e for e in catalog if e["id"] == cid)
        print(f"  {cid:>9}  n={total:<4} → {top:<9} {top_n/total:.0%}   "
              f"(service={e['service']}, sev={e['severity']})")

    # 2 ── keyword → routing, for issues quoting NO signature (the vague class)
    print()
    print("=" * 70)
    print("2. keyword → routing on unsigned (vague) reports")
    print("=" * 70)
    unsigned = [i for i in issues
                if not any(p.search(i["body"]) for _, p in pats)]
    print(f"  ({len(unsigned)} vague reports, "
          f"{len(unsigned)/len(issues):.0%} of year 1)\n")
    for kw in KEYWORDS:
        c = Counter()
        for i in unsigned:
            text = (i["title"] + " " + i["body"]).lower()
            if kw in text:
                r = res_by_issue.get(i["number"])
                if r:
                    c[r["routing"]] += 1
        total = sum(c.values())
        if total >= 5:
            top, top_n = c.most_common(1)[0]
            print(f"  {kw:>12}  n={total:<4} → {top:<9} {top_n/total:.0%}")

    # 3 ── external share by service
    print()
    print("=" * 70)
    print("3. external share by resolved service (where vendor problems live)")
    print("=" * 70)
    by_service = defaultdict(Counter)
    for i in issues:
        r = res_by_issue.get(i["number"])
        if r and r["service"]:
            by_service[r["service"]][r["routing"]] += 1
    for svc in sorted(by_service):
        c = by_service[svc]
        total = sum(c.values())
        print(f"  {svc:>10}  n={total:<4} external {c['external']/total:.0%}  "
              f"internal {c['internal']/total:.0%}  human {c['human']/total:.0%}")

    # 4 ── burst windows: many reports, short window, one likely cause
    print()
    print("=" * 70)
    print("4. burst windows (>=8 issues / 48h sharing a signature)")
    print("   this is the evidence for the fleet-wide corroboration rule")
    print("=" * 70)
    by_sig = defaultdict(list)
    for i in issues:
        for e, p in pats:
            if p.search(i["body"]):
                by_sig[e["id"]].append(
                    datetime.fromisoformat(i["created_at"].rstrip("Z")))
                break
    for cid, times in sorted(by_sig.items()):
        times.sort()
        best = 0
        for k, t in enumerate(times):
            hi = t + timedelta(hours=48)
            n = sum(1 for u in times[k:] if u <= hi)
            best = max(best, n)
        if best >= 8:
            print(f"  {cid:>9}  max {best} reports in one 48h window "
                  f"(n={len(times)} total)")


if __name__ == "__main__":
    main()
