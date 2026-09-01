#!/usr/bin/env python3
"""Create the triage label set in the live repo. Run once at setup.

Labels are the API, and gh refuses to attach a label that does not
exist yet, so the label family gets bootstrapped before the first
issue arrives.

Usage: python tools/create_labels.py
"""

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

LABELS = [
    ("sev:S0", "b60205", "fleet-wide or data loss"),
    ("sev:S1", "d93f0b", "core flow broken, no workaround"),
    ("sev:S2", "fbca04", "broken with workaround"),
    ("sev:S3", "c2e0c6", "cosmetic or question"),
    ("route:internal", "1d76db", "ours to fix"),
    ("route:external", "5319e7", "vendor side"),
    ("route:human", "bfdadc", "needs a human call"),
    ("triage:confident", "0e8a16", "phase 1 acted"),
    ("triage:investigating", "e99695", "gated to phase 2"),
]


def main():
    with open(ROOT / "data" / "error_catalog.yaml") as f:
        services = sorted({e["service"] for e in yaml.safe_load(f)["catalog"]})
    labels = LABELS + [(f"service:{s}", "006b75", f"routed to services/{s}")
                       for s in services]
    for name, color, desc in labels:
        subprocess.run(
            ["gh", "label", "create", name, "--color", color,
             "--description", desc, "--force"],
            check=True)
        print(f"  {name}")
    print(f"{len(labels)} labels ready")


if __name__ == "__main__":
    main()
