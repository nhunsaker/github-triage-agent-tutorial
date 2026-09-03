"""Phase 2b: the LLM hypothesis, finished version. Layer 6 walks you
through building this yourself in three steps:

  build_prompt         turn the dossier + suspect files into the prompt
  validate_hypothesis  check the model's structured answer against the
                        contract you asked it for
  apply_refusal_guard  route a refusal or a shaky, low-confidence
                        hypothesis to a human instead of a confident
                        automated call

Takes the phase-2a dossier plus the suspect source files and asks
Claude for a hypothesis: what broke, where, internal or external, and
a fix direction. Posts it as a comment. The coding-agent hand-off
(phase 2c) stays optional above this.

Needs ANTHROPIC_API_KEY (repo secret in Actions, env var locally).
This module is the only place the provider appears: swapping providers
means swapping this one file.

Local:  python -m solutions.investigate_llm --issue path.json --service billing
Action: python -m solutions.investigate_llm --event "$GITHUB_EVENT_PATH" \
            --service billing --post
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import anthropic

from solutions.investigate import build_dossier

ROOT = Path(__file__).resolve().parents[1]
MODEL = os.environ.get("TRIAGE_LLM_MODEL", "claude-opus-4-8")
MAX_FILE_BYTES = 6000
MAX_FILES = 3
CONFIDENCE_FLOOR = 0.3

HYPOTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "hypothesis": {
            "type": "string",
            "description": "one or two sentences: what broke and why",
        },
        "routing": {
            "type": "string",
            "enum": ["internal", "external", "human"],
            "description": "who should own this",
        },
        "confidence": {
            "type": "number",
            "description": "0.0 to 1.0, honest, grounded in the evidence",
        },
        "suspect_files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "repo-relative paths most likely involved",
        },
        "fix_direction": {
            "type": "string",
            "description": "one or two sentences: where a fix would start, "
                           "or what to verify externally if routing is not internal",
        },
    },
    "required": ["hypothesis", "routing", "confidence",
                 "suspect_files", "fix_direction"],
    "additionalProperties": False,
}


def gather_files(dossier, service):
    """The code the model reads: dossier hits first, then the catalog
    prior's file, capped hard so the prompt stays small."""
    paths = []
    for hit in dossier.get("code_hits", []):
        if hit["file"] not in paths:
            paths.append(hit["file"])
    if dossier.get("prior"):
        import yaml
        with open(ROOT / "data" / "error_catalog.yaml") as f:
            for e in yaml.safe_load(f)["catalog"]:
                if e["id"] == dossier["prior"] and e["file"] not in paths:
                    paths.append(e["file"])
    out = []
    for p in paths[:MAX_FILES]:
        full = ROOT / p
        if full.exists():
            out.append((p, full.read_text()[:MAX_FILE_BYTES]))
    return out


def build_prompt(issue, service, dossier, files):
    """Turn the dossier and suspect files into the one prompt the model
    sees."""
    file_blocks = "\n\n".join(
        f"--- {path} ---\n{text}" for path, text in files
    ) or "(no source files matched the signature)"
    evidence = json.dumps({
        "signature": dossier["signature"],
        "catalog_prior": dossier.get("prior"),
        "fleet_similar_reports": len(dossier["fleet"]),
        "evidence_for": dossier["evidence_for"],
        "evidence_against": dossier["evidence_against"],
        "deterministic_verdict": dossier["revised"],
    }, indent=2)

    return f"""You are the investigation step of an issue-triage pipeline for a
monorepo with four services (qr = queue reader, api, dashboard, billing).
A deterministic pass already gathered evidence. Your job: read the issue,
the evidence, and the suspect source code, then produce a hypothesis.

Rules:
- a grep hit can be the RAISE SITE of a vendor-side error, not the cause.
  If the catalog prior says external and the fleet corroborates, the code
  match does not make it internal.
- confidence must be honest. Low evidence means low confidence.
- routing "human" is a valid answer when the evidence is thin.

ISSUE #{issue['number']}: {issue['title']}

{issue.get('body', '')}

DETERMINISTIC EVIDENCE:
{evidence}

SUSPECT SOURCE FILES:
{file_blocks}"""


