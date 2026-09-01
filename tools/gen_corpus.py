#!/usr/bin/env python3
"""Generate the 2-year Jane's Jeans issue corpus from the error catalog.

Seeded and reproducible: same seed, same corpus. Every issue's error
signature comes from data/error_catalog.yaml, so it greps to real code
(enforced by tests/test_corpus.py).

Hardness knobs are deliberate, see PLAN.md "hard by design":
  ~15% vague reports, ~10% cross-service ambiguous, 3 vendor incident
  clusters, ~10% duplicates, year-2 drift (BILL-004 never in year 1).

Usage:
  python tools/gen_corpus.py            # writes data/issues/ + data/resolutions/
  python tools/gen_corpus.py --seed 7   # different but still reproducible world
"""

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "error_catalog.yaml"

START = datetime(2024, 9, 1, 8, 0, 0)   # month 1 of 24
MONTHS = 24
YEAR2_START_MONTH = 12                   # months >= this are "year 2"

REPORTERS = [
    "jane", "marco-ops", "priya.store", "warehouse-sam", "cs-tina",
    "devon-dev", "aisha-support", "kev-onsite", "lupe-returns", "nightshift-bot",
]

# vague report templates: thin signal, no signature quoted
VAGUE_TEMPLATES = [
    ("checkout is broken, customers cant buy",
     "several customers called saying they cant complete a purchase. nothing in the admin looks wrong to me"),
    ("site slow today",
     "everything feels sluggish since this morning, is something going on"),
    ("numbers look wrong on the dashboard",
     "the order count doesnt match what i see in the spreadsheet, not sure which is right"),
    ("customer says they were charged twice",
     "order came through once but the customer forwarded two receipts"),
    ("returns page acting weird",
     "tried to process a return and it just spun, worked after a refresh"),
    ("app broken help",
     "cant do anything right now, who do i call"),
]

# cross-service ambiguous: symptom text points at the WRONG service on purpose.
# (catalog_id = ground truth, surface = where it looks like it lives)
AMBIGUOUS = [
    # frozen dashboard, real fault = qr consumer lag
    ("QR-001", "dashboard",
     "order counts frozen since {time}",
     "the ops dashboard hasnt updated in over an hour. banner says 'orders feed stale for {minutes}m, showing cached data'. is the dashboard broken?"),
    # frozen dashboard, real fault = api publish failure
    ("API-004", "dashboard",
     "dashboard not showing new orders",
     "new orders exist in emails but never appear on the dashboard. logs mention \"failed to publish 'order_placed' to stream 'orders'\" if that helps"),
    # decode-ish confusion: schema error surfacing as order weirdness
    ("QR-004", "api",
     "orders coming through with missing fields",
     "some orders show up half-empty. saw \"event schema mismatch on 'order_placed': expected v2 got v1\" in the worker log"),
    # webhook: looks external, sometimes internal
    ("BILL-002", "billing",
     "payment confirmations stopped arriving",
     "orders sit unpaid even though customers paid. billing log repeats \"webhook signature verification failed for delivery {delivery_id}\""),
]

RESOLUTION_NOTES = {
    "internal": [
        "fixed in {service}: {symbol} path corrected, deployed",
        "root cause in {service}/{file_short}, patched and backfilled",
        "config fix in {service}, no code change needed",
    ],
    "external": [
        "vendor issue confirmed on PayFlow status page, recovered on their side",
        "PayFlow rotated webhook keys without notice, re-synced secrets",
        "tracked to vendor-side change, opened ticket with PayFlow, workaround applied",
    ],
    "human": [
        "could not reproduce, single account, closed after customer follow-up",
        "user error / training issue, documented in ops runbook",
        "insufficient information, reporter never followed up",
    ],
}


def load_catalog():
    with open(CATALOG) as f:
        entries = yaml.safe_load(f)["catalog"]
    return {e["id"]: e for e in entries}


