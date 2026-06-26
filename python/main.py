import asyncio
import queue
import os
import threading
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
import logging
import json

from config import config
from agents.agent_a import AgentA
from agents.agent_workzilla import agent_workzilla
from agents.search_params import SearchParams
from telegram_bot import telegram_bot
from browser import quit_driver
from utils.logger import setup_logging, log_queue, log_buffer, log_agent_action
from utils.categorizer import categorize
from utils.sheets_writer import write_order

setup_logging()

agent_a = AgentA()

import agents.agent_a as _agent_a_module
_agent_a_module.agent_a_instance = agent_a


import time as _time

# Reclaim Workzilla's Chrome RSS during quiet periods (matters most on 512MB Render).
_WZ_IDLE_REAP_SECS = 600      # quit Chrome after 10 min with no scrape
_WZ_REAP_INTERVAL_SECS = 120  # how often the reaper checks


async def _workzilla_idle_reaper():
    while True:
        await asyncio.sleep(_WZ_REAP_INTERVAL_SECS)
        try:
            ts = agent_workzilla._last_scrape_ts
            if (agent_workzilla.driver is not None and ts > 0
                    and _time.time() - ts > _WZ_IDLE_REAP_SECS):
                log_agent_action("Workzilla", "💤 [SELENIUM] Idle — reaping Chrome to free memory")
                await agent_workzilla.stop()
        except Exception as exc:
            log_agent_action("Workzilla", f"⚠️ [SELENIUM] Idle reaper error: {exc}", level="WARNING")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await telegram_bot.start()
    reaper = asyncio.create_task(_workzilla_idle_reaper())
    yield
    reaper.cancel()
    await telegram_bot.stop()
    quit_driver()


app = FastAPI(title="Freelance Agent A", lifespan=lifespan)

log_agent_action("App", f"🚀 Application started in {config.MODE.upper()} mode")
log_agent_action("App", f"📋 Search keywords: {', '.join(config.SEARCH_KEYWORDS_LIST)}")


@app.get("/")
async def root():
    return {"status": "ok", "mode": config.MODE}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "agent-a"}


_SSE_KEEPALIVE_TIMEOUT = 15.0


@app.get("/logs/stream")
async def stream_logs():
    async def event_generator():
        while True:
            try:
                msg = await asyncio.to_thread(log_queue.get, True, _SSE_KEEPALIVE_TIMEOUT)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            except asyncio.CancelledError:
                break

            yield f"data: {msg}\n\n"

            while True:
                try:
                    msg = log_queue.get_nowait()
                except queue.Empty:
                    break
                yield f"data: {msg}\n\n"

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
    budget_filters = tuple(int(f) for f in data.get("budget_filters", []) if str(f).isdigit())

    if agent_a.running:
        return {"status": "busy", "message": "Agent running in continuous mode.", "agent_status": agent_a.status}
    if agent_a.status == "running":
        return {"status": "busy", "message": "Session already running.", "agent_status": agent_a.status}

    asyncio.create_task(agent_a.run_session(budget_filters))
    log_agent_action("API", f"Single session requested (Filters: {budget_filters})")
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
    # found_projects is a deque (bounded); json.dumps needs a list.
    return {"total": len(agent_a.found_projects), "suitable": suitable_count, "projects": list(agent_a.found_projects)}


async def _categorize_and_save(projects: list):
    """Background: categorize each project and write to Google Sheets."""
    for p in projects:
        try:
            cat = await categorize(p.get("title", ""), p.get("description", ""))
            await write_order(p, cat["category"], cat["tags"], cat["complexity"])
        except Exception as e:
            log_agent_action("Sheets", f"⚠️ Pipeline error: {e}", level="WARNING")


@app.post("/agent/generate-cp")
async def generate_cp(request: Request):
    data = await request.json()
    description = (data.get("description") or "").strip()
    budget = data.get("budget") or "Не указан"
    title = data.get("title") or ""
    files = data.get("files") or []
    if not description:
        return {"status": "error", "message": "Нет описания проекта — КП невозможно сгенерировать"}

    attachments_text = ""
    if files:
        from utils.attachments import extract_attachments_text
        attachments_text = await asyncio.to_thread(extract_attachments_text, files)

    from utils.cp_generator import generate_proposal
    proposal = await generate_proposal(
        {"description": description, "budget": budget, "title": title}, attachments_text
    )
    return {"status": "success", "proposal": proposal}


@app.get("/debug")
async def debug_info():
    """Returns last 300 log lines + current agent state for diagnostics."""
    return {
        "agent_status": agent_a.status,
        "driver_ready": agent_a.driver is not None,
        "logged_in": agent_a.logged_in,
        "mode": config.MODE,
        "kwork_email_set": bool(config.KWORK_EMAIL),
        "kwork_password_set": bool(config.KWORK_PASSWORD),
        "projects_in_memory": len(agent_a.found_projects),
        "logs": list(log_buffer),
    }


@app.get("/debug/offer-form")
async def debug_offer_form(project: str):
    """TEMP DIAGNOSTIC — dump срок dropdown options + key selectors from the new_offer
    page. Read-only, does NOT submit an offer. Disabled by default (drives the live
    Kwork account); re-enable by setting env ENABLE_OFFER_FORM_DEBUG=1 on Render."""
    import os
    if os.getenv("ENABLE_OFFER_FORM_DEBUG") != "1":
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        result = await asyncio.to_thread(agent_a.inspect_offer_form, project)
        return {"success": True, "data": result, "error": None}
    except Exception as exc:
        log_agent_action("API", f"[OFFER-FORM] inspection error: {exc}", level="ERROR")
        return JSONResponse({"success": False, "data": None, "error": str(exc)}, status_code=500)


