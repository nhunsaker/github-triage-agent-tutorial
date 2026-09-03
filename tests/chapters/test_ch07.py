"""Layer 7 gate. Runs against YOUR triage/assign_copilot.py.

Fresh clone: every test here skips with "chapter 7 not started". As you
implement build_actor_lookup_query and build_assign_mutation the tests
flip to green. Pure offline: no gh calls, no network, no live GraphQL.
"""

import pytest

from tests.chapters.impl import load

assign_copilot = load("assign_copilot")


def run(fn, *args, **kwargs):
    """Call a starter function, skipping the test while it is stubbed."""
    try:
        return fn(*args, **kwargs)
    except NotImplementedError:
        pytest.skip("chapter 7 not started")


# ── build_actor_lookup_query ────────────────────────────────────────

def test_actor_lookup_query_names_the_capability_and_repo():
    query, variables = run(assign_copilot.build_actor_lookup_query,
                            "acme", "jeans")
    assert "suggestedActors" in query
    assert "CAN_BE_ASSIGNED" in query
    assert variables == {"owner": "acme", "repo": "jeans"}


# ── build_assign_mutation ────────────────────────────────────────────

def test_assign_mutation_carries_the_ids_it_was_given():
    query, variables = run(assign_copilot.build_assign_mutation,
                            "I_kwDOISSUE", "BOT_kwDOACTOR")
    assert "replaceActorsForAssignable" in query
    assert variables == {"issueId": "I_kwDOISSUE", "actorIds": "BOT_kwDOACTOR"}


def test_assign_mutation_payload_is_mode_invariant():
    # --mode changes the scoping comment, never the assignment payload:
    # fix and investigate mode must build the identical mutation.
    fix_query, fix_vars = run(assign_copilot.build_assign_mutation,
                              "I_1", "BOT_1")
    inv_query, inv_vars = run(assign_copilot.build_assign_mutation,
                              "I_1", "BOT_1")
    assert fix_query == inv_query
    assert fix_vars == inv_vars
