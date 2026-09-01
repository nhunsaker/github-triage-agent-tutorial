# 4. Wire it to Actions

You have a trained rulebook. This layer gets it running against real
issues, but it starts offline: a dry-run harness and a replay tool that
exercise the exact same code path the live workflow uses, no GitHub
account touched. Only the last step opens the live workflow, and it
needs no PAT, the default `GITHUB_TOKEN` covers everything through this
layer.

## Do this: dry-run a single issue

`triage/run.py` is both the Action's entrypoint and a local harness.
Pull one issue out of the corpus, strip its ground truth the way a real
issue would never have one, and run it through:

```
python -m triage.run --issue /tmp/issue3.json --dry-run --rulebook solutions/rulebook.yaml
```

```
issue #3: sold items we dont have in stock
labels:  ['sev:S1', 'route:internal', 'triage:confident', 'service:api']
gate:    act
<!-- triage:v1 {"v": 1, "issue": 3, "decision": {"service": {"value": "api", "confidence": 0.95}, "severity": {"value": "S1", "confidence": 0.95}, "routing": {"value": "internal", "confidence": 0.95}}, "gate": "act", "theta": 0.7, "fired": ["sig-oversell"]} -->
### triage

| dimension | call | confidence |
|---|---|---|
| service | `api` | 0.95 |
| severity | `S1` | 0.95 |
| routing | `internal` | 0.95 |

rules fired: `sig-oversell`

acting on this triage. want a deeper look either way? comment `/investigate` on this issue.
```

This is exactly what would get posted to a real issue, printed instead
of sent. Try an issue that gates the other way, the webhook signature
case from layers 2 and 3:

```
python -m triage.run --issue /tmp/issue9.json --dry-run --rulebook solutions/rulebook.yaml
```

```
issue #9: payment confirmations stopped arriving
labels:  ['sev:S1', 'route:external', 'triage:investigating', 'service:billing']
gate:    investigate
...
confidence below threshold, starting an investigation. want a deeper look either way? comment `/investigate` on this issue.
```

Confidence 0.62, the exact mined number from layer 2 and 3, below theta,
gated to investigate instead of act. Same code, same rulebook, different
issue, different outcome, entirely offline.

## Do this: replay a slice of the corpus

`triage/replay.py` streams any year through the same classify-and-gate
path, no per-issue file needed:

```
python -m triage.replay --year 1 --rulebook solutions/rulebook.yaml --limit 15
```

```
#   1 ✓ [internal 0.94] gate=act         gt=internal return stuck in wrong state
#   2 ✗ [external 0.62] gate=investigate gt=internal also seeing: webhook signature failures from PayFlow
#   3 ✓ [internal 0.95] gate=act         gt=internal sold items we dont have in stock
#   4 ✗ [internal 0.50] gate=investigate gt=human    checkout is broken, customers cant buy
#   5 ✗ [internal 0.92] gate=act         gt=human    events stuck, same one retried over and over
#   6 ✓ [internal 0.92] gate=act         gt=internal orders not reaching the queue
#   9 ✓ [external 0.62] gate=investigate gt=external payment confirmations stopped arriving
```

Issue #2 mentions PayFlow by name in its title, on top of quoting the
webhook signature. Both `kw-payflow` and `sig-webhook-verification` fire,
and since `kw-payflow` now bids below the signature rule, the specific
signal wins and the issue gates at 0.62, same as the plain webhook case
in #9. Earlier in this tutorial's own live run, `kw-payflow` sat above
`sig-webhook-verification` and this exact issue shape acted at theta
instead, on a class mining said was only 62% right. Layer 3 tells that
story and the fix. It is the reason a generic keyword rule must never
outbid a specific signature rule on the same text.

`--only-gated` filters to just the issues sent to phase 2, useful once
you build the investigation in layer 5 and want to see what it will
actually receive:

```
python -m triage.replay --year 1 --rulebook solutions/rulebook.yaml --only-gated --limit 8
```

