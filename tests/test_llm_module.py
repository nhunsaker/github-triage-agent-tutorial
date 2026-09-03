"""Offline checks for the LLM hypothesis module. No API calls here,
the live behavior is exercised in layer 6 and by the Actions run.

These run against solutions/ on purpose. They guard the repo's answer
key, so they stay green while your triage/ copies are still stubs. The
gates that watch YOUR code live in tests/chapters/."""

import json

from solutions.investigate import build_dossier
from solutions.investigate_llm import (HYPOTHESIS_SCHEMA, gather_files, render)


FAKE_ISSUE = {
    "number": 999,
    "title": "webhook signature failures from PayFlow",
    "body": "since morning:\n\n```\nwebhook signature verification failed "
            "for delivery whd_123456\n```\n\nworkaround: none found yet",
}


def test_schema_is_strict():
    assert HYPOTHESIS_SCHEMA["additionalProperties"] is False
    assert set(HYPOTHESIS_SCHEMA["required"]) == set(
        HYPOTHESIS_SCHEMA["properties"].keys())


def test_gather_files_finds_real_code():
    dossier = build_dossier(FAKE_ISSUE, "billing", use_gh=False)
    files = gather_files(dossier, "billing")
    assert files, "expected at least the raise site or catalog prior file"
    for path, text in files:
        assert path.startswith("services/")
        assert len(text) <= 6000


def test_render_produces_machine_marker():
    dossier = build_dossier(FAKE_ISSUE, "billing", use_gh=False)
    verdict = {
        "hypothesis": "vendor rotated webhook keys",
        "routing": "external",
        "confidence": 0.7,
        "suspect_files": ["services/billing/webhooks.py"],
        "fix_direction": "re-sync webhook secrets with the vendor",
    }
    comment = render(FAKE_ISSUE, "billing", dossier, verdict)
    assert "<!-- triage-llm:v1 " in comment
    marker = comment.split("<!-- triage-llm:v1 ")[1].split(" -->")[0]
    parsed = json.loads(marker)
    assert parsed["routing"] == "external"
    assert parsed["issue"] == 999
