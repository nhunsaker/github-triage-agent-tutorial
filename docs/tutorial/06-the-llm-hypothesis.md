# Layer 6: the LLM hypothesis

Layer 5 built a dossier with zero LLM calls: grep, git log, a fleet
search. That dossier is evidence, not a hypothesis. This layer takes
the jump from evidence to hypothesis and hands it to a model, one API
key, no Copilot seat required. `triage/investigate_llm.py` reads the
dossier, reads the suspect source files, and asks Claude what it
thinks broke.

## why this layer exists

Layer 7 hands the same evidence to the Copilot coding agent, but that
needs a paid plan. Not everyone following this tutorial has one, and
not everyone wants a general coding agent writing patches just to get
a second opinion on a hypothesis. This layer is the middle rung: an
agentic read of the code, available to anyone with any provider's API
key, that stops at a hypothesis and a fix direction instead of opening
a PR.

## the GitHub Models detour

The first design for this layer used GitHub Models, keyless inference
built into Actions, no separate API key, no separate billing account.
It doesn't exist anymore. GitHub fully retired GitHub Models on
2026-07-30, and building against it here returned a retirement
brownout error, live, on a real workflow run. That's the verify-at-
build-time discipline this whole tutorial keeps repeating: the
Copilot assign call in layer 7 says to check current docs before
relying on it, and this is why. An API that looked stable enough to
build a tutorial layer on was gone by the time the layer got written.

The honest menu after that: a Copilot seat, or one API key. This layer
is the one API key path.

## setup

Add the key as a repository secret:

```bash
gh secret set ANTHROPIC_API_KEY
```

You'll be prompted to paste the key, it never touches your shell
history this way. Locally, set the same variable in your environment
before running the module by hand.

Cost is one model call per issue that clears the confidence gate, not
per issue. Most issues resolve in phase 1 and never reach this step.
At tutorial volume that's cents, not dollars. If you want to trade
hypothesis depth for a cheaper call, `TRIAGE_LLM_MODEL` overrides the
default model, set it to whatever your provider account has access to.

## walking the module

Open `triage/investigate_llm.py`. `main()` checks for the key first:

```python
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ANTHROPIC_API_KEY not set — skipping the LLM hypothesis step. "
          "Layer 6 of the tutorial explains how to add it.", file=sys.stderr)
    return 0  # soft-skip: the pipeline still works without this step
```

No key, no crash, exit 0 with a note. The triage workflow keeps
running either way, layer 7's Copilot step still fires if it's wired
up, and a reader on the free tier loses nothing by skipping this one.

`gather_files()` builds the evidence the model reads: the files
`build_dossier()` already found by grep, plus the catalog prior's file
if there is one, capped at 3 files and 6KB each. Small and cheap on
purpose, the model needs enough code to reason about the failure, not
the whole service.

`ask_claude()` sends the issue, the dossier's evidence, and those file
excerpts as one prompt, and asks for structured output constrained to
a JSON schema: `hypothesis`, `routing`, `confidence`, `suspect_files`,
`fix_direction`. No parsing a free-form answer out of prose, the
response is already the shape `render()` needs.

Two guards worth reading closely:

- `if response.stop_reason == "refusal": return None`. The model can
  decline to answer, and the module treats that the same as a clean
  soft-skip rather than crashing or posting nothing useful.
- the prompt tells the model `confidence must be honest, low evidence
  means low confidence`, and that `routing "human"` is a valid answer.
  A hypothesis step that's rewarded for sounding certain is worse than
  no hypothesis step.

## the raise-site rule, taught to the model

Layer 5 taught you the catalog-prior lesson by hand: a grep hit on the
vendor client is where the error surfaces, not proof the fault is
ours. `ask_claude()`'s prompt teaches the same rule to the model
directly:

```
- a grep hit can be the RAISE SITE of a vendor-side error, not the cause.
  If the catalog prior says external and the fleet corroborates, the code
  match does not make it internal.
```

Same lesson, now as an instruction instead of code you read. The model
gets the deterministic dossier's `revised` call as part of its
evidence, so it isn't reasoning from scratch, it's reasoning from the
same evidence layer 5 already gathered.

## run it

```bash
grep -m1 'webhook signature' data/issues/year1.ndjson > /tmp/wh.json
python3 -m triage.investigate_llm --issue /tmp/wh.json --service billing
```

```
<!-- triage-llm:v1 {"v": 1, "kind": "llm-hypothesis", "issue": 2, "model": "claude-opus-4-8", "hypothesis": "PayFlow-side webhook signatures are failing verification fleet-wide; the billing code line is only the raise site for a vendor verification failure, not the root cause.", "routing": "external", "confidence": 0.7, "suspect_files": ["services/billing/webhooks.py", "services/billing/vendor_stub.py"], "fix_direction": "Confirm with PayFlow whether they rotated signing secrets or changed the signature scheme this morning; also sanity-check the recent billing commit didn't alter the mode/secret passed into verify_webhook_signature."} -->
### investigation (phase 2b, LLM hypothesis)

**hypothesis:** PayFlow-side webhook signatures are failing verification fleet-wide; the billing code line is only the raise site for a vendor verification failure, not the root cause.

**routing call:** `external` at 0.70 (deterministic pass said: external, corroborated)

**suspect files**
- `services/billing/webhooks.py`
- `services/billing/vendor_stub.py`

**fix direction:** Confirm with PayFlow whether they rotated signing secrets or changed the signature scheme this morning; also sanity-check the recent billing commit didn't alter the mode/secret passed into verify_webhook_signature.

model: `claude-opus-4-8` · evidence from the phase-2a dossier above. want a fix attempt? comment `/handoff` to send this to the coding agent.
```

Worth sitting with this one. `data/error_catalog.yaml` marks BILL-002,
webhook signature failures, as the genuinely hard case, resolutions
split roughly 60/40 between vendor key rotation and our own
misconfiguration. The model called it external at 0.70, a reasonable
read given the evidence, not a confident one. That's the calibration
the prompt asked for: a hard case gets a moderate confidence number,
not a model dialing to 0.95 because certainty sounds more useful.
Ground truth for this specific issue happens to be internal, one of
the 40%. The model wasn't wrong to hedge, this is exactly the case
where hedging is the honest answer.

## checkpoint

You should now see a posted hypothesis with a routing call, a
confidence number that isn't pinned to 0.99, named suspect files, and
a fix direction, all sourced from the same dossier layer 5 built. On a
repo with no `ANTHROPIC_API_KEY` set, the same workflow run produces
no comment from this step and no failure, the pipeline degrades to
layer 5's dossier alone.

### the heavy version

One model call per gated issue is cheap at Jane's Jeans' current
volume. Grown to thousands of issues a month across dozens of
services, that per-call API cost would start to matter, and the
answer wouldn't be to call the API less, it would be to stop paying
per call at all. At that scale you'd run a trained engine in a service
you own, amortizing the cost across every triage instead of metering
it per issue, with the same structured-output contract this module
already uses so nothing downstream would need to change. The raise-
site rule and the honest-confidence instruction wouldn't move to a
service either, they'd stay exactly what they are here: the part of
the prompt, or the part of the training data, that keeps a
hypothesis-generating step from being more confident than its
evidence supports.
