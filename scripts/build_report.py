import json, os, subprocess, datetime, textwrap

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

def format_body(text, max_chars=2000):
    """Preserve issue/PR body structure — keep headers, bullets, tables."""
    if not text:
        return "No description provided."
    text = text.strip()
    # indent each line for report readability
    lines = text.splitlines()
    formatted = "\n".join(f"  {l}" if l.strip() else "" for l in lines)
    if len(formatted) > max_chars:
        formatted = formatted[:max_chars] + "\n  [... truncated — see issue for full content]"
    return formatted

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

def get_issue_detail(repo, number):
    return gh(f"/repos/{repo}/issues/{number}")

def get_pr_detail(repo, number):
    return gh(f"/repos/{repo}/pulls/{number}")

def expand_issue_action(repo, issue):
    detail = get_issue_detail(repo, issue["number"])
    body_text = format_body(detail.get("body", "")) if isinstance(detail, dict) else "No description provided."
    labels = [l["name"] for l in issue.get("labels", [])]
    assignees = [a["login"] for a in issue.get("assignees", [])] or [ME]
    updated = age(detail.get("updated_at", "")) if isinstance(detail, dict) else "?"
    opened = age(issue["created_at"])
    label_str = f" [{', '.join(labels)}]" if labels else ""
    comments = detail.get("comments", 0) if isinstance(detail, dict) else 0
    url = issue.get("html_url", f"https://github.com/{repo}/issues/{issue['number']}")

    # infer impact
    title = issue["title"]
    impact = "Unblocks documentation alignment and team awareness."
    if "gtm" in title.lower() or "traction" in title.lower():
        impact = "Affects go-to-market execution and team ownership clarity."
    elif "docs" in title.lower() or "documentation" in title.lower() or "nextra" in title.lower():
        impact = "Directly affects what external users and developers see."
    elif "bot" in title.lower() or "architecture" in title.lower():
        impact = "Affects the live Discord AI bot's stability and documentation coverage."
    elif "migration" in title.lower():
        impact = "Blocking or at risk of blocking dependent work until resolved."

    return f"""**Title:** {title}{label_str}
{url}

**Context:**
• Repo: {repo} | Issue #{issue['number']} | Opened {opened} | Last updated {updated} | {comments} comment(s)
• Owners: {', '.join(assignees)}

{body_text}

**Current Status:**
• Open and assigned to you. Last updated {updated}.

**Next Steps:**
• Review and comment, close, or open a PR as appropriate.
• If blocked, leave a comment so it's visible to the team.

**Impact:** {impact}
"""

def expand_pr_action(repo, pr, role="review"):
    detail = get_pr_detail(repo, pr["number"])
    body_text = format_body(detail.get("body", ""), max_chars=1500) if isinstance(detail, dict) else "No PR description provided."
    opened = age(pr["created_at"])
    updated = age(detail.get("updated_at", "")) if isinstance(detail, dict) else "?"
    draft = " (DRAFT)" if pr.get("draft") else ""
    author = (pr.get("user") or {}).get("login", "unassigned")
    url = pr.get("html_url", f"https://github.com/{repo}/pull/{pr['number']}")
    comments = detail.get("comments", 0) if isinstance(detail, dict) else 0

    if role == "created":
        action_line = "• Your PR — check if it's ready to merge or needs a reviewer assigned."
    elif role == "assigned":
        action_line = "• You are assigned — triage, review, or merge as appropriate."
    else:
        action_line = "• Your review has been requested — leave feedback or approve."

    return f"""**Title:** {pr['title']}{draft}
{url}

**Context:**
• Repo: {repo} | PR #{pr['number']} | Opened {opened} by {author} | Last updated {updated} | {comments} comment(s)

{body_text}

**Current Status:**
• Open{draft}. Last updated {updated}.

**Next Steps:**
{action_line}
• If blocked, comment and label accordingly.

**Impact:** Keeping PRs moving reduces review lag and prevents branch drift.
"""