# ── Next.js proxy endpoints ────────────────────────────────────────────────────

@app.post("/api/search")
async def api_search(request: Request):
    """Keyword search for Next.js UI proxy."""
    import time
    t0 = time.time()

    data = await request.json()
    keywords = (data.get("keywords") or "").strip()
    # None / missing timeLeft = no time filter (show all regardless of deadline)
    max_urgency = int(data["timeLeft"]) if data.get("timeLeft") is not None else 9999

    keywords_list = tuple(kw.strip() for kw in keywords.split(",") if kw.strip()) if keywords else ()
    categories = tuple(str(c).strip() for c in (data.get("categories") or []) if str(c).strip())
    params = SearchParams(
        keywords_list=keywords_list,
        max_urgency_hours=max_urgency,
        categories=categories,
    )

    log_agent_action("API", f"[SEARCH] request received: keywords={keywords!r} mode={config.MODE} driver={agent_a.driver is not None} logged_in={agent_a.logged_in}")

    try:
        log_agent_action("API", f"[SEARCH] dispatching to thread, keywords={list(params.keywords_list)}")
        projects = await asyncio.to_thread(agent_a.search_projects, params)
        log_agent_action("API", f"[SEARCH] thread returned {len(projects)} projects in {time.time()-t0:.1f}s")
        asyncio.create_task(agent_a.notify_suitable_projects(projects))
    except Exception as exc:
        log_agent_action("API", f"[SEARCH] thread raised exception: {exc}", level="ERROR")
        raise

    hired_min = int(data["hiredMin"]) if data.get("hiredMin") else None
    proposals_max = int(data["proposalsMax"]) if data.get("proposalsMax") else None
    budget_min = int(data["budgetMin"]) if data.get("budgetMin") else None
    budget_max = int(data["budgetMax"]) if data.get("budgetMax") else None

    # None value = unknown; include those (don't penalise missing data)
    if hired_min is not None:
        projects = [p for p in projects if p.get("hired") is None or p.get("hired", 0) >= hired_min]
    if proposals_max is not None:
        projects = [p for p in projects if p.get("proposals") is None or p.get("proposals", 0) <= proposals_max]
    if budget_min is not None:
        projects = [p for p in projects if p.get("budget_value") is None or p.get("budget_value", 0) >= budget_min]
    if budget_max is not None:
        projects = [p for p in projects if p.get("budget_value") is None or p.get("budget_value", 0) <= budget_max]

    log_agent_action("API", f"[SEARCH] responding with {len(projects)} projects, total_time={time.time()-t0:.1f}s")
    return {"success": True, "data": projects, "meta": {"total": len(projects), "took_ms": round((time.time()-t0)*1000)}, "error": None}


@app.post("/api/workzilla/search")
async def workzilla_search(request: Request):
    """Stream each scraped project to the client as soon as it's ready.

    Selenium scraping is synchronous, so it runs in a worker thread that pushes
    each project into an asyncio.Queue. The async generator drains the queue and
    flushes one SSE event per project — true incremental delivery.
    """
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    _SENTINEL = object()

    def worker():
        try:
            for project in agent_workzilla.scrape_orders_iter():
                loop.call_soon_threadsafe(q.put_nowait, project)
        except Exception as exc:
            loop.call_soon_threadsafe(q.put_nowait, {"error": str(exc)})
        finally:
            loop.call_soon_threadsafe(q.put_nowait, _SENTINEL)

    async def generator():
        threading.Thread(target=worker, daemon=True).start()
        try:
            while True:
                item = await q.get()
                if item is _SENTINEL:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if "error" not in item and "_update" not in item:
                    asyncio.create_task(_categorize_and_save([item]))
            yield 'data: {"done":true}\n\n'
        except GeneratorExit:
            # Client disconnected — signal the Selenium worker thread to stop so it
            # releases agent_workzilla._lock instead of scraping on (which would block
            # the next request). Only fires on disconnect, never on clean completion,
            # so a normal finish can't leave a stale cancel flag for the next scrape.
            agent_workzilla._cancel.set()
            raise

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/workzilla/respond")
async def workzilla_respond(request: Request):
    data = await request.json()
    url = (data.get("url") or "").strip()
    cp_text = (data.get("cp_text") or "").strip()
    if not url or not cp_text:
        raise HTTPException(status_code=400, detail="url and cp_text required")
    success = await asyncio.to_thread(agent_workzilla.submit_response, url, cp_text)
    if success:
        return {"success": True, "message": "Отклик отправлен"}
    return JSONResponse({"success": False, "message": "Не удалось отправить отклик"}, status_code=422)


@app.post("/api/respond")
async def api_respond(request: Request):
    """Submit a Kwork response for a project URL with given CP text."""
    data = await request.json()
    url = (data.get("url") or "").strip()
    cp_text = (data.get("cp_text") or "").strip()
    duration = (data.get("duration") or "").strip() or None
    if not url or not cp_text:
        raise HTTPException(status_code=400, detail="url and cp_text required")

    success = await asyncio.to_thread(agent_a.submit_response, url, cp_text, duration)
    if success:
        return {"success": True, "message": "Отклик отправлен"}
    return JSONResponse({"success": False, "message": "Не удалось отправить отклик"}, status_code=422)


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
    # Pass the app OBJECT, not the "main:app" import string. The process already runs
    # as __main__; an import string makes uvicorn re-import the module as `main`, which
    # re-executes all top-level code (a second AgentA(), etc.) and leaves a duplicate set
    # of objects resident — nearly doubling baseline RSS and pushing the 512MB tier to OOM.
    # Object form loads everything once (reload/workers are off, so no import string needed).
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=config.LOG_LEVEL.lower())
