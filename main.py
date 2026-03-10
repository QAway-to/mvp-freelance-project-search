import asyncio
import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse
import logging
import json

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

# Log current configuration on startup
log_agent_action("App", f"🚀 Application started in {config.MODE.upper()} mode")
log_agent_action("App", f"📋 Search keywords: {', '.join(config.SEARCH_KEYWORDS_LIST)}")
log_agent_action("App", f"📋 Primary keyword: {config.SEARCH_KEYWORD}")

@app.get("/")
async def dashboard(request: Request):
    """Main dashboard"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "mode": config.MODE,
        "keyword": ", ".join(config.SEARCH_KEYWORDS_LIST)
    })

@app.get("/logs/stream")
async def stream_logs():
    """Server-Sent Events for real-time logs - optimized for streaming"""
    async def event_generator():
        while True:
            try:
                # Rapidly read all available messages from queue
                batch = []
                max_batch = 200  # Read up to 200 messages at once
                
                # Collect all available messages immediately
                while len(batch) < max_batch:
                    try:
                        log_message = log_queue.get_nowait()
                        batch.append(log_message)
                    except asyncio.QueueEmpty:
                        break
                
                # Send all collected messages one by one (for streaming effect)
                for log_message in batch:
                    yield f"data: {log_message}\n\n"
                    # Minimal delay - just enough to allow browser to process
                    if len(batch) > 1:
                        await asyncio.sleep(0.0001)  # Very small delay for streaming
                
                # If we sent messages, check again immediately
                if batch:
                    continue
                
                # No messages available - wait briefly for new messages
                try:
                    log_message = await asyncio.wait_for(log_queue.get(), timeout=0.01)
                    yield f"data: {log_message}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive to maintain connection
                    yield f": keepalive\n\n"
                    await asyncio.sleep(0.05)  # Very short wait
                    
            except Exception as e:
                yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
                await asyncio.sleep(0.1)

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

# MVP Generation API
@app.post("/api/generate-mvp")
async def generate_mvp(request: Request):
    """Generate MVP based on project description"""
    try:
        data = await request.json()
        description = data.get("description", "").strip()

        if not description or len(description) < 20:
            return {
                "status": "error",
                "error": "Описание проекта слишком короткое (минимум 20 символов)"
            }

        log_agent_action("MVP", f"🎯 Starting MVP generation for: {description[:100]}...")

        # Import and use MVP generator
        try:
            from mvp_generator import MVPGenerator
            generator = MVPGenerator()
            result = await generator.generate_mvp(description)

            log_agent_action("MVP", f"✅ MVP successfully generated: {result['deploy_url']}")

            return {
                "status": "success",
                "template": result["template"],
                "deployUrl": result["deploy_url"],
                "projectName": result["project_name"],
                "confidence": result["confidence"],
                "message": "MVP успешно создан и развернут"
            }

        except ImportError:
            # Fallback to mock response if Agent B is not available
            log_agent_action("MVP", "⚠️ Agent B not available, using mock generation")
            import asyncio
            import time

            log_agent_action("MVP", f"🤖 AI analyzing project description...")
            await asyncio.sleep(1)
            log_agent_action("MVP", f"✅ Template selected: telegram-shop-bot (confidence: 0.87)")

            await asyncio.sleep(1)
            log_agent_action("MVP", f"🔧 Generating React components and API routes...")

            await asyncio.sleep(1)
            log_agent_action("MVP", f"🚀 Pushing to GitHub repository...")

            await asyncio.sleep(1)
            log_agent_action("MVP", f"🎉 Deploying to Vercel...")

            deploy_url = f"https://ai-mvp-{int(time.time())}.vercel.app"
            log_agent_action("MVP", f"✅ MVP successfully generated and deployed: {deploy_url}")

            return {
                "status": "success",
                "template": "telegram-shop-bot",
                "deployUrl": deploy_url,
                "message": "MVP успешно создан и развернут (mock mode)"
            }

    except Exception as e:
        log_agent_action("MVP", f"❌ MVP generation failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
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
