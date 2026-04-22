import requests
import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

# ---------------- CONFIG ----------------
EMAIL = os.environ["EMAIL"]
APP_PASSWORD = os.environ["APP_PASSWORD"]
TO_EMAIL = "ajayitaiwomercy@gmail.com"
# ----------------------------------------


def fetch_remoteok_jobs():
    print("Fetching RemoteOK jobs...")
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers)
        data = response.json()
    except Exception as e:
        print("RemoteOK fetch failed:", e)
        return []

    jobs = []

    for job in data[1:]:
        if not job.get("position"):
            continue

        try:
            job_date = datetime.fromisoformat(job["date"].replace("Z", "+00:00"))
            hours_ago = (datetime.now(timezone.utc) - job_date).total_seconds() / 3600
        except:
            continue

        jobs.append({
            "title": job.get("position", ""),
            "company": job.get("company", ""),
            "tags": job.get("tags", []),
            "url": job.get("url"),
            "hours_ago": hours_ago
        })

    return jobs


def fetch_wellfound_jobs():
    print("Fetching Wellfound jobs...")
    jobs = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto("https://wellfound.com/jobs", timeout=60000)
            page.wait_for_timeout(5000)

            for _ in range(3):
                page.mouse.wheel(0, 4000)
                page.wait_for_timeout(2000)

            job_cards = page.locator("a[href*='/jobs/']")
            count = min(job_cards.count(), 20)

            for i in range(count):
                try:
                    card = job_cards.nth(i)
                    link = card.get_attribute("href")

                    if not link:
                        continue

                    if not link.startswith("http"):
                        link = "https://wellfound.com" + link

                    text = card.inner_text().lower()

                    if "devops" not in text and "sre" not in text:
                        continue

                    jobs.append({
                        "title": text[:80],
                        "company": "Startup",
                        "tags": ["startup", "wellfound"],
                        "url": link,
                        "hours_ago": 2
                    })

                except:
                    continue

            browser.close()

    except Exception as e:
        print("Wellfound scraping failed:", e)

    return jobs


def extract_skills(tags):
    tech_keywords = ["aws", "docker", "kubernetes", "terraform", "ci/cd", "linux", "python", "go"]
    return ", ".join([t for t in tags if t.lower() in tech_keywords][:5])


def score_job(job):
    score = 0
    title = job["title"].lower()
    tags = [t.lower() for t in job["tags"]]

    if any(x in title for x in ["devops", "sre", "platform"]):
        score += 3

    tech_stack = ["aws", "docker", "kubernetes", "terraform", "ci/cd"]
    score += min(sum(1 for t in tags if t in tech_stack), 3)

    if job["hours_ago"] <= 12:
        score += 3
    elif job["hours_ago"] <= 24:
        score += 2

    if "startup" in tags:
        score += 2

    return score


def filter_jobs(jobs):
    scored = []

    for job in jobs:
        if job["hours_ago"] > 24:
            continue

        score = score_job(job)

        if score >= 5:
            job["score"] = score
            job["keywords"] = ", ".join(job["tags"][:5])
            job["skills"] = extract_skills(job["tags"])
            scored.append(job)

    return sorted(scored, key=lambda x: x["score"], reverse=True)[:5]


def format_email(jobs):
    if not jobs:
        return "<h3>No DevOps jobs found today 😢</h3>"

    html = "<h2>🔥 AI DevOps Jobs</h2><table border='1'><tr><th>Score</th><th>Title</th><th>Company</th><th>Apply</th></tr>"

    for job in jobs:
        html += f"<tr><td>{job['score']}</td><td>{job['title']}</td><td>{job['company']}</td><td><a href='{job['url']}'>Link</a></td></tr>"

    html += "</table>"
    return html


def send_email(content):
    print("Sending email...")

    msg = MIMEText(content, "html")
    msg["Subject"] = "🔥 DevOps Jobs"
    msg["From"] = EMAIL
    msg["To"] = TO_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL, APP_PASSWORD)
        server.send_message(msg)

    print("Email sent successfully!")


if __name__ == "__main__":
    jobs = fetch_remoteok_jobs() + fetch_wellfound_jobs()
    jobs = filter_jobs(jobs)
    email_content = format_email(jobs)
    send_email(email_content)