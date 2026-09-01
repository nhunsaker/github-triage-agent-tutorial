# Layer 7: the coding agent

This layer needs a paid Copilot plan with the coding agent enabled, and
the agent turned on in your repo's settings. Layers 0 through 6 and 8
through 9 stay free. If you don't have the seat, read this layer for
the shape and skip the live steps, layer 8 does not depend on it.

The dossier from layer 5, and the hypothesis from layer 6 if you set up
a key for it, already name a suspect file or files. This layer hands
that evidence to an agent that can open a branch and write the fix, the
last and most capable rung of the three-phase investigation.

## why GraphQL, not the REST shortcut

`triage/assign_copilot.py` is one small file, deliberately. Open it.
The obvious move is `gh issue edit --add-assignee "@copilot"`, and it
has historically failed silently over REST, the call returns success
and nothing gets assigned. The known-good path is two GraphQL calls:

1. `suggestedActors(capabilities: [CAN_BE_ASSIGNED])` on the repo, to
   find the `copilot-swe-agent` bot's node id
2. `replaceActorsForAssignable`, to assign that id to the issue

`find_copilot_actor()` does the first call, `assign()` does the second.
Both go through `gh api graphql`, so no new dependency beyond the `gh`
CLI you already have.

This is the single most volatile surface in the whole tutorial. GitHub
has moved assignment APIs before and can again. That's exactly why it
lives in its own file instead of being inlined into the workflow: if it
breaks, one file changes. Before you rely on this in a real repo,
verify the call shape against GitHub's current docs, not this page.

## monorepo scoping, two layers

`on: issues` has no path filter. Left alone, the coding agent has no
signal to stay inside `services/billing/` instead of wandering into
`services/qr/`. Two documents fix that:

- `.github/copilot-instructions.md`, repo-wide, read on every task. It
  names the four services and states the standing rules: work only in
  the directory the scoping comment names, no new dependencies, run
  `pytest` before and after, and if the dossier's revised call is
  external, comment instead of patching.
- a per-issue scoping comment, generated fresh for each assignment,
  naming the one service directory for this task.

Read `SCOPING_COMMENT` in `assign_copilot.py`. `main()` posts it before
calling `assign()`, in that order, on purpose. The agent reads the
issue thread when it starts work, so the scoping has to already be
there when it looks.

## the review chain

Copilot opens a PR. Left alone, nobody reviews it. A repository ruleset
closes that gap: set it up once, by hand, in the GitHub UI.

1. repo Settings, then Rules, then Rulesets
2. New branch ruleset
3. target the default branch
4. enable "Request pull request review from Copilot"
5. save

Expected outcome: any PR opened ready-for-review against the default
branch gets a Copilot review requested automatically, no per-PR click
needed.

Two things trip people up here. Draft PRs skip the ruleset entirely,
the auto-review fires on "ready for review," not on draft-open, which
is why the copilot-instructions file tells the agent to open ready, not
draft. And re-review on a new commit isn't always automatic, if the
agent pushes a follow-up fix, you may need to re-request from the
Reviewers panel yourself.

Two agents chained: one opens the PR, the other reviews it. Neither
step needs a human in the loop to fire, only to read the result.

## the TRIAGE_PAT split

The default `GITHUB_TOKEN` that Actions hands you is enough for
labels and comments, layer 4 ran on it with no PAT at all. It is not
enough here, for two reasons. `GITHUB_TOKEN`-triggered events
deliberately don't chain further automations, that's GitHub's
anti-recursion guard, and the coding agent needs a real actor behind
the assignment, not a workflow-scoped token.

The fix is `TRIAGE_PAT`: a fine-grained personal access token scoped to
`issues:write`, `contents:write`, and `pull-requests:write`, stored as
a repo secret. That's the token `assign_copilot.py` needs to run.

Store it with `gh secret set TRIAGE_PAT` and paste at the prompt. A PAT
is worth more to an attacker than an API key, it acts as you across the
repo, so the same rule from layer 6 is stricter here: the token goes in
the GitHub secret store and nowhere else. Never in the YAML, never in a
commit. Scope it to this one repo and set an expiry so a slip has a
short blast radius.

## turning it on

`.github/workflows/triage.yml` has the Copilot-assign step already
written, commented out, at the bottom of the `investigate` job:

```yaml
      # phase 2c — Copilot coding agent. uncomment when the repo has a
      # Copilot seat and TRIAGE_PAT is set (layer 7 of the tutorial).
      # add --mode investigate for a report-only PR instead of a fix.
      # - name: hand off to the Copilot coding agent (phase 2c)
      #   env:
      #     GH_TOKEN: ${{ secrets.TRIAGE_PAT }}
      #   run: |
      #     python -m triage.assign_copilot \
      #       --issue "${{ github.event.issue.number }}" \
      #       --service "${{ needs.triage.outputs.service }}"
```

Do this once you have the seat and the ruleset:

1. add `TRIAGE_PAT` as a repository secret, the fine-grained token from
   above
2. uncomment the block
3. commit and push

Expected outcome on the next low-confidence issue: the dossier posts
as usual, the LLM hypothesis follows if you set one up, then a scoping
comment appears, then the issue gets assigned to Copilot. Within a few
minutes a PR shows up referencing the issue, opened ready-for-review,
with a Copilot review already requested on it.

## fix mode versus investigate mode

`assign_copilot.py` takes a `--mode` flag, `fix` by default. Pass
`--mode investigate` and the agent gets a different scoping comment,
one that asks it to read the code and write up what it finds in
`reports/issue-N.md` instead of opening a patch. Same agent, same
scoping discipline, no PR that touches `services/`. Useful when you
want the coding agent's read of the code without handing it write
access to production paths, or when the dossier's revised call is
external and there's nothing to patch anyway.

## checkpoint

With the seat and the ruleset live, a low-confidence issue should walk
itself from dossier to assignment to PR to requested review with no
human step in between. Without the seat, you've read the shape: one
isolated, verify-before-trusting module for the assign call, two
documents for scoping, one ruleset for the review chain, and a token
split that exists because the default token can't chain automations by
design.

### the heavy version

One coding agent scoped by a comment works when there are four
services and one repo. At the size where Jane's Jeans has dozens of
services owned by dozens of teams, a single general-purpose agent
assigned by issue label stops being enough, you'd want a fleet of
agents, each one scoped in advance to the one service it's allowed to
touch, with credentials that physically can't reach the others rather
than a comment asking politely. The confidence gate would stay exactly
this shape, deterministic first, an agent dispatched only below theta.
The review step would stop being a UI ruleset you click once and
become a policy enforced at the platform level, so a PR that skips
review can't merge no matter who or what opened it. Two agents chained
either way, one writes, one checks the writing, the difference at
scale is that neither step trusts a single shared credential to do it.
