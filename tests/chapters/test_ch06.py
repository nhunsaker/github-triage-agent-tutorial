"""Layer 6 gate. Runs against YOUR triage/investigate_llm.py.

Fresh clone: every test here skips with "chapter 6 not started". As you
implement build_prompt, validate_hypothesis, and apply_refusal_guard the
matching tests go green. No ANTHROPIC_API_KEY and no network call
anywhere in this file, everything runs against a fixture dossier built
inline, never the live model and never chapter 5's build_dossier.
"""

import pytest

from tests.chapters.impl import load

investigate_llm = load("investigate_llm")


def run(fn, *args, **kwargs):
    """Call a starter function, skipping the test while it is stubbed."""
    try:
        return fn(*args, **kwargs)
    except NotImplementedError:
        pytest.skip("chapter 6 not started")


# A fixture issue and dossier, mirroring the shape
# triage.investigate.build_dossier returns, built inline so this gate
# never depends on chapter 5's stub.

ISSUE = {
    "number": 999,
    "title": "webhook signature failures from PayFlow",
    "body": "since morning:\n\n```\nwebhook signature verification failed "
            "for delivery whd_123456\n```\n\nworkaround: none found yet",
}

DOSSIER = {
    "prior": "BILL-002",
    "signature": "webhook signature verification failed for delivery whd_123456",
    "code_hits": [{"file": "services/billing/webhooks.py", "line": "42",
                   "code": "verify_webhook_signature(payload, sig)"}],
    "commits": ["a1b2c3d bump webhook retry timeout"],
    "fleet": [
        {"number": 10, "title": "webhook sig failing", "createdAt": "2026-01-01"},
        {"number": 11, "title": "webhook sig failing again", "createdAt": "2026-01-02"},
        {"number": 12, "title": "more webhook failures", "createdAt": "2026-01-03"},
    ],
    "evidence_for": [
        "signature resolves to code: services/billing/webhooks.py:42",
        "fleet-wide: 3 similar reports found",
        "signature matches catalog BILL-002 (typical routing: external)",
    ],
    "evidence_against": [],
    "hypothesis": "vendor-side fault (BILL-002): the code match is the raise "
                  "site in our billing client, not the cause",
    "revised": "external, corroborated",
}

FILES = [("services/billing/webhooks.py",
          "def verify_webhook_signature(payload, sig):\n    ...\n")]


# ── step 1: build_prompt ─────────────────────────────────────────────

def test_build_prompt_includes_dossier_evidence_and_issue_text():
    prompt = run(investigate_llm.build_prompt, ISSUE, "billing", DOSSIER, FILES)
    assert str(ISSUE["number"]) in prompt
    assert ISSUE["title"] in prompt
    assert ISSUE["body"] in prompt
    assert DOSSIER["signature"] in prompt
    assert DOSSIER["revised"] in prompt
    assert FILES[0][0] in prompt
    assert FILES[0][1] in prompt


def test_build_prompt_falls_back_when_no_files_matched():
    prompt = run(investigate_llm.build_prompt, ISSUE, "billing", DOSSIER, [])
    assert "no source files matched" in prompt


# ── step 2: validate_hypothesis ──────────────────────────────────────

GOOD_VERDICT = {
    "hypothesis": "vendor rotated webhook keys",
    "routing": "external",
    "confidence": 0.7,
    "suspect_files": ["services/billing/webhooks.py"],
    "fix_direction": "re-sync webhook secrets with the vendor",
}


def test_validate_hypothesis_accepts_conforming_object():
    out = run(investigate_llm.validate_hypothesis, dict(GOOD_VERDICT))
    assert out == GOOD_VERDICT


def test_validate_hypothesis_rejects_missing_key():
    bad = {k: v for k, v in GOOD_VERDICT.items() if k != "confidence"}
    try:
        result = run(investigate_llm.validate_hypothesis, bad)
    except ValueError:
        return
    pytest.fail(f"expected ValueError, got {result!r}")


def test_validate_hypothesis_rejects_extra_key():
    bad = dict(GOOD_VERDICT, extra_field="nope")
    try:
        result = run(investigate_llm.validate_hypothesis, bad)
    except ValueError:
        return
    pytest.fail(f"expected ValueError, got {result!r}")


def test_validate_hypothesis_rejects_bad_routing_enum():
    bad = dict(GOOD_VERDICT, routing="vendor")
    try:
        result = run(investigate_llm.validate_hypothesis, bad)
    except ValueError:
        return
    pytest.fail(f"expected ValueError, got {result!r}")


def test_validate_hypothesis_rejects_out_of_range_confidence():
    bad = dict(GOOD_VERDICT, confidence=1.5)
    try:
        result = run(investigate_llm.validate_hypothesis, bad)
    except ValueError:
        return
    pytest.fail(f"expected ValueError, got {result!r}")


# ── step 3: apply_refusal_guard ──────────────────────────────────────

def test_refusal_guard_routes_none_to_human():
    out = run(investigate_llm.apply_refusal_guard, None)
    assert out["routing"] == "human"
    assert out["confidence"] == 0.0
    assert out["suspect_files"] == []


def test_refusal_guard_routes_vague_report_to_human_at_reported_confidence():
    # the repo's live-verified behavior: a vague report earns the model
    # an honest, thin 0.25. The guard's job is making sure a call that
    # thin does not drive an internal or external routing decision on
    # its own, while leaving the rest of the model's answer alone.
    vague = dict(GOOD_VERDICT, routing="external", confidence=0.25)
    out = run(investigate_llm.apply_refusal_guard, vague)
    assert out["routing"] == "human"
    assert out["confidence"] == 0.25
    assert out["hypothesis"] == vague["hypothesis"]
    assert out["fix_direction"] == vague["fix_direction"]


def test_refusal_guard_leaves_confident_verdicts_alone():
    confident = dict(GOOD_VERDICT, routing="external", confidence=0.7)
    out = run(investigate_llm.apply_refusal_guard, confident)
    assert out == confident