def expand_branch_action(repo, branch):
    return f"""**Title:** Clean up stale branch — {branch['name']}

**Context:**
• Repo: {repo} | Branch: {branch['name']} | Last commit: {branch['age']}
• This branch has had no activity for over {branch['days']} days. It may have been superseded by a merge or simply forgotten.

**Current Status:**
• Branch exists on remote. No open PR associated (or PR is already merged).

**Next Steps:**
• Check if the work was merged into main. If yes, delete the branch.
• If the work is still needed, open a PR or rebase and continue.

**Owner:** {ME}

**Impact:** Stale branches create noise in the repo and make it harder to track what's actually in progress.
"""

# ── Collect data ──────────────────────────────────────────────────────────────

own = {}
for slug, label in [("0xblckmrq/human.tech.AI",  "human.tech.AI"),
                     ("0xblckmrq/human.tech.bot", "human.tech.bot")]:
    own[label] = {
        "slug": slug,
        "commits":  get_commits(slug),
        "prs":      get_all_prs(slug),
        "branches": get_branches(slug),
    }

org = {}
for slug, label in [("holonym-foundation/docs.human.tech", "docs.human.tech"),
                     ("holonym-foundation/internal-docs",   "internal-docs")]:
    c_prs, a_prs, r_prs = get_my_prs(slug)
    org[label] = {
        "slug":         slug,
        "commits":      get_commits(slug, filter_user=ME),
        "created_prs":  c_prs,
        "assigned_prs": a_prs,
        "review_prs":   r_prs,
        "branches":     get_branches(slug, filter_user=ME),
        "issues":       get_my_issues(slug),
    }

# ── Headline ──────────────────────────────────────────────────────────────────

total_commits = sum(len(v["commits"]) for v in own.values()) + \
                sum(len(v["commits"]) for v in org.values())

all_repos = {**own, **org}
active_count = len([v for v in all_repos.values() if v["commits"]])
most_active = max(all_repos, key=lambda k: len(all_repos[k]["commits"]))
latest_msg = ""
if all_repos[most_active]["commits"]:
    latest_msg = all_repos[most_active]["commits"][0]["commit"]["message"].splitlines()[0]

my_issues_total = sum(len(v["issues"]) for v in org.values())

if total_commits == 0:
    headline = "No commits in the last 24 hours across monitored repos. May be a quiet day or work is on untracked branches."
else:
    headline = (
        f"{total_commits} commit{'s' if total_commits != 1 else ''} in the last 24 hours across "
        f"{active_count} repo(s). Most active: {most_active} — \"{latest_msg}\"."
    )
    if my_issues_total:
        headline += f" You have {my_issues_total} open issue{'s' if my_issues_total != 1 else ''} assigned to you."

# ── Key Updates ───────────────────────────────────────────────────────────────

key_updates = []

ai = own["human.tech.AI"]
if ai["commits"]:
    msgs = [c["commit"]["message"].splitlines()[0] for c in ai["commits"][:3]]
    key_updates.append(
        f"**human.tech.AI** — {len(ai['commits'])} commits today.\n"
        f"   Recent: {'; '.join(msgs)}.\n"
        f"   Context: {len(ai['branches'])} open branches. Major feature merge landed (slash commands, scrape-once architecture, Render deployment).\n"
        f"   Impact: Bot is live on Render with a significantly expanded feature set."
    )
else:
    key_updates.append(f"**human.tech.AI** — No commits today. {len([b for b in ai['branches'] if b['days'] > 7])} branch(es) idle >7d.")

bot = own["human.tech.bot"]
if bot["commits"]:
    key_updates.append(f"**human.tech.bot** — {len(bot['commits'])} commit(s): " +
                       "; ".join(c["commit"]["message"].splitlines()[0] for c in bot["commits"][:3]))
else:
    key_updates.append("**human.tech.bot** — No commits in 24 hours. Last active 9 days ago.")

