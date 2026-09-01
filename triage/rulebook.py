"""Phase 1: the deterministic classify + route pass.

One pass over an issue emits the FULL hypothesis: service, severity,
routing, each with its own confidence. Rules live in rulebook.yaml
(data, not code) so tuning is an edit + re-eval, not a deploy.

No LLM anywhere in this file. That is the point of phase 1.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

DIMENSIONS = ("service", "severity", "routing")
DEFAULTS = {
    "service": ("unknown", 0.20),
    "severity": ("S2", 0.30),
    "routing": ("human", 0.30),
}


def load_rulebook(path=None):
    path = Path(path) if path else ROOT / "triage" / "rulebook.yaml"
    with open(path) as f:
        book = yaml.safe_load(f)
    for rule in book["rules"]:
        rule["_pattern"] = re.compile(rule["match"], re.I | re.S)
    return book


def classify(issue, rulebook, recent_issues=None):
    """Return {dimension: (value, confidence)} plus the fired rule ids.

    recent_issues: other issues from the last 48h, used by the
    corroboration rule — an external call at S0 needs fleet-wide
    evidence, one report alone is downgraded to human.
    """
    text = issue["title"] + "\n" + issue["body"]
    result = {dim: DEFAULTS[dim] for dim in DIMENSIONS}
    fired = []

    for rule in rulebook["rules"]:
        if not rule["_pattern"].search(text):
            continue
        fired.append(rule["id"])
        for dim in DIMENSIONS:
            if dim in rule:
                value, conf = rule[dim], float(rule.get("confidence", 0.5))
                if conf > result[dim][1]:
                    result[dim] = (value, conf)

    # ── corroboration rule ────────────────────────────────────────────
    # an S0 external call is a fleet-wide-outage claim, and a fleet-wide
    # claim requires fleet-wide evidence: N similar reports inside the
    # window. A single 503 is more likely a local blip. S1 external
    # (a declined refund, a deprecation notice) stands on its own
    # signature — it is verifiable without corroboration.
    corr = rulebook.get("corroboration", {})
    if corr and result["routing"][0] == "external":
        sev = result["severity"][0]
        if sev == "S0":
            n_similar = _count_similar(issue, recent_issues or [], rulebook)
            if n_similar < int(corr.get("min_reports", 3)):
                result["routing"] = ("human", min(result["routing"][1], 0.45))
                fired.append("corroboration-downgrade")
            else:
                # corroborated fleet-wide event: confidence goes UP
                result["routing"] = ("external", min(0.95, result["routing"][1] + 0.10))
                fired.append("corroboration-confirm")

    return result, fired


def _count_similar(issue, recent_issues, rulebook):
    """How many recent issues fired the same external-looking pattern."""
    ext_rules = [r for r in rulebook["rules"] if r.get("routing") == "external"]
    mine = {r["id"] for r in ext_rules
            if r["_pattern"].search(issue["title"] + "\n" + issue["body"])}
    if not mine:
        return 0
    count = 0
    for other in recent_issues:
        text = other["title"] + "\n" + other["body"]
        if any(r["_pattern"].search(text) for r in ext_rules if r["id"] in mine):
            count += 1
    return count


def recent_window(issue, all_issues, hours=48):
    """Issues created in the `hours` before this one (corpus replay helper)."""
    t = datetime.fromisoformat(issue["created_at"].rstrip("Z"))
    lo = t - timedelta(hours=hours)
    out = []
    for other in all_issues:
        if other["number"] == issue["number"]:
            continue
        ot = datetime.fromisoformat(other["created_at"].rstrip("Z"))
        if lo <= ot <= t:
            out.append(other)
    return out


def decide(result, theta=0.70):
    """The gate. Above theta on routing → act. Below → phase 2."""
    routing_conf = result["routing"][1]
    return "act" if routing_conf >= theta else "investigate"
