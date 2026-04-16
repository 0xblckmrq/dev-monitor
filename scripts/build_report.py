import json, os, subprocess, datetime, sys

TOKEN = os.environ.get("GH_TOKEN", "")
SINCE = (datetime.datetime.utcnow() - datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
TODAY = datetime.datetime.utcnow().strftime("%Y-%m-%d")

def gh(path):
    r = subprocess.run(
        ["curl", "-sf", "-H", f"Authorization: Bearer {TOKEN}",
         f"https://api.github.com{path}"],
        capture_output=True, text=True
    )
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}

def commits(repo):
    data = gh(f"/repos/{repo}/commits?since={SINCE}&per_page=10")
    if not isinstance(data, list):
        return 0, ["  (unavailable)"]
    lines = [f"  {c['sha'][:7]} {c['commit']['message'].splitlines()[0]}" for c in data]
    return len(data), lines or ["  (none)"]

def prs(repo):
    data = gh(f"/repos/{repo}/pulls?state=open&per_page=10")
    if not isinstance(data, list):
        return 0, ["  (unavailable)"]
    lines = [f"  #{p['number']} {p['title']}" for p in data]
    return len(data), lines or ["  (none)"]

def branches(repo):
    data = gh(f"/repos/{repo}/branches?per_page=100")
    if not isinstance(data, list):
        return [], "(unavailable)"
    non_main = [b["name"] for b in data if b["name"] not in ("main", "master")]
    return non_main, "\n".join(f"  {b}" for b in non_main) or "  (none)"

REPOS = [
    ("holonym-foundation/docs.human.tech", "docs.human.tech", "holonym-foundation"),
    ("0xblckmrq/human.tech.AI",            "human.tech.AI",   "0xblckmrq"),
    ("0xblckmrq/human.tech.bot",           "human.tech.bot",  "0xblckmrq"),
]

sections = []
all_branches = {}

for slug, name, org in REPOS:
    n_commits, commit_lines = commits(slug)
    n_prs, pr_lines = prs(slug)
    branch_list, branch_str = branches(slug)
    all_branches[slug] = branch_list

    sections.append(
        f"📁 {name} ({org})\n"
        f"Commits (24h): {n_commits}\n"
        + "\n".join(commit_lines) + "\n"
        f"Open PRs: {n_prs}\n"
        + "\n".join(pr_lines) + "\n"
        f"Branches (non-main):\n{branch_str}"
    )

# internal-docs (private)
internal = gh("/repos/holonym-foundation/internal-docs/commits?since={SINCE}&per_page=1")
i_commits = len(internal) if isinstance(internal, list) else "private repo"
internal_pr = gh("/repos/holonym-foundation/internal-docs/pulls?state=open&per_page=1")
i_prs = len(internal_pr) if isinstance(internal_pr, list) else "private repo"
sections.append(
    f"📁 internal-docs (holonym-foundation)\n"
    f"Commits (24h): {i_commits}\n"
    f"Open PRs: {i_prs}"
)

# Risk analysis
risks = []
ai_branches = all_branches.get("0xblckmrq/human.tech.AI", [])
known_long_lived = {"staging"}
feature_branches = [b for b in ai_branches if b not in known_long_lived]
if len(feature_branches) >= 5:
    risks.append(
        f"human.tech.AI has {len(feature_branches)} unmerged feature branches "
        f"({', '.join(feature_branches[:4])}, …) — review for staleness."
    )

total_commits = sum(
    commits(s)[0] for s, _, _ in REPOS
)
if total_commits == 0:
    risks.append("Zero commits across all repos in the last 24h — confirm this is expected.")

risk_block = "\n".join(f"{i+1}. {r}" for i, r in enumerate(risks)) if risks else "No critical risks detected."

next_actions = [
    "Review and merge or close stale branches in human.tech.AI.",
    "Confirm docs.human.tech is still active and publicly accessible.",
    "Add a scoped PAT secret (HOLONYM_TOKEN) to enable internal-docs monitoring.",
]
actions_block = "\n".join(f"{i+1}. {a}" for i, a in enumerate(next_actions))

report = f"""📊 DAILY DEV REPORT — {TODAY} UTC

━━━━━━━━━━━━━━━━
{chr(10).join(chr(10).join(["", s]) for s in sections)}

━━━━━━━━━━━━━━━━
⚠️  RISKS
{risk_block}

✅ NEXT ACTIONS
{actions_block}
"""

with open("/tmp/daily-report.txt", "w") as f:
    f.write(report)

print(report)
