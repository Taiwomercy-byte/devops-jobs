# DevOps Job Hunter

An automated job pipeline that scrapes multiple remote job boards, scores and filters DevOps/SRE/DevSecOps roles, and delivers a ranked digest to your inbox on a schedule — all powered by GitHub Actions.

---

## What This Project Demonstrates

| Area | Implementation |
|------|----------------|
| **Automation** | GitHub Actions scheduled workflow (cron) — runs without a server |
| **Multi-source scraping** | RemoteOK (JSON API), WeWorkRemotely (RSS), Himalayas (JSON API), Arbeitnow (JSON API), Wellfound (Playwright headless browser) |
| **Scoring algorithm** | Custom scoring: title relevance (4pts) + tech stack overlap (4pts) + recency (4pts) + remote signal (1pt) + security keywords (2pts) |
| **Deduplication** | URL-based dedup across all sources before scoring |
| **Notification** | HTML email digest via Gmail SMTP with colour-coded source badges and direct apply links |
| **Secrets management** | Gmail credentials stored as GitHub Actions secrets — never in source |

---

## How It Works

```
GitHub Actions cron trigger (scheduled)
            │
            ▼
  Fetch jobs from 5 sources concurrently
  ┌──────────────┬──────────────────┬───────────┬───────────┬───────────┐
  │  RemoteOK    │ WeWorkRemotely   │ Himalayas │ Arbeitnow │ Wellfound │
  │  (JSON API)  │    (RSS feed)    │ (JSON API)│ (JSON API)│(Playwright│
  └──────────────┴──────────────────┴───────────┴───────────┴───────────┘
            │
            ▼
  Deduplicate by URL
            │
            ▼
  Filter: DevOps title keywords only
            │
            ▼
  Score each job (max 15pts)
            │
            ▼
  Filter: score ≥ MIN_SCORE, posted within MAX_HOURS_OLD
            │
            ▼
  Rank top MAX_RESULTS jobs
            │
            ▼
  Send HTML email digest
```

---

## Scoring Breakdown

```python
Title match      → up to 4pts  ("devops"/"sre" = 4, "platform"/"cloud" = 3, "mlops" = 2)
Tech stack match → up to 4pts  (aws, kubernetes, terraform, docker, github actions, etc.)
Recency          → up to 4pts  (≤6h = 4, ≤12h = 3, ≤24h = 2, ≤48h = 1)
Remote signal    → 1pt
Security keywords→ 2pts        (devsecops, trivy, snyk, sonarqube, sast, dast)
```

---

## Configuration

Edit these constants at the top of `main.py`:

```python
MIN_SCORE      = 3    # Minimum score to include a job
MAX_HOURS_OLD  = 48   # Maximum age of job postings (hours)
MAX_RESULTS    = 10   # Maximum jobs per email digest
```

---

## Setup

**Prerequisites:** Python 3.10+, Playwright, a Gmail account with an App Password

```bash
# Clone the repo
git clone https://github.com/Taiwomercy-byte/devops-jobs.git
cd devops-jobs

# Install dependencies
pip install requests playwright
playwright install chromium

# Run locally (requires EMAIL and APP_PASSWORD env vars)
EMAIL=you@gmail.com APP_PASSWORD=your-app-password python main.py
```

### GitHub Actions Setup

1. Go to **Settings → Secrets and variables → Actions**
2. Add two repository secrets:
   - `EMAIL` — your Gmail address
   - `APP_PASSWORD` — your [Gmail App Password](https://support.google.com/accounts/answer/185833)
3. Push to `main` — the workflow runs on schedule or you can trigger it manually via **Actions → Run workflow**

---

## Tech Stack

- **Python 3** — core scripting
- **Playwright** — headless Chromium for Wellfound (JavaScript-rendered pages)
- **Requests** — HTTP calls to JSON/RSS APIs
- **smtplib** — Gmail SMTP email delivery
- **GitHub Actions** — scheduled execution, zero infrastructure

---

## Author

**Taiwo Mercy** — Backend / DevSecOps Engineer
- GitHub: [@Taiwomercy-byte](https://github.com/Taiwomercy-byte)
- LinkedIn: [linkedin.com/in/taiwo-ajayi-261788163](https://www.linkedin.com/in/taiwo-ajayi-261788163)
