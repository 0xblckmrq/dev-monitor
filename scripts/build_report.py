import json, os, subprocess, datetime, sys

TOKEN = os.environ.get("GH_TOKEN", "")
NOW = datetime.datetime.utcnow()
SINCE = (NOW - datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
TODAY = NOW.strftime("%Y-%m-%d")

ME = "0xblckmrq"  # filter org repos to only my activity

def gh(path):
    headers = ["-H", f"Authorization: Bearer {TOKEN}"] if TOKEN else []
    r = subprocess.run(
        ["curl", "-sf"] + headers + [f"https://api.github.com{path}"],
        capture_output=True, text=True
    )
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}

def age(iso):
    try:
        dt = datetime.datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
        delta = NOW - dt
        if delta.days > 0:
            return f"{delta.days}d ago"
        hours = delta.seconds // 3600
        return f"{hours}h ago" if hours > 0 else "just now"
    except Exception:
        return "?"

def commits(repo, filter_user=None):
    data = gh(f"/repos/{repo}/commits?since={SINCE}&per_page=30")
    if not isinstance(data, list):
        return 0, ["  (unavailable — private repo or API limit)"]
    if filter_user:
        data = [c for c in data if
                c.get("author") and c["author"].get("login", "").lower() == filter_user.lower()]
    lines = [
        f"  {c['sha'][:7]} {c['commit']['message'].splitlines()[0]}"
        for c in data
    ]
    return len(data), lines or ["  (none in last 24h)"]

def my_prs(repo):
    """PRs created by me or assigned to me or requesting my review."""
    created, assigned, review_requested = [], [], []

    # created by me
    data = gh(f"/repos/{repo}/pulls?state=open&per_page=50")
    if isinstance(data, list):
        for p in data:
            draft = " [DRAFT]" if p.get("draft") else ""
            opened = age(p["created_at"])
            line = f"  #{p['number']} {p['title']}{draft} — opened {opened}"
            author = (p.get("user") or {}).get("login", "")
            assignees = [(a.get("login","")) for a in p.get("assignees", [])]
            reviewers = [(r.get("login","")) for r in p.get("requested_reviewers", [])]

            if author.lower() == ME.lower():
                created.append(line)
            elif ME.lower() in [a.lower() for a in assignees]:
                assigned.append(line)
            elif ME.lower() in [r.lower() for r in reviewers]:
                review_requested.append(line)

    return created, assigned, review_requested

def all_prs(repo):
    """All open PRs — used for own repos."""
    data = gh(f"/repos/{repo}/pulls?state=open&per_page=20")
    if not isinstance(data, list):
        return 0, []
    lines = []
    for p in data:
        opened = age(p["created_at"])
        assignee = p["assignee"]["login"] if p.get("assignee") else "unassigned"
        draft = " [DRAFT]" if p.get("draft") else ""
        lines.append(f"  #{p['number']} {p['title']}{draft} — {assignee}, opened {opened}")
    return len(data), lines or ["  (none)"]

def branch_details(repo, filter_user=None):
    data = gh(f"/repos/{repo}/branches?per_page=100")
    if not isinstance(data, list):
        return [], []
    non_main = [b for b in data if b["name"] not in ("main", "master")]

    # for org repos, only show branches with my name or username pattern
    if filter_user:
        non_main = [b for b in non_main if filter_user.lower() in b["name"].lower()]

    details = []
    stale = []
    for b in non_main:
        commit_data = gh(f"/repos/{repo}/commits/{b['commit']['sha']}")
        last_date = ""
        days_old = 0
        if isinstance(commit_data, dict):
            iso = commit_data.get("commit", {}).get("author", {}).get("date", "")
            last_date = age(iso)
            try:
                dt = datetime.datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
                days_old = (NOW - dt).days
            except Exception:
                pass
        stale_flag = " ⚠️ STALE" if days_old > 30 else ""
        details.append(f"  {b['name']} — last commit {last_date}{stale_flag}")
        if days_old > 30:
            stale.append(b["name"])
    return details, stale

def issue_count(repo):
    data = gh(f"/repos/{repo}?per_page=1")
    if isinstance(data, dict):
        return data.get("open_issues_count", "?")
    return "?"