```
#   2 ✗ [external 0.62] gate=investigate gt=internal also seeing: webhook signature failures from PayFlow
#   4 ✗ [internal 0.50] gate=investigate gt=human    checkout is broken, customers cant buy
#   9 ✓ [external 0.62] gate=investigate gt=external payment confirmations stopped arriving
#  10 ✗ [external 0.62] gate=investigate gt=internal webhook signature failures from PayFlow
#  18 ✗ [internal 0.66] gate=investigate gt=human    customer says they were charged twice
```

The webhook class, #2, #9, #10, now fills more of this list than it did
before the specificity fix, which is expected: it is a genuinely 62/38
class, and gating all of it to phase 2 instead of letting a generic
keyword rule act on part of it is the correct, if less flattering,
behavior.

Both harnesses run the whole training and iteration loop from layer 3
without ever opening GitHub. Layers 2 through 3 and half of this one are
entirely offline, on purpose, the live workflow below is the last step,
not the first.

## The workflow, block by block

`.github/workflows/triage.yml` fires on `issues.opened`:

```yaml
name: triage

on:
  issues:
    types: [opened]

concurrency:
  group: triage-${{ github.event.issue.number }}
  cancel-in-progress: false
```

`concurrency` scopes to one group per issue number. Two rapid edits to
the same issue will not race two triage runs against each other, but
different issues still run in parallel. Skip this and a flaky rerun or a
fast edit-then-reopen can produce two competing comments on the same
issue.

```yaml
jobs:
  triage:
    runs-on: ubuntu-latest
    if: ${{ !endsWith(github.actor, '[bot]') }}
```

The bot-skip guard. Without it, a bot-authored issue, say, one your own
flywheel opens in layer 8, could trigger triage on itself. `[bot]` is the
suffix GitHub appends to bot actor logins, checking for it here is
cheaper and more explicit than relying on token semantics alone.

```yaml
    permissions:
      contents: read
      issues: write
    outputs:
      gate: ${{ steps.classify.outputs.gate }}
      service: ${{ steps.classify.outputs.service }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: classify + route (phase 1)
        id: classify
        env:
          GH_TOKEN: ${{ github.token }}
          TRIAGE_RULEBOOK: solutions/rulebook.yaml
        run: |
          python -m triage.run --event "$GITHUB_EVENT_PATH" \
            --rulebook "$TRIAGE_RULEBOOK"
```

`issues: write` is the only elevated permission this job needs, and
`github.token`, the default `GITHUB_TOKEN`, is enough to label and
comment. That token is scoped to this run and expires after the job
finishes, no PAT, no secret to provision, which is why everything through
this layer runs on the free tier with zero credentials beyond a GitHub
account. `triage.run` writes `gate` and `service` to `$GITHUB_OUTPUT`,
which the job exposes as outputs for the next job to read.

Layers 6 and 7 do add credentials, an API key and a token, and the rule
for both is the same one worth internalizing now: a credential lives in
a GitHub secret (`gh secret set NAME`, read as `${{ secrets.NAME }}`) or
in a local git-ignored `.env`, never in a file you commit. The README's
"never commit a token" section is the short version. `GITHUB_TOKEN` here
needs none of that because Actions mints and destroys it for you.

```yaml
  investigate:
    needs: triage
    if: ${{ needs.triage.outputs.gate == 'investigate' }}
```

A second job, gated on the first job's output. Only issues below theta
reach it, everything else stops after labeling and commenting. This is
the confidence gate from layer 3, expressed as workflow control flow.

Inside `investigate`, phase 2a, the evidence dossier, is layer 5's
territory, it always runs. Right after it sits a step for phase 2b, an
LLM hypothesis:

```yaml
      - name: LLM hypothesis (phase 2b — one API key)
        env:
          GH_TOKEN: ${{ github.token }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python -m triage.investigate_llm \
            --event "$GITHUB_EVENT_PATH" \
            --service "${{ needs.triage.outputs.service }}" \
            --post
```

That step is layer 6's whole subject. It reads `ANTHROPIC_API_KEY` from
repo secrets, and when the secret is absent it soft-skips, exits clean
with a note instead of failing the run, so a free-tier reader following
layers 0 through 5 loses nothing by not having it set. Phase 2c, the
Copilot hand-off, is commented out below that entirely, layer 7 explains
why and what it takes to turn on.

