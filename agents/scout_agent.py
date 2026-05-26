"""
Scout Agent — finds internship listings from Internshala, Unstop, and Indeed India.

Usage:
    from agents.scout_agent import run_scout
    jobs = run_scout(profile)

Or standalone:
    python -m agents.scout_agent
"""

import json
import os
import time
import re
import random
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Non-tech role blacklist — scout-level filter (coarse)
NON_TECH = re.compile(
    r"\b(hr|human resource|recruiter|marketing|sales|content writ|"
    r"finance|accounting|social media|graphic design|digital marketing|"
    r"business development|management trainee|project management|"
    r"ayurved|food quality|psychology|legal|law|teaching|educat|"
    r"civil engineer|mechanical|electrical engineer|interior design|"
    r"fashion|event manag|public relation|influencer|brand manag|"
    r"video edit|administration|training coord|fundrais)\b",
    re.I,
)

# Tech signal whitelist — title must have at least one of these
TECH_SIGNAL = re.compile(
    r"\b(software|developer|engineer|backend|frontend|full.?stack|"
    r"devops|cloud|data|ml|ai|python|node|react|java|web|"
    r"platform|infrastructure|research|api|mobile|android|ios|"
    r"cyber|security|blockchain|database|system|embedded|"
    r"automation|seo|wordpress|testing|firmware|hardware|"
    r"computer science|programming|coding|tech)\b",
    re.I,
)

def _is_tech_role(title: str) -> bool:
    return bool(TECH_SIGNAL.search(title)) and not bool(NON_TECH.search(title))

def _sleep(lo=1.2, hi=2.8):
    time.sleep(random.uniform(lo, hi))

def _get(url: str, params: dict = None, timeout: int = 12,
         extra_headers: dict = None, max_tries: int = 3):
    """GET with retry + backoff. Returns Response or None."""
    h = {**HEADERS, **(extra_headers or {})}
    for attempt in range(max_tries):
        try:
            r = requests.get(url, headers=h, params=params,
                             timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503):
                wait = 5 * (attempt + 1)
                log.warning(f"  Rate-limited ({r.status_code}), retrying in {wait}s…")
                time.sleep(wait)
            else:
                log.warning(f"  HTTP {r.status_code}: {url}")
                return None
        except requests.exceptions.Timeout:
            log.warning(f"  Timeout (attempt {attempt+1})")
        except requests.exceptions.RequestException as e:
            log.warning(f"  Request error: {e}")
        time.sleep(2 ** attempt)
    return None


def _keywords_from_profile(profile: dict, platform: str) -> list:
    """Build search keywords from profile target_roles."""
    ROLE_MAP = {
        "Software Development Engineer Intern (SDE)": {
            "internshala": ["software-development", "computer-science"],
            "unstop":      ["software development", "SDE"],
            "indeed":      ["software developer intern"],
        },
        "Backend Developer Intern": {
            "internshala": ["backend-development", "nodejs", "python"],
            "unstop":      ["backend developer", "python developer"],
            "indeed":      ["backend developer intern"],
        },
        "Full Stack Developer Intern": {
            "internshala": ["web-development", "reactjs", "full-stack-development"],
            "unstop":      ["full stack developer"],
            "indeed":      ["full stack developer intern"],
        },
        "DevOps / Cloud Intern": {
            "internshala": ["cloud-computing", "devops"],
            "unstop":      ["devops", "cloud engineer"],
            "indeed":      ["devops intern", "cloud intern"],
        },
        "AI/ML Engineering Intern": {
            "internshala": ["machine-learning", "data-science", "artificial-intelligence"],
            "unstop":      ["machine learning", "AI developer"],
            "indeed":      ["machine learning intern", "AI engineer intern"],
        },
        "Frontend Developer Intern": {
            "internshala": ["reactjs", "web-development"],
            "unstop":      ["frontend developer"],
            "indeed":      ["frontend developer intern"],
        },
        "Research Engineering Intern": {
            "internshala": ["data-science", "python"],
            "unstop":      ["research engineer"],
            "indeed":      ["research engineer intern"],
        },
    }
    roles = profile.get("internship_preferences", {}).get("target_roles", [])
    seen, out = set(), []
    for role in roles:
        for kw in ROLE_MAP.get(role, {}).get(platform, []):
            if kw not in seen:
                seen.add(kw)
                out.append(kw)
    if not out:
        defaults = {
            "internshala": ["software-development", "python", "web-development"],
            "unstop":      ["software development", "python"],
            "indeed":      ["software engineer intern"],
        }
        out = defaults.get(platform, ["software development"])
    return out


