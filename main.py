"""
Intern Agent — Master Orchestrator
Runs the full pipeline with one command: python main.py

Pipeline:
    START
      │
      ▼
   scout_node        — scrape Internshala, Unstop, Indeed
      │
      ▼
   score_node        — score each job with Groq/Llama
      │
      ▼
   queue_node        — deduplicate and save to job queue
      │
      ▼
   dashboard_node    — open interactive CLI review
      │
      ▼
    END

Usage:
    python main.py                  # full pipeline
    python main.py --scout-only     # scrape + score, skip dashboard
    python main.py --dashboard-only # just open dashboard (no scraping)
    python main.py --max N          # max N listings per source (default 20)
"""

import os
import sys
import argparse
import logging
from typing import TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, END

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared pipeline state
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    # Inputs
    max_per_source: int

    # Scout output
    raw_jobs: Annotated[list, operator.add]        # jobs found by scout

    # Score output
    scored_jobs: Annotated[list, operator.add]     # jobs with scores attached

    # Queue output
    added_ids: Annotated[list, operator.add]       # job IDs added to queue
    skipped_duplicates: int                        # duplicates skipped

    # Control
    errors: Annotated[list, operator.add]          # any errors encountered
    run_dashboard: bool                            # whether to open dashboard


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def scout_node(state: AgentState) -> dict:
    """Scrape all sources and return raw job listings."""
    log.info("\n" + "="*60)
    log.info("  STEP 1 — Scout Agent")
    log.info("="*60)

    try:
        from tools.profile_loader import load_profile
        from agents.scout_agent import run_scout

        profile = load_profile()
        jobs = run_scout(profile, max_per_source=state["max_per_source"])

        log.info(f"\n✅ Scout complete — {len(jobs)} listings found")
        return {"raw_jobs": jobs, "errors": []}

    except Exception as e:
        log.error(f"❌ Scout failed: {e}")
        return {"raw_jobs": [], "errors": [f"scout_node: {e}"]}


def score_node(state: AgentState) -> dict:
    """Score each raw job against the candidate profile."""
    log.info("\n" + "="*60)
    log.info("  STEP 2 — Fit Scorer")
    log.info("="*60)

    raw_jobs = state.get("raw_jobs", [])
    if not raw_jobs:
        log.warning("No jobs to score — skipping")
        return {"scored_jobs": [], "errors": []}

    try:
        from agents.fit_scorer import score_opportunity

        scored = []
        for i, job in enumerate(raw_jobs, 1):
            try:
                result = score_opportunity(job)
                scored.append(result)
                icon = "✅" if result["verdict"] == "apply" \
                    else "👀" if result["verdict"] == "review" else "❌"
                log.info(f"  {icon} {result['score']:>3}/100 — "
                         f"{job['title']} @ {job['company']} [{job.get('source','?')}]")
            except Exception as e:
                log.warning(f"  ⚠ Could not score {job.get('title','?')}: {e}")
                continue

        log.info(f"\n✅ Scoring complete — {len(scored)}/{len(raw_jobs)} scored")
        return {"scored_jobs": scored, "errors": []}

    except Exception as e:
        log.error(f"❌ Scorer failed: {e}")
        return {"scored_jobs": [], "errors": [f"score_node: {e}"]}