## Labels are the API

The rulebook's output becomes labels, and those labels are the interface
downstream tools, including the flywheel in layer 8, read. `build_labels`
in `triage/run.py`:

```python
def build_labels(result, gate):
    sev, _ = result["severity"]
    svc, _ = result["service"]
    route, _ = result["routing"]
    labels = [f"sev:{sev}", f"route:{route}",
              "triage:confident" if gate == "act" else "triage:investigating"]
    if svc != "unknown":
        labels.append(f"service:{svc}")
    return labels
```

Four label families: `sev:S0` through `sev:S3`, `service:<name>`,
`route:internal|external|human`, and `triage:confident` or
`triage:investigating`. Anyone, or anything, working the issue tracker
can filter on these without parsing a comment.

The comment carries more than the labels can: a human-readable table plus
a hidden machine-readable block above it.

```python
return f"""<!-- triage:v1 {json.dumps(machine)} -->
### triage

| dimension | call | confidence |
|---|---|---|
{rows}

rules fired: {', '.join(f'`{f}`' for f in fired) if fired else 'none (defaults)'}

{verdict}. want a deeper look either way? comment `/investigate` on this issue.
"""
```

The HTML comment marker `triage:v1 {json}` is invisible when the comment renders on
GitHub, but it is right there in the raw comment body
for anything parsing the issue's activity to read. It carries the full
decision: value and confidence per dimension, the gate, theta, which
rules fired. Layer 7's flywheel reads this exact marker to diff what the
bot decided at open time against what humans eventually decided at close
time. The version number, `v1`, exists so a future format change does
not silently break a parser reading old comments.

## Seeding live issues

Bulk work runs offline through `replay.py`, opening 900 live issues would
be an API-abuse footgun against your own repo and against GitHub's rate
limits. `tools/seed_issues.py` opens a small, curated slice instead, about
10 issues, picked to cover the interesting cases: confident signatures,
one ambiguous case, one vague report, the webhook case that always gates,
one duplicate pair.

```
python tools/seed_issues.py --dry-run
```

```
[sig-confident] would open: sold items we dont have in stock
[sig-confident] would open: 500 on checkout
[sig-confident] would open: dead letter queue filling up again
[sig-confident] would open: refund declined by vendor
[ambiguous] would open: order counts frozen since 2pm
[ambiguous] would open: dashboard not showing new orders
[vague] would open: checkout is broken, customers cant buy
[vague] would open: numbers look wrong on the dashboard
[hard] would open: also seeing: webhook signature failures from PayFlow
[dupe] would open: same as an earlier report i think: orders not reaching the queue

10 issues previewed. watch the Actions tab for the triage workflow.
```

Ground truth is stripped before any of this opens, the NDJSON carries the
answer key and a live issue must not. Drop `--dry-run` against a repo you
control, authed with `gh`, and each one opens for real, throttled a few
seconds apart, and the triage workflow above fires on each as it lands.

## Checkpoint

You should have run at least one issue through `triage.run --dry-run` and
one through `triage.replay`, and be able to point at the exact line in
`triage.yml` that decides whether phase 2 runs at all. Run
`python tools/seed_issues.py --dry-run` and confirm you see ten curated
issues, not the full corpus. If you have a repo to seed against, run it
for real and watch the Actions tab: labels and a comment should land on
each issue within one run, and the webhook case should visibly gate to
investigate. Layer 5 builds what runs when it does.

## the heavy version

A Jane's Jeans running forty services would not want its rulebook read
out of a YAML file checked into git on every issue. It would want a
service holding versioned rulebooks, or in the trained-model case,
versioned model weights, served to whatever is doing the classifying,
with real deploy and rollback semantics instead of a merge to main. The
labels-as-API pattern would still hold at that scale, whatever the
routing engine, downstream systems need a stable, parseable output
contract, and a label plus a structured comment is a lightweight version
of the same idea a bigger system would solve with an actual event schema
and a message bus.
