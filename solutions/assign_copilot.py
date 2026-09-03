"""Phase 2b: hand the issue to the Copilot coding agent.

Deliberately isolated in this one file — the assign API is the most
volatile surface in the whole tutorial. When GitHub moves it, this is
the only file that changes.

Current method (verify against docs before relying on it):
  1. GraphQL suggestedActors(capabilities:[CAN_BE_ASSIGNED]) to find
     the copilot-swe-agent bot id
  2. GraphQL replaceActorsForAssignable to assign it
The REST shortcut (`gh issue edit --add-assignee "@copilot"`) has
historically failed silently — that's why this is GraphQL.

Needs TRIAGE_PAT (fine-grained: issues:write, contents:write,
pull-requests:write) — GITHUB_TOKEN-triggered events deliberately
don't chain automations, and the coding agent needs a real actor.

Usage: python -m triage.assign_copilot --issue 123 --service billing
"""

import argparse
import json
import subprocess
import sys

SCOPING_COMMENT = """\
@copilot scope for this task:

- work ONLY inside `services/{service}/` — this is a monorepo and the \
other services are out of bounds
- read the investigation dossier in the comment above: it names the \
suspect files and the evidence
- reproduce first: `python -m pytest tests/ -q` must pass before and \
after your change
- open the PR as ready-for-review (draft PRs skip the auto-review \
ruleset)
- if the dossier's revised call is "external", do NOT patch code — \
comment what you verified and close the loop with a human
"""

# investigate-only: the agent reads code and reports, it does not patch.
# its output vehicle is still a PR, so the "PR" is a report file.
INVESTIGATE_COMMENT = """\
@copilot scope for this task — INVESTIGATE ONLY, do not patch:

- read the dossier and hypothesis comments above, then read the code \
in `services/{service}/` (other services are out of bounds)
- do NOT modify any source file. write your findings to \
`reports/issue-{issue}.md`: root cause hypothesis, evidence with \
file:line references, whether this is ours or vendor-side, and what a \
fix would involve
- open the PR ready-for-review containing only that report file
"""


def gql(query, **variables):
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        cmd += ["-f", f"{k}={v}"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def build_actor_lookup_query(owner, repo):
    """Build the GraphQL query + variables for finding the Copilot
    coding-agent bot's assignable-actor id."""
    query = """
    query($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        suggestedActors(capabilities: [CAN_BE_ASSIGNED], first: 100) {
          nodes { login __typename ... on Bot { id } ... on User { id } }
        }
      }
    }"""
    return query, {"owner": owner, "repo": repo}


def find_copilot_actor(owner, repo):
    query, variables = build_actor_lookup_query(owner, repo)
    data = gql(query, **variables)
    for node in data["data"]["repository"]["suggestedActors"]["nodes"]:
        if node["login"] == "copilot-swe-agent":
            return node["id"]
    return None


def issue_node_id(owner, repo, number):
    out = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/issues/{number}",
         "--jq", ".node_id"],
        capture_output=True, text=True, check=True)
    return out.stdout.strip()


def build_assign_mutation(issue_id, actor_id):
    """Build the GraphQL mutation + variables that assigns actor_id to
    issue_id via replaceActorsForAssignable."""
    query = """
    mutation($issueId: ID!, $actorIds: [ID!]!) {
      replaceActorsForAssignable(
        input: {assignableId: $issueId, actorIds: $actorIds}) {
        assignable { ... on Issue { number } }
      }
    }"""
    return query, {"issueId": issue_id, "actorIds": actor_id}


def assign(issue_id, actor_id):
    query, variables = build_assign_mutation(issue_id, actor_id)
    return gql(query, **variables)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", type=int, required=True)
    ap.add_argument("--service", required=True)
    ap.add_argument("--mode", choices=["fix", "investigate"], default="fix",
                    help="fix = patch + PR; investigate = report-only PR")
    ap.add_argument("--repo", default=None,
                    help="owner/repo, defaults to current")
    args = ap.parse_args()

    if args.repo:
        owner, repo = args.repo.split("/")
    else:
        out = subprocess.run(
            ["gh", "repo", "view", "--json", "owner,name",
             "--jq", '.owner.login + "/" + .name'],
            capture_output=True, text=True, check=True)
        owner, repo = out.stdout.strip().split("/")

    actor_id = find_copilot_actor(owner, repo)
    if not actor_id:
        print("copilot-swe-agent is not assignable on this repo.\n"
              "check: paid Copilot plan with the coding agent enabled, "
              "and the agent turned on in repo settings.", file=sys.stderr)
        return 1

    # post the scoping comment BEFORE assigning, so the agent reads it
    template = (INVESTIGATE_COMMENT if args.mode == "investigate"
                else SCOPING_COMMENT)
    subprocess.run(
        ["gh", "issue", "comment", str(args.issue),
         "--body", template.format(service=args.service, issue=args.issue)],
        check=True)

    node_id = issue_node_id(owner, repo, args.issue)
    assign(node_id, actor_id)
    print(f"assigned issue #{args.issue} to the Copilot coding agent "
          f"({args.mode} mode), scoped to services/{args.service}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
