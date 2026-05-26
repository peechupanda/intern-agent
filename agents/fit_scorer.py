from langchain_groq import ChatGroq
from dotenv import load_dotenv
from tools.profile_loader import load_profile, summarise_profile
import os, json

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

llm = ChatGroq(model="llama-3.3-70b-versatile")

def score_opportunity(job: dict) -> dict:
    profile = load_profile()
    summary = summarise_profile(profile)
    hard_filters = profile["internship_preferences"]["hard_filters"]
    top_tier = profile["internship_preferences"]["top_tier_companies"]

    prompt = f"""
You are an internship fit scorer. Given a candidate profile and a job listing, return a JSON object with these exact fields:
- score: integer 0-100
- verdict: one of "apply", "skip", "review"
- skill_match: integer 0-100
- reasons: list of 2-3 strings explaining the score
- gaps: list of 1-2 strings describing missing requirements
- stipend_ok: boolean (true if stipend is mentioned or company is top-tier)

Rules:
- verdict is "apply" if score >= 70
- verdict is "review" if score 50-69
- verdict is "skip" if score < 50
- Hard filters: {json.dumps(hard_filters)}
- Top tier companies (unpaid is ok): {json.dumps(top_tier)}
- If role is non-tech (HR, marketing, sales), score must be 0 and verdict must be "skip"
- Return ONLY valid JSON, no explanation, no markdown

Candidate profile:
{summary}

Job listing:
Title: {job.get('title', 'N/A')}
Company: {job.get('company', 'N/A')}
Location: {job.get('location', 'N/A')}
Stipend: {job.get('stipend', 'Not mentioned')}
Duration: {job.get('duration', 'N/A')}
Description: {job.get('description', 'N/A')}
Requirements: {job.get('requirements', 'N/A')}
"""

    response = llm.invoke(prompt)
    
    try:
        result = json.loads(response.content)
    except:
        result = {"score": 0, "verdict": "skip", "skill_match": 0,
                  "reasons": ["Could not parse response"], "gaps": [], "stipend_ok": False}
    
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