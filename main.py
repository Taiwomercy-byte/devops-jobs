import requests
import smtplib
import os
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

# ---------------- CONFIG ----------------
EMAIL = os.environ["EMAIL"]
APP_PASSWORD = os.environ["APP_PASSWORD"]
TO_EMAIL = "ajayitaiwomercy@gmail.com"

MIN_SCORE = 3          # Lowered from 5 — catches more relevant jobs
MAX_HOURS_OLD = 48     # Extended from 24 — catches recent jobs you might have missed
MAX_RESULTS = 10       # Increased from 5
# ----------------------------------------

DEVOPS_TITLE_KEYWORDS = [
    "backend developer", "backend engineer", "devops", "sre", "platform engineer", "cloud engineer",
    "infrastructure engineer", "devsecops", "reliability engineer",
    "site reliability", "mlops", "cloud ops"
]

TECH_STACK_KEYWORDS = [
    "aws", "node.js", "typescript", "javascript", "nest.js", "restful api design",
     "express.js", "postgresql", "prisma orm", "mongodb", "jwt", "oauth", "rbac", 
    "owasp api security", "gcp", "azure", "docker", "kubernetes", "k8s",
    "terraform", "ansible", "ci/cd", "jenkins", "github actions",
    "linux", "python", "go", "golang", "helm", "prometheus",
    "grafana", "datadog", "argocd", "vault", "istio", "pulumi"
]

SECURITY_KEYWORDS = ["devsecops", "security", "sast", "dast", "trivy", "snyk", "sonarqube"]


def is_devops_title(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in DEVOPS_TITLE_KEYWORDS)


def extract_tech_skills(tags: list) -> str:
    matched = [t for t in tags if t.lower() in TECH_STACK_KEYWORDS]
    return ", ".join(matched[:6])


def score_job(job: dict) -> int:
    score = 0
    title = job.get("title", "").lower()
    tags = [t.lower() for t in job.get("tags", [])]
    description = job.get("description", "").lower()
    combined = title + " " + description + " " + " ".join(tags)

    # Title relevance (up to 4 pts)
    if any(x in title for x in ["devops", "devsecops", "backend developer"]):
        score += 4
    elif any(x in title for x in ["platform", "cloud engineer", "infrastructure"]):
        score += 3
    elif any(x in title for x in ["backend engineer", "cloud ops", "reliability"]):
        score += 2

    # Tech stack match (up to 4 pts, 1pt each, capped)
    tech_hits = sum(1 for kw in TECH_STACK_KEYWORDS if kw in combined)
    score += min(tech_hits, 4)

    # Recency bonus
    hours = job.get("hours_ago", 999)
    if hours <= 6:
        score += 4
    elif hours <= 12:
        score += 3
    elif hours <= 24:
        score += 2
    elif hours <= 48:
        score += 1

    # Remote-friendly signal
    if job.get("remote", False) or "remote" in combined:
        score += 1

    # Security/DevSecOps bonus (relevant to your target role)
    if any(kw in combined for kw in SECURITY_KEYWORDS):
        score += 2

    return score


# ─────────────────────────────────────────
# SOURCE 1: RemoteOK
# ─────────────────────────────────────────
def fetch_remoteok_jobs() -> list:
    print("[RemoteOK] Fetching...")
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; job-bot/1.0)"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()
    except Exception as e:
        print(f"[RemoteOK] Failed: {e}")
        return []

    jobs = []
    for job in data[1:]:
        if not job.get("position"):
            continue
        if not is_devops_title(job.get("position", "")):
            continue  # Pre-filter early — only process relevant titles

        try:
            job_date = datetime.fromisoformat(job["date"].replace("Z", "+00:00"))
            hours_ago = (datetime.now(timezone.utc) - job_date).total_seconds() / 3600
        except Exception:
            hours_ago = 999

        jobs.append({
            "source": "RemoteOK",
            "title": job.get("position", ""),
            "company": job.get("company", "N/A"),
            "tags": job.get("tags", []),
            "url": job.get("url", ""),
            "description": job.get("description", ""),
            "hours_ago": hours_ago,
            "remote": True,
        })

    print(f"[RemoteOK] Found {len(jobs)} DevOps-relevant jobs")
    return jobs


# ─────────────────────────────────────────
# SOURCE 2: We Work Remotely (RSS — no scraping needed)
# ─────────────────────────────────────────
def fetch_weworkremotely_jobs() -> list:
    print("[WeWorkRemotely] Fetching via RSS...")
    import xml.etree.ElementTree as ET

    url = "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; job-bot/1.0)"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        root = ET.fromstring(response.content)
    except Exception as e:
        print(f"[WeWorkRemotely] Failed: {e}")
        return []

    jobs = []
    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_date_el = item.find("pubDate")
        desc_el = item.find("description")

        if title_el is None or link_el is None:
            continue

        title = title_el.text or ""
        # WWR titles are formatted as "Company: Role" — split them
        if ": " in title:
            company, role = title.split(": ", 1)
        else:
            company, role = "Unknown", title

        # Parse publish date
        hours_ago = 999
        if pub_date_el is not None and pub_date_el.text:
            try:
                from email.utils import parsedate_to_datetime
                pub = parsedate_to_datetime(pub_date_el.text)
                hours_ago = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
            except Exception:
                pass

        description = desc_el.text or "" if desc_el is not None else ""

        jobs.append({
            "source": "WeWorkRemotely",
            "title": role.strip(),
            "company": company.strip(),
            "tags": [],  # WWR RSS doesn't include tags — scored on title/desc
            "url": link_el.text or "",
            "description": description,
            "hours_ago": hours_ago,
            "remote": True,
        })

    print(f"[WeWorkRemotely] Found {len(jobs)} jobs")
    return jobs


