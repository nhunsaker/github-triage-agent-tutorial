"""The entrypoint the GitHub Action calls. Also the local dry-run harness.

Live (in Actions):
  python -m triage.run --event "$GITHUB_EVENT_PATH"
Local:
  python -m triage.run --issue path/to/issue.json --dry-run

Output contract (labels are the API):
  labels:  sev:S0..S3 · service:<name> · route:internal|external|human
           · triage:confident | triage:investigating
  comment: human-readable table + hidden machine block
           <!-- triage:v1 {json} -->  (the flywheel parses this)
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from triage.rulebook import classify, decide, load_rulebook

ROOT = Path(__file__).resolve().parents[1]
THETA = float(os.environ.get("TRIAGE_THETA", "0.70"))


def load_issue(args):
    if args.event:
        event = json.loads(Path(args.event).read_text())
        i = event["issue"]
        return {"number": i["number"], "title": i["title"],
                "body": i.get("body") or "", "created_at": i["created_at"]}
    issue = json.loads(Path(args.issue).read_text())
    issue.setdefault("body", "")
    return issue


def build_labels(result, gate):
    sev, _ = result["severity"]
    svc, _ = result["service"]
    route, _ = result["routing"]
    labels = [f"sev:{sev}", f"route:{route}",
              "triage:confident" if gate == "act" else "triage:investigating"]
    if svc != "unknown":
        labels.append(f"service:{svc}")
    return labels


def build_comment(issue, result, fired, gate):
    machine = {
        "v": 1,
        "issue": issue["number"],
        "decision": {dim: {"value": v, "confidence": c}
                     for dim, (v, c) in result.items()},
        "gate": gate,
        "theta": THETA,
        "fired": fired,
    }
    rows = "\n".join(
        f"| {dim} | `{v}` | {c:.2f} |" for dim, (v, c) in result.items())
    verdict = ("acting on this triage" if gate == "act"
               else "confidence below threshold, starting an investigation")
    return f"""<!-- triage:v1 {json.dumps(machine)} -->
### triage

| dimension | call | confidence |
|---|---|---|
{rows}

rules fired: {', '.join(f'`{f}`' for f in fired) if fired else 'none (defaults)'}

{verdict}. want a deeper look either way? comment `/investigate` on this issue.
"""


def apply_live(issue_number, labels, comment):
    """Label + comment via gh. Default GITHUB_TOKEN is enough for this."""
    subprocess.run(["gh", "issue", "edit", str(issue_number),
                    "--add-label", ",".join(labels)], check=True)
    subprocess.run(["gh", "issue", "comment", str(issue_number),
                    "--body", comment], check=True)


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--event", help="path to the GitHub event payload")
    src.add_argument("--issue", help="path to a local issue JSON")
    ap.add_argument("--rulebook", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    issue = load_issue(args)
    rulebook = load_rulebook(args.rulebook)
    # live mode has no replay window; corroboration uses whatever recent
    # issues the caller provides. In Actions, investigate.py does the
    # cluster check against the live repo instead.
    result, fired = classify(issue, rulebook)
    gate = decide(result, THETA)

    labels = build_labels(result, gate)
    comment = build_comment(issue, result, fired, gate)

    if args.dry_run or not args.event:
        print(f"issue #{issue['number']}: {issue['title']}")
        print(f"labels:  {labels}")
        print(f"gate:    {gate}")
        print(comment)
    else:
        apply_live(issue["number"], labels, comment)

    # the workflow reads this to decide whether to run phase 2
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"gate={gate}\n")
            f.write(f"service={result['service'][0]}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