def queue_node(state: AgentState) -> dict:
    """Save scored jobs to the queue, skipping duplicates."""
    log.info("\n" + "="*60)
    log.info("  STEP 3 — Job Queue")
    log.info("="*60)

    scored_jobs = state.get("scored_jobs", [])
    if not scored_jobs:
        log.warning("No scored jobs to queue — skipping")
        return {"added_ids": [], "skipped_duplicates": 0, "errors": []}

    try:
        from tools.job_queue import add_job, get_all

        existing = {
            f"{j['job']['title'].lower()}|{j['job']['company'].lower()}"
            for j in get_all()
        }

        added_ids, skipped = [], 0
        apply_count, review_count, skip_count = 0, 0, 0

        for result in scored_jobs:
            job = result.get("job", {})
            key = f"{job.get('title','').lower()}|{job.get('company','').lower()}"

            if key in existing:
                skipped += 1
                continue

            job_id = add_job(job, result)
            added_ids.append(job_id)
            existing.add(key)

            v = result.get("verdict", "skip")
            if v == "apply":   apply_count += 1
            elif v == "review": review_count += 1
            else:               skip_count += 1

        log.info(f"\n  Added  : {len(added_ids)} new listings")
        log.info(f"  Dupes  : {skipped} skipped")
        log.info(f"  Breakdown → ✅ {apply_count} apply  "
                 f"👀 {review_count} review  ❌ {skip_count} skip")
        log.info(f"\n✅ Queue updated")
        return {
            "added_ids": added_ids,
            "skipped_duplicates": skipped,
            "errors": [],
        }

    except Exception as e:
        log.error(f"❌ Queue node failed: {e}")
        return {"added_ids": [], "skipped_duplicates": 0, "errors": [f"queue_node: {e}"]}


def dashboard_node(state: AgentState) -> dict:
    """Open the interactive CLI review dashboard."""
    if not state.get("run_dashboard", True):
        log.info("\nDashboard skipped (--scout-only mode)")
        return {}

    added = state.get("added_ids", [])
    if not added:
        log.info("\nNo new listings added — nothing to review")
        _print_final_summary(state)
        return {}

    log.info("\n" + "="*60)
    log.info("  STEP 4 — Review Dashboard")
    log.info("="*60)
    log.info(f"\n  {len(added)} new listings ready for review\n")

    try:
        from tools.dashboard import run_review
        run_review()
    except Exception as e:
        log.error(f"❌ Dashboard failed: {e}")
        log.info("  Run manually: python -m tools.dashboard")

    return {}


def _print_final_summary(state: AgentState):
    """Print a quick stats summary at the end."""
    log.info("\n" + "="*60)
    log.info("  PIPELINE COMPLETE")
    log.info("="*60)
    log.info(f"  Jobs found   : {len(state.get('raw_jobs', []))}")
    log.info(f"  Jobs scored  : {len(state.get('scored_jobs', []))}")
    log.info(f"  Jobs added   : {len(state.get('added_ids', []))}")
    log.info(f"  Duplicates   : {state.get('skipped_duplicates', 0)}")
    errors = state.get("errors", [])
    if errors:
        log.warning(f"  Errors       : {len(errors)}")
        for e in errors:
            log.warning(f"    • {e}")
    log.info("="*60)
    log.info("  Run  python -m tools.dashboard  to review anytime")
    log.info("="*60 + "\n")


# ---------------------------------------------------------------------------
# Build the LangGraph pipeline
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("scout",     scout_node)
    graph.add_node("score",     score_node)
    graph.add_node("queue",     queue_node)
    graph.add_node("dashboard", dashboard_node)

    graph.set_entry_point("scout")
    graph.add_edge("scout",     "score")
    graph.add_edge("score",     "queue")
    graph.add_edge("queue",     "dashboard")
    graph.add_edge("dashboard", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Intern Agent — Master Orchestrator")
    parser.add_argument("--scout-only",     action="store_true",
                        help="Scrape and score only, skip dashboard")
    parser.add_argument("--dashboard-only", action="store_true",
                        help="Open dashboard without scraping")
    parser.add_argument("--max", type=int, default=20,
                        help="Max listings per source (default: 20)")
    args = parser.parse_args()

    # Dashboard-only shortcut — skip the graph entirely
    if args.dashboard_only:
        from tools.dashboard import run_review
        run_review()
        sys.exit(0)

    log.info("\n🤖 Intern Agent — Starting Pipeline")
    log.info(f"   Max per source : {args.max}")
    log.info(f"   Mode           : {'scout-only' if args.scout_only else 'full pipeline'}\n")

    pipeline = build_graph()

    initial_state: AgentState = {
        "max_per_source":     args.max,
        "raw_jobs":           [],
        "scored_jobs":        [],
        "added_ids":          [],
        "skipped_duplicates": 0,
        "errors":             [],
        "run_dashboard":      not args.scout_only,
    }

    final_state = pipeline.invoke(initial_state)
    _print_final_summary(final_state)