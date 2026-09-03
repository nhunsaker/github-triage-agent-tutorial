# Layer 8: build the flywheel

Layer 3 trained a rulebook and hit a wall. Real issue traffic drifts
past whatever the rulebook learned, and the fix is not to retrain from
scratch, it's to turn every human correction into a training label. You
build that mechanism yourself, in four steps, each one runnable and
checkable on its own before you wire the next.

Your working copy is `triage/flywheel.py`. The plumbing is given, the
CLI, the live `gh` sweep, the corpus replay, because fetching issues is
not the lesson. The four functions that are the lesson raise
`NotImplementedError` until you write them: `diff`, `accumulate`,
`measure`, `suggest`. Each one's docstring is its contract, and each
step below is one of them. `solutions/flywheel.py` is the finished
version, for comparison after you've built it, not before. The loop is
the lesson.

Your gate for this layer:

```bash
python3 -m pytest tests/chapters/test_ch08.py -q
```

On a fresh clone every test in it skips with "chapter 8 not started".
As you land each step, its tests flip from skipped to green. All green
means the flywheel is built and your numbers should match the ones
printed below.

## the signal

Every triage comment carries a hidden machine block, an HTML comment
tagged `triage:v1` with the decision as JSON. It records what the bot
decided when the issue opened, service, severity, routing, each with a
confidence. When
a human closes the issue, the labels on it at that point are the
ground truth the bot should have produced. The gap between the two is
a training label.

## step 1: capture

Diff the bot's decision against the labels at close. The capture
plumbing already walks closed issues (or replays the corpus) and hands
each one to `diff`, the function you write. Open `triage/flywheel.py`,
read `diff`'s docstring, and implement it: one correction record per
dimension where the human's label at close disagrees with the bot's
decision at open.

Until `diff` exists the command below dies with
`NotImplementedError: chapter 8`. That's the shape of this whole layer,
the scaffold runs, the core is yours.

```bash
rm -f triage/labels.jsonl
python3 -m triage.flywheel capture --simulate --year 2
```

```
captured 265 corrections
  #441 routing: human → external
  #442 severity: S2 → S1
  #449 severity: S2 → S1
  #450 routing: human → external
  #459 routing: external → internal
  #465 severity: S2 → S1
  #467 routing: internal → human
  #467 severity: S2 → S3
  #467 service: dashboard → api
  #469 routing: internal → human
```

`--simulate --year 2` replays year 2 of the corpus and treats ground
truth as the labels a human would have left at close, so the whole loop
is walkable with no live repo. `capture` alone only prints, it doesn't
write anything yet, that's step 2.

## step 2: accumulate

Append the corrections to `triage/labels.jsonl`, the flywheel's
training set. Implement `accumulate` next. The docstring pins the two
behaviors that matter: the dedup key is `(issue, dimension)`, and
re-running is idempotent.

```bash
python3 -m triage.flywheel accumulate --simulate --year 2
```

```
accumulated 265 new corrections (265 total in triage/labels.jsonl)
```

Run it again and the count of new corrections drops to zero, it
dedupes on `(issue, dimension)` so re-running the sweep is safe.

## step 3: measure

Fold the corrections back in and look at what they say. `measure` is
an aggregation: read the file, bucket by dimension, count the
bot-to-human pairs, print the biggest first.

```bash
python3 -m triage.flywheel measure
```

```
265 corrections on file

routing: bot → human (count)
    internal → human      37
       human → external   14
    external → internal   14
       human → internal   9

severity: bot → human (count)
          S2 → S1         114
          S1 → S3         7
          S2 → S3         6
          S1 → S2         4

service: bot → human (count)
   dashboard → qr         11
     billing → api        9
         api → billing    6
     unknown → billing    5
         api → dashboard  5
     unknown → dashboard  5
   dashboard → api        4
     unknown → qr         4
```

One row jumps out: `S2 → S1`, 114 times. The rulebook is calling
something an S2 that humans keep re-labeling S1. That's not noise, it's
a pattern big enough to act on, which is what step 4 is for.

## step 4: suggest

Cluster the corrections on the catalog signature they share, and
propose the rule that's missing. `suggest` is the one function here
with real moving parts, matching excerpts against the catalog's
message templates and turning a big cluster into a rulebook-ready
fragment. Its docstring walks the whole contract, including the
placeholder-to-wildcard regex trick.

```bash
python3 -m triage.flywheel suggest
```

```
# proposed rule from 82 corrections clustered on BILL-004:
  - id: fly-bill-004
    match: "PayFlow v1 endpoint "
    service: billing
    severity: S1
    routing: external
    confidence: 0.85  # 82 human corrections agree

# proposed rule from 19 corrections clustered on DASH-001:
  - id: fly-dash-001
    match: "orders feed stale for"
    service: dashboard
    severity: S2
    routing: human
    confidence: 0.85  # 19 human corrections agree

# proposed rule from 14 corrections clustered on BILL-001:
  - id: fly-bill-001
    match: "PayFlow API unreachable: 503 from"
    service: billing
    severity: S0
    routing: external
    confidence: 0.85  # 14 human corrections agree

# proposed rule from 14 corrections clustered on BILL-002:
  - id: fly-bill-002
    match: "webhook signature verification failed for delivery"
    service: billing
    severity: S1
    routing: internal
    confidence: 0.85  # 14 human corrections agree
```

