"""Load the implementation under test for a chapter gate.

Default is your working copy in triage/. CI sets TRIAGE_IMPL=solutions
to run the same gates against the answer key, which is how main stays
provably complete while your copy is still stubs.
"""

import importlib
import os


def load(name):
    package = os.environ.get("TRIAGE_IMPL", "triage")
    return importlib.import_module(f"{package}.{name}")
