# 2. The corpus

You now know what can fail and where. This layer loads two years of
issues about those failures, runs the mining script that turns raw
history into signal tables, and ends with you writing a rule by hand from
one of those tables. Nothing here is hidden. The rulebook you build in
layer 3 comes from reading these exact numbers, not from a file someone
handed you.

## The two years

```
data/issues/year1.ndjson
data/issues/year2.ndjson
data/resolutions/year1.ndjson
data/resolutions/year2.ndjson
```

NDJSON, one JSON object per line. An issue:

```json
{"number": 3, "title": "sold items we dont have in stock", "body": "repeated 27 times in the last hour:\n\n```\nstock below zero for sku JJ-SLIM-38: reserved 4, on hand 0\n```\n\ncan someone take a look", "created_at": "2024-09-01T19:00:00Z", "reporter": "priya.store", "labels": [], "ground_truth": {"catalog_id": "API-001", "service": "api", "severity": "S1", "routing": "internal", "resolution_id": "res_0001", "duplicate_of": null, "cluster_id": null}}
```

Its paired resolution:

```json
{"resolution_id": "res_0001", "issue_number": 3, "service": "api", "routing": "internal", "root_cause": "OversellError", "fix": "config fix in api, no code change needed", "no_pr": false, "external": false, "resolved_at": "2024-09-03T08:00:00Z"}
```

`ground_truth` on the issue and the matching row in `resolutions` are the
same fact recorded twice: what actually happened. That is what "ground
truth" means here, and it is the only reason any of this is trainable.
Real issue trackers do not ship a `ground_truth` field, they ship a
closed issue with labels and a linked PR, and extracting the equivalent
signal from that is real work. The corpus hands it to you directly so the
lesson is about the training loop, not about label archaeology.

Split is time-based, not random. Year 1 is what you mine and tune
against. Year 2 stays sealed until layer 3 unseals it once, at the end,
as a holdout. This mirrors why the split exists at all: a rule that
memorizes year 1 and never sees anything new looks great on year 1 and
tells you nothing about how it holds up on issues it has never seen,
which is the only question that matters.

The corpus is hard by design, not incidentally. `tools/gen_corpus.py`
draws from the error catalog with realistic per-entry frequencies, then
layers in four kinds of difficulty on purpose: about 15% vague reports
with thin signal, about 10% cross-service ambiguous cases where the
symptom points at the wrong service, three vendor incident clusters
where one root cause produces twenty to forty issues inside 48 hours,
about 10% duplicate reports, and a year-2-only drift class, PayFlow's v2
deprecation, that never appears in year 1 so no year-1-trained rule can
catch it. `tests/test_corpus.py` enforces the shape of all of this, so it
is not a claim you have to take on faith:

```python
def test_hardness_mix():
    ...
    assert 0.04 < dupes / n < 0.20, f"duplicate share off: {dupes/n:.2f}"
    assert clustered >= 60, f"incident clusters too small: {clustered}"
    assert human >= 20, "need a real abstain-to-human class"
    assert external >= 60, "need a real external class"
```

## Do this: mine year 1

```
python tools/mine_patterns.py
```

The script joins issues to resolutions on year 1 and prints four tables.
Table 1, quoted signature to final routing, is the strongest signal in
the corpus, real output, trimmed to the rows worth reading:

```
======================================================================
1. quoted signature → final routing (write signature rules from this)
======================================================================
    API-001  n=15   → internal  100%   (service=api, sev=S1)
   BILL-001  n=32   → external  100%   (service=billing, sev=S0)
   BILL-002  n=29   → external  62%   (service=billing, sev=S1)
   BILL-003  n=26   → external  100%   (service=billing, sev=S2)
   BILL-005  n=17   → internal  94%   (service=billing, sev=S1)
   DASH-001  n=25   → internal  100%   (service=dashboard, sev=S2)
     QR-001  n=33   → internal  94%   (service=qr, sev=S1)
     QR-004  n=25   → internal  84%   (service=qr, sev=S2)
```