def fill(template, rng):
    """Fill {vars} in catalog message templates with plausible values."""
    subs = {
        "seconds": rng.choice([90, 240, 600, 1800]),
        "stream": "orders",
        "attempts": 3,
        "event_id": f"evt_{rng.randrange(10**6):06d}",
        "count": rng.choice([120, 340, 875, 2100]),
        "event_type": rng.choice(["order_placed", "stock_updated", "return_started"]),
        "expected": 2, "got": 1,
        "sku": f"JJ-{rng.choice(['SLIM','BOOT','WIDE','FLARE'])}-{rng.randrange(20,44):02d}",
        "reserved": rng.randrange(1, 5), "on_hand": 0,
        "reason": rng.choice(["missing shipping address", "invalid sku", "empty cart", "bad zip code"]),
        "cart_id": f"cart_{rng.randrange(10**5):05d}",
        "return_id": f"ret_{rng.randrange(10**4):04d}",
        "state": rng.choice(["received", "refunded", "cancelled"]),
        "action": rng.choice(["refund", "restock", "cancel"]),
        "minutes": rng.choice([12, 35, 70, 160]),
        "filters": "status=refunded+state=open",
        "endpoint": rng.choice(["/v1/charges", "/v1/refunds", "/v1/tokens"]),
        "delivery_id": f"whd_{rng.randrange(10**6):06d}",
        "order_id": f"ord_{rng.randrange(10**5):05d}",
        "code": rng.choice(["R102", "R217", "R400"]),
        "time": "2pm",
    }
    out = template
    for k, v in subs.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def body_for(entry, rng, quoted_msg):
    """A plausible issue body quoting the real signature."""
    openers = [
        "seeing this in the {service} logs since {when}:",
        "hit this while processing {what}:",
        "this started after the {when} deploy:",
        "repeated {n} times in the last hour:",
    ]
    opener = rng.choice(openers).format(
        service=entry["service"],
        when=rng.choice(["morning", "friday", "yesterday", "weekend"]),
        what=rng.choice(["a big order", "returns", "the nightly batch", "a flash sale"]),
        n=rng.choice([4, 11, 27]),
    )
    closer = rng.choice([
        "anyone know what this means",
        "impact: {sev_hint}",
        "can someone take a look",
        "workaround: none found yet",
        "workaround: retrying manually for now",
    ]).format(sev_hint=rng.choice([
        "customers blocked", "ops only", "cosmetic but noisy", "money involved",
    ]))
    return f"{opener}\n\n```\n{quoted_msg}\n```\n\n{closer}"


def title_for(entry, rng):
    titles = {
        "QR-001": "worker falling behind on order events",
        "QR-002": "events stuck, same one retried over and over",
        "QR-003": "dead letter queue filling up",
        "QR-004": "schema errors from the order stream",
        "QR-005": "duplicate order events in the log",
        "API-001": "sold items we dont have in stock",
        "API-002": "order rejected but reason seems wrong",
        "API-003": "500 on checkout",
        "API-004": "orders not reaching the queue",
        "API-005": "return stuck in wrong state",
        "DASH-001": "dashboard showing stale data banner",
        "DASH-002": "stock chart crashes the page",
        "DASH-003": "filters break the orders view",
        "BILL-001": "payments failing, PayFlow unreachable",
        "BILL-002": "webhook signature failures from PayFlow",
        "BILL-003": "refund declined by vendor",
        "BILL-004": "PayFlow deprecation warnings on charges",
        "BILL-005": "duplicate charge blocked, customer confused",
    }
    t = titles[entry["id"]]
    if rng.random() < 0.3:
        t = t + " " + rng.choice(["again", "(urgent)", "since this morning", "??"])
    return t