# ─────────────────────────────────────────
# SOURCE 3: Himalayas.app (clean JSON API)
# ─────────────────────────────────────────
def fetch_himalayas_jobs() -> list:
    print("[Himalayas] Fetching...")
    url = "https://himalayas.app/jobs/api?q=devops&limit=30"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; job-bot/1.0)"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()
    except Exception as e:
        print(f"[Himalayas] Failed: {e}")
        return []

    jobs = []
    for job in data.get("jobs", []):
        title = job.get("title", "")
        if not is_devops_title(title):
            continue

        # Parse createdAt timestamp
        hours_ago = 999
        created = job.get("createdAt", "")
        if created:
            try:
                pub = datetime.fromisoformat(created.replace("Z", "+00:00"))
                hours_ago = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
            except Exception:
                pass

        jobs.append({
            "source": "Himalayas",
            "title": title,
            "company": job.get("companyName", "N/A"),
            "tags": job.get("tags", []),
            "url": job.get("applicationLink", job.get("url", "")),
            "description": job.get("description", ""),
            "hours_ago": hours_ago,
            "remote": True,
        })

    print(f"[Himalayas] Found {len(jobs)} DevOps jobs")
    return jobs


# ─────────────────────────────────────────
# SOURCE 4: Arbeitnow (free jobs API, no auth)
# ─────────────────────────────────────────
def fetch_arbeitnow_jobs() -> list:
    print("[Arbeitnow] Fetching...")
    url = "https://www.arbeitnow.com/api/job-board-api?search=devops&remote=true"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; job-bot/1.0)"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()
    except Exception as e:
        print(f"[Arbeitnow] Failed: {e}")
        return []

    jobs = []
    for job in data.get("data", []):
        title = job.get("title", "")
        if not is_devops_title(title):
            continue

        hours_ago = 999
        created_at = job.get("created_at", 0)
        if created_at:
            try:
                pub = datetime.fromtimestamp(created_at, tz=timezone.utc)
                hours_ago = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
            except Exception:
                pass

        jobs.append({
            "source": "Arbeitnow",
            "title": title,
            "company": job.get("company_name", "N/A"),
            "tags": job.get("tags", []),
            "url": job.get("url", ""),
            "description": job.get("description", ""),
            "hours_ago": hours_ago,
            "remote": job.get("remote", False),
        })

    print(f"[Arbeitnow] Found {len(jobs)} DevOps jobs")
    return jobs


# ─────────────────────────────────────────
# SOURCE 5: Wellfound (Playwright scraper — kept but improved)
# ─────────────────────────────────────────
def fetch_wellfound_jobs() -> list:
    print("[Wellfound] Fetching via Playwright...")
    jobs = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
            )
            page = context.new_page()

            # Search specifically for DevOps roles
            page.goto("https://wellfound.com/jobs?role=devops-engineer", timeout=60000)
            page.wait_for_timeout(4000)

            # Scroll to load more listings
            for _ in range(3):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1500)

            # Grab job card containers (more reliable selector)
            cards = page.locator("[data-test='StartupResult']")
            count = min(cards.count(), 15)
            print(f"[Wellfound] Found {count} cards")

            for i in range(count):
                try:
                    card = cards.nth(i)
                    title_el = card.locator("a[data-test='job-title']").first
                    company_el = card.locator("[class*='startupName']").first

                    title = title_el.inner_text(timeout=2000).strip()
                    href = title_el.get_attribute("href") or ""
                    company = company_el.inner_text(timeout=2000).strip()

                    if not href.startswith("http"):
                        href = "https://wellfound.com" + href

                    if not is_devops_title(title):
                        continue

                    jobs.append({
                        "source": "Wellfound",
                        "title": title,
                        "company": company,
                        "tags": ["startup", "wellfound"],
                        "url": href,
                        "description": "",
                        "hours_ago": 12,  # Wellfound doesn't expose timestamps on cards
                        "remote": True,
                    })

                except Exception as ex:
                    print(f"[Wellfound] Card {i} parse error: {ex}")
                    continue

            browser.close()

    except Exception as e:
        print(f"[Wellfound] Scraping failed: {e}")

    print(f"[Wellfound] Collected {len(jobs)} DevOps jobs")
    return jobs


