from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import asyncio
import json
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/jobs")
def get_jobs():
    from tools.job_queue import get_all
    return get_all()

@app.post("/jobs/{job_id}/approve")
def approve_job(job_id: str):
    from tools.job_queue import update_status
    update_status(job_id, "approved")
    return {"ok": True}

@app.post("/jobs/{job_id}/skip")
def skip_job(job_id: str):
    from tools.job_queue import update_status
    update_status(job_id, "skipped")
    return {"ok": True}

@app.get("/pipeline/run")
async def run_pipeline_stream(max: int = 10):
    async def event_stream():
        import threading
        results = []
        errors = []
        done = threading.Event()

        def run():
            try:
                from agents.scout_agent import scrape_internshala
                from agents.fit_scorer import score_opportunity
                from tools.job_queue import add_job

                yield_queue = []

                jobs = scrape_internshala(max_results=max)
                yield_queue.append(("scout_done", len(jobs)))

                for job in jobs:
                    result = score_opportunity(job)
                    add_job(job, result)
                    yield_queue.append(("job_scored", {
                        "title": job["title"],
                        "company": job["company"],
                        "score": result["score"],
                        "verdict": result["verdict"],
                        "stipend": job["stipend"],
                        "location": job["location"],
                        "url": job.get("url", ""),
                        "source": job.get("source", ""),
                    }))

                results.extend(yield_queue)
            except Exception as e:
                errors.append(str(e))
            finally:
                done.set()

        import threading
        thread = threading.Thread(target=run)
        thread.start()

        sent = 0
        while not done.is_set() or sent < len(results):
            await asyncio.sleep(0.3)
            while sent < len(results):
                event, data = results[sent]
                yield f"data: {json.dumps({'event': event, 'data': data})}\n\n"
                sent += 1

        if errors:
            yield f"data: {json.dumps({'event': 'error', 'data': errors[0]})}\n\n"

        yield f"data: {json.dumps({'event': 'done', 'data': 'Pipeline complete'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/stats")
def get_stats():
    from tools.job_queue import get_all
    jobs = get_all()
    return {
        "total": len(jobs),
        "apply": len([j for j in jobs if j["verdict"] == "apply"]),
        "review": len([j for j in jobs if j["verdict"] == "review"]),
        "skip": len([j for j in jobs if j["verdict"] == "skip"]),
        "approved": len([j for j in jobs if j["status"] == "approved"]),
        "pending": len([j for j in jobs if j["status"] == "pending"]),
    }