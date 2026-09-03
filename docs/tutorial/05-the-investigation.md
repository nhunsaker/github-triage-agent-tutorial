# Layer 5: the investigation

Layer 3 trained a rulebook that hits a wall around 80%. Below the
confidence gate, the bot should not guess. It should look. That's
`build_dossier()`: four evidence sources, then a hand-off offer, zero
LLM calls. Free tier, no PAT.

Your working copy is `triage/investigate.py`. The CLI, issue loading,
the change-evidence and fleet-evidence sources, and the dossier
rendering are given, plumbing gh events and formatting the
machine-marker comment is not the lesson. The two functions that are
the lesson raise `NotImplementedError` until you write them:
`grep_code`, `catalog_prior`. Each one's docstring is its contract.
`solutions/investigate.py` is the finished version, for comparison
after you've built it, not before. The evidence trick is the lesson.

Your gate for this layer:

```bash
python3 -m pytest tests/chapters/test_ch05.py -q
```

On a fresh clone every test in it skips with "chapter 5 not started".
As you land each function, its tests flip from skipped to green.

## the four evidence sources

`build_dossier()` runs four checks in order.

**1. code evidence.** `grep_code()` pulls the quoted error line out of
the issue body, strips the parts that vary (ids, numbers, quoted
values), and greps `services/` for the stable words that remain. A
filled-in id like `event_887a2` never appears in the source template,
only the literal words around it do. That's the stable-fragment trick:
match on what the code actually contains, not what the reporter typed
in. Implement it and it must never hallucinate a location, every hit
it returns has to trace back to a real `grep` match.

**2. change evidence.** `recent_commits()` runs `git log --oneline -8`
scoped to the suspect service directory. Did something ship there
recently. This one's given, read it for the pattern, you won't write
it.

**3. fleet evidence.** `fleet_check()` searches other issues for the
same signature fragment. One report is an anecdote. Several in a
window is a pattern, and the corroboration rule from layer 3 already
told you why that distinction matters for routing. Also given.

**4. catalog prior.** `catalog_prior()` matches the signature back to
`data/error_catalog.yaml` and reads its typical routing. This is the
function you write, and it's the one that keeps the dossier honest.

## the catalog-prior lesson

A grep hit on `services/billing/payflow.py` looks like proof the bug is
ours. It isn't. That file is where our client *raises* the error after
the vendor's API returns a 503. The code match tells you where the
failure surfaces, not where it originates. The catalog knows the
difference because it records each signature's typical routing, so a
match against an entry marked `external` overrides the naive "code
found it, code owns it" read.

Open `triage/investigate.py` and read `catalog_prior`'s docstring.
Each catalog entry's `message` field is a template with `{placeholder}`
vars, the corpus generator fills those in when it writes an issue
body, so the literal text you're matching against never appears
verbatim in the catalog. The trick: escape the whole template with
`re.escape`, then swap the now-escaped placeholder braces for a
non-greedy wildcard. That turns `"stock below zero for sku {sku}"`
into a pattern that matches the real, filled-in signature. Test
catalog entries in order and return the first one that matches, first
match wins, no scoring. Return the whole entry, callers cite its
`file` and `symbol` straight from the catalog instead of re-deriving
them.

Once both functions are in place, run it on a real corpus issue to see
this play out.

```bash
grep -m1 'PayFlow API unreachable' data/issues/year2.ndjson > /tmp/ext.json
python3 -m triage.investigate --issue /tmp/ext.json --service billing
```

```
<!-- triage-dossier:v1 {"v": 1, "kind": "dossier", "issue": 441, "hypothesis": "vendor-side fault (BILL-001): the code match is the raise site in our billing client, not the cause", "revised": "external, corroborated", "n_code_hits": 2, "n_fleet": 30} -->
### investigation (phase 2a)

**signature:** `PayFlow API unreachable: 503 from /v1/tokens`

**code evidence** (grep services/)
- `services/billing/vendor_stub.py:33` — `raise VendorOutageError("PayFlow API unreachable: 503 from /v1/charges")`
- `services/billing/vendor_stub.py:44` — `raise VendorOutageError("PayFlow API unreachable: 503 from /v1/refunds")`

**change evidence** (recent commits, services/billing/)
- none found

**fleet evidence** (similar reports)
- 30 similar report(s): #441, #450, #500, #514, #526, #531

**evidence for**
- signature resolves to code: services/billing/vendor_stub.py:33
- fleet-wide: 30 similar reports found
- signature matches catalog BILL-001 (typical routing: external)

**evidence against**
- none

**hypothesis:** vendor-side fault (BILL-001): the code match is the raise site in our billing client, not the cause
**revised call:** external, corroborated

want me to go deeper — assign this to the coding agent for a fix attempt? comment `/handoff` on this issue.
```

