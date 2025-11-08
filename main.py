import asyncio
import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse
import logging

from config import config
from agents.agent_a import AgentA
from utils.logger import setup_logging, log_queue, log_agent_action

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
        # Check if agent is already running
        if agent_a.running:
            return {
                "status": "already_running", 
                "message": "Agent A is already running. Use /agent/stop to stop it first.",
                "agent_status": agent_a.status
            }
        
        # Start continuous monitoring
        asyncio.create_task(agent_a.run_continuous())
        log_agent_action("API", "Agent A start requested via API")
        return {
            "status": "started", 
            "message": "Agent A started successfully",
            "agent_status": agent_a.status
        }
    except Exception as e:
        log_agent_action("API", f"Error starting agent: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.post("/agent/run-session")
async def run_single_session():
    """Run a single search session"""
    try:
        if agent_a.status == "running":
            return {
                "status": "busy",
                "message": "Agent A is currently running a session. Please wait.",
                "agent_status": agent_a.status
            }
        
        # Run single session
        asyncio.create_task(agent_a.run_session())
        log_agent_action("API", "Single session start requested via API")
        return {
            "status": "session_started",
            "message": "Single search session started",
            "agent_status": agent_a.status
        }
    except Exception as e:
        log_agent_action("API", f"Error starting session: {str(e)}")
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
    from datetime import datetime
    
    session_info = None
    if agent_a.current_session_start:
        elapsed = (datetime.now() - agent_a.current_session_start).total_seconds()
        session_info = {
            "started_at": agent_a.current_session_start.isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "steps": len(agent_a.session_steps)
        }
    
    # Count suitable projects
    suitable_count = len([p for p in agent_a.found_projects if p.get('evaluation', {}).get('suitable', False)])
    
    return {
        "agent_a_status": agent_a.status,
        "is_running": agent_a.running,
        "mode": config.MODE,
        "last_check": agent_a.last_run_time,
        "projects_found": len(agent_a.found_projects),
        "suitable_projects": suitable_count,
        "current_session": session_info,
        "search_keyword": config.SEARCH_KEYWORD
    }

@app.post("/webhook/n8n")
async def n8n_webhook(request: Request):
    """Webhook endpoint for n8n to trigger agent actions"""
    try:
        data = await request.json()
        action = data.get("action", "")
        
        if action == "start":
            asyncio.create_task(agent_a.run_continuous())
            return {"status": "started", "message": "Agent A started via n8n webhook"}
        elif action == "stop":
            await agent_a.stop()
            return {"status": "stopped", "message": "Agent A stopped via n8n webhook"}
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/health")
async def health_check():
    """Health check endpoint for Railway"""
    return {"status": "healthy", "service": "agent-a"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,  # Disable reload in production
        log_level=config.LOG_LEVEL.lower()
    )
