"""Layer 8 gate. Runs against YOUR triage/flywheel.py.

Fresh clone: every test here skips with "chapter 8 not started". As you
implement each step the matching tests go green. All green means the
flywheel is built and your numbers should match the chapter's.
"""

import json

import pytest

from tests.chapters.impl import load

flywheel = load("flywheel")


def run(fn, *args, **kwargs):
    """Call a starter function, skipping the test while it is stubbed."""
    try:
        return fn(*args, **kwargs)
    except NotImplementedError:
        pytest.skip("chapter 8 not started")


# ── step 1: diff ─────────────────────────────────────────────────────

BOT = {
    "issue": 7,
    "decision": {
        "routing": {"value": "human", "confidence": 0.45},
        "severity": {"value": "S2", "confidence": 0.30},
        "service": {"value": "billing", "confidence": 0.80},
    },
}


def test_diff_flags_each_overridden_dimension():
    final = {"route:external", "sev:S1", "service:billing"}
    out = run(flywheel.diff, 7, BOT, final, body="PayFlow blew up")
    got = {(c["dimension"], c["bot"], c["human"]) for c in out}
    assert got == {("routing", "human", "external"), ("severity", "S2", "S1")}
    for c in out:
        assert c["issue"] == 7
        assert c["body_excerpt"] == "PayFlow blew up"


def test_diff_is_silent_on_agreement():
    final = {"route:human", "sev:S2", "service:billing"}
    assert run(flywheel.diff, 7, BOT, final) == []


def test_diff_ignores_missing_sides():
    # no service label at close, and a bot with no severity decision
    bot = {"issue": 9, "decision": {"routing": {"value": "internal",
                                                "confidence": 0.9}}}
    out = run(flywheel.diff, 9, bot, {"route:internal"})
    assert out == []


# ── step 2: accumulate ───────────────────────────────────────────────

def _corr(issue, dim, bot="human", human="external"):
    return {"issue": issue, "dimension": dim, "bot": bot, "human": human,
            "confidence": 0.4, "body_excerpt": ""}


def test_accumulate_appends_and_dedups(tmp_path, monkeypatch, capsys):
    labels = tmp_path / "labels.jsonl"
    # patch ROOT too: an impl may print the labels path relative to it
    monkeypatch.setattr(flywheel, "ROOT", tmp_path)
    monkeypatch.setattr(flywheel, "LABELS", labels)
    run(flywheel.accumulate, [_corr(1, "routing"), _corr(1, "severity")])
    run(flywheel.accumulate, [_corr(1, "routing"), _corr(2, "routing")])
    rows = [json.loads(l) for l in labels.read_text().splitlines()]
    assert len(rows) == 3
    assert {(r["issue"], r["dimension"]) for r in rows} == {
        (1, "routing"), (1, "severity"), (2, "routing")}


# ── step 3: measure ──────────────────────────────────────────────────

def test_measure_reports_confusion_pairs(tmp_path, monkeypatch, capsys):
    labels = tmp_path / "labels.jsonl"
    labels.write_text("\n".join(
        json.dumps(_corr(i, "routing")) for i in range(4)) + "\n")
    monkeypatch.setattr(flywheel, "LABELS", labels)
    run(flywheel.measure)
    out = capsys.readouterr().out
    assert "4 corrections" in out
    assert "routing" in out
    assert "human" in out and "external" in out


def test_measure_copes_with_no_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(flywheel, "LABELS", tmp_path / "missing.jsonl")
    run(flywheel.measure)
    assert "labels.jsonl" in capsys.readouterr().out


# ── step 4: suggest ──────────────────────────────────────────────────

def test_suggest_proposes_rule_from_bill004_cluster(tmp_path, monkeypatch,
                                                    capsys):
    labels = tmp_path / "labels.jsonl"
    body = "PayFlow v1 endpoint '/v1/charges' is deprecated, migrate to v2"
    rows = [dict(_corr(100 + i, "routing", bot="human", human="external"),
                 body_excerpt=body) for i in range(6)]
    labels.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(flywheel, "LABELS", labels)
    run(flywheel.suggest)
    out = capsys.readouterr().out
    assert "fly-bill-004" in out
    assert "service: billing" in out
    assert "severity: S1" in out
    assert "routing: external" in out


def test_suggest_needs_five(tmp_path, monkeypatch, capsys):
    labels = tmp_path / "labels.jsonl"
    body = "PayFlow v1 endpoint '/v1/charges' is deprecated, migrate to v2"
    rows = [dict(_corr(100 + i, "routing"), body_excerpt=body)
            for i in range(3)]
    labels.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(flywheel, "LABELS", labels)
    run(flywheel.suggest)
    assert "fly-" not in capsys.readouterr().out


# ── the whole loop, chapter numbers ──────────────────────────────────

def test_capture_simulate_matches_chapter_count():
    out = run(flywheel.capture_simulate, 2, "solutions/rulebook.yaml")
    assert len(out) == 265
