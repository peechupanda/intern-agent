# 🤖 Intern Agent — AI-Powered Internship Application System

A multi-agent system that autonomously finds, scores, and applies to internship opportunities — built with LangGraph, Groq (Llama 3.3 70B), and Python.

---

## What it does

| Agent | Role |
|---|---|
| **Master Orchestrator** | Plans and delegates tasks across all agents |
| **Scout Agent** | Scrapes internship listings from LinkedIn, Unstop, Internshala |
| **Fit Scorer** | Scores each role against your profile (0–100) with reasons and gaps |
| **Applicator Agent** | Auto-fills and submits applications for approved roles |
| **Email Agent** | Monitors inbox and drafts responses to recruiter emails |

The system maintains a **shared job queue** that deduplicates listings, tracks application status, and surfaces a daily review dashboard — so you stay in control while the agents do the grunt work.

---

## Architecture

```
Your Profile (JSON)
       │
       ▼
Master Orchestrator
       │
  ┌────┴─────────────────────┐
  │           │              │
Scout      Fit Scorer    Email Agent
Agent         │
         Job Queue
              │
         Your Review
              │
         Applicator
```

---

## Tech Stack

- **LLM**: Llama 3.3 70B via [Groq](https://groq.com) (free tier)
- **Agent Framework**: LangGraph + LangChain
- **Scraping**: Playwright + BeautifulSoup4
- **Storage**: JSON-based job queue (SQLite planned)
- **Language**: Python 3.12

---

## Project Structure

```
intern-agent/
├── agents/
│   ├── fit_scorer.py       # Scores jobs against your profile
│   ├── scout_agent.py      # Scrapes internship platforms
│   ├── applicator.py       # Submits applications
│   └── email_agent.py      # Handles recruiter emails
├── tools/
│   ├── profile_loader.py   # Loads and summarises your profile
│   └── job_queue.py        # Shared job queue with status tracking
├── data/
│   └── profile.json        # Your skills, preferences, filters
├── main.py                 # Master orchestrator entry point
└── .env                    # API keys (not committed)
```

---

## Getting Started

### 1. Clone and set up

```bash
git clone https://github.com/peechupanda/intern-agent.git
cd intern-agent
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Add your API key

Create a `.env` file:
```
GROQ_API_KEY=your_groq_key_here
```
Get a free key at [console.groq.com](https://console.groq.com)

### 3. Set up your profile

Edit `data/profile.json` with your details — skills, preferred roles, hard filters, and top-tier companies list.

### 4. Test the fit scorer

```bash
python -m agents.fit_scorer
```

### 5. Run the full pipeline

```bash
python main.py
```

---

## Fit Scoring Logic

Each opportunity is scored across three dimensions:

- **Skill match** (50%) — overlap between your stack and the JD requirements
- **Profile strength** (30%) — how competitive your resume looks for this specific role  
- **Timing** (20%) — deadline proximity, recency of posting

| Score | Verdict |
|---|---|
| 70–100 | ✅ Apply |
| 50–69 | 👀 Review |
| 0–49 | ❌ Skip |

Hard filters (non-tech roles, unpaid unless top-tier, expired deadlines) override scoring entirely.

---

## Roadmap

- [x] Profile loader
- [x] Fit scorer with Groq/Llama
- [x] Job queue with deduplication and status tracking
- [ ] Scout agent (LinkedIn, Unstop, Internshala scrapers)
- [ ] Daily review dashboard (CLI)
- [ ] Auto-applicator with Playwright
- [ ] Email agent with Gmail API
- [ ] Master orchestrator with LangGraph
- [ ] Web UI dashboard

---

## Why I built this

Applying to internships manually is repetitive and slow — most students either apply to too few roles or waste time on poor-fit ones. This system automates the pipeline while keeping humans in the loop for the final approval step.

---

## Author

**Pratyush Talwar** — B.Tech Information Technology, Delhi Technological University  
[LinkedIn](https://linkedin.com/in/pratyush-talwar) • [GitHub](https://github.com/peechupanda)
