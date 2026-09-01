# 3. Train the rulebook

This is the layer that produces a trained rulebook, the same numbered
loop the flywheel in layer 8 later automates. You run it by hand first so
you understand what "automating the loop" actually means before you
build something that does it unattended. Expect this layer to take a
while and to feel repetitive in the middle. That repetition is the point.

## The severity ladder and routing, first

Before training anything, know what you are predicting. Every issue gets
three calls: a service, a severity, and a routing.

Severity is S0 through S3, defined by observable symptoms, not by how
upset anyone sounds in the title. S0 is fleet-wide or data loss. S1 is a
core flow broken for a cohort with no workaround. S2 is broken but a
workaround exists. S3 is cosmetic or a question. A rule claims a
severity the same way it claims a service or a routing, as one of its
dimensions.

Routing is internal, external, or human. Internal means Jane's Jeans code
owns the fix. External means the fault is on PayFlow's side. Human means
no rule should act at all, someone needs to look, this is the abstain
option and it is a legitimate answer, not a failure of the rulebook.

`triage/rulebook.py` runs every rule against an issue's title and body.
Every rule that matches bids on whatever dimensions it claims, and for
each dimension the highest-confidence bid wins:

```python
for rule in rulebook["rules"]:
    if not rule["_pattern"].search(text):
        continue
    fired.append(rule["id"])
    for dim in DIMENSIONS:
        if dim in rule:
            value, conf = rule[dim], float(rule.get("confidence", 0.5))
            if conf > result[dim][1]:
                result[dim] = (value, conf)
```

If nothing fires, or nothing fires with enough confidence, the defaults
take over: service unknown at 0.20, severity S2 at 0.30, routing human at
0.30. An untrained rulebook mostly ships the defaults, which is why it
scores badly and why the baseline run below matters.

## The corroboration rule, and how it got scoped

Billing is the one service that routes external often, layer 2's table 3
showed that directly. But "external" is a claim about fault, someone
else broke this, and that claim deserves evidence before you act on it,
not just a signature match.

The rule: an external call at severity S0 requires fleet-wide evidence,
N similar reports inside a time window. Without that evidence, it
downgrades to human. With it, confidence goes up instead:

```python
if corr and result["routing"][0] == "external":
    sev = result["severity"][0]
    if sev == "S0":
        n_similar = _count_similar(issue, recent_issues or [], rulebook)
        if n_similar < int(corr.get("min_reports", 3)):
            result["routing"] = ("human", min(result["routing"][1], 0.45))
            fired.append("corroboration-downgrade")
        else:
            result["routing"] = ("external", min(0.95, result["routing"][1] + 0.10))
            fired.append("corroboration-confirm")
```

Read the condition again: `if sev == "S0"`. Not every external call, only
S0. That scoping was not the first draft. The first pass applied
corroboration to every external routing, S0 through S3, on the theory
that any vendor-fault claim deserves fleet-wide backup. Running
`--show-misses` against that version surfaced a class of misses that made
no sense: single, isolated reports of `BILL-003`, refund declined by
vendor, correctly quoting the signature, correctly identifying billing,
getting downgraded to human for lack of corroboration that a refund
decline never needed in the first place. A declined refund is
signature-verifiable on its own: the vendor's response code is right
there in the message, one report is enough evidence, waiting for two more
customers to also get declined refunds before believing the first one
gains nothing.

The S0 case is different in kind, not just degree. `BILL-001`, PayFlow
unreachable, is a claim about the vendor's entire service being down. One
person's timeout could be their wifi. Twenty-one people reporting the
same 503 inside 48 hours, which is the real burst layer 2's table 4
found, is a claim you can act on. S1 externals like a declined refund or
a deprecation notice stand on their own signature. S0 externals are a
fleet-wide claim and need fleet-wide evidence to back it. That is the
whole justification, and it came from reading the misses, not from
designing it up front.

## Confidence and the gate

Every dimension carries a confidence alongside its value. `theta`, the
gate, defaults to 0.70:

```python
def decide(result, theta=0.70):
    routing_conf = result["routing"][1]
    return "act" if routing_conf >= theta else "investigate"
```

Above theta, the rulebook's call ships as-is, a label and a comment,
layer 4 covers the mechanics. Below theta, the issue goes to phase 2, the
evidence dossier in layer 5. Calibration is the check that theta means
what it says: if the rulebook claims 0.9 confidence on a batch of calls,
roughly 9 in 10 of them should be correct. `eval.py` prints a calibration
table for exactly this reason, and you will watch it below.

## The training loop