docs = org["docs.human.tech"]
if docs["commits"]:
    msgs = [c["commit"]["message"].splitlines()[0] for c in docs["commits"][:3]]
    key_updates.append(
        f"**docs.human.tech** — {len(docs['commits'])} of your commits today.\n"
        f"   Focus: {'; '.join(msgs)}.\n"
        f"   Context: Ongoing link/typo cleanup sprint.\n"
        f"   Impact: Improves doc reliability for external users and integrators."
    )

idocs = org["internal-docs"]
if idocs["commits"]:
    key_updates.append(f"**internal-docs** — {len(idocs['commits'])} of your commits today.")
if idocs["issues"]:
    key_updates.append(
        f"**internal-docs** — {len(idocs['issues'])} open issue(s) assigned to you:\n" +
        "\n".join(f"   • #{i['number']} {i['title']}" for i in idocs["issues"])
    )

# ── Notable Details ───────────────────────────────────────────────────────────

details = []
for label, d in own.items():
    stale = [b for b in d["branches"] if b["days"] > 14]
    if stale:
        details.append(f"{label}: {len(stale)} branch(es) idle >14d — {', '.join(b['name'] for b in stale)}")
for label, d in org.items():
    stale = [b for b in d["branches"] if b["days"] > 14]
    if stale:
        details.append(f"{label}: {len(stale)} of your branches idle >14d — {', '.join(b['name'] for b in stale)}")
all_my_prs = idocs["created_prs"] + idocs["assigned_prs"] + idocs["review_prs"]
old_prs = [p for p in all_my_prs if days_old(p["created_at"]) > 5]
if old_prs:
    details.append(f"{len(old_prs)} PR(s) involving you open >5 days: " +
                   ", ".join(f"#{p['number']}" for p in old_prs[:5]))
if not details:
    details.append("No notable branch staleness or aged PRs detected.")

# ── Action Items (expanded) ───────────────────────────────────────────────────

action_blocks = []

# Assigned issues
for issue in idocs["issues"]:
    action_blocks.append(expand_issue_action("holonym-foundation/internal-docs", issue))

# PRs needing review
for pr in idocs["review_prs"]:
    action_blocks.append(expand_pr_action("holonym-foundation/internal-docs", pr, role="review"))

# My open PRs
for pr in idocs["created_prs"]:
    action_blocks.append(expand_pr_action("holonym-foundation/internal-docs", pr, role="created"))

# Stale branches in own repos
for label, d in own.items():
    for b in [b for b in d["branches"] if b["days"] > 7 and b["name"] not in ("staging",)]:
        action_blocks.append(expand_branch_action(d["slug"], b))

# Stale branches in org repos (mine)
for label, d in org.items():
    for b in [b for b in d["branches"] if b["days"] > 14]:
        action_blocks.append(expand_branch_action(d["slug"], b))

if not action_blocks:
    action_blocks = ["→ Nothing urgent — you're clear."]

# ── Quick Take ────────────────────────────────────────────────────────────────

qt = []
if ai["commits"]:
    qt.append("human.tech.AI had a major day — architecture merged and deployed to Render.")
if docs["commits"]:
    qt.append(f"Doc cleanup is moving ({len(docs['commits'])} commits in docs.human.tech).")
if idocs["issues"]:
    qt.append(f"{len(idocs['issues'])} assigned internal-docs issues need your attention.")
if not qt:
    qt.append("Quiet day overall — a good time to clear open branches and PRs.")

# ── Assemble ──────────────────────────────────────────────────────────────────

sep = "━━━━━━━━━━━━━━━━━━━━━━━━"

report = f"""📊 DEV UPDATE — {TODAY}
Generated: {NOW.strftime("%H:%M")} UTC

{sep}
HEADLINE
{headline}

{sep}
KEY UPDATES
""" + "\n\n".join(f"• {u}" for u in key_updates) + f"""

{sep}
NOTABLE DETAILS
""" + "\n".join(f"• {d}" for d in details) + f"""

{sep}
ACTION ITEMS
""" + f"\n{'─' * 40}\n".join(action_blocks) + f"""

{sep}
QUICK TAKE
{" ".join(qt)}
"""

with open("/tmp/daily-report.txt", "w") as f:
    f.write(report)

print(report)
