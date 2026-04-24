import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

import agent_a
from config import settings
from models import SearchRequest, ParseRequest, SearchResponse, ParseResponse, Meta

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Kwork parser service starting")
    yield
    logger.info("Kwork parser service stopped")


app = FastAPI(title="Kwork Parser", version="0.1.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url)
    return JSONResponse(
        status_code=500,
        content={"success": False, "data": None, "error": "INTERNAL_ERROR"},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/search", response_model=SearchResponse)
async def search(body: SearchRequest):
    start = time.monotonic()
    try:
        projects = await agent_a.search(
            keywords=body.keywords,
            category=body.category,
            time_left_filter=body.timeLeft,
            hired_min=body.hiredMin,
            proposals_max=body.proposalsMax,
            limit=body.limit,
        )
    except Exception as exc:
        logger.exception("Search failed for keywords=%r", body.keywords)
        raise HTTPException(status_code=500, detail="SEARCH_FAILED") from exc

    took_ms = round((time.monotonic() - start) * 1000)
    return SearchResponse(
        success=True,
        data=projects,
        meta=Meta(total=len(projects), took_ms=took_ms),
        error=None,
    )


@app.post("/api/parse", response_model=ParseResponse)
async def parse(body: ParseRequest):
    try:
        project = await agent_a.parse_project(body.url)
    except Exception as exc:
        logger.exception("Parse failed for url=%r", body.url)
        raise HTTPException(status_code=500, detail="PARSE_FAILED") from exc

    if project is None:
        return ParseResponse(success=False, data=None, error="PARSE_FAILED")

    return ParseResponse(success=True, data=project, error=None)