1. Baseline the starter rulebook on year 1.
2. Mine, from layer 2, pick the strongest signal you have not used yet.
3. Write one rule, confidence grounded in the mined contingency.
4. Re-eval. Did routing move. Did calibration hold.
5. Read the misses, grouped, and decide the next rule from what you see.
6. Repeat 2 through 5 until year-1 gains flatten. Then unseal year 2 once
   and record the holdout number.

## Do this: baseline

```
python -m triage.eval --year 1 --rulebook triage/rulebook.starter.yaml
```

```
rulebook: triage/rulebook.starter.yaml · year 1 · theta 0.7

issues:          440
routing top-1:   30.9%
severity:        36.6%
service:         22.7%
sent to phase 2: 100.0%  (below theta)

routing confusion (rows=truth, cols=pred):
            internal  external     human
  internal        65         8       248
  external         0        41        35
     human        13         0        30

routing calibration (bucket → accuracy in bucket):
  conf ~0.4: 24.3%  (n=391)
  conf ~0.6: 83.7%  (n=49)
```

Three rules in the starter, `payflow-mention`, `checkout-broken`,
`dashboard-mention`, cover a sliver of the corpus. 391 of 440 issues land
in the 0.4 confidence bucket, meaning the defaults fired because nothing
matched, and every single issue gates to phase 2 since nothing clears
0.70. 30.9% routing accuracy, close to what you'd get labeling everything
"internal" by chance given the corpus mix.

## Read the misses

```
python -m triage.eval --year 1 --rulebook triage/rulebook.starter.yaml --show-misses
```

The biggest miss group by far:

```
  internal → human  (248 issues)
    #   1 [API-005] return stuck in wrong state
    #   3 [API-001] sold items we dont have in stock
    #   6 [API-004] orders not reaching the queue
    #   7 [API-002] order rejected but reason seems wrong
    #  12 [QR-004] schema errors from the order stream
    #  13 [DASH-003] filters break the orders view
    #  14 [QR-005] duplicate order events in the log
    #  15 [API-002] order rejected but reason seems wrong
    … 240 more
```

248 issues that should route internal are landing on the human default
because no rule fires for them at all. This is the group table 1 from
layer 2 exists to fix: `API-001`, `stock below zero for sku`, resolved
internal 100% of the time in 15 issues. That is a rule waiting to be
written.

## Write one rule, re-eval

```yaml
- id: sig-oversell
  match: "stock below zero for sku"
  service: api
  severity: S1
  routing: internal
  confidence: 0.95
```

Add it to the rulebook, alongside the three starter rules, and re-eval:

```
rulebook: /tmp/step2.yaml · year 1 · theta 0.7

issues:          440
routing top-1:   34.3%
severity:        40.0%
service:         26.1%
sent to phase 2: 96.6%  (below theta)
```

One rule, 30.9% to 34.3%. `API-001` alone accounts for 15 of the 440
issues, and each one now routes correctly instead of hitting the human
default. That is the whole loop: mine, write, re-eval, and the number
moves by an amount you can attribute to the exact rule you just wrote.

Keep going. Every signature in layer 2's table 1 above roughly 80% is a
candidate signature rule. The vague keywords in table 2 are weaker
candidates for the unsigned slice, kept at lower confidence so they stay
under the signature rules when both could fire. Read the misses again
after each addition, and after enough rounds a pattern shows up: gains
per rule shrink. The first rule bought four points. The tenth rule buys a
fraction of a point. That flattening is the signal to stop tuning on
year 1.

## Do this: unseal year 2, once

`solutions/rulebook.yaml` is what running this loop to convergence
produces. Do not open it until your own year-1 number has flattened, and
do not copy it in, the loop is the lesson, not the destination. When you
are ready:

```
python -m triage.eval --year 1 --rulebook solutions/rulebook.yaml
```

```
issues:          440
routing top-1:   82.5%
severity:        87.5%
service:         86.1%
sent to phase 2: 24.5%  (below theta)

routing calibration (bucket → accuracy in bucket):
  conf ~0.4: 22.7%  (n=44)
  conf ~0.6: 60.9%  (n=64)
  conf ~0.8: 90.9%  (n=77)
  conf ~1.0: 95.7%  (n=255)
```

```
python -m triage.eval --year 2 --rulebook solutions/rulebook.yaml
```

```
issues:          463
routing top-1:   84.0%
severity:        71.7%
service:         87.0%
sent to phase 2: 40.2%  (below theta)
```