def validate_hypothesis(verdict):
    """Check the model's parsed JSON against HYPOTHESIS_SCHEMA. Raises
    ValueError naming the problem; returns `verdict` unchanged when it
    conforms."""
    required = set(HYPOTHESIS_SCHEMA["required"])
    allowed = set(HYPOTHESIS_SCHEMA["properties"].keys())
    keys = set(verdict.keys())
    if keys != allowed:
        missing = required - keys
        extra = keys - allowed
        problems = []
        if missing:
            problems.append(f"missing {sorted(missing)}")
        if extra:
            problems.append(f"unexpected {sorted(extra)}")
        raise ValueError(f"hypothesis does not match schema: {'; '.join(problems)}")

    routing_enum = HYPOTHESIS_SCHEMA["properties"]["routing"]["enum"]
    if verdict["routing"] not in routing_enum:
        raise ValueError(f"routing {verdict['routing']!r} not in {routing_enum}")

    confidence = verdict["confidence"]
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValueError(f"confidence must be a number, got {confidence!r}")
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence {confidence} out of range [0.0, 1.0]")

    suspect_files = verdict["suspect_files"]
    if not isinstance(suspect_files, list) or not all(
            isinstance(f, str) for f in suspect_files):
        raise ValueError("suspect_files must be a list of strings")

    for field in ("hypothesis", "fix_direction"):
        if not isinstance(verdict[field], str) or not verdict[field].strip():
            raise ValueError(f"{field} must be a non-empty string")

    return verdict


def apply_refusal_guard(verdict):
    """The honest fallback: a refusal and a low-confidence hypothesis
    both get routed to a human instead of a confident-sounding
    automated call."""
    if verdict is None:
        return {
            "hypothesis": "the model declined to venture a hypothesis for "
                          "this issue",
            "routing": "human",
            "confidence": 0.0,
            "suspect_files": [],
            "fix_direction": "a human should review this issue directly",
        }
    if verdict["confidence"] < CONFIDENCE_FLOOR:
        return dict(verdict, routing="human")
    return verdict


def ask_claude(issue, service, dossier, files):
    client = anthropic.Anthropic()

    prompt = build_prompt(issue, service, dossier, files)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema",
                                  "schema": HYPOTHESIS_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        return apply_refusal_guard(None)
    text = next(b.text for b in response.content if b.type == "text")
    verdict = validate_hypothesis(json.loads(text))
    return apply_refusal_guard(verdict)


def render(issue, service, dossier, verdict):
    machine = {"v": 1, "kind": "llm-hypothesis", "issue": issue["number"],
               "model": MODEL, **verdict}
    files = "\n".join(f"- `{f}`" for f in verdict["suspect_files"]) or "- none"
    return f"""<!-- triage-llm:v1 {json.dumps(machine)} -->
### investigation (phase 2b, LLM hypothesis)

**hypothesis:** {verdict['hypothesis']}

**routing call:** `{verdict['routing']}` at {verdict['confidence']:.2f} \
(deterministic pass said: {dossier['revised']})

**suspect files**
{files}

**fix direction:** {verdict['fix_direction']}

model: `{MODEL}` · evidence from the phase-2a dossier above. \
want a fix attempt? comment `/handoff` to send this to the coding agent.
"""


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--event")
    src.add_argument("--issue")
    ap.add_argument("--service", default="unknown")
    ap.add_argument("--post", action="store_true")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — skipping the LLM hypothesis step. "
              "Layer 6 of the tutorial explains how to add it.", file=sys.stderr)
        return 0  # soft-skip: the pipeline still works without this step

    if args.event:
        event = json.loads(Path(args.event).read_text())
        i = event["issue"]
        issue = {"number": i["number"], "title": i["title"],
                 "body": i.get("body") or ""}
    else:
        issue = json.loads(Path(args.issue).read_text())

    dossier = build_dossier(issue, args.service, use_gh=bool(args.event))
    files = gather_files(dossier, args.service)
    verdict = ask_claude(issue, args.service, dossier, files)

    comment = render(issue, args.service, dossier, verdict)
    if args.post:
        subprocess.run(["gh", "issue", "comment", str(issue["number"]),
                        "--body", comment], check=True)
    else:
        print(comment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
