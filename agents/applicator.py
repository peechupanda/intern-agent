"""
Applicator Agent — auto-fills and submits internship applications.

Flow per job:
  1. Generate custom cover letter (Groq/Llama)
  2. Open job URL in Playwright browser
  3. Login to platform if needed
  4. Auto-fill form fields
  5. Pause — user reviews filled form
  6. User presses Enter to submit or 's' to skip
  7. Update queue status → applied / skipped

Supported platforms:
  - Internshala  : full auto-fill + submit
  - Unstop       : open in browser, manual apply
  - Indeed       : open in browser, manual apply

Usage:
    python -m agents.applicator          # apply to all approved jobs
    python -m agents.applicator --dry    # dry run (no submission)

Setup:
  - Add resume PDF at data/resume.pdf
  - Add to .env:
      INTERNSHALA_EMAIL=your@email.com
      INTERNSHALA_PASSWORD=yourpassword
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.profile_loader import load_profile, summarise_profile
from tools.job_queue import get_approved, update_status, _load, _save

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

llm = ChatGroq(model="llama-3.3-70b-versatile")

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

class C:
    RESET  = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
    GREEN  = "\033[92m"; YELLOW = "\033[93m"; RED = "\033[91m"
    CYAN   = "\033[96m"; WHITE = "\033[97m"

def enable_ansi():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Cover letter generator
# ---------------------------------------------------------------------------

def generate_cover_letter(job: dict, profile: dict) -> str:
    """Generate a tailored cover letter using Groq/Llama."""
    summary = summarise_profile(profile)
    prompt = f"""
Write a concise, genuine internship cover letter for this candidate applying to this role.

RULES:
- 3 short paragraphs, max 150 words total
- Paragraph 1: Why this specific company/role excites them (be specific to the JD)
- Paragraph 2: 2-3 concrete skills/projects that directly match the requirements
- Paragraph 3: One sentence closing with availability
- Sound like a real student, not a template — no "I am writing to express my interest"
- Do NOT include subject line, date, or "Dear Hiring Manager"
- Return only the cover letter text, nothing else

Candidate:
{summary}

