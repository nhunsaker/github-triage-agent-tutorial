"""Phase 2a: the deterministic investigation. Zero LLM.

Evidence first, then hand off — the hypothetico-deductive step done
with grep and git. Builds a dossier:

  1. code evidence   — grep services/ for the quoted error signature
  2. change evidence — recent commits touching the suspect service
  3. fleet evidence  — other open/recent issues sharing the signature
  4. verdict         — hypothesis, evidence for/against, revised call

Always ends with the offer: "investigate further?" — even when
confident. (The always-offer rule.)

Local:  python -m triage.investigate --issue path.json --service billing
Action: python -m triage.investigate --event "$GITHUB_EVENT_PATH" \
            --service billing --post
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def catalog_prior(signature):
    """Match the signature back to the error catalog. The catalog knows
    each failure's typical routing — a grep hit on payflow.py is the
    RAISE SITE of a vendor error, not evidence the fault is ours."""
    if not signature:
        return None
    with open(ROOT / "data" / "error_catalog.yaml") as f:
        entries = yaml.safe_load(f)["catalog"]
    for e in entries:
        pat = re.sub(r"\\\{[a-z_]+\\\}", ".+?", re.escape(e["message"]))
        if re.search(pat, signature):
            return e
    return None


def extract_signature(body):
    """The quoted error block, if the reporter pasted one."""
    m = re.search(r"```\n(.+?)\n```", body, re.S)
    if m:
        return m.group(1).strip().splitlines()[0]
    # fall back to anything that looks like an error line
    m = re.search(r"\"([^\"]{20,120})\"", body)
    return m.group(1) if m else None


def grep_code(signature):
    """Where in services/ does this error text live? Stable fragments only."""
    if not signature:
        return []
    # strip the variable parts: numbers, ids, quoted values
    fragment = re.sub(r"/\S+|\b\d+\b|'[^']*'|\"[^\"]*\"|\b\w+_\w{4,}\b",
                      " ", signature)
    # only stable alphabetic words survive: filled-in values (ids, paths,
    # numbers) exist in the issue but never in the source templates
    words = [w for w in re.findall(r"[A-Za-z-]{4,}", fragment)][:4]
    if not words:
        return []
    pattern = ".*".join(re.escape(w) for w in words)
    try:
        out = subprocess.run(
            ["grep", "-rn", "-E", pattern, str(ROOT / "services")],
            capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    hits = []
    for line in out.stdout.splitlines()[:8]:
        path, _, rest = line.partition(":")
        lineno, _, code = rest.partition(":")
        hits.append({"file": str(Path(path).relative_to(ROOT)),
                     "line": lineno, "code": code.strip()[:100]})
    return hits


def recent_commits(service):
    """What changed lately in the suspect service dir?"""
    if not service or service == "unknown":
        return []
    try:
        out = subprocess.run(
            ["git", "log", "--oneline", "-8", "--", f"services/{service}/"],
            capture_output=True, text=True, cwd=ROOT, timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    return out.stdout.splitlines()


def fleet_check(signature, use_gh):
    """Other recent issues with the same signature = corroboration."""
    if not signature:
        return []
    fragment = " ".join(signature.split()[:4])
    if use_gh:
        try:
            out = subprocess.run(
                ["gh", "issue", "list", "--state", "all", "--limit", "30",
                 "--search", fragment, "--json", "number,title,createdAt"],
                capture_output=True, text=True, timeout=30)
            return json.loads(out.stdout or "[]")
        except (subprocess.TimeoutExpired, FileNotFoundError,
                json.JSONDecodeError):
            return []
    # local mode: search the corpus instead
    matches = []
    for f in (ROOT / "data" / "issues").glob("*.ndjson"):
        for line in f.read_text().splitlines():
            issue = json.loads(line)
            if fragment.lower() in issue["body"].lower():
                matches.append({"number": issue["number"],
                                "title": issue["title"],
                                "createdAt": issue["created_at"]})
    return matches[:30]


def build_dossier(issue, service, use_gh=False):
    signature = extract_signature(issue.get("body", ""))
    code_hits = grep_code(signature)
    commits = recent_commits(service)
    fleet = fleet_check(signature, use_gh)

    # the verdict logic is deliberately simple and legible
    evidence_for, evidence_against = [], []
    if code_hits:
        evidence_for.append(
            f"signature resolves to code: {code_hits[0]['file']}:{code_hits[0]['line']}")
    else:
        evidence_against.append("signature does not grep to any service — "
                                "possibly external or misreported")
    if len(fleet) >= 3:
        evidence_for.append(f"fleet-wide: {len(fleet)} similar reports found")
    elif fleet:
        evidence_against.append(
            f"only {len(fleet)} similar report(s) — not corroborated")
    if commits:
        evidence_for.append(
            f"recent changes in services/{service}/ ({len(commits)} commits)")

    prior = catalog_prior(signature)
    if prior:
        evidence_for.append(
            f"signature matches catalog {prior['id']} "
            f"(typical routing: {prior['routing']})")

    if prior and prior["routing"] == "external" and len(fleet) >= 3:
        hypothesis = (f"vendor-side fault ({prior['id']}): the code match is "
                      f"the raise site in our {prior['service']} client, not "
                      "the cause")
        revised = "external, corroborated"
    elif code_hits and len(fleet) >= 3:
        hypothesis = (f"regression or systemic fault in services/{service}/ "
                      f"near {code_hits[0]['file']}")
        revised = "internal, corroborated"
    elif code_hits:
        hypothesis = f"isolated fault near {code_hits[0]['file']}"
        revised = "internal, uncorroborated — verify before acting"
    elif len(fleet) >= 3:
        hypothesis = "external or infrastructure-level: many reports, no code match"
        revised = "external, corroborated"
    else:
        hypothesis = "insufficient evidence"
        revised = "human review needed"

    return {
        "prior": prior["id"] if prior else None,
        "signature": signature,
        "code_hits": code_hits,
        "commits": commits,
        "fleet": fleet,
        "evidence_for": evidence_for,
        "evidence_against": evidence_against,
        "hypothesis": hypothesis,
        "revised": revised,
    }


def render(issue, service, d):
    code = "\n".join(f"- `{h['file']}:{h['line']}` — `{h['code']}`"
                     for h in d["code_hits"]) or "- no matches in services/"
    commits = "\n".join(f"- `{c}`" for c in d["commits"][:5]) or "- none found"
    fleet = (f"- {len(d['fleet'])} similar report(s): " +
             ", ".join(f"#{m['number']}" for m in d["fleet"][:6])
             if d["fleet"] else "- none found")
    ef = "\n".join(f"- {e}" for e in d["evidence_for"]) or "- none"
    ea = "\n".join(f"- {e}" for e in d["evidence_against"]) or "- none"
    machine = {"v": 1, "kind": "dossier", "issue": issue["number"],
               "hypothesis": d["hypothesis"], "revised": d["revised"],
               "n_code_hits": len(d["code_hits"]), "n_fleet": len(d["fleet"])}
    return f"""<!-- triage-dossier:v1 {json.dumps(machine)} -->
