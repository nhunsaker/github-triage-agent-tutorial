# Layer 9: going further

Jane's Jeans is fictional so the corpus could be designed to teach a
specific lesson. Your repo isn't designed, it's just what you've got.
Here's what changes when you point this at a real codebase, and what
this tutorial left out on purpose.

## what replaces the error catalog

`data/error_catalog.yaml` worked because someone wrote it down: every
failure mode, the file and symbol that raises it, its typical severity
and routing. In a real repo nobody wrote that file. Your exception
classes and your log messages already are the catalog, they're just
scattered instead of collected.

Start the same way `investigate.py`'s `grep_code()` does, but pointed
at your own history instead of a corpus:

```bash
grep -rn "raise \|logger.error(\|logger.warning(" src/ | head -50
```

Read through it and pull out the ones that show up in issues or pages
repeatedly. That short list, message template, file, typical severity,
typical routing, is your catalog's first draft. You don't need all of
it before you start, the training protocol from layer 3 is built to
grow the rulebook incrementally against whatever catalog you have.

## what replaces ground truth

The corpus paired every issue with `ground_truth`, the answer key. You
won't have that. What you have instead is your closed issues and the
PRs that fixed them, and that's a better source than a hand-labeled
answer key because it's real. Mine it the way layer 8's `capture` step
does: for each closed issue, what would the rulebook have said, and
what actually happened. The commit that closed it names the real
service. The final labels, if your tracker has any, name the real
severity and routing. Feed that into `triage/labels.jsonl` directly and
you've bootstrapped a training set without ever running the corpus
generator.

## more on the LLM hypothesis versus the coding agent

Layer 6 already built the one-API-key path, `triage/investigate_llm.py`
does the dossier-to-hypothesis jump with a single Claude call, no
Copilot seat required. Layer 7's coding agent goes further, it opens a
branch and writes a patch, but it needs the paid seat to do it. Now
that you've run both, here's how to think about picking between them
on your own repo.

`investigate_llm.py` isolates every provider-specific line inside
`ask_claude()`. Swapping to a different vendor's API means rewriting
that one function, the request shape and the response parsing change,
but the interface around it doesn't: dossier and file excerpts go in,
a hypothesis dict comes out, `render()` doesn't care which provider
produced it.

Tradeoffs against the coding agent:

- **provider choice.** Any LLM API works once you've rewritten
  `ask_claude()`, you're not locked to one vendor's coding-agent
  product.
- **API key management.** `ANTHROPIC_API_KEY` is a secret you own,
  same blast radius as `TRIAGE_PAT` if it leaks. Copilot's approach
  avoids this because the key lives in your GitHub plan, not your
  workflow.
- **cost per call.** One model call per gated issue, cents at most,
  versus a Copilot seat's flat monthly cost that covers unlimited
  coding-agent assignments. Below some issue volume the API is
  cheaper, above it the seat is. `TRIAGE_LLM_MODEL` lets you point at a
  cheaper model if per-issue cost matters more than hypothesis depth.
- **what you get back.** A hypothesis and a fix direction, not a PR.
  If you want code written and tested, you're back to needing an agent
  with repo write access, the coding agent or something like it.

## token permissions, recap

Four things guard access, in order of how much they can do:

- default `GITHUB_TOKEN`, scoped to the workflow run. Enough for
  labels and comments and both evidence steps, layers 0 through 6.
  Cannot chain further automations, by design, that's the
  anti-recursion guard.
- `ANTHROPIC_API_KEY`, a repo secret with no GitHub scope at all, it
  authenticates against the model provider, not the repo. Needed only
  for the LLM hypothesis in layer 6, and the step soft-skips without
  it.
- `TRIAGE_PAT`, a fine-grained personal access token with
  `issues:write`, `contents:write`, `pull-requests:write`. Needed only
  for the Copilot assign step in layer 7, because that step needs a
  real actor behind it, not a workflow-scoped token.
- your own GitHub account's normal permissions, needed once, by hand,
  to set up the repository ruleset that requests Copilot review.
  Nothing in the workflow needs a token for that, it's a repo setting.

## honest limits

- **rules plateau.** Layer 3 trains to roughly 80% and stops moving no
  matter how many more rules you add, because the remaining issues are
  genuinely ambiguous, vague reports, novel failures, cross-service
  bait. More rules against a wall don't move the wall.
- **vague reports still need a human.** A dossier with no code hits and
  no fleet corroboration says exactly that, "insufficient evidence,
  human review needed." That's a correct answer, not a failure of the
  investigation step, some reports don't have enough signal in them for
  any deterministic pass to resolve.
- **the corroboration rule trades recall for safety.** An external call
  at S0 needs fleet-wide evidence before it routes external. An S1
  external, a declined refund or a deprecation notice, stands on its
  own signature. That means a real single-report outage sits at lower
  confidence and goes to phase 2 instead of auto-routing, on purpose.
  You lose some cases the rule could have gotten right alone, in
  exchange for not auto-routing a real internal outage as "someone
  else's problem" on a single ambiguous report.

## costs

- **Actions minutes.** GitHub's free tier includes 2,000 minutes a
  month for private repos, unlimited for public ones. Every layer
  through 6 and 8 runs well inside that, the workflows here finish in
  under a minute per issue.
- **LLM API calls.** One model call per issue that clears the
  confidence gate, cents each at tutorial volume. `TRIAGE_LLM_MODEL`
  swaps in a cheaper model if that number matters at your issue
  volume.
- **Copilot tiers.** The coding agent and automatic code review both
  need a paid plan, Pro+, Business, or Enterprise depending on the
  feature. Check GitHub's current pricing page before committing,
  tiers and inclusions change more often than the rest of this stack.

## checkpoint

You should now have a plan for pointing this at a real repo: grep your
own exceptions and logs for a starter catalog, mine your closed issues
for ground truth instead of generating a corpus, and a clear read on
when the LLM hypothesis from layer 6 covers what you need versus when
the coding agent's paid seat earns its cost. Everything from layer 0
through layer 6, plus the flywheel in layer 8, runs on the free tier
either way.

### the heavy version

Jane's Jeans starts with four services and a catalog someone hand
wrote in an afternoon. Grown to hundreds of engineers and dozens of
services, nobody could hand write that file anymore, it would have to
grow the way this layer describes for your own repo, mined from real
exception classes and log lines as they accumulate, not authored up
front. Ground truth would come from closed tickets and the engineers
who resolved them, the same source this layer points you to, just at
a volume where mining it needs its own tooling instead of a grep
command. The limits wouldn't go away at that size either. A rulebook
or a trained engine both plateau against genuinely ambiguous reports,
vague issues would still land on a human's desk, and the corroboration
rule would still trade some recall for safety on single-report claims,
because that trade doesn't get safer just because the company got
bigger.
