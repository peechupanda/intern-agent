"""
Daily Review Dashboard — CLI

Usage:
    python -m tools.dashboard          # review pending jobs
    python -m tools.dashboard --all    # show full queue summary
    python -m tools.dashboard --reset  # clear the queue (fresh start)
"""

import os
import sys
import json
import argparse
import webbrowser
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.job_queue import get_pending, get_approved, get_all, update_status, _load

# ---------------------------------------------------------------------------
# Terminal colours (works on Windows 10+ and all Unix)
# ---------------------------------------------------------------------------

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    WHITE  = "\033[97m"
    BG_DARK = "\033[40m"

def enable_ansi_windows():
    """Enable ANSI escape codes on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

def cls():
    os.system("cls" if sys.platform == "win32" else "clear")

# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

VERDICT_COLOUR = {
    "apply":  C.GREEN,
    "review": C.YELLOW,
    "skip":   C.RED,
}

STATUS_COLOUR = {
    "pending":  C.YELLOW,
    "approved": C.GREEN,
    "skipped":  C.RED,
    "deferred": C.CYAN,
}

def score_bar(score: int, width: int = 20) -> str:
    filled = int(score / 100 * width)
    colour = C.GREEN if score >= 70 else C.YELLOW if score >= 50 else C.RED
    bar = "█" * filled + "░" * (width - filled)
    return f"{colour}{bar}{C.RESET}"

def verdict_badge(verdict: str) -> str:
    icons = {"apply": "✅", "review": "👀", "skip": "❌"}
    col   = VERDICT_COLOUR.get(verdict, C.WHITE)
    return f"{col}{icons.get(verdict, '?')} {verdict.upper()}{C.RESET}"

def source_badge(source: str) -> str:
    colours = {
        "internshala": C.BLUE,
        "unstop":      C.CYAN,
        "indeed":      C.GREEN,
        "linkedin":    C.BLUE,
    }
    col = colours.get(source.lower(), C.WHITE)
    return f"{col}[{source}]{C.RESET}"

def divider(char="─", width=70):
    print(C.DIM + char * width + C.RESET)

def header(text: str, width=70):
    pad = (width - len(text) - 2) // 2
    print(C.BOLD + C.CYAN + "─" * pad + f" {text} " + "─" * pad + C.RESET)

# ---------------------------------------------------------------------------
# Job card display
# ---------------------------------------------------------------------------

def print_job_card(entry: dict, index: int, total: int):
    job     = entry["job"]
    score   = entry.get("score", 0)
    verdict = entry.get("verdict", "skip")
    reasons = entry.get("reasons", [])
    gaps    = entry.get("gaps", [])
    source  = job.get("source", "unknown")

    cls()
    header(f"INTERNSHIP REVIEW  {index}/{total}")
    print()

    # Title + company
    print(f"  {C.BOLD}{C.WHITE}{job.get('title', 'N/A')}{C.RESET}  "
          f"{source_badge(source)}")
    print(f"  {C.DIM}@ {job.get('company', 'N/A')}  •  "
          f"{job.get('location', 'N/A')}{C.RESET}")
    print()

    # Score bar
    print(f"  Score   {score_bar(score)}  "
          f"{C.BOLD}{score}/100{C.RESET}  {verdict_badge(verdict)}")
    print(f"  Stipend {C.BOLD}{job.get('stipend', 'Not mentioned')}{C.RESET}  "
          f"│  Duration {C.BOLD}{job.get('duration', 'N/A')}{C.RESET}  "
          f"│  Stipend OK {C.GREEN + '✓' if entry.get('stipend_ok') else C.RED + '✗'}{C.RESET}")
    print()

    # Reasons
    if reasons:
        print(f"  {C.GREEN}Why it fits:{C.RESET}")
        for r in reasons:
            print(f"    {C.DIM}•{C.RESET} {r}")
        print()

    # Gaps
    if gaps:
        print(f"  {C.YELLOW}Gaps:{C.RESET}")
        for g in gaps:
            print(f"    {C.DIM}•{C.RESET} {g}")
        print()

    # Requirements snippet
    req = job.get("requirements", "")
    if req and req != "N/A":
        print(f"  {C.DIM}Requirements: {req[:120]}{'…' if len(req) > 120 else ''}{C.RESET}")
        print()

    # URL
    url = job.get("url", "")
    if url:
        print(f"  {C.CYAN}🔗 {url[:80]}{C.RESET}")
        print()

    divider()
    print(f"  {C.BOLD}[a]{C.RESET} Approve   "
          f"{C.BOLD}[s]{C.RESET} Skip   "
          f"{C.BOLD}[d]{C.RESET} Defer   "
          f"{C.BOLD}[o]{C.RESET} Open URL   "
          f"{C.BOLD}[q]{C.RESET} Quit")
    divider()


# ---------------------------------------------------------------------------
# Summary screen
# ---------------------------------------------------------------------------

def print_summary():
    all_jobs = get_all()
    if not all_jobs:
        print(f"\n{C.YELLOW}Queue is empty.{C.RESET}\n")
        return

    approved = [j for j in all_jobs if j["status"] == "approved"]
    skipped  = [j for j in all_jobs if j["status"] == "skipped"]
    deferred = [j for j in all_jobs if j["status"] == "deferred"]
    pending  = [j for j in all_jobs if j["status"] == "pending"]

    cls()
    header("QUEUE SUMMARY")
    print()
    print(f"  Total listings : {C.BOLD}{len(all_jobs)}{C.RESET}")
    print(f"  {C.GREEN}✅ Approved  : {len(approved)}{C.RESET}")
    print(f"  {C.RED}❌ Skipped   : {len(skipped)}{C.RESET}")
    print(f"  {C.CYAN}⏸  Deferred  : {len(deferred)}{C.RESET}")
    print(f"  {C.YELLOW}⏳ Pending   : {len(pending)}{C.RESET}")
    print()

    if approved:
        header("APPROVED — Ready to Apply")
        print()
        for j in sorted(approved, key=lambda x: x["score"], reverse=True):
            col = VERDICT_COLOUR.get(j["verdict"], C.WHITE)
            print(f"  {C.GREEN}✅{C.RESET} {j['score']:>3}/100  "
                  f"{C.BOLD}{j['job']['title'][:35]:<35}{C.RESET}  "
                  f"{j['job']['company'][:25]:<25}  "
                  f"{source_badge(j['job'].get('source','?'))}")
            if j["job"].get("url"):
                print(f"       {C.DIM}{j['job']['url'][:70]}{C.RESET}")
        print()

    if pending:
        header(f"PENDING — {len(pending)} left to review")
        print()
        for j in sorted(pending, key=lambda x: x["score"], reverse=True):
            vc = VERDICT_COLOUR.get(j["verdict"], C.WHITE)
            print(f"  {vc}●{C.RESET} {j['score']:>3}/100  "
                  f"{j['job']['title'][:35]:<35}  "
                  f"{j['job']['company'][:25]}")
        print()

    # Source breakdown
    from collections import Counter
    sources = Counter(j["job"].get("source", "unknown") for j in all_jobs)
    header("BY SOURCE")
    print()
    for src, count in sources.most_common():
        print(f"  {source_badge(src)}  {count} listings")
    print()

    divider()
    print(f"  {C.DIM}Run  python -m tools.dashboard  to review pending listings{C.RESET}")
    divider()
    print()


# ---------------------------------------------------------------------------
# Interactive review loop
# ---------------------------------------------------------------------------

def run_review():
    pending = sorted(get_pending(), key=lambda x: x.get("score", 0), reverse=True)

    if not pending:
        print(f"\n{C.GREEN}✅ No pending listings to review!{C.RESET}")
        print_summary()
        return

    approved_count = 0
    skipped_count  = 0
    deferred_count = 0
    total = len(pending)

    for i, entry in enumerate(pending, 1):
        print_job_card(entry, i, total)

        while True:
            try:
                key = input("\n  Your choice: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print(f"\n\n{C.YELLOW}Interrupted. Progress saved.{C.RESET}\n")
                break

            if key == "a":
                update_status(entry["id"], "approved")
                approved_count += 1
                print(f"  {C.GREEN}✅ Approved!{C.RESET}")
                break
            elif key == "s":
                update_status(entry["id"], "skipped")
                skipped_count += 1
                print(f"  {C.RED}❌ Skipped.{C.RESET}")
                break
            elif key == "d":
                update_status(entry["id"], "deferred")
                deferred_count += 1
                print(f"  {C.CYAN}⏸  Deferred.{C.RESET}")
                break
            elif key == "o":
                url = entry["job"].get("url", "")
                if url:
                    webbrowser.open(url)
                    print(f"  {C.CYAN}Opened in browser.{C.RESET}")
                else:
                    print(f"  {C.YELLOW}No URL available.{C.RESET}")
            elif key == "q":
                print(f"\n{C.YELLOW}Quit. Progress saved.{C.RESET}\n")
                _print_session_summary(approved_count, skipped_count, deferred_count)
                return
            else:
                print(f"  {C.DIM}Invalid — press a / s / d / o / q{C.RESET}")

    print()
    divider()
    _print_session_summary(approved_count, skipped_count, deferred_count)
    print()
    print_summary()


def _print_session_summary(approved, skipped, deferred):
    print(f"\n  {C.BOLD}Session complete:{C.RESET}")
    print(f"    {C.GREEN}✅ Approved : {approved}{C.RESET}")
    print(f"    {C.RED}❌ Skipped  : {skipped}{C.RESET}")
    print(f"    {C.CYAN}⏸  Deferred : {deferred}{C.RESET}")
    divider()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    enable_ansi_windows()

    parser = argparse.ArgumentParser(description="Intern Agent — Daily Review Dashboard")
    parser.add_argument("--all",   action="store_true", help="Show full queue summary")
    parser.add_argument("--reset", action="store_true", help="Clear the job queue")
    args = parser.parse_args()

    if args.reset:
        confirm = input("Clear entire job queue? [y/N]: ").strip().lower()
        if confirm == "y":
            queue_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "job_queue.json"
            )
            if os.path.exists(queue_path):
                os.remove(queue_path)
                print(f"{C.GREEN}Queue cleared.{C.RESET}")
            else:
                print(f"{C.YELLOW}Queue already empty.{C.RESET}")
    elif args.all:
        print_summary()
    else:
        run_review()