# ---------------------------------------------------------------------------
# Internshala  — HTML scraper with aggressive multi-selector fallback
# ---------------------------------------------------------------------------

def _internshala_detail(url: str) -> dict:
    if not url:
        return {"description": "", "requirements": ""}
    r = _get(url)
    if not r:
        return {"description": "", "requirements": ""}
    soup = BeautifulSoup(r.text, "html.parser")

    desc = ""
    for sel in ["#about_internship", ".about_company_text_container",
                 "[id*='about_internship']", ".internship_details",
                 ".detail_view", "[class*='about']"]:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            desc = el.get_text(" ", strip=True)
            break

    skills = [s.get_text(strip=True)
               for s in soup.select(
                   ".round_tabs span, .skills_container span, "
                   "[class*='skill'] span, .round_tabs"
               ) if s.get_text(strip=True)]
    who = soup.select_one("#who_can_apply, [id*='who_can_apply'], [class*='who_can_apply']")
    req_parts = []
    if skills:
        req_parts.append(", ".join(dict.fromkeys(skills)))  # dedup skills
    if who:
        req_parts.append(who.get_text(" ", strip=True))

    return {
        "description": desc[:600],
        "requirements": " | ".join(req_parts)[:400],
    }


def _parse_card(card, seen: set, category: str) -> Optional[dict]:
    """
    Parse an Internshala card using multiple selector strategies.
    Internshala has changed their HTML several times; this tries all known shapes.
    """
    try:
        # --- Title ---
        title_el = (
            card.select_one(".job-internship-name")             # old shape
            or card.select_one(".profile")                       # newer shape
            or card.select_one("h3 a")
            or card.select_one("h3")
            or card.select_one("[class*='title'] a")
            or card.select_one("[class*='title']")
            or card.select_one("a[class*='name']")
        )
        # --- Company ---
        company_el = (
            card.select_one(".company-name a")
            or card.select_one(".company-name")
            or card.select_one(".company_name")
            or card.select_one("[class*='company'] a")
            or card.select_one("[class*='company']")
        )
        # --- Stipend ---
        stipend_el = (
            card.select_one(".stipend")
            or card.select_one("[class*='stipend']")
            or card.select_one("[id*='stipend']")
        )
        # --- Location ---
        location_el = (
            card.select_one(".location-names")
            or card.select_one(".location_names")
            or card.select_one("[class*='location']")
        )
        # --- Duration ---
        duration_el = (
            card.select_one(".duration-container span")
            or card.select_one("[class*='duration']")
        )
        # --- Link ---
        link_el = (
            card.select_one("a[href*='/internship/detail']")
            or card.select_one("a[href*='/internships/']")
            or card.select_one("h3 a")
            or card.select_one("a")
        )

        title   = title_el.get_text(strip=True)   if title_el   else ""
        company = company_el.get_text(strip=True)  if company_el else ""

        # Clean up Internshala UI noise that sometimes lands in title
        title = re.sub(r"(Actively hiring|Career.Domain|Earn certif.*)", "", title, flags=re.I).strip()

        if not title or not company or len(title) < 3:
            return None

        if not _is_tech_role(title):
            return None

        key = f"{title.lower()}|{company.lower()}"
        if key in seen:
            return None
        seen.add(key)

        href = link_el.get("href", "") if link_el else ""
        job_url = ("https://internshala.com" + href
                   if href and not href.startswith("http") else href)

        return {
            "title":    title,
            "company":  company,
            "location": location_el.get_text(strip=True) if location_el else "India",
            "stipend":  stipend_el.get_text(strip=True)  if stipend_el  else "Not mentioned",
            "duration": duration_el.get_text(strip=True) if duration_el else "N/A",
            "description": "",
            "requirements": "",
            "source": "internshala",
            "url": job_url,
            "_cat": category,
        }
    except Exception:
        return None