Job:
Title: {job.get('title', 'N/A')}
Company: {job.get('company', 'N/A')}
Description: {job.get('description', 'N/A')[:400]}
Requirements: {job.get('requirements', 'N/A')[:300]}
"""
    try:
        response = llm.invoke(prompt)
        return response.content.strip()
    except Exception as e:
        log.warning(f"  Cover letter generation failed: {e}")
        return (f"I'm excited to apply for the {job.get('title')} role at "
                f"{job.get('company')}. My experience with "
                f"{', '.join(list(profile['skills'].get('backend', []))[:3])} "
                f"makes me a strong fit. I'm available immediately for a full-time internship.")


# ---------------------------------------------------------------------------
# Internshala applicator
# ---------------------------------------------------------------------------

def _internshala_login(page, email: str, password: str) -> bool:
    """Login to Internshala. Returns True if successful."""
    try:
        page.goto("https://internshala.com/login/user", wait_until="domcontentloaded", timeout=15000)
        time.sleep(1)

        # Fill login form
        page.fill("#email", email)
        page.fill("#password", password)
        page.click("#login_submit")
        time.sleep(2)

        # Check if login succeeded
        if "dashboard" in page.url or "student" in page.url:
            log.info("  ✅ Logged in to Internshala")
            return True

        # Sometimes redirects to home — check for logout link
        if page.query_selector("a[href*='logout']"):
            log.info("  ✅ Logged in to Internshala")
            return True

        log.warning("  ⚠ Login may have failed — check credentials in .env")
        return False
    except Exception as e:
        log.warning(f"  Login error: {e}")
        return False


def _apply_internshala(page, job: dict, cover_letter: str,
                       resume_path: str, dry_run: bool) -> bool:
    """
    Navigate to job page, click Apply, fill cover letter + resume, pause for review.
    Returns True if applied/skipped by user, False on error.
    """
    try:
        log.info(f"  Opening: {job['url']}")
        page.goto(job["url"], wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)

        # Click the Apply button
        apply_btn = (
            page.query_selector("#apply_now_btn")
            or page.query_selector(".apply_button")
            or page.query_selector("button:has-text('Apply Now')")
            or page.query_selector("a:has-text('Apply Now')")
        )
        if not apply_btn:
            log.warning("  Could not find Apply button")
            return False

        apply_btn.click()
        time.sleep(2)

        # Fill cover letter
        cover_field = (
            page.query_selector("#cover_letter_holder")
            or page.query_selector("textarea[name='cover_letter']")
            or page.query_selector("textarea[placeholder*='cover']")
            or page.query_selector(".cover_letter_box textarea")
        )
        if cover_field:
            cover_field.fill(cover_letter)
            log.info("  ✅ Cover letter filled")
        else:
            log.warning("  ⚠ Cover letter field not found")

        # Upload resume if field exists
        if resume_path and os.path.exists(resume_path):
            resume_input = (
                page.query_selector("input[type='file'][name*='resume']")
                or page.query_selector("input[type='file']")
            )
            if resume_input:
                resume_input.set_input_files(resume_path)
                log.info("  ✅ Resume uploaded")
                time.sleep(1)
        else:
            log.warning(f"  ⚠ Resume not found at {resume_path}")

        # Pause for user review
        print(f"\n  {C.CYAN}{'─'*55}{C.RESET}")
        print(f"  {C.BOLD}Form filled for: {job['title']} @ {job['company']}{C.RESET}")
        print(f"  {C.DIM}Review the browser window before submitting.{C.RESET}")
        print(f"  {C.CYAN}{'─'*55}{C.RESET}")

        if dry_run:
            print(f"  {C.YELLOW}[DRY RUN] Skipping submission.{C.RESET}")
            return True

        choice = input(f"\n  Press {C.GREEN}Enter{C.RESET} to SUBMIT  "
                       f"or {C.RED}s{C.RESET} to SKIP: ").strip().lower()

        if choice == "s":
            log.info("  Skipped by user.")
            return False

        # Submit the form
        submit_btn = (
            page.query_selector("#submit_button")
            or page.query_selector("button[type='submit']")
            or page.query_selector("input[type='submit']")
            or page.query_selector("button:has-text('Submit')")
        )
        if submit_btn:
            submit_btn.click()
            time.sleep(2)
            log.info(f"  {C.GREEN}✅ Application submitted!{C.RESET}")
            return True
        else:
            log.warning("  ⚠ Submit button not found — please submit manually")
            input("  Press Enter when done: ")
            return True

    except Exception as e:
        log.warning(f"  Internshala apply error: {e}")
        return False


def _apply_manual(page, job: dict, cover_letter: str) -> bool:
    """
    For Unstop/Indeed — open in browser, show cover letter, let user apply manually.
    """
    try:
        log.info(f"  Opening in browser: {job['url']}")
        page.goto(job["url"], wait_until="domcontentloaded", timeout=20000)

        print(f"\n  {C.CYAN}{'─'*55}{C.RESET}")
        print(f"  {C.BOLD}Manual apply: {job['title']} @ {job['company']}{C.RESET}")
        print(f"  {C.DIM}Source: {job.get('source','?')} — apply manually in the browser{C.RESET}")
        print(f"\n  {C.YELLOW}Generated cover letter:{C.RESET}")
        print(f"  {C.DIM}{'─'*50}{C.RESET}")
        for line in cover_letter.split("\n"):
            print(f"  {line}")
        print(f"  {C.DIM}{'─'*50}{C.RESET}")
        print(f"  (Cover letter also saved to clipboard if pyperclip is installed)\n")

        # Try to copy to clipboard
        try:
            import pyperclip
            pyperclip.copy(cover_letter)
            print(f"  {C.GREEN}✅ Cover letter copied to clipboard{C.RESET}")
        except Exception:
            pass

        choice = input(f"\n  Press {C.GREEN}Enter{C.RESET} when applied  "
                       f"or {C.RED}s{C.RESET} to skip: ").strip().lower()
        return choice != "s"

    except Exception as e:
        log.warning(f"  Manual apply error: {e}")
        return False


# ---------------------------------------------------------------------------
# Status tracker
# ---------------------------------------------------------------------------

def _mark_applied(job_id: str, cover_letter: str):
    """Save applied status + cover letter to queue."""
    queue = _load()
    for item in queue:
        if item["id"] == job_id:
            item["status"] = "applied"
            item["applied_at"] = datetime.now().isoformat()
            item["cover_letter"] = cover_letter
    _save(queue)


def _mark_skipped_apply(job_id: str):
    queue = _load()
    for item in queue:
        if item["id"] == job_id:
            item["status"] = "apply_skipped"
            item["updated_at"] = datetime.now().isoformat()
    _save(queue)


# ---------------------------------------------------------------------------
# Main applicator runner
# ---------------------------------------------------------------------------

def run_applicator(dry_run: bool = False):
    from playwright.sync_api import sync_playwright

    profile     = load_profile()
    approved    = get_approved()
    resume_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "resume.pdf"
    )

    email    = os.getenv("INTERNSHALA_EMAIL", "")
    password = os.getenv("INTERNSHALA_PASSWORD", "")

    if not approved:
        print(f"\n{C.YELLOW}No approved jobs to apply to.{C.RESET}")
        print(f"Run  {C.BOLD}python main.py{C.RESET}  first, then approve jobs in the dashboard.\n")
        return

    print(f"\n{C.BOLD}{C.CYAN}{'='*60}{C.RESET}")
    print(f"  Auto-Applicator — {len(approved)} approved jobs")
    if dry_run:
        print(f"  {C.YELLOW}DRY RUN MODE — forms will be filled but not submitted{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'='*60}{C.RESET}\n")

    applied_count = 0
    skipped_count = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page    = context.new_page()

        # Login to Internshala once upfront
        internshala_jobs = [j for j in approved
                            if j["job"].get("source") == "internshala"]
        logged_in = False
        if internshala_jobs and email and password:
            log.info("Logging in to Internshala…")
            logged_in = _internshala_login(page, email, password)
        elif internshala_jobs and not email:
            log.warning("⚠ INTERNSHALA_EMAIL not set in .env — skipping login")

        for entry in approved:
            job    = entry["job"]
            source = job.get("source", "unknown")

            print(f"\n{'─'*60}")
            print(f"  {C.BOLD}{job['title']}{C.RESET} @ {job['company']}")
            print(f"  Score: {entry['score']}/100  |  Source: {source_badge(source)}")
            print(f"{'─'*60}")

            # Generate cover letter
            log.info("  Generating cover letter…")
            cover_letter = generate_cover_letter(job, profile)
            log.info("  ✅ Cover letter ready")

            # Apply based on source
            if source == "internshala" and logged_in:
                success = _apply_internshala(
                    page, job, cover_letter, resume_path, dry_run)
            else:
                # Unstop, Indeed, or not logged in → manual
                success = _apply_manual(page, job, cover_letter)

            if success:
                _mark_applied(entry["id"], cover_letter)
                applied_count += 1
                print(f"  {C.GREEN}✅ Marked as applied{C.RESET}")
            else:
                _mark_skipped_apply(entry["id"])
                skipped_count += 1
                print(f"  {C.YELLOW}⏭ Skipped{C.RESET}")

            time.sleep(1)

        browser.close()

    print(f"\n{'='*60}")
    print(f"  {C.BOLD}Applicator complete{C.RESET}")
    print(f"  {C.GREEN}✅ Applied  : {applied_count}{C.RESET}")
    print(f"  {C.YELLOW}⏭ Skipped  : {skipped_count}{C.RESET}")
    print(f"{'='*60}\n")


def source_badge(source: str) -> str:
    colours = {"internshala": "\033[94m", "unstop": "\033[96m", "indeed": "\033[92m"}
    col = colours.get(source.lower(), "\033[97m")
    return f"{col}[{source}]\033[0m"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    enable_ansi()
    parser = argparse.ArgumentParser(description="Intern Agent — Auto Applicator")
    parser.add_argument("--dry", action="store_true",
                        help="Fill forms but don't submit")
    args = parser.parse_args()
    run_applicator(dry_run=args.dry)