# Instructions for the Copilot coding agent

This is the Jane's Jeans monorepo. Four services live under `services/`:
qr (queue reader), api (orders + inventory), dashboard (React store-ops
UI), billing (PayFlow vendor integration).

Standing rules, they apply to every task:

- Work only inside the single service directory named in the issue's
  scoping comment. Never touch the other services in the same PR.
- Python services: no new dependencies beyond requirements.txt. The
  dashboard is plain JavaScript React, never TypeScript.
- Run `python -m pytest tests/ -q` before and after changes, both must
  pass, and add a test that covers your fix.
- Every issue you receive has a triage comment and usually an
  investigation dossier. Read both, the dossier names suspect files.
- If the dossier's revised call is "external", the fault is on the
  vendor side. Do not patch our code to mask it, comment your findings
  instead.
- Do not modify data/error_catalog.yaml, the corpus in data/, or the
  triage/ engine. Those are the tutorial's instruments, not the app.
- Open PRs ready-for-review, not draft. Draft PRs skip the auto-review
  ruleset.