def scrape_internshala(profile: dict, max_results: int = 25) -> list:
    keywords = _keywords_from_profile(profile, "internshala")
    all_jobs, seen = [], set()

    for kw in keywords:
        if len(all_jobs) >= max_results:
            break
        url = f"https://internshala.com/internships/{kw}-internship/"
        log.info(f"[Internshala] {kw}")
        r = _get(url)
        if not r:
            continue

        soup = BeautifulSoup(r.text, "html.parser")

        # Try every card container selector we know of
        cards = (
            soup.select("div.individual_internship")
            or soup.select(".internship_meta")
            or soup.select("[id^='individual_internship']")
            or soup.select("[class*='internship_meta']")
            or soup.select(".internship-listing-card")
            or soup.select("[class*='InternshipCard']")
        )

        # Last-resort: if none matched, debug-dump what containers exist
        if not cards:
            log.warning(f"  No cards matched. Page title: {soup.title.string if soup.title else 'N/A'}")
            log.warning(f"  Top-level divs: {[d.get('class') for d in soup.select('div[class]')[:8]]}")
            _sleep(2, 3)
            continue

        log.info(f"  {len(cards)} cards → filtering…")
        batch = []
        for card in cards:
            if len(all_jobs) + len(batch) >= max_results:
                break
            job = _parse_card(card, seen, kw)
            if job:
                batch.append(job)

        log.info(f"  {len(batch)} tech roles found")

        # Fetch details for this batch
        for job in batch:
            if job["url"]:
                details = _internshala_detail(job["url"])
                job["description"]  = details["description"]  or kw.replace("-", " ")
                job["requirements"] = details["requirements"] or kw.replace("-", " ")
            job.pop("_cat", None)
            all_jobs.append(job)
            _sleep(1.0, 2.0)

        _sleep(2, 3)

    log.info(f"[Internshala] Total: {len(all_jobs)}")
    return all_jobs


# ---------------------------------------------------------------------------
# Unstop  — public API with post-fetch tech filtering
# ---------------------------------------------------------------------------

def scrape_unstop(profile: dict, max_results: int = 20) -> list:
    keywords = _keywords_from_profile(profile, "unstop")
    all_jobs, seen = [], set()

    for kw in keywords:
        if len(all_jobs) >= max_results:
            break
        log.info(f"[Unstop] {kw}")

        r = _get(
            "https://unstop.com/api/public/opportunity/search-result",
            params={"search": kw, "type": "internship",
                    "opportunity": "internships", "per_page": 20},
        )
        if not r:
            continue

        try:
            data = r.json()
        except Exception:
            log.warning("  Bad JSON from Unstop")
            continue

        items = (
            data.get("data", {}).get("data", [])
            or data.get("data", [])
            or data.get("items", [])
        )

        for item in items:
            if len(all_jobs) >= max_results:
                break
            try:
                org   = item.get("organisation") or item.get("company") or {}
                title = (item.get("title") or item.get("name") or "").strip()
                company = (org.get("name", "") if isinstance(org, dict) else str(org)).strip()

                if not title or not company:
                    continue
                if not _is_tech_role(title):          # filter non-tech post-fetch
                    continue

                key = f"{title.lower()}|{company.lower()}"
                if key in seen:
                    continue
                seen.add(key)

                slug = item.get("public_url") or item.get("slug") or ""
                job_url = f"https://unstop.com/internships/{slug}" if slug else "https://unstop.com"

                raw_stip = item.get("salary") or item.get("stipend") or ""
                stipend  = (f"₹{raw_stip}/month"
                            if str(raw_stip).isdigit() and int(raw_stip) > 0
                            else str(raw_stip) or "Not mentioned")

                raw_desc = item.get("description") or item.get("about") or ""
                desc = BeautifulSoup(raw_desc, "html.parser").get_text(" ", strip=True)

                skills = item.get("skills") or []
                req    = ", ".join(skills) if skills else kw

                all_jobs.append({
                    "title":       title,
                    "company":     company,
                    "location":    item.get("city") or item.get("location") or "Remote",
                    "stipend":     stipend,
                    "duration":    str(item.get("duration") or "N/A"),
                    "description": desc[:600] or kw,
                    "requirements": req[:400],
                    "source":      "unstop",
                    "url":         job_url,
                })
            except Exception:
                continue

        _sleep(1, 2)

    log.info(f"[Unstop] Total: {len(all_jobs)}")
    return all_jobs


# ---------------------------------------------------------------------------
# Indeed India  — static HTML, works without auth
# ---------------------------------------------------------------------------

