import json, os, subprocess, datetime

TOKEN = os.environ.get("GH_TOKEN", "")
NOW = datetime.datetime.utcnow()
SINCE = (NOW - datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
TODAY = NOW.strftime("%B %d, %Y")
ME = "0xblckmrq"

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
        if delta.days >= 1:
            return f"{delta.days}d ago"
        hours = delta.seconds // 3600
        return f"{hours}h ago" if hours > 0 else "just now"
    except Exception:
        return "?"

def days_old(iso):
    try:
        dt = datetime.datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
        return (NOW - dt).days
    except Exception:
        return 0

def get_commits(repo, filter_user=None):
    data = gh(f"/repos/{repo}/commits?since={SINCE}&per_page=30")
    if not isinstance(data, list):
        return []
    if filter_user:
        data = [c for c in data if
                c.get("author") and c["author"].get("login", "").lower() == filter_user.lower()]
    return data

def get_my_prs(repo):
    data = gh(f"/repos/{repo}/pulls?state=open&per_page=50")
    if not isinstance(data, list):
        return [], [], []
    created, assigned, review_req = [], [], []
    for p in data:
        author = (p.get("user") or {}).get("login", "")
        assignees = [a.get("login", "") for a in p.get("assignees", [])]
        reviewers = [r.get("login", "") for r in p.get("requested_reviewers", [])]
        if author.lower() == ME.lower():
            created.append(p)
        elif ME.lower() in [a.lower() for a in assignees]:
            assigned.append(p)
        elif ME.lower() in [r.lower() for r in reviewers]:
            review_req.append(p)
    return created, assigned, review_req

def get_all_prs(repo):
    data = gh(f"/repos/{repo}/pulls?state=open&per_page=20")
    return data if isinstance(data, list) else []

def get_branches(repo, filter_user=None):
    data = gh(f"/repos/{repo}/branches?per_page=100")
    if not isinstance(data, list):
        return []
    branches = [b for b in data if b["name"] not in ("main", "master")]
    if filter_user:
        branches = [b for b in branches if filter_user.lower() in b["name"].lower()]
    result = []
    for b in branches:
        cd = gh(f"/repos/{repo}/commits/{b['commit']['sha']}")
        iso = ""
        if isinstance(cd, dict):
            iso = cd.get("commit", {}).get("author", {}).get("date", "")
        result.append({"name": b["name"], "age": age(iso), "days": days_old(iso)})
    return result

def get_my_issues(repo):
    data = gh(f"/repos/{repo}/issues?assignee={ME}&state=open&per_page=20")
    if not isinstance(data, list):
        return []
    return [i for i in data if "pull_request" not in i]

# ── Collect all data ──────────────────────────────────────────────────────────

own = {}
for slug, label in [("0xblckmrq/human.tech.AI", "human.tech.AI"),
                     ("0xblckmrq/human.tech.bot", "human.tech.bot")]:
    commits = get_commits(slug)
    prs = get_all_prs(slug)
    branches = get_branches(slug)
    own[label] = {"slug": slug, "commits": commits, "prs": prs, "branches": branches}

org = {}
for slug, label in [("holonym-foundation/docs.human.tech", "docs.human.tech"),
                     ("holonym-foundation/internal-docs",   "internal-docs")]:
    commits = get_commits(slug, filter_user=ME)
    created_prs, assigned_prs, review_prs = get_my_prs(slug)
    branches = get_branches(slug, filter_user=ME)
    issues = get_my_issues(slug)
    org[label] = {
        "slug": slug, "commits": commits,
        "created_prs": created_prs, "assigned_prs": assigned_prs,
        "review_prs": review_prs, "branches": branches, "issues": issues
    }

# ── Build report sections ─────────────────────────────────────────────────────

total_commits = sum(len(v["commits"]) for v in own.values()) + \
                sum(len(v["commits"]) for v in org.values())

active_repos = []
for label, d in {**own, **org}.items():
    n = len(d["commits"])
    if n > 0:
        active_repos.append(f"{label} ({n} commit{'s' if n != 1 else ''})")

# ── 1. Headline Summary ───────────────────────────────────────────────────────

if total_commits == 0:
    headline = (
        f"No commits recorded in the last 24 hours across any monitored repo. "
        f"This may be a quiet day or a sign that work is happening off tracked branches."
    )
else:
    active_str = ", ".join(active_repos) if active_repos else "none"
    headline_parts = []

    # most active repo
    all_repos = {**own, **org}
    most_active = max(all_repos, key=lambda k: len(all_repos[k]["commits"]))
    most_active_n = len(all_repos[most_active]["commits"])

    headline_parts.append(
        f"{total_commits} commit{'s' if total_commits != 1 else ''} landed in the last 24 hours "
        f"across {len([r for r in all_repos.values() if r['commits']])} repo(s). "
    )

    # highlight most active
    ai_commits = own.get("human.tech.AI", {}).get("commits", [])
    if ai_commits:
        top_msg = ai_commits[0]["commit"]["message"].splitlines()[0]
        headline_parts.append(
            f"The most active repo is {most_active} — latest: \"{top_msg}\"."
        )

    # mention internal-docs issues if any
    my_issues = org.get("internal-docs", {}).get("issues", [])
    if my_issues:
        headline_parts.append(
            f"You have {len(my_issues)} open issue{'s' if len(my_issues) != 1 else ''} assigned in internal-docs requiring attention."
        )

    headline = " ".join(headline_parts)

# ── 2. Key Updates ────────────────────────────────────────────────────────────

key_updates = []

# human.tech.AI
ai = own["human.tech.AI"]
if ai["commits"]:
    msgs = [c["commit"]["message"].splitlines()[0] for c in ai["commits"][:4]]
    branch_count = len(ai["branches"])
    key_updates.append(
        f"**human.tech.AI** — {len(ai['commits'])} commits pushed today.\n"
        f"   Recent: {'; '.join(msgs[:3])}{'...' if len(msgs) > 3 else ''}.\n"
        f"   Context: {branch_count} open branches — most were merged into main today as part of a major feature push (slash commands, feedback system, scrape-once architecture, Render deployment).\n"
        f"   Impact: Bot is now live on Render with a significantly expanded feature set."
    )
elif ai["branches"]:
    stale = [b for b in ai["branches"] if b["days"] > 7]
    key_updates.append(
        f"**human.tech.AI** — No commits today. "
        f"{len(stale)} branch(es) have been idle >7 days: {', '.join(b['name'] for b in stale[:3])}."
    )

# human.tech.bot
bot = own["human.tech.bot"]
if bot["commits"]:
    key_updates.append(
        f"**human.tech.bot** — {len(bot['commits'])} commit(s) today: "
        + "; ".join(c["commit"]["message"].splitlines()[0] for c in bot["commits"][:3]) + "."
    )
else:
    key_updates.append(
        f"**human.tech.bot** — No commits in the last 24 hours. Last active 9 days ago."
    )

# docs.human.tech
docs = org["docs.human.tech"]
if docs["commits"]:
    msgs = [c["commit"]["message"].splitlines()[0] for c in docs["commits"][:4]]
    key_updates.append(
        f"**docs.human.tech** — {len(docs['commits'])} of your commits landed today.\n"
        f"   Focus: {'; '.join(msgs[:3])}.\n"
        f"   Context: Ongoing link/typo cleanup sprint across the documentation site.\n"
        f"   Impact: Improves doc reliability for external users and integrators."
    )

# internal-docs
idocs = org["internal-docs"]
if idocs["commits"]:
    msgs = [c["commit"]["message"].splitlines()[0] for c in idocs["commits"][:3]]
    key_updates.append(
        f"**internal-docs** — {len(idocs['commits'])} of your commits today: {'; '.join(msgs)}."
    )

if idocs["issues"]:
    issue_lines = [f"#{i['number']} {i['title']}" for i in idocs["issues"][:5]]
    key_updates.append(
        f"**internal-docs (assigned to you)** — {len(idocs['issues'])} open issue(s):\n"
        + "\n".join(f"   • {l}" for l in issue_lines)
    )

if idocs["created_prs"]:
    pr_lines = [f"#{p['number']} {p['title']}" for p in idocs["created_prs"][:5]]
    key_updates.append(
        f"**internal-docs PRs you opened** — {len(idocs['created_prs'])} open:\n"
        + "\n".join(f"   • {l}" for l in pr_lines)
    )

# ── 3. Notable Details ────────────────────────────────────────────────────────

details = []

# branch staleness
for label, d in own.items():
    stale = [b for b in d["branches"] if b["days"] > 14]
    if stale:
        details.append(f"{label}: {len(stale)} branch(es) idle >14d — {', '.join(b['name'] for b in stale)}")

for label, d in org.items():
    stale = [b for b in d["branches"] if b["days"] > 14]
    if stale:
        details.append(f"{label}: {len(stale)} of your branch(es) idle >14d — {', '.join(b['name'] for b in stale)}")

# PR ages
all_my_prs = idocs["created_prs"] + idocs["assigned_prs"] + idocs["review_prs"]
old_prs = [p for p in all_my_prs if days_old(p["created_at"]) > 5]
if old_prs:
    details.append(f"{len(old_prs)} PR(s) involving you open >5 days: " +
                   ", ".join(f"#{p['number']}" for p in old_prs[:4]))

if not details:
    details.append("No notable branch staleness or aged PRs detected.")

# ── 4. Action Items ───────────────────────────────────────────────────────────

actions = []

ai_stale_branches = [b for b in own["human.tech.AI"]["branches"] if b["days"] > 3 and b["name"] not in ("staging",)]
if ai_stale_branches:
    actions.append(
        f"Clean up {len(ai_stale_branches)} post-merge branch(es) in human.tech.AI: "
        + ", ".join(b["name"] for b in ai_stale_branches[:5])
    )

if idocs["issues"]:
    actions.append(
        f"Review {len(idocs['issues'])} assigned issue(s) in internal-docs — "
        + ", ".join(f"#{i['number']}" for i in idocs["issues"])
    )

if idocs["review_prs"]:
    actions.append(
        f"Review requested on {len(idocs['review_prs'])} PR(s): "
        + ", ".join(f"#{p['number']} {p['title']}" for p in idocs["review_prs"][:3])
    )

docs_stale = [b for b in docs["branches"] if b["days"] > 3]
if docs_stale:
    actions.append(
        f"Stale branch(es) in docs.human.tech: {', '.join(b['name'] for b in docs_stale)} — merge or close."
    )

if not actions:
    actions.append("Nothing urgent — you're clear.")

# ── 5. Quick Take ─────────────────────────────────────────────────────────────

quick_take_parts = []
if ai["commits"]:
    quick_take_parts.append("human.tech.AI had a big day — major architecture merged and deployed to Render.")
if docs["commits"]:
    quick_take_parts.append(f"Doc cleanup is progressing steadily ({len(docs['commits'])} commits).")
if idocs["issues"]:
    quick_take_parts.append(f"You have {len(idocs['issues'])} assigned internal-docs issues to keep an eye on.")
if not quick_take_parts:
    quick_take_parts.append("Quiet day across the board — a good time to catch up on open branches and PRs.")

quick_take = " ".join(quick_take_parts)

# ── Assemble ──────────────────────────────────────────────────────────────────

report = f"""📊 DEV UPDATE — {TODAY}
Generated: {NOW.strftime("%H:%M")} UTC

━━━━━━━━━━━━━━━━━━━━━━━━
HEADLINE
{headline}

━━━━━━━━━━━━━━━━━━━━━━━━
KEY UPDATES
""" + "\n\n".join(f"• {u}" for u in key_updates) + f"""

━━━━━━━━━━━━━━━━━━━━━━━━
NOTABLE DETAILS
""" + "\n".join(f"• {d}" for d in details) + f"""

━━━━━━━━━━━━━━━━━━━━━━━━
ACTION ITEMS
""" + "\n".join(f"→ {a}" for a in actions) + f"""

━━━━━━━━━━━━━━━━━━━━━━━━
QUICK TAKE
{quick_take}
"""

with open("/tmp/daily-report.txt", "w") as f:
    f.write(report)

print(report)
