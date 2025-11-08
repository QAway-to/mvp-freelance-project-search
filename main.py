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
                # Get log message from queue with timeout to prevent blocking
                try:
                    log_message = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                    yield f"data: {log_message}\n\n"
                    # Small delay to ensure streaming effect
                    await asyncio.sleep(0.01)
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"
                    await asyncio.sleep(0.5)
            except Exception as e:
                yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
                await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
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
        # Check if continuous mode is running
        if agent_a.running:
            return {
                "status": "busy",
                "message": "Agent A is running in continuous mode. Stop it first.",
                "agent_status": agent_a.status
            }
        
        # Check if a session is already running
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

@app.get("/projects")
async def get_projects():
    """Get list of all found projects"""
    suitable_count = len([p for p in agent_a.found_projects if p.get('evaluation', {}).get('suitable', False)])
    
    return {
        "total": len(agent_a.found_projects),
        "suitable": suitable_count,
        "projects": agent_a.found_projects
    }

@app.get("/projects/suitable")
async def get_suitable_projects():
    """Get only suitable projects"""
    suitable = [p for p in agent_a.found_projects if p.get('evaluation', {}).get('suitable', False)]
    return {
        "total": len(suitable),
        "projects": suitable
    }

@app.post("/webhook/n8n/projects")
async def n8n_projects_webhook(request: Request):
    """Webhook endpoint for n8n to get projects data"""
    try:
        data = await request.json()
        action = data.get("action", "all")  # all, suitable, or specific project_id
        
        if action == "suitable":
            # Return only suitable projects
            suitable = [p for p in agent_a.found_projects if p.get('evaluation', {}).get('suitable', False)]
            return {
                "status": "success",
                "total": len(suitable),
                "projects": suitable
            }
        elif action == "all":
            # Return all projects
            suitable_count = len([p for p in agent_a.found_projects if p.get('evaluation', {}).get('suitable', False)])
            return {
                "status": "success",
                "total": len(agent_a.found_projects),
                "suitable": suitable_count,
                "projects": agent_a.found_projects
            }
        elif action == "get" and data.get("project_id"):
            # Return specific project
            project_id = data.get("project_id")
            project = next((p for p in agent_a.found_projects if p.get("id") == project_id), None)
            if project:
                return {
                    "status": "success",
                    "project": project
                }
            else:
                return {
                    "status": "not_found",
                    "message": f"Project with ID {project_id} not found"
                }
        else:
            return {
                "status": "error",
                "message": "Invalid action. Use 'all', 'suitable', or 'get' with project_id"
            }
    except Exception as e:
        log_agent_action("API", f"Error in n8n projects webhook: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

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