def scrape_indeed(profile: dict, max_results: int = 20) -> list:
    """
    Scrapes Indeed India's public job listings.
    Indeed renders enough in static HTML for basic card data.
    """
    keywords = _keywords_from_profile(profile, "indeed")
    prefs    = profile.get("internship_preferences", {})
    locations = [l for l in prefs.get("preferred_locations", []) if l != "Remote"]
    location  = locations[0] if locations else "India"

    all_jobs, seen = [], set()

    for kw in keywords:
        if len(all_jobs) >= max_results:
            break
        log.info(f"[Indeed] {kw} in {location}")

        r = _get(
            "https://in.indeed.com/jobs",
            params={"q": kw, "l": location, "fromage": "14"},  # last 14 days
            extra_headers={"Referer": "https://in.indeed.com/"},
        )
        if not r:
            continue

        soup = BeautifulSoup(r.text, "html.parser")

        cards = (
            soup.select(".job_seen_beacon")
            or soup.select(".tapItem")
            or soup.select("[class*='job_seen']")
            or soup.select("[class*='cardOutline']")
            or soup.select("li[class*='css-']")  # Indeed's generated class names
        )

        log.info(f"  {len(cards)} cards found")

        for card in cards:
            if len(all_jobs) >= max_results:
                break
            try:
                title_el   = (card.select_one(".jobTitle span[title]")
                               or card.select_one(".jobTitle")
                               or card.select_one("h2 a span")
                               or card.select_one("h2"))
                company_el = (card.select_one(".companyName")
                               or card.select_one("[class*='companyName']")
                               or card.select_one(".css-1h7lukg"))
                location_el = (card.select_one(".companyLocation")
                                or card.select_one("[class*='companyLocation']"))
                salary_el   = card.select_one(".salary-snippet, [class*='salary']")
                link_el     = card.select_one("a[id^='job_'], a[href*='/rc/clk']")

                title   = (title_el.get("title") or title_el.get_text(strip=True)) if title_el else ""
                company = company_el.get_text(strip=True) if company_el else ""

                if not title or not company:
                    continue
                if not _is_tech_role(title):
                    continue

                key = f"{title.lower()}|{company.lower()}"
                if key in seen:
                    continue
                seen.add(key)

                href = link_el.get("href", "") if link_el else ""
                job_url = ("https://in.indeed.com" + href
                           if href and not href.startswith("http") else href)

                all_jobs.append({
                    "title":        title,
                    "company":      company,
                    "location":     location_el.get_text(strip=True) if location_el else location,
                    "stipend":      salary_el.get_text(strip=True) if salary_el else "Not mentioned",
                    "duration":     "N/A",
                    "description":  f"{kw} role at {company}",
                    "requirements": kw,
                    "source":       "indeed",
                    "url":          job_url,
                })
            except Exception:
                continue

        _sleep(2, 4)

    log.info(f"[Indeed] Total: {len(all_jobs)}")
    return all_jobs


# ---------------------------------------------------------------------------
# Master entry point
# ---------------------------------------------------------------------------

def run_scout(profile: dict, max_per_source: int = 20) -> list:
    """
    Run all scrapers → merge → deduplicate → return list of job dicts.
    Each dict: title, company, location, stipend, duration,
               description, requirements, source, url
    """
    log.info("=== Scout Agent starting ===\n")
    all_jobs, global_seen = [], set()

    sources = [
        ("Internshala", scrape_internshala),
        ("Unstop",      scrape_unstop),
        ("Indeed",      scrape_indeed),
    ]

    for name, fn in sources:
        try:
            jobs = fn(profile, max_results=max_per_source)
            added = 0
            for job in jobs:
                key = f"{job['title'].lower()}|{job['company'].lower()}"
                if key not in global_seen:
                    global_seen.add(key)
                    all_jobs.append(job)
                    added += 1
            log.info(f"[{name}] {added} unique listings added\n")
        except Exception as e:
            log.warning(f"[{name}] Scraper failed: {e}")

    log.info(f"=== Scout done — {len(all_jobs)} total listings ===\n")
    return all_jobs


# ---------------------------------------------------------------------------
# Standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from tools.profile_loader import load_profile
    from agents.fit_scorer import score_opportunity
    from tools.job_queue import add_job, print_queue

    profile = load_profile()
    jobs = run_scout(profile, max_per_source=10)

    if not jobs:
        print("No listings found from any source.")
        sys.exit(0)

    print(f"\nScoring {len(jobs)} listings…\n")
    for job in jobs:
        result = score_opportunity(job)
        add_job(job, result)
        icon = "✅" if result["verdict"] == "apply" else "👀" if result["verdict"] == "review" else "❌"
        print(f"{icon} {result['score']:>3}/100 — {job['title']} @ {job['company']} [{job['source']}]")
        print(f"     {job.get('requirements','')[:80]}")
        print()

    print_queue()