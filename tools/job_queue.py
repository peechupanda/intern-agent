import json, os, uuid
from datetime import datetime

QUEUE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "job_queue.json")

def _load() -> list:
    if not os.path.exists(QUEUE_PATH):
        return []
    with open(QUEUE_PATH, "r") as f:
        return json.load(f)

def _save(queue: list):
    with open(QUEUE_PATH, "w") as f:
        json.dump(queue, f, indent=2)

def add_job(job: dict, score_result: dict) -> str:
    queue = _load()
    job_id = str(uuid.uuid4())[:8]
    
    # check for duplicate
    for item in queue:
        if item["job"].get("title") == job.get("title") and \
           item["job"].get("company") == job.get("company"):
            return item["id"]
    
    entry = {
        "id": job_id,
        "added_at": datetime.now().isoformat(),
        "status": "pending",
        "job": job,
        "score": score_result.get("score"),
        "verdict": score_result.get("verdict"),
        "skill_match": score_result.get("skill_match"),
        "reasons": score_result.get("reasons"),
        "gaps": score_result.get("gaps"),
        "stipend_ok": score_result.get("stipend_ok")
    }
    queue.append(entry)
    _save(queue)
    return job_id

def get_pending() -> list:
    return [j for j in _load() if j["status"] == "pending"]

def get_approved() -> list:
    return [j for j in _load() if j["status"] == "approved"]

def update_status(job_id: str, status: str):
    queue = _load()
    for item in queue:
        if item["id"] == job_id:
            item["status"] = status
            item["updated_at"] = datetime.now().isoformat()
    _save(queue)

def get_all() -> list:
    return _load()

def print_queue():
    queue = _load()
    if not queue:
        print("Queue is empty.")
        return
    print(f"\n{'='*60}")
    print(f"{'ID':<10} {'Status':<12} {'Score':<8} {'Verdict':<10} {'Title':<30} Company")
    print(f"{'='*60}")
    for j in sorted(queue, key=lambda x: x["score"], reverse=True):
        print(f"{j['id']:<10} {j['status']:<12} {j['score']:<8} {j['verdict']:<10} {j['job']['title'][:28]:<30} {j['job']['company']}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    from agents.fit_scorer import score_opportunity

    test_jobs = [
        {
            "title": "Backend Developer Intern",
            "company": "Razorpay",
            "location": "Bangalore",
            "stipend": "25000/month",
            "duration": "3 months",
            "description": "Build payment APIs with Node.js and MongoDB.",
            "requirements": "Node.js, MongoDB, DSA. 2nd year preferred."
        },
        {
            "title": "ML Engineering Intern",
            "company": "Swiggy",
            "location": "Remote",
            "stipend": "20000/month",
            "duration": "2 months",
            "description": "Work on recommendation systems and data pipelines.",
            "requirements": "Python, basic ML knowledge, SQL."
        },
        {
            "title": "HR Intern",
            "company": "Some Startup",
            "location": "Delhi",
            "stipend": "5000/month",
            "duration": "2 months",
            "description": "Assist with recruitment and onboarding.",
            "requirements": "Good communication skills."
        }
    ]

    for job in test_jobs:
        result = score_opportunity(job)
        job_id = add_job(job, result)
        print(f"Added: {job['title']} at {job['company']} — Score: {result['score']} — {result['verdict'].upper()}")

    print_queue()