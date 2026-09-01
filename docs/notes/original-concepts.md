# Source notes for layer 0 (the original README, preserved)

## 1. GitHub Actions — the vocabulary

"GitHub Actions" is the automation/CI platform built into GitHub. The word "action" is overloaded:

- **Workflow** — a YAML file in `.github/workflows/` that says *"when X happens, run these steps."*
- **Event / trigger** (`on:`) — what starts it: `push`, `pull_request`, `issues`, `schedule` (cron),
  `workflow_dispatch` (manual), etc.
- **Job** — a unit of work that runs on a **runner** (a fresh VM: GitHub-hosted `ubuntu-latest`, or
  self-hosted).
- **Step** — one thing in a job. Either runs shell (`run: python foo.py`) or **uses a reusable
  action** (`uses: actions/checkout@v4`).
- **An action** (noun) — a packaged, reusable step someone published (checkout, setup-python, …).

Model: **event → workflow → job(s) on a runner → steps.**

## 2. CI vs CD (context)

- **CI (Continuous Integration)** — merge to a shared branch often; every change auto-builds + tests
  so integration problems surface in minutes, not weeks.
- **CD** splits into two:
  - **Continuous Delivery** — every passing change is packaged and *ready to ship*; a human clicks
    deploy.
  - **Continuous Deployment** — every passing change ships to prod automatically, no human gate.
- Naming which one you mean is the tell that you know the distinction.

## 3. Copilot on PRs — the two surfaces (important distinction)

There are **two different Copilots**, and they do different jobs:

1. **Copilot code review** — reviews a **PR diff**. It comments on changes; it does *not* review "a
   monorepo" in the abstract. Needs a pull request to look at.
2. **Copilot coding agent** — the autonomous one. **Assign an issue to it**, it works in the repo on
   a branch, makes changes, and **opens a PR**. This is the surface that "works on code in a
   monorepo."

### Triggering Copilot code review on a PR
- **Prereq:** a paid Copilot plan that includes code review (Pro / Pro+ / Business / Enterprise). Not
  in free tier.
- **Manual, per-PR:** PR → Reviewers gear → select **Copilot**. Reviews in ~30s, posts inline
  comments + summary.
- **Automatic on every PR:** create a **repository ruleset** — Repo → Settings → Rules → Rulesets →
  New branch ruleset → target the default branch → enable **"Request pull request review from
  Copilot"**.
- **Draft PRs are skipped.** The auto-review fires when a PR is opened **ready for review** or moved
  from **draft → "Ready for review."** So: iterate freely in draft, click "Ready for review" to
  trigger.
- **Re-review on new commits:** not always automatic — re-request from the Reviewers panel (refresh
  icon next to Copilot).
- **Advisory by default:** Copilot's review comments don't block merge unless you also add a
  required-review branch rule.

## 4. The target pipeline: issue → Python → Copilot in a monorepo

```yaml
on:
  issues:
    types: [opened]

jobs:
  handle-issue:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      issues: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4          # the whole monorepo
      - uses: actions/setup-python@v5
      - run: python scripts/triage.py       # your Python step (parse issue, decide scope, label)
      # then hand the issue to the Copilot coding agent:
      - run: gh issue edit ${{ github.event.issue.number }} --add-assignee "@copilot"
        env: { GH_TOKEN: ${{ secrets.PAT }} }
```

Flow: **`issues.opened` → runner checks out monorepo → Python does triage/prep → assign issue to the
Copilot coding agent → agent works in the repo and opens a PR → the ruleset from §3 auto-requests
Copilot code review on that PR.** Two agents chained: one does the work, one reviews it.

### Gotchas that will actually bite
- **Review vs. work.** Decide up front: Copilot *making changes* (coding agent, issue-assigned) vs.
  Copilot *commenting on a PR* (code review, PR-scoped). "Review code in a monorepo" with no PR really
  means the agent → PR → review chain above.
- **Plan gating.** The coding agent needs the right Copilot tier (Business/Enterprise, or Pro+
  depending) and to be enabled for the repo. Verify first.
- **Token permissions.** Default `GITHUB_TOKEN` can't kick off other automations and can't do
  everything (assigning to the Copilot agent, triggering downstream workflows). Use a **PAT or GitHub
  App token** for the agent-assign step.
- **Loop prevention.** Actions triggered by `GITHUB_TOKEN` deliberately don't trigger further
  workflows (anti-recursion). Rulesets aren't workflows, so the Copilot-review ruleset still fires on
  the agent's PR — but workflow→workflow chaining would need a PAT.
- **Monorepo scoping.** `on: issues` has no path filter. Scope "only touch `packages/billing/`" in the
  Python step and/or a repo `copilot-instructions.md` the agent reads to stay in bounds.

## 5. Open item to verify (docs move fast)
The exact API/`gh` call to **assign an issue to the Copilot coding agent from within an Action** is the
step most likely to have changed — confirm against current GitHub docs before relying on it.
