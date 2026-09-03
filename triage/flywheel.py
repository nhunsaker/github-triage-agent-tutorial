#!/usr/bin/env python3
"""The flywheel. Layer 8 walks you through building this yourself in
four steps. Each subcommand is one step and runs standalone before you
wire the next.

  capture     diff bot-decision vs labels-at-close on closed issues
  accumulate  append corrections to triage/labels.jsonl
  measure     what would accuracy be with the corrections folded in
  suggest     cluster corrections into a proposed rulebook edit

The training signal is the label diff: the triage comment's machine
block records what the bot decided at open, humans relabel/close as
reality lands, and every disagreement is a training label.

This file is the starter. The capture plumbing (live gh calls, corpus
replay) is given, because fetching issues is not the lesson. The four
functions that ARE the lesson raise NotImplementedError until you
write them: diff, accumulate, measure, suggest. Layer 8 specs each
one. Do not copy solutions/flywheel.py, the loop is the lesson.

Your gate: pytest tests/chapters/test_ch08.py -q

Live mode reads closed issues via gh. --simulate replays the corpus
instead (ground truth stands in for labels-at-close), so the whole
loop is walkable offline.
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


# ── step 1: capture (plumbing given, diff is yours) ──────────────────

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
    """One correction record per dimension the human overrode.

    Contract, from layer 8 step 1:
      - `bot` is the machine block: {"issue": N, "decision": {dim:
        {"value": ..., "confidence": ...}}} for dims routing, severity,
        service.
      - `final_labels` is the set of label strings at close. The label
        prefixes are route: / sev: / service: (create_labels.py is the
        source of truth for those).
      - Return a list of correction dicts, one per dimension where the
        human's label disagrees with the bot's value: {"issue",
        "dimension", "bot", "human", "confidence", "body_excerpt"}.
        body_excerpt is the first 200 chars of `body` (empty string
        when body is None). Agreement, or a missing side, emits
        nothing for that dimension.
    """
    raise NotImplementedError("chapter 8")


# ── step 2: accumulate ───────────────────────────────────────────────

def accumulate(corrections):
    """Append new corrections to triage/labels.jsonl, deduped.

    Contract, from layer 8 step 2:
      - The dedup key is (issue, dimension). A correction already on
        file never appends again, so reruns are idempotent.
      - Append as one JSON object per line (jsonl).
      - Print one summary line: how many appended, how many total on
        file. The chapter shows the expected format.
    """
    raise NotImplementedError("chapter 8")


# ── step 3: measure ──────────────────────────────────────────────────

def measure():
    """Aggregate the corrections on file into a per-dimension confusion
    view.

    Contract, from layer 8 step 3:
      - Read triage/labels.jsonl. If it does not exist yet, say so and
        return (capture + accumulate come first).
      - Print the total count, then for each dimension the bot → human
        pairs with counts, most common first (top 8 per dimension is
        plenty). This is the view that makes the drift legible: one
        pair dominating a dimension is a rule waiting to be written.
    """
    raise NotImplementedError("chapter 8")


# ── step 4: suggest ──────────────────────────────────────────────────

def suggest():
    """Cluster corrections by shared catalog signature → proposed rule.

    Contract, from layer 8 step 4:
      - Read triage/labels.jsonl (if missing, say so and return) and
        data/error_catalog.yaml.
      - Match each correction's body_excerpt against the catalog
        message templates. The templates hold {placeholders}, so build
        a regex per entry: escape the message, then replace the escaped
        placeholders with a non-greedy wildcard. First matching entry
        claims the correction.
      - Any entry with 5 or more corrections proposes a rule, largest
        cluster first. Print it as a rulebook-ready YAML fragment:
        id fly-<catalog-id-lowercased>, match = the message up to the
        first placeholder (trimmed), service + severity from the
        catalog entry, routing = the humans' majority routing
        correction (fall back to the catalog's routing), confidence
        0.85 with a comment counting the agreeing corrections.
      - No cluster of 5+ prints a plain "no cluster big enough" line.
    """
    raise NotImplementedError("chapter 8")


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