Two code hits, thirty corroborating reports, and a catalog entry that
says "external." The dossier calls it a vendor fault even though the
grep found our own code. That's the point of carrying the catalog into
this step instead of trusting the grep alone.

Now run it on an issue where the fault really is internal.

```bash
grep -m1 'consumer lag' data/issues/year1.ndjson > /tmp/int.json
python3 -m triage.investigate --issue /tmp/int.json --service qr
```

```
<!-- triage-dossier:v1 {"v": 1, "kind": "dossier", "issue": 21, "hypothesis": "regression or systemic fault in services/qr/ near services/qr/consumer.py", "revised": "internal, corroborated", "n_code_hits": 1, "n_fleet": 11} -->
### investigation (phase 2a)

**signature:** `consumer lag exceeded 90s on stream 'orders'`

**code evidence** (grep services/)
- `services/qr/consumer.py:52` — `f"consumer lag exceeded {int(lag)}s on stream '{STREAM}'",`

**change evidence** (recent commits, services/qr/)
- none found

**fleet evidence** (similar reports)
- 11 similar report(s): #703, #869, #898, #901, #21, #98

**evidence for**
- signature resolves to code: services/qr/consumer.py:52
- fleet-wide: 11 similar reports found
- signature matches catalog QR-001 (typical routing: internal)

**evidence against**
- none

**hypothesis:** regression or systemic fault in services/qr/ near services/qr/consumer.py
**revised call:** internal, corroborated

want me to go deeper — assign this to the coding agent for a fix attempt? comment `/handoff` on this issue.
```

This one pins the exact line, `services/qr/consumer.py:52`, where the
lag warning is raised. No catalog override here, the routing stays
internal because the code that raises it is the code that's wrong.

## the always-offer rule

Read the last line of both dossiers. Even the corroborated,
high-confidence PayFlow dossier ends with the same offer to go deeper:
comment `/handoff` and the issue moves to phase 2b. Confidence in the
evidence dossier is not the same gate as confidence in the rulebook.
The dossier can be sure of its hypothesis and still leave the door open,
because a human or the coding agent might see something the four
checks missed. Every dossier this script writes carries that line,
unconditionally, and that part is given, `render()` is not one of the
functions you write.

## checkpoint

Run the gate:

```bash
python3 -m pytest tests/chapters/test_ch05.py -q
```

All green means `grep_code` cites real, checked-in file paths and
never invents one, and `catalog_prior` picks the right entry on a
known signature, stays silent on a vague one, and resolves ties by
catalog order. You should now see the two dossiers above, one that
overrides its own code match with the catalog's external routing, one
that pins an internal fault to a single line. Both end with the same
handoff offer. `triage/run.py` calls this same `build_dossier()` path
whenever the rulebook's confidence falls below theta, so the live
workflow in layer 4 is already wired to produce this on real issues.

If you seeded the layer-4 tickets, you already have live subjects:
`seed_issues.py --expect` predicted exactly three would gate, the two
vague reports and the webhook one. Open any of them in the Issues tab
and the dossier is sitting there as a workflow comment below the
triage verdict. Compare it against a local run on the same issue:

```bash
gh issue view <n> --json title,body > /tmp/live.json
python3 -m triage.investigate --issue /tmp/live.json --service billing
```

Same catalog hit, same cited file, the comment and your terminal
agree because they run the same code.

### the heavy version

Four services is small enough that one grep and one git log cover the
whole company. Jane's Jeans at fifty services and hundreds of
engineers would need to split this dossier apart. Picture one agent
scoped only to the billing repos, another that only reads commit
history, another that only queries the issue tracker, each with
credentials that can't reach anything outside its one job, instead of
a single script with read access to the whole monorepo. The rulebook
would stop being a file checked into this repo and become a service of
its own, versioned, so a dozen consuming teams read the same rules
without redeploying anyone's code. The gate would still be two phases,
deterministic first, evidence-gathering only below theta, and the
dossier would still end with the same offer regardless of how
confident the hypothesis looks, because certainty in the evidence is
never a reason to stop asking a human if they want more.