## the payoff, with real numbers

Here's why 82 corrections cluster on one catalog id. Open
`solutions/rulebook.yaml` and read its header comment: it deliberately
has no rule for BILL-004, the PayFlow v1 deprecation. That failure mode
doesn't exist in year 1, so the reader training the rulebook in layer 3
never sees it and never writes a rule for it. Year 2 introduces it as
drift, exactly the kind of thing a rulebook trained on last year's
issues can't know about.

Check the baseline:

```bash
python3 -m triage.eval --year 2 --rulebook solutions/rulebook.yaml
```

```
routing top-1:   84.0%
severity:        71.7%
service:         87.0%
sent to phase 2: 40.2%  (below theta)
```

Severity sits at 71.7%, dragged down by the missing BILL-004 case
firing the `S2 → S1` correction 114 times, 82 of those clustered
tightly enough on one signature to become the `suggest` step's top
proposal. And look at the gate line: 40.2% of year 2 falls below theta
and gets sent to phase 2. Drift doesn't just cost severity accuracy, it
floods the investigation queue, every one of those PayFlow v1 issues
lands on the rulebook with no matching rule, so it can't clear the
confidence gate and gets kicked to the dossier step instead. That's
real load on phase 2 for a failure mode a rule could have handled in
phase 1.

Splice that proposed rule into the rulebook and re-run eval:

```
routing top-1:   84.0%
severity:        89.4%
service:         87.0%
sent to phase 2: 22.5%  (below theta)
```

Severity moves from 71.7% to 89.4%. Routing holds steady at 84.0%,
because the correction was about severity, not which team owns the
fault. And the gate load nearly halves, 40.2% down to 22.5%, because
the whole PayFlow v1 cluster now resolves at high confidence in phase 1
and never reaches the investigation queue. One clustered correction,
one rule, an 18-point jump on the dimension it targeted, a matching
drop in phase-2 load, and no regression on the others.

## close the loop

Wrap the four steps into a scheduled workflow. `solutions/flywheel.yml`
is the finished copy: weekly cron plus `workflow_dispatch` for a manual
run, it captures and accumulates against live closed issues, runs
`measure` and `suggest`, and if `labels.jsonl` changed, opens a PR
carrying the correction batch and any proposed rulebook edits.

```yaml
      - name: open the correction PR
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          if git diff --quiet triage/labels.jsonl; then
            echo "no new corrections this week"; exit 0
          fi
          branch="flywheel/$(date +%Y-%m-%d)"
          git checkout -b "$branch"
          git add triage/labels.jsonl
          git -c user.name=flywheel -c user.email=flywheel@users.noreply.github.com \
            commit -m "flywheel: weekly correction batch"
          git push origin "$branch"
          gh pr create --title "flywheel: correction batch $(date +%Y-%m-%d)" \
            --body-file body.md
```

The "retrain" here is that PR. Nothing merges automatically, a human
reads the correction counts and the proposed rule and decides whether
it holds up, same as reviewing any other change. To activate it, copy
`solutions/flywheel.yml` to `.github/workflows/flywheel.yml`.

Regenerate a clean `labels.jsonl` before you move on, the run above
left the file mid-experiment:

```bash
rm -f triage/labels.jsonl
python3 -m triage.flywheel capture --simulate --year 2
python3 -m triage.flywheel accumulate --simulate --year 2
```

## checkpoint

Run the gate:

```bash
python3 -m pytest tests/chapters/test_ch08.py -q
```

Nine green, none skipped. Then check the artifacts.
You should now have `triage/labels.jsonl` holding 265 corrections from
the year-2 simulation, a `measure` table showing where the rulebook and
reality disagree, and a `suggest` output that names the exact rule
year 1 couldn't have written. On a live repo, closing a batch of
relabeled issues and letting `flywheel.yml` run produces the same
sequence against real data: a PR, a correction count, a proposed edit.

This is the whole point of the layer. The flywheel is not a new idea
bolted onto the tutorial, it's layer 3's training protocol, the one you
ran by hand, mine, write a rule, re-eval, repeat, running unattended on
a schedule instead of at your keyboard.

### the heavy version

265 corrections from two years of a four-service company fit in a
text file and cluster by eye. At thousands of issues a month across
dozens of services, the label diff is still the same idea, bot
decision versus human correction, but `labels.jsonl` would stop being
a file and become a feed into a real training pipeline, and the
`suggest` step's simple clustering would stop being enough to catch
every drift pattern on its own. The engine on the other end might be
trained rather than rule-based at that volume. What wouldn't change is
the shape: every correction becomes a training signal, the retrain
still runs on a schedule, and the result still comes back as something
a human reviews before it goes live, the same PR gate this layer builds
with plain GitHub infra, just fed by a bigger pipe.
