# Layer 5: the investigation

Layer 3 trained a rulebook that hits a wall around 80%. Below the
confidence gate, the bot should not guess. It should look. `triage/investigate.py`
builds an evidence dossier with zero LLM calls: grep, git log, and a
search over past issues. Evidence first, then hand off. Free tier, no
PAT.

## the four evidence sources

Open `triage/investigate.py`. `build_dossier()` runs four checks in
order.

**1. code evidence.** `grep_code()` pulls the quoted error line out of
the issue body, strips the parts that vary (ids, numbers, quoted
values), and greps `services/` for the stable words that remain. A
filled-in id like `event_887a2` never appears in the source template,
only the literal words around it do. That's the stable-fragment trick:
match on what the code actually contains, not what the reporter typed
in.

**2. change evidence.** `recent_commits()` runs `git log --oneline -8`
scoped to the suspect service directory. Did something ship there
recently.

**3. fleet evidence.** `fleet_check()` searches other issues for the
same signature fragment. One report is an anecdote. Several in a
window is a pattern, and the corroboration rule from layer 3 already
told you why that distinction matters for routing.

**4. catalog prior.** `catalog_prior()` matches the signature back to
`data/error_catalog.yaml` and reads its typical routing. This is the
step that keeps the dossier honest.

## the catalog-prior lesson

A grep hit on `services/billing/payflow.py` looks like proof the bug is
ours. It isn't. That file is where our client *raises* the error after
the vendor's API returns a 503. The code match tells you where the
failure surfaces, not where it originates. The catalog knows the
difference because it records each signature's typical routing, so a
match against an entry marked `external` overrides the naive "code
found it, code owns it" read.

Run it on a real corpus issue to see this play out.

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
unconditionally.

## checkpoint

You should now see two dossiers, one that overrides its own code match
with the catalog's external routing, one that pins an internal fault to
a single line. Both end with the same handoff offer. `triage/run.py`
calls this same `build_dossier()` path whenever the rulebook's
confidence falls below theta, so the live workflow in layer 4 is
already wired to produce this on real issues.

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
