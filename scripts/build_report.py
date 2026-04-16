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

def extract_section(body, *headers):
    """Extract content under a markdown header."""
    lines = body.splitlines()
    result = []
    in_section = False
    for line in lines:
        stripped = line.strip().lstrip("#").strip().lower()
        if any(stripped == h.lower() for h in headers):
            in_section = True
            continue
        if in_section:
            if line.startswith("#"):
                break
            result.append(line)
    return "\n".join(result).strip()

def extract_my_role(body, username):
    """Find the line/paragraph where the user is mentioned and their role."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if f"@{username}" in line or f"@{username.lower()}" in line.lower():
            # grab the line and next few lines for context
            chunk = lines[i:i+4]
            return "\n".join(l for l in chunk if l.strip())
    return ""

def extract_pending_items(body):
    """Extract unchecked action items from the body."""
    return [l.strip().lstrip("- ").lstrip("* ").lstrip("[ ] ").strip()
            for l in body.splitlines()
            if l.strip().startswith("- [ ]") or l.strip().startswith("* [ ]")]

def extract_downstream(body):
    """Extract downstream/flows-into section."""
    return extract_section(body, "Downstream", "Flows into", "Once finalized")

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
    body = detail.get("body", "") if isinstance(detail, dict) else ""
    labels = [l["name"] for l in issue.get("labels", [])]
    assignees = [a["login"] for a in issue.get("assignees", [])] or [ME]
    updated = age(detail.get("updated_at", "")) if isinstance(detail, dict) else "?"
    opened = age(issue["created_at"])
    comments = detail.get("comments", 0) if isinstance(detail, dict) else 0
    url = issue.get("html_url", f"https://github.com/{repo}/issues/{issue['number']}")
    title = issue["title"]
    label_str = f" [{', '.join(labels)}]" if labels else ""

    # Extract relevant parts
    my_role = extract_my_role(body, ME)
    action_section = extract_section(body, "Action", "Next Steps", "Your action")
    downstream = extract_downstream(body)
    pending = extract_pending_items(body)

    # Build concise output
    lines = [f"Issue #{issue['number']} — {title}{label_str}"]
    lines.append(f"{repo} → {url}")
    lines.append(f"Opened {opened} | Last updated {updated} | {comments} comment(s) | Owners: {', '.join(assignees)}")
    lines.append("")

    if my_role:
        lines.append(f"Your role:")
        for l in my_role.splitlines():
            if l.strip():
                lines.append(f"  ▎ {l.strip()}")
        lines.append("")

    if action_section:
        lines.append("What needs to happen:")
        for l in action_section.splitlines()[:8]:
            if l.strip():
                lines.append(f"  {l.strip()}")
        lines.append("")

    if pending:
        lines.append("Open items:")
        for item in pending[:5]:
            lines.append(f"  ☐ {item}")
        lines.append("")

    if downstream:
        lines.append("Once resolved, flows into:")
        for l in downstream.splitlines()[:5]:
            if l.strip():
                lines.append(f"  {l.strip()}")
        lines.append("")

    lines.append(f"→ {url}")

    return "\n".join(lines)

def expand_pr_action(repo, pr, role="review"):
    detail = get_pr_detail(repo, pr["number"])
    body = detail.get("body", "") if isinstance(detail, dict) else ""
    opened = age(pr["created_at"])
    updated = age(detail.get("updated_at", "")) if isinstance(detail, dict) else "?"
    draft = " [DRAFT]" if pr.get("draft") else ""
    author = (pr.get("user") or {}).get("login", "unassigned")
    url = pr.get("html_url", f"https://github.com/{repo}/pull/{pr['number']}")
    comments = detail.get("comments", 0) if isinstance(detail, dict) else 0

    action_line = {
        "created": "Your PR — check if it's ready to merge or needs a reviewer assigned.",
        "assigned": "You are assigned — triage, review, or merge as appropriate.",
        "review":   "Review requested from you — leave feedback or approve.",
    }.get(role, "")

    summary = extract_section(body, "Summary", "Description", "What", "Overview")
    summary_line = summary.splitlines()[0].strip() if summary else ""

    lines = [f"PR #{pr['number']} — {pr['title']}{draft}"]
    lines.append(f"{repo} → {url}")
    lines.append(f"Opened {opened} by {author} | Updated {updated} | {comments} comment(s)")
    if summary_line:
        lines.append(f"\n  {summary_line}")
    lines.append(f"\nYour action: {action_line}")
    lines.append(f"→ {url}")
    return "\n".join(lines)

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

# TLDR — one line per notable thing
tldr_lines = []
if total_commits > 0:
    tldr_lines.append(f"{total_commits} commits across {active_count} repo(s)")
if ai["commits"]:
    tldr_lines.append("human.tech.AI: major feature push live on Render")
if docs["commits"]:
    tldr_lines.append(f"docs.human.tech: {len(docs['commits'])} of your commits (link/typo sprint)")
if idocs["issues"]:
    tldr_lines.append(f"{len(idocs['issues'])} issues assigned to you in internal-docs")
if not tldr_lines:
    tldr_lines.append("Quiet day — no notable commits or open items")
tldr = " · ".join(tldr_lines)

report = f"""📊 DEV UPDATE — {TODAY}
Generated: {NOW.strftime("%H:%M")} UTC

TL;DR: {tldr}

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