82.5% on year 1, 84.0% on year 2, holding up on data the rulebook never
tuned against. The calibration table is doing real work too, look at it:
confidence around 0.8 is right about 91% of the time, confidence around
1.0 is right about 96% of the time. The gate at theta 0.70 is trustworthy
because the confidence numbers behind it are honest, not because they
are high.

Look at the 0.6 bucket specifically: 61% accuracy on 64 issues, well
below the confidence claimed. That bucket is where every rule sitting
just under theta lands, including `sig-webhook-verification` at its
mined 0.62. A generic keyword rule bidding anywhere near a specific
signature rule's confidence pulls that bucket's accuracy toward the
keyword's noisier hit rate, and a live run of this exact rulebook caught
that directly: `kw-payflow`, a bare "payflow" match, once sat at 0.70,
just above `sig-webhook-verification`'s mined 0.62, so on an issue titled
with "PayFlow" the generic rule outbid the specific one and acted at
theta on a class that mining said was only 62% external. The fix was not
tuning the number down until the accuracy looked better, it was
recognizing that mined confidence belongs to the signal that earned it.
`sig-webhook-verification` earned 0.62 from the quoted signature itself.
`kw-payflow` matches on a bare word and never gets to borrow that number,
so it now sits at 0.60, read the comment next to it in
`solutions/rulebook.yaml` for the specifics. The general principle: a
generic rule must never outbid the most specific rule that could have
fired on the same text.

Notice severity drops from 87.5% on year 1 to 71.7% on year 2. That gap
is worth sitting with rather than explaining away: it is exactly the kind
of thing a rulebook tuned on one slice of history will not tell you about
itself, you only see it by actually running the held-out year.

## The wall

82 to 84%, and no amount of additional rule-writing against year 1 pushes
year 2 much past it. This is by design, not a coincidence or a skill
issue. Layer 2 built roughly 15% vague reports with no exploitable
signature, roughly 10% cross-service ambiguous cases where the surface
symptom points at the wrong service, and a year-2-only drift class,
`BILL-004`, the PayFlow v2 deprecation, that literally does not exist in
year-1 history for any rule to have learned from. `solutions/rulebook.yaml`
says as much in its own header comment: notably absent is any rule for
that deprecation, because writing one would mean reading the answer key
instead of training on evidence, and the corpus was built specifically so
that this gap exists.

That gap sent to phase 2 is not overflow to be tuned away, it is the
designed hard population: vague reports genuine ambiguity cannot resolve
from text alone, cross-service symptoms that need code to disambiguate,
and drift no historical rule could have anticipated. Look at the two
numbers above rather than averaging them: year 1 sends 24.5% to phase 2,
year 2 sends 40.2%, nearly double. That jump is not the rulebook getting
worse, routing accuracy holds at 84.0%, it is `BILL-004`, the PayFlow v2
deprecation, showing up as investigation load instead of as misrouting.
No year-1 rule can act confidently on a signature it has never seen, so
every one of those issues correctly falls through the gate instead of
guessing. That is the gate doing its job on drift. Layer 7 closes this
gap from the other direction, once a human corrects a few of these, the
flywheel writes a rule and the sent-to-phase-2 share on year 2 comes back
down to 22.5%. A rulebook is a lookup table over patterns it has already
seen. The residual is everything a lookup table structurally cannot
cover, and that residual is the reason phase 2, the evidence dossier in
layer 5, exists at all.

## Checkpoint

You should have run the baseline, watched it sit at 30.9%, added at least
one rule yourself and watched the number move, and read `--show-misses`
output well enough to explain which class of issue a given rule fixes
before you re-eval. You should be able to state the corroboration
scoping rule, S0 external needs fleet evidence, S1 external does not,
and explain why in your own words. Finally, you should have your own
year-1 and year-2 numbers in the neighborhood of `solutions/rulebook.yaml`'s
82.5% and 84.0%, and be able to say what the remaining 16 to 18% is made
of. Layer 4 wires whatever rulebook you end up with into a live GitHub
Actions workflow.

## the heavy version

A Jane's Jeans with forty services and a real ML team would run this
exact loop, baseline, mine, adjust, re-evaluate, read the misses, on a
trained model instead of a hand-edited YAML file, and the model would
find interactions across far more signal than four mined tables surface
by hand. It would still hit the same kind of wall, a routing ceiling
somewhere in the mid-70s, for the same underlying reason: a classifier,
however it is built, can only be as good as the patterns present in its
training history, and vague reports, cross-service ambiguity, and drift
do not go away because the classifier got smarter. That ceiling, not a
specific accuracy target, is what would motivate building a second phase
at all, the same reason this tutorial builds one at 82.5%.
