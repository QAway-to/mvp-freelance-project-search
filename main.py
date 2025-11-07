import asyncio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse
import logging

from config import config
from agents.agent_a import AgentA
from utils.logger import setup_logging, log_queue

# Setup logging
setup_logging()

app = FastAPI(title="Freelance Agents MVP")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Global agent instance
agent_a = AgentA()

@app.get("/")
async def dashboard(request: Request):
    """Main dashboard"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "mode": config.MODE,
        "keyword": config.SEARCH_KEYWORD
    })

@app.get("/logs/stream")
async def stream_logs():
    """Server-Sent Events for real-time logs"""
    async def event_generator():
        while True:
            try:
                # Get log message from queue
                log_message = await log_queue.get()
                yield f"data: {log_message}\n\n"
            except Exception as e:
                yield f"data: Error: {str(e)}\n\n"
                await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@app.post("/agent/start")
async def start_agent():
    """Start the agent"""
    try:
        asyncio.create_task(agent_a.run_continuous())
        return {"status": "started", "message": "Agent A started successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/agent/stop")
async def stop_agent():
    """Stop the agent"""
    try:
        await agent_a.stop()
        return {"status": "stopped", "message": "Agent A stopped successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/status")
async def get_status():
    """Get current agent status"""
    return {
        "agent_a_status": agent_a.status,
        "mode": config.MODE,
        "last_check": agent_a.last_run_time,
        "projects_found": len(agent_a.found_projects)
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=config.LOG_LEVEL.lower()
    )