def gen(seed):
    rng = random.Random(seed)
    catalog = load_catalog()
    issues, resolutions = [], []
    number = 0

    def emit(created, catalog_id=None, vague=None, ambiguous=None,
             duplicate_of=None, cluster_id=None):
        nonlocal number
        number += 1
        gt_routing, gt_service, gt_severity = None, None, None
        if catalog_id:
            e = catalog[catalog_id]
            gt_routing, gt_service, gt_severity = e["routing"], e["service"], e["severity"]

        if vague:
            title, body = vague
            # vague reports still have ground truth: pick a plausible cause
            e = catalog[rng.choice(["API-003", "DASH-001", "BILL-005", "QR-001", "API-002"])]
            catalog_id = e["id"]
            gt_routing, gt_service, gt_severity = e["routing"], e["service"], e["severity"]
            # ~1/3 of vague reports resolve as human (cant repro / user error)
            if rng.random() < 0.33:
                gt_routing = "human"
        elif ambiguous:
            cid, surface, title_t, body_t = ambiguous
            e = catalog[cid]
            catalog_id = cid
            gt_routing, gt_service, gt_severity = e["routing"], e["service"], e["severity"]
            title = fill(title_t, rng)
            body = fill(body_t, rng)
        else:
            e = catalog[catalog_id]
            msg = fill(e["message"], rng)
            title = title_for(e, rng)
            body = body_for(e, rng, msg)

        # ── resolution noise: the world is not deterministic ──────────
        # BILL-002 genuinely splits ~60/40 external/internal (sometimes
        # the vendor rotated keys, sometimes we misconfigured).
        if catalog_id == "BILL-002" and rng.random() < 0.40:
            gt_routing = "internal"
        # a slice of internal reports die as could-not-reproduce
        elif gt_routing == "internal" and rng.random() < 0.05:
            gt_routing = "human"

        res_id = f"res_{number:04d}"
        issue = {
            "number": number,
            "title": title,
            "body": body,
            "created_at": created.isoformat() + "Z",
            "reporter": rng.choice(REPORTERS),
            "labels": [],
            # ── ground truth: stripped by seed_issues.py, never posted live ──
            "ground_truth": {
                "catalog_id": catalog_id,
                "service": gt_service,
                "severity": gt_severity,
                "routing": gt_routing,
                "resolution_id": res_id,
                "duplicate_of": duplicate_of,
                "cluster_id": cluster_id,
            },
        }
        issues.append(issue)

        note_t = rng.choice(RESOLUTION_NOTES[gt_routing])
        e = catalog[catalog_id]
        resolutions.append({
            "resolution_id": res_id,
            "issue_number": number,
            "service": gt_service,
            "routing": gt_routing,
            "root_cause": e["symbol"] if gt_routing != "human" else "unconfirmed",
            "fix": note_t.format(
                service=gt_service,
                symbol=e["symbol"],
                file_short=Path(e["file"]).name,
            ),
            "no_pr": gt_routing != "internal" or rng.random() < 0.15,
            "external": gt_routing == "external",
            "resolved_at": (created + timedelta(hours=rng.randrange(2, 96))).isoformat() + "Z",
        })
        return issue

    # ── baseline monthly volume from catalog weights ──────────────────
    weighted = []
    for e in catalog.values():
        weighted += [e["id"]] * e["weight"]

    for month in range(MONTHS):
        month_start = START + timedelta(days=30 * month)
        n_month = rng.randrange(28, 44)
        for _ in range(n_month):
            created = month_start + timedelta(
                days=rng.randrange(0, 28), hours=rng.randrange(0, 14))
            roll = rng.random()
            cid = rng.choice(weighted)
            # drift: BILL-004 only exists in year 2, remap in year 1
            if cid == "BILL-004" and month < YEAR2_START_MONTH:
                cid = "BILL-003"
            # in year 2, boost the drift case so it becomes a visible pattern
            if month >= YEAR2_START_MONTH + 3 and rng.random() < 0.10:
                cid = "BILL-004"

            if roll < 0.15:                                   # vague
                emit(created, vague=rng.choice(VAGUE_TEMPLATES))
            elif roll < 0.25:                                 # ambiguous
                emit(created, ambiguous=rng.choice(AMBIGUOUS))
            elif roll < 0.35 and issues:                      # duplicate
                orig = rng.choice(issues[-min(len(issues), 40):])
                dup = emit(created,
                           catalog_id=orig["ground_truth"]["catalog_id"] or "API-002",
                           duplicate_of=orig["number"])
                dup["title"] = rng.choice([
                    "same as an earlier report i think: ", "also seeing: ", "",
                ]) + dup["title"]
            else:
                emit(created, catalog_id=cid)

    # ── 3 vendor incident clusters: one root cause, 48h burst ─────────
    cluster_months = [5, 14, 20]  # one in year 1, two in year 2
    for ci, cm in enumerate(cluster_months):
        cluster_id = f"incident_{ci+1}"
        cid = "BILL-001" if ci != 2 else "BILL-004"  # last cluster IS the drift
        if cid == "BILL-004" and cm < YEAR2_START_MONTH:
            cid = "BILL-001"
        burst_start = START + timedelta(days=30 * cm + rng.randrange(3, 20))
        for _ in range(rng.randrange(20, 41)):
            created = burst_start + timedelta(minutes=rng.randrange(0, 48 * 60))
            emit(created, catalog_id=cid, cluster_id=cluster_id)

    issues.sort(key=lambda i: i["created_at"])
    # renumber chronologically so issue numbers look natural
    remap = {}
    for n, iss in enumerate(issues, start=1):
        remap[iss["number"]] = n
        iss["number"] = n
    for iss in issues:
        d = iss["ground_truth"]["duplicate_of"]
        if d:
            iss["ground_truth"]["duplicate_of"] = remap.get(d)
    for r in resolutions:
        r["issue_number"] = remap[r["issue_number"]]
    resolutions.sort(key=lambda r: r["issue_number"])

    return issues, resolutions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    issues, resolutions = gen(args.seed)

    issues_dir = ROOT / "data" / "issues"
    res_dir = ROOT / "data" / "resolutions"
    issues_dir.mkdir(parents=True, exist_ok=True)
    res_dir.mkdir(parents=True, exist_ok=True)

    # one file per year, ndjson
    y1 = [i for i in issues if i["created_at"] < (START + timedelta(days=365)).isoformat()]
    y2 = [i for i in issues if i not in y1]
    for name, chunk in [("year1", y1), ("year2", y2)]:
        with open(issues_dir / f"{name}.ndjson", "w") as f:
            for i in chunk:
                f.write(json.dumps(i) + "\n")
    nums_y1 = {i["number"] for i in y1}
    with open(res_dir / "year1.ndjson", "w") as f:
        for r in resolutions:
            if r["issue_number"] in nums_y1:
                f.write(json.dumps(r) + "\n")
    with open(res_dir / "year2.ndjson", "w") as f:
        for r in resolutions:
            if r["issue_number"] not in nums_y1:
                f.write(json.dumps(r) + "\n")

    by_routing = {}
    for i in issues:
        by_routing[i["ground_truth"]["routing"]] = by_routing.get(i["ground_truth"]["routing"], 0) + 1
    print(f"generated {len(issues)} issues ({len(y1)} year1 / {len(y2)} year2), "
          f"routing mix {by_routing}")


if __name__ == "__main__":
    main()
