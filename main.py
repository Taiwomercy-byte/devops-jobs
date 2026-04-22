import requests
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone

# ---------------- CONFIG ----------------
EMAIL = "ajayitaiwomercy@gmail.com"
APP_PASSWORD = "mwzw iokd hdob jday"
TO_EMAIL = "ajayitaiwomercy@gmail.com"

# ----------------------------------------

def fetch_remoteok_jobs():
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    data = response.json()

    jobs = []
    for job in data[1:]:  # skip metadata
        if not job.get("position"):
            continue

        title = job.get("position", "")
        company = job.get("company", "")
        tags = job.get("tags", [])
        date = job.get("date", "")

        # Convert date
        try:
            job_date = datetime.fromisoformat(date.replace("Z", "+00:00"))
            hours_ago = (datetime.now(timezone.utc) - job_date).total_seconds() / 3600
        except:
            continue

        jobs.append({
            "title": title,
            "company": company,
            "tags": tags,
            "url": job.get("url"),
            "hours_ago": hours_ago
        })

    return jobs


def filter_jobs(jobs):
    filtered = []

    for job in jobs:
        title = job["title"].lower()

        # Criteria
        if "devops" not in title and "sre" not in title and "platform" not in title:
            continue

        if job["hours_ago"] > 24:
            continue

        # Assume RemoteOK = remote
        keywords = ", ".join(job["tags"][:5])

        skills = extract_skills(job["tags"])

        filtered.append({
            "title": job["title"],
            "company": job["company"],
            "link": job["url"],
            "keywords": keywords,
            "skills": skills
        })

    return filtered


def extract_skills(tags):
    tech_keywords = ["aws", "docker", "kubernetes", "terraform", "ci/cd", "linux", "python", "go"]

    found = []
    for tag in tags:
        if tag.lower() in tech_keywords:
            found.append(tag)

    return ", ".join(found[:5])


def format_email(jobs):
    if not jobs:
        return "<h3>No matching jobs found today 😢</h3>"

    html = """
    <h2>🚀 Daily Remote DevOps Jobs</h2>
    <table border="1" cellpadding="5">
    <tr>
        <th>Job Title</th>
        <th>Company</th>
        <th>Link</th>
        <th>Keywords</th>
        <th>Technical Skills</th>
    </tr>
    """

    for job in jobs:
        html += f"""
        <tr>
            <td>{job['title']}</td>
            <td>{job['company']}</td>
            <td><a href="{job['link']}">Apply</a></td>
            <td>{job['keywords']}</td>
            <td>{job['skills']}</td>
        </tr>
        """

    html += "</table>"
    return html


def send_email(content):
    msg = MIMEText(content, "html")
    msg["Subject"] = "🔥 Daily DevOps Jobs (Remote + Startup)"
    msg["From"] = EMAIL
    msg["To"] = TO_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL, APP_PASSWORD)
        server.send_message(msg)


if __name__ == "__main__":
    jobs = fetch_remoteok_jobs()
    filtered = filter_jobs(jobs)
    email_content = format_email(filtered)
    send_email(email_content)