def my_issues(repo):
    """Issues assigned to me."""
    data = gh(f"/repos/{repo}/issues?assignee={ME}&state=open&per_page=20")
    if not isinstance(data, list):
        return []
    # exclude PRs (GitHub issues API returns PRs too)
    issues = [i for i in data if "pull_request" not in i]
    return [f"  #{i['number']} {i['title']} — opened {age(i['created_at'])}" for i in issues]

# ── Own repos (full report) ──────────────────────────────────────────────────
OWN_REPOS = [
    ("0xblckmrq/human.tech.AI",  "human.tech.AI",  "0xblckmrq"),
    ("0xblckmrq/human.tech.bot", "human.tech.bot", "0xblckmrq"),
]

# ── Org repos (my activity only) ─────────────────────────────────────────────
ORG_REPOS = [
    ("holonym-foundation/docs.human.tech", "docs.human.tech",  "holonym-foundation"),
    ("holonym-foundation/internal-docs",   "internal-docs",    "holonym-foundation"),
]

sections = []
all_stale = {}
all_pr_counts = {}
zero_commit_repos = []

# Own repos — full detail
for slug, name, org in OWN_REPOS:
    n_commits, commit_lines = commits(slug)
    n_prs, pr_lines = all_prs(slug)
    branch_lines, stale_branches = branch_details(slug)
    all_stale[slug] = stale_branches
    all_pr_counts[slug] = n_prs
    if n_commits == 0:
        zero_commit_repos.append(name)

    branch_block = "\n".join(branch_lines) if branch_lines else "  (none)"
    sections.append(
        f"📁 {name} ({org})\n"
        f"Open PRs: {n_prs}  |  Commits (24h): {n_commits}\n"
        + "\n".join(commit_lines) + "\n"
        + (f"PRs:\n" + "\n".join(pr_lines) + "\n" if pr_lines and pr_lines != ["  (none)"] else "PRs: (none)\n")
        + f"Branches:\n{branch_block}"
    )

# Org repos — my activity only
for slug, name, org in ORG_REPOS:
    n_commits, commit_lines = commits(slug, filter_user=ME)
    created_prs, assigned_prs, review_prs = my_prs(slug)
    branch_lines, stale_branches = branch_details(slug, filter_user=ME)
    my_issue_lines = my_issues(slug)
    all_stale[slug] = stale_branches

    if n_commits == 0 and not created_prs and not assigned_prs and not review_prs:
        zero_commit_repos.append(name)

    branch_block = "\n".join(branch_lines) if branch_lines else "  (none)"
    issue_block = "\n".join(my_issue_lines) if my_issue_lines else "  (none)"

    pr_block = ""
    if created_prs:
        pr_block += "  My PRs:\n" + "\n".join(f"  {l}" for l in created_prs) + "\n"
    if assigned_prs:
        pr_block += "  Assigned to me:\n" + "\n".join(f"  {l}" for l in assigned_prs) + "\n"
    if review_prs:
        pr_block += "  Review requested:\n" + "\n".join(f"  {l}" for l in review_prs) + "\n"
    if not pr_block:
        pr_block = "  (none)\n"

    sections.append(
        f"📁 {name} ({org})  [my activity only]\n"
        f"My commits (24h): {n_commits}\n"
        + "\n".join(commit_lines) + "\n"
        + f"My PRs / assigned:\n{pr_block}"
        + f"My issues assigned:\n{issue_block}\n"
        + f"My branches:\n{branch_block}"
    )

# Risk analysis
risks = []
for slug, name, org in OWN_REPOS + ORG_REPOS:
    stale = all_stale.get(slug, [])
    if stale:
        risks.append(f"{name}: {len(stale)} stale branch(es) >30d — {', '.join(stale)}")
    if all_pr_counts.get(slug, 0) >= 10:
        risks.append(f"{name}: {all_pr_counts[slug]} open PRs — review backlog.")

if zero_commit_repos:
    risks.append(f"No personal activity in 24h: {', '.join(zero_commit_repos)}")

risk_block = "\n".join(f"  • {r}" for r in risks) if risks else "  No critical risks detected."

report = f"""📊 DAILY DEV REPORT — {TODAY} UTC
Generated: {NOW.strftime("%H:%M")} UTC

━━━━━━━━━━━━━━━━━━━━━━━━
{chr(10).join(chr(10).join(["", s]) for s in sections)}
━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  RISKS
{risk_block}
"""

with open("/tmp/daily-report.txt", "w") as f:
    f.write(report)

print(report)
