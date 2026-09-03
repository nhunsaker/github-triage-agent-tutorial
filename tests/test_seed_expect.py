"""Pin the seed-and-check predictions the chapter 4 doc prints.

These run the same live classify path as tools/seed_issues.py --expect,
against the answer-key rulebook, so the expected-results block in the
tutorial can't silently drift from what the tool actually predicts."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from seed_issues import pick  # noqa: E402
from triage.rulebook import classify, decide, load_rulebook  # noqa: E402

THETA = 0.70


def _predictions():
    issues = []
    for f in sorted((ROOT / "data" / "issues").glob("*.ndjson")):
        issues += [json.loads(l) for l in f.read_text().splitlines()]
    rulebook = load_rulebook("solutions/rulebook.yaml")
    out = {}
    for kind, issue in pick(issues):
        result, _ = classify(issue, rulebook)
        gate = decide(result, THETA)
        out[issue["title"]] = (result, gate)
    return out


def test_curated_slice_has_confident_and_gated():
    preds = _predictions()
    gates = [gate for _, gate in preds.values()]
    assert gates.count("act") == 7
    assert gates.count("investigate") == 3


def test_refund_ticket_prediction_is_stable():
    preds = _predictions()
    title = next(t for t in preds if "refund declined" in t)
    result, gate = preds[title]
    assert result["severity"][0] == "S2"
    assert result["routing"][0] == "external"
    assert result["service"][0] == "billing"
    assert gate == "act"


def test_webhook_ticket_always_gates():
    preds = _predictions()
    title = next(t for t in preds if "webhook signature" in t)
    result, gate = preds[title]
    assert gate == "investigate"
    assert result["service"][0] == "billing"