### investigation (phase 2a)

**signature:** `{d['signature'] or 'none quoted'}`

**code evidence** (grep services/)
{code}

**change evidence** (recent commits, services/{service}/)
{commits}

**fleet evidence** (similar reports)
{fleet}

**evidence for**
{ef}

**evidence against**
{ea}

**hypothesis:** {d['hypothesis']}
**revised call:** {d['revised']}

want me to go deeper — assign this to the coding agent for a fix attempt? \
comment `/handoff` on this issue.
"""


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--event")
    src.add_argument("--issue")
    ap.add_argument("--service", default="unknown")
    ap.add_argument("--post", action="store_true",
                    help="post the dossier as a comment via gh")
    args = ap.parse_args()

    if args.event:
        event = json.loads(Path(args.event).read_text())
        i = event["issue"]
        issue = {"number": i["number"], "title": i["title"],
                 "body": i.get("body") or ""}
    else:
        issue = json.loads(Path(args.issue).read_text())

    dossier = build_dossier(issue, args.service, use_gh=bool(args.event))
    comment = render(issue, args.service, dossier)

    if args.post:
        subprocess.run(["gh", "issue", "comment", str(issue["number"]),
                        "--body", comment], check=True)
    else:
        print(comment)


if __name__ == "__main__":
    main()
