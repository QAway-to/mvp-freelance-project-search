import asyncio
import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
import logging
import json

from config import config
from agents.agent_a import AgentA
from utils.logger import setup_logging, log_queue, log_agent_action

setup_logging()

app = FastAPI(title="Freelance Agent A")

agent_a = AgentA()

log_agent_action("App", f"🚀 Application started in {config.MODE.upper()} mode")
log_agent_action("App", f"📋 Search keywords: {', '.join(config.SEARCH_KEYWORDS_LIST)}")


@app.get("/")
async def root():
    return {"status": "ok", "mode": config.MODE}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "agent-a"}


@app.get("/logs/stream")
async def stream_logs():
    async def event_generator():
        while True:
            try:
                batch = []
                while len(batch) < 200:
                    try:
                        log_message = log_queue.get_nowait()
                        batch.append(log_message)
                    except asyncio.QueueEmpty:
                        break

                for log_message in batch:
                    yield f"data: {log_message}\n\n"
                    if len(batch) > 1:
                        await asyncio.sleep(0.0001)

                if batch:
                    continue

                try:
                    log_message = await asyncio.wait_for(log_queue.get(), timeout=0.01)
                    yield f"data: {log_message}\n\n"
                except asyncio.TimeoutError:
                    yield f": keepalive\n\n"
                    await asyncio.sleep(0.05)

            except Exception as e:
                yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
                await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/agent/start")
async def start_agent():
    if agent_a.running:
        return {"status": "already_running", "agent_status": agent_a.status}
    asyncio.create_task(agent_a.run_continuous())
    log_agent_action("API", "Agent A start requested")
    return {"status": "started", "agent_status": agent_a.status}


@app.post("/agent/run-session")
async def run_single_session(request: Request):
    data = await request.json()
    budget_filters = data.get("budget_filters", [])
    config.BUDGET_FILTERS = [int(f) for f in budget_filters if str(f).isdigit()]

    if agent_a.running:
        return {"status": "busy", "message": "Agent running in continuous mode.", "agent_status": agent_a.status}
    if agent_a.status == "running":
        return {"status": "busy", "message": "Session already running.", "agent_status": agent_a.status}

    asyncio.create_task(agent_a.run_session())
    log_agent_action("API", f"Single session requested (Filters: {config.BUDGET_FILTERS})")
    return {"status": "session_started", "agent_status": agent_a.status}


@app.post("/agent/stop")
async def stop_agent():
    await agent_a.stop()
    return {"status": "stopped"}


@app.get("/status")
async def get_status():
    from datetime import datetime
    session_info = None
    if agent_a.current_session_start:
        elapsed = (datetime.now() - agent_a.current_session_start).total_seconds()
        session_info = {"started_at": agent_a.current_session_start.isoformat(), "elapsed_seconds": round(elapsed, 2)}

    suitable_count = len([p for p in agent_a.found_projects if p.get("evaluation", {}).get("suitable", False)])
    return {
        "agent_a_status": agent_a.status,
        "is_running": agent_a.running,
        "mode": config.MODE,
        "last_check": agent_a.last_run_time,
        "projects_found": len(agent_a.found_projects),
        "suitable_projects": suitable_count,
        "current_session": session_info,
        "search_keyword": config.SEARCH_KEYWORD,
    }


@app.get("/projects")
async def get_projects():
    suitable_count = len([p for p in agent_a.found_projects if p.get("evaluation", {}).get("suitable", False)])
    return {"total": len(agent_a.found_projects), "suitable": suitable_count, "projects": agent_a.found_projects}


@app.post("/agent/generate-cp")
async def generate_cp(request: Request):
    data = await request.json()
    description = data.get("description")
    budget = data.get("budget", "Не указан")
    if not description:
        return {"status": "error", "message": "Description is required"}
    from utils.cp_generator import cp_generator
    proposal = await cp_generator.generate_proposal(description, budget)
    return {"status": "success", "proposal": proposal}


# ── Next.js proxy endpoints ────────────────────────────────────────────────────

@app.post("/api/search")
async def api_search(request: Request):
    """Keyword search for Next.js UI proxy."""
    data = await request.json()
    keywords = (data.get("keywords") or "").strip()
    if not keywords:
        raise HTTPException(status_code=400, detail="keywords required")

    max_urgency = int(data["timeLeft"]) if data.get("timeLeft") else config.MAX_URGENCY_HOURS

    original_keywords = list(config.SEARCH_KEYWORDS_LIST)
    original_keyword = config.SEARCH_KEYWORD
    original_urgency = config.MAX_URGENCY_HOURS

    config.SEARCH_KEYWORDS_LIST = [kw.strip() for kw in keywords.split(",") if kw.strip()] or [keywords]
    config.SEARCH_KEYWORD = config.SEARCH_KEYWORDS_LIST[0]
    config.MAX_URGENCY_HOURS = max_urgency

    try:
        projects = await asyncio.to_thread(agent_a.search_projects)
    finally:
        config.SEARCH_KEYWORDS_LIST = original_keywords
        config.SEARCH_KEYWORD = original_keyword
        config.MAX_URGENCY_HOURS = original_urgency

    hired_min = int(data["hiredMin"]) if data.get("hiredMin") else None
    proposals_max = int(data["proposalsMax"]) if data.get("proposalsMax") else None

    if hired_min is not None:
        projects = [p for p in projects if p.get("hired", 0) >= hired_min]
    if proposals_max is not None:
        projects = [p for p in projects if p.get("proposals", 0) <= proposals_max]

    return {"success": True, "data": projects, "meta": {"total": len(projects), "took_ms": 0}, "error": None}


@app.post("/api/parse")
async def api_parse(request: Request):
    """Parse single Kwork URL for Next.js UI proxy."""
    data = await request.json()
    url = (data.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url required")

    project = await asyncio.to_thread(agent_a.parse_single_url, url)

    if project is None:
        return JSONResponse({"success": False, "data": None, "error": "PARSE_FAILED"}, status_code=422)

    return {"success": True, "data": project, "error": None}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    log_agent_action("App", f"📡 Starting server on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level=config.LOG_LEVEL.lower())
