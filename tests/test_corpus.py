"""The coupling test: every corpus signature must resolve to real code.

This is what keeps the tutorial honest. If an issue quotes an error, the
file and symbol the catalog points at must actually exist in services/,
or the "agent looks at the code" layers investigate fiction.
"""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_catalog():
    with open(ROOT / "data" / "error_catalog.yaml") as f:
        return yaml.safe_load(f)["catalog"]


def test_catalog_files_exist():
    missing = [e["id"] for e in load_catalog() if not (ROOT / e["file"]).exists()]
    assert not missing, f"catalog entries point at missing files: {missing}"


def test_catalog_symbols_exist_in_named_file():
    bad = []
    for e in load_catalog():
        path = ROOT / e["file"]
        if not path.exists():
            bad.append((e["id"], "file missing"))
            continue
        if e["symbol"] not in path.read_text():
            bad.append((e["id"], f"{e['symbol']} not in {e['file']}"))
    assert not bad, f"catalog symbols missing from code: {bad}"


def test_corpus_exists_and_covers_catalog():
    issues = []
    for f in (ROOT / "data" / "issues").glob("*.ndjson"):
        issues += [json.loads(l) for l in f.read_text().splitlines()]
    assert len(issues) > 700, f"corpus too small: {len(issues)}"

    catalog_ids = {e["id"] for e in load_catalog()}
    used = {i["ground_truth"]["catalog_id"] for i in issues}
    unused = catalog_ids - used
    assert not unused, f"catalog entries never used in corpus: {unused}"


def test_year2_only_drift():
    catalog = {e["id"]: e for e in load_catalog()}
    drift_ids = {cid for cid, e in catalog.items() if e.get("year2_only")}
    assert drift_ids, "catalog needs at least one year2_only drift entry"
    y1 = [json.loads(l) for l in (ROOT / "data" / "issues" / "year1.ndjson").read_text().splitlines()]
    leaked = [i["number"] for i in y1 if i["ground_truth"]["catalog_id"] in drift_ids]
    assert not leaked, f"drift entries leaked into year 1: {leaked}"


def test_quoted_messages_grep_to_catalog_templates():
    """Any issue body quoting a signature must match a catalog template
    (with {vars} treated as wildcards)."""
    catalog = load_catalog()
    patterns = []
    for e in catalog:
        pat = re.escape(e["message"])
        pat = re.sub(r"\\\{[a-z_]+\\\}", ".+?", pat)
        patterns.append((e["id"], re.compile(pat)))

    issues = []
    for f in (ROOT / "data" / "issues").glob("*.ndjson"):
        issues += [json.loads(l) for l in f.read_text().splitlines()]

    unmatched = 0
    quoted = 0
    for i in issues:
        m = re.search(r"```\n(.+?)\n```", i["body"], re.S)
        if not m:
            continue
        quoted += 1
        text = m.group(1)
        if not any(p.search(text) for _, p in patterns):
            unmatched += 1
    assert quoted > 400, f"too few issues quote signatures: {quoted}"
    assert unmatched == 0, f"{unmatched} quoted signatures match no catalog template"


def test_hardness_mix():
    issues = []
    for f in (ROOT / "data" / "issues").glob("*.ndjson"):
        issues += [json.loads(l) for l in f.read_text().splitlines()]
    n = len(issues)
    dupes = sum(1 for i in issues if i["ground_truth"]["duplicate_of"])
    clustered = sum(1 for i in issues if i["ground_truth"]["cluster_id"])
    human = sum(1 for i in issues if i["ground_truth"]["routing"] == "human")
    external = sum(1 for i in issues if i["ground_truth"]["routing"] == "external")
    assert 0.04 < dupes / n < 0.20, f"duplicate share off: {dupes/n:.2f}"
    assert clustered >= 60, f"incident clusters too small: {clustered}"
    assert human >= 20, "need a real abstain-to-human class"
    assert external >= 60, "need a real external class"
