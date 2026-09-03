"""Layer 4 gate. Runs against YOUR triage/run.py.

Fresh clone: every test here skips with "chapter 4 not started". As you
implement build_labels and build_comment the matching tests go green.
All green means the wiring is done and your dry-run output should
match the chapter's.
"""

import json
import re

import pytest

from tests.chapters.impl import load

run = load("run")
from triage.rulebook import classify, decide, load_rulebook

MARKER = re.compile(r"<!-- triage:v1 (\{.*?\}) -->", re.S)


def run_step(fn, *args, **kwargs):
    """Call a starter function, skipping the test while it is stubbed."""
    try:
        return fn(*args, **kwargs)
    except NotImplementedError:
        pytest.skip("chapter 4 not started")


RESULT = {
    "service": ("billing", 0.90),
    "severity": ("S1", 0.90),
    "routing": ("external", 0.90),
}


# ── step 1: build_labels ─────────────────────────────────────────────

def test_build_labels_full_set_on_act():
    labels = run_step(run.build_labels, RESULT, "act")
    assert set(labels) == {"sev:S1", "route:external", "service:billing",
                            "triage:confident"}


def test_build_labels_investigating_gate():
    labels = run_step(run.build_labels, RESULT, "investigate")
    assert "triage:investigating" in labels
    assert "triage:confident" not in labels


def test_build_labels_skips_unknown_service():
    result = dict(RESULT, service=("unknown", 0.20))
    labels = run_step(run.build_labels, result, "act")
    assert not any(l.startswith("service:") for l in labels)


def test_build_labels_gate_at_theta_boundary():
    # decide() itself is chapter 3's engine, not stubbed: this pins
    # build_labels to the exact confidence decide() already gates on.
    at_theta = dict(RESULT, routing=("external", 0.70))
    below_theta = dict(RESULT, routing=("external", 0.6999))
    assert decide(at_theta, 0.70) == "act"
    assert decide(below_theta, 0.70) == "investigate"
    assert "triage:confident" in run_step(
        run.build_labels, at_theta, decide(at_theta, 0.70))
    assert "triage:investigating" in run_step(
        run.build_labels, below_theta, decide(below_theta, 0.70))


# ── step 2: build_comment ────────────────────────────────────────────

ISSUE = {"number": 9, "title": "payment confirmations stopped arriving"}


def test_build_comment_marker_round_trips():
    comment = run_step(run.build_comment, ISSUE, RESULT,
                        ["sig-webhook-verification"], "act")
    m = MARKER.search(comment)
    assert m, "no <!-- triage:v1 {...} --> marker found"
    machine = json.loads(m.group(1))
    assert machine["v"] == 1
    assert machine["issue"] == 9
    assert machine["gate"] == "act"
    assert machine["fired"] == ["sig-webhook-verification"]
    assert machine["decision"]["severity"] == {"value": "S1", "confidence": 0.90}
    assert machine["decision"]["service"] == {"value": "billing", "confidence": 0.90}
    assert machine["decision"]["routing"] == {"value": "external", "confidence": 0.90}


def test_build_comment_verdict_text_matches_gate():
    acting = run_step(run.build_comment, ISSUE, RESULT, [], "act")
    investigating = run_step(run.build_comment, ISSUE, RESULT, [], "investigate")
    assert "acting on this triage" in acting
    assert "confidence below threshold" in investigating
    assert "/investigate" in acting and "/investigate" in investigating


def test_build_comment_no_rules_fired_says_defaults():
    comment = run_step(run.build_comment, ISSUE, RESULT, [], "act")
    assert "none (defaults)" in comment


# ── the whole path, chapter numbers ──────────────────────────────────

def test_dry_run_matches_chapter_labels_for_issue_3():
    # the exact issue and rulebook the chapter's first dry-run walks
    # through: `python -m triage.run --issue ... --dry-run --rulebook
    # solutions/rulebook.yaml` for issue #3.
    issue = json.loads(
        (run.ROOT / "data" / "issues" / "year1.ndjson").read_text()
        .splitlines()[2])
    assert issue["number"] == 3
    rulebook = load_rulebook("solutions/rulebook.yaml")
    result, fired = classify(issue, rulebook)
    gate = decide(result, run.THETA)
    labels = run_step(run.build_labels, result, gate)
    assert set(labels) == {"sev:S1", "route:internal", "service:api",
                            "triage:confident"}
    assert gate == "act"
    assert fired == ["sig-oversell"]
