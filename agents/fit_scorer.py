from langchain_groq import ChatGroq
from dotenv import load_dotenv
from tools.profile_loader import load_profile, summarise_profile
import os, json, re

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

llm = ChatGroq(model="llama-3.3-70b-versatile")


def _clean_requirements(req: str) -> str:
    """Strip Internshala UI noise from requirements string."""
    noise = [
        r"Skill\(s\) required[,\s]*",
        r"Earn certifications? in these skills?[^|]*",
        r"\+\s*\d+\s*more skills?[^|]*",
        r"Only those candidates can apply who.*",
        r"Actively hiring",
        r"Career.Domain",
        r"\|\s*\|",
    ]
    for pattern in noise:
        req = re.sub(pattern, "", req, flags=re.I)
    return re.sub(r"\s{2,}", " ", req).strip(" |,")


def score_opportunity(job: dict) -> dict:
    profile  = load_profile()
    summary  = summarise_profile(profile)
    hard_filters = profile["internship_preferences"]["hard_filters"]
    top_tier     = profile["internship_preferences"]["top_tier_companies"]

    # Clean noisy fields before sending to LLM
    title       = job.get("title", "N/A")
    company     = job.get("company", "N/A")
    location    = job.get("location", "N/A")
    stipend     = job.get("stipend", "Not mentioned")
    duration    = job.get("duration", "N/A")
    description = job.get("description", "N/A")
    requirements = _clean_requirements(job.get("requirements", ""))

    prompt = f"""
You are an internship fit scorer for a developer candidate. Score the job and return a JSON object.

SCORING RULES — read carefully:
1. Score based on SKILL MATCH between candidate's stack and the job's tech requirements.
2. If requirements mention Python, Django, Flask, ML, AI, Node.js, React, MongoDB, Docker, AWS,
   DevOps, JavaScript, Express, REST API, or any tech from the candidate's profile → score >= 60.
3. If requirements are vague or mostly noise (e.g. "certificate", "full time available") →
   assume it's a general dev role and score based on title alone. Do NOT score 0 for vague requirements.
4. Only score 0–30 for clearly non-tech roles: HR, marketing, sales, content writing.
5. The candidate is a 1st-year student — do NOT penalise for missing experience.
6. Stipend below ₹5000/month → stipend_ok = false. "Not mentioned" → stipend_ok = true (assume ok).

VERDICT:
- score >= 70 → "apply"
- score 50–69 → "review"  
- score < 50  → "skip"

Hard filters (auto-skip if violated): {json.dumps(hard_filters)}
Top tier companies (unpaid ok): {json.dumps(top_tier)}

Return ONLY valid JSON with these exact fields:
- score: integer 0–100
- verdict: "apply" | "review" | "skip"
- skill_match: integer 0–100
- reasons: list of 2–3 strings
- gaps: list of 0–2 strings
- stipend_ok: boolean

No markdown, no explanation, only JSON.

Candidate profile:
{summary}

Job listing:
Title: {title}
Company: {company}
Location: {location}
Stipend: {stipend}
Duration: {duration}
Description: {description}
Requirements: {requirements if requirements else "Not specified — score based on title"}
"""

    response = llm.invoke(prompt)

    try:
        # Strip markdown fences if LLM wraps response
        content = response.content.strip()
        content = re.sub(r"^```json\s*|^```\s*|```$", "", content, flags=re.M).strip()
        result = json.loads(content)
    except Exception:
        result = {
            "score": 0, "verdict": "skip", "skill_match": 0,
            "reasons": ["Could not parse LLM response"], "gaps": [], "stipend_ok": False
        }

    result["job"] = job
    return result


if __name__ == "__main__":
    test_job = {
        "title": "Backend Developer Intern",
        "company": "Razorpay",
        "location": "Bangalore (Remote OK)",
        "stipend": "25000/month",
        "duration": "3 months",
        "description": "Work on payment APIs, build microservices, improve system reliability.",
        "requirements": "Node.js, REST APIs, MongoDB, DSA fundamentals. 1st or 2nd year preferred."
    }

    result = score_opportunity(test_job)
    print(f"\nJob: {result['job']['title']} at {result['job']['company']}")
    print(f"Score: {result['score']}/100")
    print(f"Verdict: {result['verdict'].upper()}")
    print(f"Skill match: {result['skill_match']}%")
    print(f"Stipend OK: {result['stipend_ok']}")
    print(f"Reasons: {result['reasons']}")
    print(f"Gaps: {result['gaps']}")