Read `BILL-002` closely. Every other row in this table is a landslide,
84% and up, several at 100%. `BILL-002`, the webhook signature failure,
sits at 62%. That is not noise in the mining script, it is the real
split: 29 issues quote this exact signature, and resolutions send 18 of
them external and 11 internal. Sometimes the vendor rotated keys,
sometimes Jane's Jeans misconfigured something on its end, and the
quoted error text alone cannot tell you which. Hold onto this number,
layer 3 comes back to it twice.

Table 2 covers the vague reports, the roughly 15% of issues that quote no
signature at all:

```
======================================================================
2. keyword → routing on unsigned (vague) reports
======================================================================
  (65 vague reports, 15% of year 1)

        charge  n=14   → internal  71%
      checkout  n=11   → human     55%
     dashboard  n=8    → human     62%
        return  n=13   → internal  62%
```

Weaker signal than table 1, as expected, plain words in a title are a
worse predictor than a quoted stack trace. Notice "checkout" and
"dashboard" both lean human, meaning a plurality of these vague reports
resolved with no fix at all, the reporter's own environment, a training
gap, something that was never really a bug.

Table 3, external share by resolved service, is where the internal
versus external split lives structurally:

```
======================================================================
3. external share by resolved service (where vendor problems live)
======================================================================
         api  n=142  external 0%  internal 85%  human 15%
     billing  n=113  external 67%  internal 29%  human 4%
   dashboard  n=69   external 0%  internal 91%  human 9%
          qr  n=116  external 0%  internal 91%  human 9%
```

Three of the four services never route external, not once in 440 issues.
Billing routes external two-thirds of the time. This single table is why
the whole corroboration story in layer 3 attaches only to billing: it is
the one place in Jane's Jeans where "someone else's fault" is a normal
outcome instead of a rare one.

Table 4 finds the incident clusters:

```
======================================================================
4. burst windows (>=8 issues / 48h sharing a signature)
   this is the evidence for the fleet-wide corroboration rule
======================================================================
   BILL-001  max 21 reports in one 48h window (n=32 total)
```

`BILL-001` is the PayFlow outage signature, and 21 of its 32 total
reports arrive inside one 48-hour window. That is a vendor outage: one
root cause, many simultaneous reporters. This burst pattern is the
evidence behind the corroboration rule you will read about in layer 3,
before you get there, just notice the shape: many reports, short window,
one signature.

## Write your first rule

You have everything you need for one rule right now, no code, just the
`BILL-002` finding from table 1: webhook signature failures resolve
external 62% of the time. `triage/rulebook.starter.yaml` already has this
exact shape for a different signal, `payflow-mention`:

```yaml
- id: payflow-mention
  match: "payflow"
  service: billing
  routing: external
  confidence: 0.55
```

Write the webhook version yourself, on paper or in a scratch file, before
layer 3 tells you the exact match string:

```yaml
- id: sig-webhook-verification
  match: "webhook signature verification failed"
  service: billing
  severity: S1
  routing: external
  confidence: 0.62
```

The confidence is not a guess, it is the mined number from table 1,
62%, restated as a decimal. That grounding, a rule's confidence equals
a real contingency you measured, not a vibe, is the discipline the entire
training protocol in layer 3 runs on. You will also notice, once you
start evaluating, that 0.62 sits below the default confidence gate of
0.70. That is not a bug to fix by inflating the number. It means this
class of issue should always fall through to phase 2 for a closer look,
and layer 3 explains why that is the correct behavior rather than a weak
rule.

## Checkpoint

You should now be able to open `data/issues/year1.ndjson`, find an issue,
find its resolution by `resolution_id`, and say in one sentence what
"ground truth" means for this corpus. Run `python tools/mine_patterns.py`
yourself if you have not, and be able to point at the `BILL-002` row and
explain, without rereading this page, why 62% is a more honest number
than 95% would be. Layer 3 uses this exact mining output as the fuel for
the training loop.

## the heavy version

At thousands of issues a month across forty services, Jane's Jeans would
not run a mining script by hand once a layer. The equivalent of these
four tables would get recomputed continuously as a feature pipeline
feeding a trained model, and the model would find signal humans would not
think to tabulate, not just signature-to-routing and keyword-to-routing
but combinations and interactions across dozens of fields. What this
layer teaches, that a rule's strength should be measured against real
outcomes before you trust it, is the same discipline that model would
need, just automated and running at a scale no one reads by hand.
