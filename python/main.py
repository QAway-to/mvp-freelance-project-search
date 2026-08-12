import asyncio
import hashlib
import queue
import os
import threading
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
import logging
import json
from typing import Optional

from config import config
from agents.agent_a import AgentA
from agents.agent_workzilla import agent_workzilla
from agents.job_store import Job, job_store
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


@app.post(telegram_bot.WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """Точка входа для Telegram.

    Именно этот запрос будит спящий контейнер на free tier — поэтому бот
    отвечает с задержкой на холодный старт, а не пропадает совсем. Отвечаем
    200 сразу: Telegram ждёт ответа считанные секунды и при таймауте присылает
    апдейт заново, а это дубли сообщений у человека.
    """
    accepted = await telegram_bot.handle_webhook(
        await request.json(),
        request.headers.get("X-Telegram-Bot-Api-Secret-Token"),
    )
    if not accepted:
        raise HTTPException(status_code=403, detail="bad secret")
    return {"ok": True}


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

    # Attachments are downloaded via Selenium/Chrome — slow and OOM-prone on the
    # 512MB tier. They must NEVER hold the whole КП hostage: time-box them and,
    # on timeout/error, generate from the description alone (a КП without the
    # attachment text is still a successful КП). This is what makes generation
    # reliably succeed instead of hanging until the client times out.
    attachments_text = ""
    if files:
        from utils.attachments import extract_attachments_text
        try:
            attachments_text = await asyncio.wait_for(
                asyncio.to_thread(extract_attachments_text, files),
                timeout=_ATTACH_EXTRACT_TIMEOUT,
            )
        except asyncio.TimeoutError:
            log_agent_action("API", f"[CP] attachments extraction exceeded {_ATTACH_EXTRACT_TIMEOUT}s — generating КП without them", level="WARNING")
        except Exception as exc:
            log_agent_action("API", f"[CP] attachments extraction failed ({exc}) — generating КП without them", level="WARNING")

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


@app.get("/debug/offer-trace")
async def debug_offer_trace():
    """Read the crash-survivable offer-submit trace (survives OOM restarts)."""
    from utils.trace import read_trace
    return {"trace": read_trace(120)}


@app.get("/debug/offer-page")
async def debug_offer_page(project: str):
    """Read-only (no Chrome): fetch the new_offer page over authenticated HTTP and
    surface the submit endpoint / CSRF / field names so the offer POST can be
    replicated without Selenium."""
    import re as _re
    from agents.kwork_http import _request, _extract_state_data

    url = f"https://kwork.ru/new_offer?project={project}"
    r = await asyncio.to_thread(lambda: _request("GET", url, use_cookies=True))
    if r is None:
        return {"error": "no response (rate-limited / challenge / cookies)"}
    html = r.text or ""
    sd = _extract_state_data(html) or {}
    offer_eps = sorted(set(_re.findall(r"""["'](/[A-Za-z0-9_\-/]*(?:offer|want)[A-Za-z0-9_\-/]*)["']""", html, _re.I)))
    return {
        "status": r.status_code,
        "len": len(html),
        "looks_like_form": ("trumbowyg" in html) or ("offer-custom-price" in html),
        "title": (_re.search(r"<title[^>]*>(.*?)</title>", html, _re.S) or [None, None])[1],
        "stateData_top_keys": sorted(sd.keys())[:50] if sd else None,
        "csrf_token_cookie_present": "csrf_user_token" in (html and "" or "") or None,
        "csrf_in_html": _re.findall(r"""csrf[^"']{0,25}["']([A-Za-z0-9_\-]{16,})""", html)[:3],
        "form_actions": _re.findall(r'action="([^"]+)"', html)[:10],
        "offer_endpoints_in_html": offer_eps[:25],
        "has_trumbowyg": "trumbowyg" in html,
        "has_price_input": "offer-custom-price" in html,
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

def _parse_search_request(data: dict) -> tuple[SearchParams, dict]:
    """Parse the UI search body into SearchParams + business filters (shared by
    the legacy synchronous /api/search and the job-based flow)."""
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
    # `not in (None, "")` — an explicit 0 is a real filter value (e.g.
    # proposalsMax=0 = "no proposals yet"), while the UI sends ""/null for unset.
    def _num(key: str):
        return int(data[key]) if data.get(key) not in (None, "") else None

    filters = {
        "hired_min": _num("hiredMin"),
        "proposals_max": _num("proposalsMax"),
        "budget_min": _num("budgetMin"),
        "budget_max": _num("budgetMax"),
    }
    return params, filters


def _passes_business_filters(p: dict, f: dict) -> bool:
    """hired/proposals/budget filters. None value on the project = unknown;
    include those (don't penalise missing data) — same semantics the batch
    /api/search always had."""
    if f["hired_min"] is not None and p.get("hired") is not None and p.get("hired", 0) < f["hired_min"]:
        return False
    if f["proposals_max"] is not None and p.get("proposals") is not None and p.get("proposals", 0) > f["proposals_max"]:
        return False
    if f["budget_min"] is not None and p.get("budget_value") is not None and p.get("budget_value", 0) < f["budget_min"]:
        return False
    if f["budget_max"] is not None and p.get("budget_value") is not None and p.get("budget_value", 0) > f["budget_max"]:
        return False
    return True


# ── Job-based search (poll delivery) ───────────────────────────────────────────
# A Kwork scrape is rate-limited to ≥5s/request and can run for many minutes.
# One long HTTP response dies in the Telegram-miniapp WebView (suspend), at
# Render's edge (~100s no-byte cutoff) and on free-tier cold starts. So: POST
# creates a job and returns immediately; the scrape runs in a daemon thread
# appending into job_store; the UI polls GET .../{job_id}?since=N.

_WZ_JOB_DEADLINE_SECS = 300  # WZ scrape is short (≤15 cards); hard stop as a safety net
# Cap on Selenium attachment download+parse during КП generation. Past this we
# drop the attachments and generate from the description — a successful КП beats
# a hung one. Env-tunable in case a slow but working setup wants more headroom.
# A bit above selenium_download's own 30s wall-clock budget (+Chrome launch), so
# the worker thread finishes and reaps Chrome on its own instead of being
# abandoned by wait_for. The outer cap is only a safety net for a stuck launch.
_ATTACH_EXTRACT_TIMEOUT = float(os.getenv("ATTACH_EXTRACT_TIMEOUT", "50"))


def _run_kwork_job(job: "Job", params: SearchParams, filters: dict,
                   loop: asyncio.AbstractEventLoop) -> None:
    """Worker thread: run the Kwork search, streaming filtered projects into the
    job store as listing pages arrive."""
    job_store.set_status(job.id, "running")

    def on_project(p: dict) -> None:
        p.setdefault("evaluation", {"score": 1.0, "reasons": [], "suitable": True})
        if _passes_business_filters(p, filters):
            job_store.append(job.id, p)

    def on_progress(meta: dict) -> None:
        job_store.set_progress(job.id, meta)

    try:
        projects = agent_a.search_projects(
            params, on_project=on_project, on_progress=on_progress,
            should_stop=job.cancel.is_set,
        )
        # The HTTP path already streamed everything via on_project; this sweep
        # covers the Selenium fallback (non-incremental) — append() dedupes.
        for p in projects:
            if _passes_business_filters(p, filters):
                job_store.append(job.id, p)
        job_store.set_status(job.id, "done")
        # Telegram notifications are intentionally NOT sent for manual UI/miniapp
        # searches — a wide search fired 296 cards at the bot at once (spam). The
        # autonomous background agent (run_session) still notifies; that's its job.
    except Exception as exc:
        log_agent_action("API", f"[SEARCH-JOB] job {job.id} failed: {exc}", level="ERROR")
        job_store.set_error(job.id, str(exc))


def _run_wz_job(job: "Job", loop: asyncio.AbstractEventLoop) -> None:
    """Worker thread: drain the Workzilla scrape generator into the job store.
    `_update` enrich events are appended as-is — the frontend already merges
    them by id, so the poll stream keeps the exact SSE semantics."""
    job_store.set_status(job.id, "running")
    deadline = _time.time() + _WZ_JOB_DEADLINE_SECS
    try:
        for item in agent_workzilla.scrape_orders_iter():
            if job.cancel.is_set() or _time.time() > deadline:
                # Generator checks _cancel per card and releases its lock.
                agent_workzilla._cancel.set()
                if not job.cancel.is_set():
                    job_store.mark_truncated(job.id)  # deadline stop = partial results
            job_store.append(job.id, item)
            if "_update" not in item:
                asyncio.run_coroutine_threadsafe(_categorize_and_save([item]), loop)
        job_store.set_status(job.id, "done")
    except Exception as exc:
        log_agent_action("API", f"[WZ-JOB] job {job.id} failed: {exc}", level="ERROR")
        job_store.set_error(job.id, str(exc))


@app.post("/api/search/jobs")
async def api_search_job_create(request: Request):
    data = await request.json()
    params, filters = _parse_search_request(data)
    fingerprint = hashlib.sha1(json.dumps(
        {"kind": "kwork", "keywords": list(params.keywords_list),
         "urgency": params.max_urgency_hours, "categories": sorted(params.categories),
         "filters": filters},
        sort_keys=True, ensure_ascii=False,
    ).encode()).hexdigest()

    loop = asyncio.get_running_loop()
    job, reused = job_store.create("kwork", fingerprint)
    if not reused:
        threading.Thread(target=_run_kwork_job, args=(job, params, filters, loop), daemon=True).start()
    log_agent_action("API", f"[SEARCH-JOB] {'reattached to' if reused else 'created'} job {job.id} "
                            f"(keywords={list(params.keywords_list)}, categories={len(params.categories)})")
    return JSONResponse({"success": True, "job_id": job.id, "reused": reused}, status_code=202)


@app.get("/api/search/jobs/{job_id}")
async def api_search_job_status(job_id: str, since: int = 0):
    snap = job_store.snapshot(job_id, since)
    if snap is None:
        # In-memory store: after an OOM/deploy restart every old job_id lands here.
        return JSONResponse({"success": False, "error": "JOB_NOT_FOUND"}, status_code=404)
    return {"success": True, "job_id": job_id, **snap}


@app.post("/api/search/jobs/{job_id}/cancel")
async def api_search_job_cancel(job_id: str):
    cancelled = job_store.cancel(job_id)
    if not cancelled and job_store.snapshot(job_id) is None:
        return JSONResponse({"success": False, "error": "JOB_NOT_FOUND"}, status_code=404)
    # Idempotent: cancelling an already-finished job is a no-op success.
    return {"success": True, "cancelled": cancelled}


@app.post("/api/workzilla/jobs")
async def workzilla_job_create():
    loop = asyncio.get_running_loop()
    # Constant fingerprint: WZ search has no params, and agent_workzilla._lock
    # serializes scrapes anyway — concurrent requests share one job.
    job, reused = job_store.create("workzilla", "workzilla")
    if not reused:
        threading.Thread(target=_run_wz_job, args=(job, loop), daemon=True).start()
    log_agent_action("API", f"[WZ-JOB] {'reattached to' if reused else 'created'} job {job.id}")
    return JSONResponse({"success": True, "job_id": job.id, "reused": reused}, status_code=202)


@app.get("/api/workzilla/jobs/{job_id}")
async def workzilla_job_status(job_id: str, since: int = 0):
    snap = job_store.snapshot(job_id, since)
    if snap is None:
        return JSONResponse({"success": False, "error": "JOB_NOT_FOUND"}, status_code=404)
    return {"success": True, "job_id": job_id, **snap}


@app.post("/api/workzilla/jobs/{job_id}/cancel")
async def workzilla_job_cancel(job_id: str):
    cancelled = job_store.cancel(job_id)
    if cancelled:
        # Only when an ACTIVE job was transitioned: agent_workzilla._cancel is a
        # process-wide Event — setting it off a stale/terminal job_id would abort
        # whatever scrape is currently running for someone else's job.
        agent_workzilla._cancel.set()
        return {"success": True, "cancelled": True}
    if job_store.snapshot(job_id) is None:
        return JSONResponse({"success": False, "error": "JOB_NOT_FOUND"}, status_code=404)
    return {"success": True, "cancelled": False}


# ── Kwork offer submission as a job (poll delivery) ────────────────────────────
# Submitting an offer drives Selenium (Chrome start + login + slow vue-select on
# the memory-pressured 512MB tier) and takes ~3.5 min — right at the old 240s
# client timeout, so a slow-but-successful submit surfaced as a false "Ошибка
# отправки" and invited a duplicate re-submit. Same cure as search: POST returns
# a job_id immediately; the submit runs in a worker thread; the UI polls the true
# outcome. Single-flight on the offer URL structurally prevents a double submit.

def _run_respond_job(job: "Job", url: str, cp_text: str,
                     duration: Optional[str], title: Optional[str], description: Optional[str],
                     loop: asyncio.AbstractEventLoop) -> None:
    job_store.set_status(job.id, "running")
    try:
        ok = agent_a.submit_response(url, cp_text, duration, title, description)
        job_store.append(job.id, {
            "success": bool(ok),
            "message": "Отклик отправлен" if ok else "Не удалось отправить отклик",
        })
        job_store.set_status(job.id, "done")
    except Exception as exc:
        log_agent_action("API", f"[RESPOND-JOB] job {job.id} failed: {exc}", level="ERROR")
        job_store.set_error(job.id, str(exc))


@app.post("/api/respond/jobs")
async def api_respond_job_create(request: Request):
    data = await request.json()
    url = (data.get("url") or "").strip()
    cp_text = (data.get("cp_text") or "").strip()
    duration = (data.get("duration") or "").strip() or None
    title = (data.get("title") or "").strip() or None
    description = (data.get("description") or "").strip() or None
    if not url or not cp_text:
        raise HTTPException(status_code=400, detail="url and cp_text required")

    loop = asyncio.get_running_loop()
    # Fingerprint on the offer URL: a second submit for the same offer while one
    # is in flight reattaches to it instead of starting a duplicate Selenium run.
    job, reused = job_store.create("respond", f"respond:{url}")
    if not reused:
        threading.Thread(
            target=_run_respond_job,
            args=(job, url, cp_text, duration, title, description, loop),
            daemon=True,
        ).start()
    log_agent_action("API", f"[RESPOND-JOB] {'reattached to' if reused else 'created'} job {job.id} for {url}")
    return JSONResponse({"success": True, "job_id": job.id, "reused": reused}, status_code=202)


@app.get("/api/respond/jobs/{job_id}")
async def api_respond_job_status(job_id: str, since: int = 0):
    snap = job_store.snapshot(job_id, since)
    if snap is None:
        return JSONResponse({"success": False, "error": "JOB_NOT_FOUND"}, status_code=404)
    # The worker appends exactly one outcome dict on completion.
    outcome = snap["results"][-1] if snap["results"] else None
    return {
        "success": True,
        "job_id": job_id,
        "status": snap["status"],
        "outcome": outcome,
        "next_since": snap["next_since"],
        "error": snap["error"],
    }


@app.post("/api/search")
async def api_search(request: Request):
    """Keyword search for Next.js UI proxy (legacy synchronous path — kept for
    one release while the UI migrates to /api/search/jobs)."""
    import time
    t0 = time.time()

    data = await request.json()
    params, filters = _parse_search_request(data)
    keywords = ",".join(params.keywords_list)

    log_agent_action("API", f"[SEARCH] request received: keywords={keywords!r} mode={config.MODE} driver={agent_a.driver is not None} logged_in={agent_a.logged_in}")

    try:
        log_agent_action("API", f"[SEARCH] dispatching to thread, keywords={list(params.keywords_list)}")
        projects = await asyncio.to_thread(agent_a.search_projects, params)
        log_agent_action("API", f"[SEARCH] thread returned {len(projects)} projects in {time.time()-t0:.1f}s")
        asyncio.create_task(agent_a.notify_suitable_projects(projects))
    except Exception as exc:
        log_agent_action("API", f"[SEARCH] thread raised exception: {exc}", level="ERROR")
        raise

    projects = [p for p in projects if _passes_business_filters(p, filters)]

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
    title = (data.get("title") or "").strip() or None
    description = (data.get("description") or "").strip() or None
    if not url or not cp_text:
        raise HTTPException(status_code=400, detail="url and cp_text required")

    success = await asyncio.to_thread(agent_a.submit_response, url, cp_text, duration, title, description)
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

    from agents.kwork_http import fetch_project
    project = await asyncio.to_thread(fetch_project, url)

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