# ─────────────────────────────────────────
# FILTER + RANK
# ─────────────────────────────────────────
def filter_and_rank(jobs: list) -> list:
    print(f"\n[Filter] Total raw jobs before filter: {len(jobs)}")

    # Deduplicate by URL
    seen_urls = set()
    unique = []
    for job in jobs:
        url = job.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(job)

    print(f"[Filter] After dedup: {len(unique)}")

    scored = []
    for job in unique:
        if job["hours_ago"] > MAX_HOURS_OLD:
            continue

        score = score_job(job)
        print(f"  score={score:2d} | {job['source']:<15} | {job['hours_ago']:.1f}h ago | {job['title'][:55]}")

        if score >= MIN_SCORE:
            job["score"] = score
            job["skills"] = extract_tech_skills(job.get("tags", []))
            scored.append(job)

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:MAX_RESULTS]
    print(f"[Filter] {len(top)} jobs passed scoring (min score={MIN_SCORE})")
    return top


# ─────────────────────────────────────────
# EMAIL FORMATTER
# ─────────────────────────────────────────
def format_email(jobs: list) -> str:
    if not jobs:
        return """
        <div style="font-family:sans-serif;padding:20px">
          <h3 style="color:#c0392b">No DevOps jobs matched your criteria today</h3>
          <p>Sources checked: RemoteOK, WeWorkRemotely, Himalayas, Arbeitnow, Wellfound</p>
          <p>Try lowering MIN_SCORE or extending MAX_HOURS_OLD in the script config.</p>
        </div>
        """

    rows = ""
    for job in jobs:
        source_color = {
            "RemoteOK": "#2c3e50", "WeWorkRemotely": "#16a085",
            "Himalayas": "#8e44ad", "Arbeitnow": "#2980b9", "Wellfound": "#e67e22"
        }.get(job["source"], "#555")

        age_label = f"{job['hours_ago']:.0f}h ago" if job["hours_ago"] < 48 else "2d ago"
        skills_html = f"<br><small style='color:#888'>{job['skills']}</small>" if job.get("skills") else ""

        rows += f"""
        <tr>
          <td style='padding:10px;text-align:center;font-size:22px;font-weight:bold;color:#e74c3c'>{job['score']}</td>
          <td style='padding:10px'>
            <strong>{job['title']}</strong><br>
            <span style='color:#555'>{job['company']}</span>
            {skills_html}
          </td>
          <td style='padding:10px;text-align:center'>
            <span style='background:{source_color};color:white;padding:2px 8px;border-radius:4px;font-size:12px'>{job['source']}</span>
          </td>
          <td style='padding:10px;color:#888;font-size:13px'>{age_label}</td>
          <td style='padding:10px;text-align:center'>
            <a href='{job['url']}' style='background:#2ecc71;color:white;padding:6px 14px;border-radius:4px;text-decoration:none;font-size:13px'>Apply</a>
          </td>
        </tr>"""

    return f"""
    <div style="font-family:sans-serif;max-width:800px;margin:0 auto">
      <h2 style="color:#2c3e50">DevOps Jobs Digest — {datetime.now().strftime('%b %d, %Y')}</h2>
      <p style="color:#555">{len(jobs)} jobs matched · Sources: RemoteOK, WeWorkRemotely, Himalayas, Arbeitnow, Wellfound</p>
      <table cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;border:1px solid #ddd;border-radius:8px">
        <thead>
          <tr style="background:#f8f9fa">
            <th style="padding:10px;text-align:center;width:50px">Score</th>
            <th style="padding:10px;text-align:left">Role</th>
            <th style="padding:10px;text-align:center;width:120px">Source</th>
            <th style="padding:10px;text-align:center;width:80px">Age</th>
            <th style="padding:10px;text-align:center;width:80px">Link</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="color:#aaa;font-size:12px;margin-top:16px">
        Scoring: title match (4pts) + tech stack overlap (4pts) + recency (4pts) + remote signal (1pt) + security keywords (2pts)
      </p>
    </div>
    """


# ─────────────────────────────────────────
# SEND EMAIL
# ─────────────────────────────────────────
def send_email(content: str, job_count: int):
    print("[Email] Sending...")
    subject = f"DevOps Jobs Digest — {job_count} found ({datetime.now().strftime('%b %d')})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL
    msg["To"] = TO_EMAIL
    msg.attach(MIMEText(content, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL, APP_PASSWORD)
        server.send_message(msg)

    print(f"[Email] Sent: '{subject}'")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print(f"DevOps Job Engine — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Config: MIN_SCORE={MIN_SCORE}, MAX_HOURS={MAX_HOURS_OLD}h, MAX_RESULTS={MAX_RESULTS}")
    print("=" * 55)

    all_jobs = []
    all_jobs += fetch_remoteok_jobs()
    all_jobs += fetch_weworkremotely_jobs()
    all_jobs += fetch_himalayas_jobs()
    all_jobs += fetch_arbeitnow_jobs()
    all_jobs += fetch_wellfound_jobs()

    top_jobs = filter_and_rank(all_jobs)
    email_html = format_email(top_jobs)
    send_email(email_html, len(top_jobs))

    print("\nDone.")