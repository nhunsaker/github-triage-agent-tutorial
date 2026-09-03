"""Layer 5 gate. Runs against YOUR triage/investigate.py.

Fresh clone: every test here skips with "chapter 5 not started". As you
implement grep_code and catalog_prior the matching tests go green. All
green means the evidence-selection core is built and build_dossier can
cite real catalog entries and real code locations.
"""

import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

from tests.chapters.impl import load

investigate = load("investigate")

# BILL-001 is a real, checked-in catalog entry: a vendor 503 with a
# stable message template and a code site that actually raises it.
CATALOG = yaml.safe_load(
    (investigate.ROOT / "data" / "error_catalog.yaml").read_text())["catalog"]
BILL_001 = next(e for e in CATALOG if e["id"] == "BILL-001")
BILL_001_SIGNATURE = "PayFlow API unreachable: 503 from /v1/charges"


def run(fn, *args, **kwargs):
    """Call a starter function, skipping the test while it is stubbed."""
    try:
        return fn(*args, **kwargs)
    except NotImplementedError:
        pytest.skip("chapter 5 not started")


# ── catalog_prior ──────────────────────────────────────────────────────

def test_catalog_prior_matches_real_signature():
    entry = run(investigate.catalog_prior, BILL_001_SIGNATURE)
    assert entry["id"] == "BILL-001"
    assert entry["file"] == BILL_001["file"]
    assert entry["symbol"] == BILL_001["symbol"]
    assert entry["routing"] == "external"


def test_catalog_prior_selects_nothing_for_a_vague_body():
    assert run(investigate.catalog_prior, "the app feels slow today") is None


def test_catalog_prior_selects_nothing_with_no_signature():
    assert run(investigate.catalog_prior, None) is None
    assert run(investigate.catalog_prior, "") is None


def test_catalog_prior_first_match_wins(monkeypatch):
    # Two templates that both match the same filled-in text. Catalog
    # order should decide, not specificity: A-001 comes first and
    # claims the match even though A-002 also matches.
    catalog = {"catalog": [
        {"id": "A-001", "service": "x", "file": "services/x/a.py",
         "symbol": "AError", "message": "boom went {thing}",
         "severity": "S1", "routing": "internal"},
        {"id": "A-002", "service": "x", "file": "services/x/b.py",
         "symbol": "BError", "message": "boom went {thing} badly",
         "severity": "S2", "routing": "external"},
    ]}
    tmp = Path(tempfile.mkdtemp())
    (tmp / "data").mkdir()
    (tmp / "data" / "error_catalog.yaml").write_text(yaml.dump(catalog))
    monkeypatch.setattr(investigate, "ROOT", tmp)
    try:
        entry = run(investigate.catalog_prior, "boom went the pipes badly")
        assert entry["id"] == "A-001"
    finally:
        shutil.rmtree(tmp)


# ── grep_code ────────────────────────────────────────────────────────────

def test_grep_code_finds_the_real_raise_site():
    hits = run(investigate.grep_code, BILL_001_SIGNATURE)
    assert hits, "expected at least one hit for a real, checked-in signature"
    for h in hits:
        assert h["file"].startswith("services/")
        assert (investigate.ROOT / h["file"]).exists(), \
            "grep_code must cite a real path, never a hallucinated one"
    assert any(h["file"] == "services/billing/vendor_stub.py" for h in hits)


def test_grep_code_selects_nothing_for_a_vague_body():
    assert run(investigate.grep_code, "the app feels slow today, nothing "
                                      "specific to report") == []


def test_grep_code_selects_nothing_with_no_signature():
    assert run(investigate.grep_code, None) == []
    assert run(investigate.grep_code, "") == []


# ── build_dossier, the whole core wired together ─────────────────────────

def test_build_dossier_cites_catalog_and_code_for_a_known_signature():
    issue = {"number": 1, "title": "PayFlow errors",
             "body": f"seeing this a lot:\n\n```\n{BILL_001_SIGNATURE}\n```"}
    dossier = run(investigate.build_dossier, issue, "billing")
    assert dossier["prior"] == "BILL-001"
    assert dossier["code_hits"]
    assert any("BILL-001" in e for e in dossier["evidence_for"])
