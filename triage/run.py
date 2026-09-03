"""The entrypoint the GitHub Action calls. Also the local dry-run harness.

Layer 4 walks you through wiring the trained rulebook to Actions. The
CLI, event/issue loading, and the live `gh` calls are given, because
parsing argv and shelling out to gh is not the lesson. The two
functions that ARE the lesson raise NotImplementedError until you
write them: build_labels, build_comment. Layer 4 specs each one. Do
not copy solutions/run.py, the wiring is the lesson.

Your gate: pytest tests/chapters/test_ch04.py -q

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
    """Turn a classify() result + gate decision into the label set.

    Contract, from layer 4 step 1:
      - `result` is classify()'s return: {dimension: (value, confidence)}
        for dims severity, service, routing (see triage/rulebook.py).
      - `gate` is decide()'s return, the string "act" or "investigate".
      - Always emit `sev:<severity>` and `route:<routing>` (the
        route:/sev: prefixes are the label API create_labels.py
        expects).
      - Emit `service:<service>` too, prefixed `service:`, UNLESS the
        service value is the "unknown" default, in which case skip it,
        an unknown service is not worth a label.
      - Emit `triage:confident` when gate == "act", otherwise
        `triage:investigating`. This is the theta gate surfaced as a
        label: decide() already compared routing confidence to THETA,
        build_labels just encodes which side it landed on.
      - Return the labels as a list. Order isn't load-bearing for
        callers, but match sev, route, triage:*, service (when
        present) so dry-run output is stable and matches the chapter.
    """
    raise NotImplementedError("chapter 4")


def build_comment(issue, result, fired, gate):
    """Render the triage comment: human table + hidden machine block.

    Contract, from layer 4 step 2:
      - Build `machine`, a dict: {"v": 1, "issue": issue["number"],
        "decision": {dim: {"value": v, "confidence": c} for dim, (v, c)
        in result.items()}, "gate": gate, "theta": THETA, "fired":
        fired}. This is the exact shape the flywheel (layer 8) reads
        back out of the comment. THETA is the module constant already
        in scope, not a parameter. Iterate `result` in its given
        order, it follows rulebook.DIMENSIONS, and the machine block,
        the table rows, and the chapter's sample output all share it.
      - Emit it as the comment's first line, wrapped in an HTML
        comment tagged with a version: `<!-- triage:v1 {json} -->`
        (json.dumps(machine), no extra whitespace requirements). The
        marker is invisible when GitHub renders the comment but is
        right there in the raw body for anything parsing activity to
        read.
      - Below the marker: a `### triage` heading, then a markdown
        table with a header row `| dimension | call | confidence |`
        and one row per dimension: `| {dim} | \\`{value}\\` |
        {confidence:.2f} |`.
      - A "rules fired" line: the fired rule ids backtick-quoted and
        comma-joined, or the literal `none (defaults)` when `fired` is
        empty.
      - A closing verdict sentence: "acting on this triage" when
        gate == "act", else "confidence below threshold, starting an
        investigation" (this is the theta gate again, in prose this
        time), followed by an invitation to comment `/investigate` on
        the issue either way.
      - Return the whole comment as one string.
    """
    raise NotImplementedError("chapter 4")


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
