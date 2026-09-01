#!/usr/bin/env python3
"""The flywheel, finished version. Layer 7 walks you through building
this yourself in four steps — each subcommand is one step and runs
standalone before you wire the next.

  capture     diff bot-decision vs labels-at-close on closed issues
  accumulate  append corrections to triage/labels.jsonl
  measure     what would accuracy be with the corrections folded in
  suggest     cluster corrections into a proposed rulebook edit

The training signal is the label diff: the triage comment's machine
block records what the bot decided at open, humans relabel/close as
reality lands, and every disagreement is a training label.

Live mode reads closed issues via gh. --simulate replays the corpus
instead (ground truth stands in for labels-at-close), so the whole
loop is walkable offline.

The "retrain" is a PR against rulebook.yaml — see flywheel.yml.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "triage" / "labels.jsonl"
MARKER = re.compile(r"<!-- triage:v1 (\{.*?\}) -->", re.S)


# ── step 1: capture ──────────────────────────────────────────────────

def capture_live(limit):
    """Closed issues → (bot decision from marker, labels at close)."""
    out = subprocess.run(
        ["gh", "issue", "list", "--state", "closed", "--limit", str(limit),
         "--json", "number,labels,comments"],
        capture_output=True, text=True, check=True)
    corrections = []
    for issue in json.loads(out.stdout):
        bot = None
        for c in issue["comments"]:
            m = MARKER.search(c["body"])
            if m:
                bot = json.loads(m.group(1))
        if not bot:
            continue
        final = {l["name"] for l in issue["labels"]}
        corrections += diff(issue["number"], bot, final)
    return corrections


def capture_simulate(year, rulebook_path):
    """Offline: run the rulebook over the corpus, treat ground truth as
    the labels a human would have left at close."""
    from triage.rulebook import classify, decide, load_rulebook, recent_window
    issues = [json.loads(l) for l in
              (ROOT / "data" / "issues" / f"year{year}.ndjson").read_text().splitlines()]
    rulebook = load_rulebook(rulebook_path)
    corrections = []
    for issue in issues:
        result, fired = classify(issue, rulebook,
                                 recent_issues=recent_window(issue, issues))
        bot = {"issue": issue["number"],
               "decision": {dim: {"value": v, "confidence": c}
                            for dim, (v, c) in result.items()}}
        gt = issue["ground_truth"]
        final = {f"route:{gt['routing']}", f"sev:{gt['severity']}"}
        if gt["service"]:
            final.add(f"service:{gt['service']}")
        corrections += diff(issue["number"], bot, final,
                            body=issue["body"])
    return corrections


def diff(number, bot, final_labels, body=None):
    """One correction record per dimension the human overrode."""
    out = []
    prefix = {"routing": "route:", "severity": "sev:", "service": "service:"}
    for dim, pre in prefix.items():
        bot_value = bot["decision"].get(dim, {}).get("value")
        final = next((l[len(pre):] for l in final_labels
                      if l.startswith(pre)), None)
        if final and bot_value and final != bot_value:
            out.append({"issue": number, "dimension": dim,
                        "bot": bot_value, "human": final,
                        "confidence": bot["decision"][dim].get("confidence"),
                        "body_excerpt": (body or "")[:200]})
    return out


# ── step 2: accumulate ───────────────────────────────────────────────

def accumulate(corrections):
    seen = set()
    if LABELS.exists():
        for line in LABELS.read_text().splitlines():
            r = json.loads(line)
            seen.add((r["issue"], r["dimension"]))
    added = 0
    with open(LABELS, "a") as f:
        for c in corrections:
            key = (c["issue"], c["dimension"])
            if key not in seen:
                f.write(json.dumps(c) + "\n")
                seen.add(key)
                added += 1
    print(f"accumulated {added} new corrections "
          f"({len(seen)} total in {LABELS.relative_to(ROOT)})")


# ── step 3: measure ──────────────────────────────────────────────────

def measure():
    if not LABELS.exists():
        print("no labels.jsonl yet — run capture + accumulate first")
        return
    rows = [json.loads(l) for l in LABELS.read_text().splitlines()]
    by_dim = defaultdict(Counter)
    for r in rows:
        by_dim[r["dimension"]][(r["bot"], r["human"])] += 1
    print(f"{len(rows)} corrections on file\n")
    for dim, pairs in by_dim.items():
        print(f"{dim}: bot → human (count)")
        for (bot, human), n in pairs.most_common(8):
            print(f"  {bot:>10} → {human:<10} {n}")
        print()


# ── step 4: suggest ──────────────────────────────────────────────────

def suggest():
    """Cluster corrections by shared catalog signature → proposed rule."""
    if not LABELS.exists():
        print("no labels.jsonl yet")
        return
    with open(ROOT / "data" / "error_catalog.yaml") as f:
        catalog = yaml.safe_load(f)["catalog"]
    rows = [json.loads(l) for l in LABELS.read_text().splitlines()]

    by_entry = defaultdict(list)
    for r in rows:
        for e in catalog:
            pat = re.sub(r"\\\{[a-z_]+\\\}", ".+?", re.escape(e["message"]))
            if re.search(pat, r.get("body_excerpt", "")):
                by_entry[e["id"]].append(r)
                break

    proposed = False
    for cid, items in sorted(by_entry.items(), key=lambda kv: -len(kv[1])):
        if len(items) < 5:
            continue
        e = next(x for x in catalog if x["id"] == cid)
        human = Counter(i["human"] for i in items
                        if i["dimension"] == "routing").most_common(1)
        routing = human[0][0] if human else e["routing"]
        share = len(items)
        fragment = re.sub(r"\{[a-z_]+\}.*", "", e["message"]).strip().rstrip(":,'")
        print(f"# proposed rule from {share} corrections clustered on {cid}:")
        print(f"  - id: fly-{cid.lower()}")
        print(f"    match: \"{fragment}\"")
        print(f"    service: {e['service']}")
        print(f"    severity: {e['severity']}")
        print(f"    routing: {routing}")
        print(f"    confidence: 0.85  # {share} human corrections agree")
        print()
        proposed = True
    if not proposed:
        print("no correction cluster big enough to propose a rule (need 5+)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["capture", "accumulate", "measure",
                                     "suggest", "all"])
    ap.add_argument("--simulate", action="store_true",
                    help="replay the corpus instead of live gh")
    ap.add_argument("--year", type=int, default=2)
    ap.add_argument("--rulebook", default="solutions/rulebook.yaml")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))

    if args.step in ("capture", "all"):
        corrections = (capture_simulate(args.year, args.rulebook)
                       if args.simulate else capture_live(args.limit))
        print(f"captured {len(corrections)} corrections")
        if args.step == "capture":
            for c in corrections[:10]:
                print(f"  #{c['issue']} {c['dimension']}: "
                      f"{c['bot']} → {c['human']}")
            return
        accumulate(corrections)
    if args.step == "accumulate":
        corrections = (capture_simulate(args.year, args.rulebook)
                       if args.simulate else capture_live(args.limit))
        accumulate(corrections)
    if args.step in ("measure", "all"):
        measure()
    if args.step in ("suggest", "all"):
        suggest()


if __name__ == "__main__":
    main()
