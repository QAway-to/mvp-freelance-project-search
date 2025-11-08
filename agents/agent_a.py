import asyncio
import time
from datetime import datetime
from typing import List, Dict, Any
import aiohttp
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from fake_useragent import UserAgent
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from config import config
from utils.logger import logger, log_agent_action
from evaluation.evaluator import ProjectEvaluator
from telegram_bot import TelegramNotifier

class AgentA:
    def __init__(self):
        self.driver = None
        self.evaluator = ProjectEvaluator()
        self.telegram = TelegramNotifier() if config.TELEGRAM_BOT_TOKEN else None
        self.status = "stopped"
        self.last_run_time = None
        self.found_projects: List[Dict[str, Any]] = []
        self.running = False
        self.current_session_start = None
        self.current_session_end = None
        self.session_steps: List[Dict[str, Any]] = []

    def setup_driver(self):
        """Setup stealth browser"""
        log_agent_action("Agent A", "🔧 [SELENIUM] Starting browser setup...")

        if config.MODE == "demo":
            # In demo mode, skip browser setup entirely
            log_agent_action("Agent A", "🔧 [SELENIUM] Demo mode: skipping browser setup")
            self.driver = None
            return

        log_agent_action("Agent A", "🔧 [SELENIUM] Creating Chrome options...")
        options = Options()

        # Basic options
        log_agent_action("Agent A", "🔧 [SELENIUM] Configuring Chrome options (no-sandbox, disable-automation)...")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Random User-Agent
        log_agent_action("Agent A", "🔧 [SELENIUM] Generating random User-Agent...")
        ua = UserAgent()
        user_agent = ua.random
        options.add_argument(f"--user-agent={user_agent}")
        log_agent_action("Agent A", f"🔧 [SELENIUM] User-Agent: {user_agent[:50]}...")

        # Disable WebRTC
        log_agent_action("Agent A", "🔧 [SELENIUM] Disabling WebRTC and security features...")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=VizDisplayCompositor")

        # Headless for server deployment
        if config.MODE == "demo":
            options.add_argument("--headless")
            log_agent_action("Agent A", "🔧 [SELENIUM] Headless mode enabled")

        # Create driver - let Selenium Manager handle it
        log_agent_action("Agent A", "🔧 [SELENIUM] Initializing Chrome driver...")
        try:
            # Selenium 4.15+ has built-in manager
            self.driver = webdriver.Chrome(options=options)
            log_agent_action("Agent A", "✅ [SELENIUM] Chrome driver initialized successfully")
        except Exception as e:
            log_agent_action("Agent A", f"⚠️ [SELENIUM] Chrome driver setup failed: {e}")
            # Try with explicit service
            try:
                log_agent_action("Agent A", "🔧 [SELENIUM] Retrying with explicit service...")
                service = Service()
                self.driver = webdriver.Chrome(service=service, options=options)
                log_agent_action("Agent A", "✅ [SELENIUM] Chrome driver initialized with service")
            except Exception as e2:
                log_agent_action("Agent A", f"❌ [SELENIUM] Service setup also failed: {e2}")
                raise Exception("Could not setup Chrome driver")

        # Apply stealth
        log_agent_action("Agent A", "🔧 [SELENIUM] Applying stealth configuration...")
        try:
            stealth(self.driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True)
            log_agent_action("Agent A", "✅ [SELENIUM] Stealth configuration applied")
        except Exception as e:
            log_agent_action("Agent A", f"⚠️ [SELENIUM] Stealth setup failed: {e}")

        log_agent_action("Agent A", "✅ [SELENIUM] Browser setup complete")

    def human_delay(self, min_sec: float = None, max_sec: float = None):
        """Human-like delay between actions"""
        if min_sec is None:
            min_sec = config.DELAY_BETWEEN_ACTIONS_MIN
        if max_sec is None:
            max_sec = config.DELAY_BETWEEN_ACTIONS_MAX

        delay = min_sec + (max_sec - min_sec) * (time.time() % 1)  # Pseudo-random
        time.sleep(delay)
        return delay

    def simulate_reading(self, duration: int = None):
        """Simulate human reading"""
        if duration is None:
            duration = config.READING_TIME_MIN + int((config.READING_TIME_MAX - config.READING_TIME_MIN) * (time.time() % 1))

        log_agent_action("Agent A", f"Simulating reading for {duration} seconds")

        if self.driver:
            # Scroll to simulate reading
            scroll_steps = min(5, duration // 2)
            for i in range(scroll_steps):
                try:
                    self.driver.execute_script("window.scrollBy(0, 200);")
                    time.sleep(duration / scroll_steps)
                except:
                    break

        time.sleep(duration % 2)  # Remaining time

    def search_projects(self) -> List[Dict[str, Any]]:
        """Search for projects with keyword"""
        log_agent_action("Agent A", f"Searching projects with keyword: {config.SEARCH_KEYWORD}")

        if config.MODE == "demo":
            # Demo mode: generate fake projects
            return self._generate_demo_projects()
        else:
            # Full mode: real search on Kwork
            return self._search_real_projects()

    def _generate_demo_projects(self) -> List[Dict[str, Any]]:
        """Generate fake projects for demo mode"""
        log_agent_action("Agent A", "🎭 [DEMO] Generating fake projects for demo mode...")

        # Simulate browser activity (without actual browser)
        log_agent_action("Agent A", "🎭 [DEMO] Simulating browser navigation...")
        delay = self.human_delay()
        log_agent_action("Agent A", f"⏱️ [DEMO] Human delay: {delay:.2f}s")
        
        log_agent_action("Agent A", "🎭 [DEMO] Simulating reading page...")
        self.simulate_reading()
        log_agent_action("Agent A", "✅ [DEMO] Reading simulation complete")

        # Fake projects data - include "бот" keyword for better demo
        log_agent_action("Agent A", "🎭 [DEMO] Loading demo projects database...")
        fake_projects = [
            {
                "id": "demo_1",
                "title": "Создать Telegram бота для уведомлений о скидках",
                "description": "Нужен бот который будет мониторить скидки на сайте и отправлять уведомления пользователям. Требуется опыт работы с Telegram API, Python или Node.js. Бот должен уметь работать с базой данных пользователей.",
                "budget": "15 000 ₽",
                "url": "https://kwork.ru/projects/demo_1",
                "found_at": datetime.now().isoformat()
            },
            {
                "id": "demo_2",
                "title": "Разработка Discord бота модератора",
                "description": "Требуется создать бота для Discord сервера. Функционал: автоматическая модерация чата, система предупреждений, логирование действий. Предпочтительно на Python с использованием discord.py",
                "budget": "8 000 ₽",
                "url": "https://kwork.ru/projects/demo_2",
                "found_at": datetime.now().isoformat()
            },
            {
                "id": "demo_3",
                "title": "Бот для парсинга данных с сайтов",
                "description": "Нужно разработать бота для автоматического сбора информации с нескольких сайтов. Обработка HTML, сохранение в базу данных. Защита от блокировок, ротация прокси. Бот должен работать автономно.",
                "budget": "25 000 ₽",
                "url": "https://kwork.ru/projects/demo_3",
                "found_at": datetime.now().isoformat()
            },
            {
                "id": "demo_4",
                "title": "Умный бот для обработки заказов",
                "description": "Создать бота который будет автоматически обрабатывать заказы с сайта. Интеграция с платежными системами, отправка уведомлений клиентам. Бот должен быть умным и адаптивным.",
                "budget": "20 000 ₽",
                "url": "https://kwork.ru/projects/demo_4",
                "found_at": datetime.now().isoformat()
            },
            {
                "id": "demo_5",
                "title": "Создать чатбот для сайта на JavaScript",
                "description": "Интегрировать чатбот на сайт компании. Бот должен отвечать на типичные вопросы, собирать контакты, передавать информацию менеджеру. Использовать Dialogflow или аналог.",
                "budget": "12 000 ₽",
                "url": "https://kwork.ru/projects/demo_5",
                "found_at": datetime.now().isoformat()
            }
        ]

        # Simulate finding projects with delays
        log_agent_action("Agent A", f"🔍 [DEMO] Processing {min(len(fake_projects), config.MAX_PROJECTS_PER_SESSION)} projects...")
        found_projects = []
        for i, project in enumerate(fake_projects[:config.MAX_PROJECTS_PER_SESSION]):
            log_agent_action("Agent A", f"📄 [DEMO] Project {i+1}/{min(len(fake_projects), config.MAX_PROJECTS_PER_SESSION)}: {project['title'][:50]}...")
            log_agent_action("Agent A", f"💰 [DEMO] Budget: {project.get('budget', 'N/A')}")
            found_projects.append(project)
            delay = self.human_delay(1, 3)  # Simulate processing time
            log_agent_action("Agent A", f"⏱️ [DEMO] Processing delay: {delay:.2f}s")

        log_agent_action("Agent A", f"✅ [DEMO] Demo search complete: {len(found_projects)} projects generated and processed")
        return found_projects

    def _search_real_projects(self) -> List[Dict[str, Any]]:
        """Real search on Kwork"""
        log_agent_action("Agent A", "🌐 [SELENIUM] Real search mode: accessing Kwork")

        # Navigate to search URL
        search_url = f"{config.KWORK_PROJECTS_URL}?query={config.SEARCH_KEYWORD}"
        log_agent_action("Agent A", f"🌐 [SELENIUM] Navigating to: {search_url}")
        self.driver.get(search_url)
        log_agent_action("Agent A", "✅ [SELENIUM] Page loaded successfully")

        log_agent_action("Agent A", "⏱️ [SELENIUM] Waiting for page to stabilize...")
        delay = self.human_delay()
        log_agent_action("Agent A", f"⏱️ [SELENIUM] Human delay: {delay:.2f}s")
        
        log_agent_action("Agent A", "👁️ [SELENIUM] Simulating human reading behavior...")
        self.simulate_reading()
        log_agent_action("Agent A", "✅ [SELENIUM] Reading simulation complete")

        projects = []

        try:
            # Wait for projects to load
            log_agent_action("Agent A", "🔍 [SELENIUM] Waiting for project elements to load...")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1 a[href*='/projects/']"))
            )
            log_agent_action("Agent A", "✅ [SELENIUM] Project elements found on page")

            # Find all project elements
            log_agent_action("Agent A", "🔍 [SELENIUM] Searching for project links...")
            project_elements = self.driver.find_elements(By.CSS_SELECTOR, "h1 a[href*='/projects/']")
            log_agent_action("Agent A", f"✅ [SELENIUM] Found {len(project_elements)} potential projects")

            log_agent_action("Agent A", f"📊 [SELENIUM] Processing first {min(len(project_elements), config.MAX_PROJECTS_PER_SESSION)} projects...")
            for i, link_element in enumerate(project_elements[:config.MAX_PROJECTS_PER_SESSION]):
                try:
                    log_agent_action("Agent A", f"🔍 [SELENIUM] Parsing project {i+1}/{min(len(project_elements), config.MAX_PROJECTS_PER_SESSION)}...")
                    
                    # Extract project data
                    title = link_element.text.strip()
                    url = link_element.get_attribute("href")
                    log_agent_action("Agent A", f"📄 [SELENIUM] Title: {title[:50]}...")

                    # Get description (usually in the same container)
                    log_agent_action("Agent A", f"🔍 [SELENIUM] Extracting description...")
                    project_container = link_element.find_element(By.XPATH, "../../../..")

                    # Try different selectors for description
                    description = ""
                    try:
                        desc_element = project_container.find_element(By.CSS_SELECTOR, ".project-description, .task__description")
                        description = desc_element.text.strip()
                        log_agent_action("Agent A", f"✅ [SELENIUM] Description extracted: {len(description)} chars")
                    except:
                        # Fallback: get text from container
                        container_text = project_container.text
                        # Remove title and get next meaningful text
                        desc_start = container_text.find(title) + len(title)
                        description = container_text[desc_start:].strip().split('\n')[0][:200]
                        log_agent_action("Agent A", f"⚠️ [SELENIUM] Using fallback description: {len(description)} chars")

                    # Get budget information
                    log_agent_action("Agent A", f"💰 [SELENIUM] Extracting budget...")
                    budget = ""
                    try:
                        budget_element = project_container.find_element(By.CSS_SELECTOR, "[class*='price'], [class*='budget']")
                        budget = budget_element.text.strip()
                        log_agent_action("Agent A", f"✅ [SELENIUM] Budget: {budget}")
                    except:
                        log_agent_action("Agent A", f"⚠️ [SELENIUM] Budget not found")

                    project_data = {
                        "id": url.split('/')[-1] if '/' in url else str(i),
                        "title": title,
                        "description": description,
                        "budget": budget,
                        "url": url,
                        "found_at": datetime.now().isoformat()
                    }

                    projects.append(project_data)
                    log_agent_action("Agent A", f"✅ [SELENIUM] Project {i+1} parsed successfully")

                    # Human delay between projects
                    delay = self.human_delay(1, 3)
                    log_agent_action("Agent A", f"⏱️ [SELENIUM] Processing delay: {delay:.2f}s")

                except Exception as e:
                    log_agent_action("Agent A", f"❌ [SELENIUM] Error parsing project {i+1}: {str(e)}")
                    continue

            log_agent_action("Agent A", f"✅ [SELENIUM] Successfully parsed {len(projects)} projects")

        except TimeoutException:
            log_agent_action("Agent A", "❌ [SELENIUM] Timeout waiting for projects to load (10s)")
        except Exception as e:
            log_agent_action("Agent A", f"❌ [SELENIUM] Error during search: {str(e)}")

        return projects

    def evaluate_and_notify(self, projects: List[Dict[str, Any]]):
        """Evaluate projects and send notifications"""
        log_agent_action("Agent A", f"📊 [EVALUATION] Starting evaluation of {len(projects)} projects...")
        log_agent_action("Agent A", f"📊 [EVALUATION] Threshold: {config.EVALUATION_THRESHOLD}")

        suitable_projects = []

        for i, project in enumerate(projects):
            try:
                log_agent_action("Agent A", f"📊 [EVALUATION] Evaluating project {i+1}/{len(projects)}: {project['title'][:50]}...")
                
                # Evaluate relevance
                score, reasons = self.evaluator.evaluate_project(project)

                project["evaluation"] = {
                    "score": score,
                    "reasons": reasons,
                    "suitable": score >= config.EVALUATION_THRESHOLD
                }

                log_agent_action("Agent A", f"📊 [EVALUATION] Score: {score:.2f}/1.0 | Threshold: {config.EVALUATION_THRESHOLD}")

                if project["evaluation"]["suitable"]:
                    suitable_projects.append(project)
                    log_agent_action("Agent A", f"✅ [EVALUATION] Project APPROVED: {project['title'][:50]}... (score: {score:.2f})")
                    log_agent_action("Agent A", f"📋 [EVALUATION] Reasons: {', '.join(reasons[:3])}")

                    # Send to Telegram if configured
                    if self.telegram:
                        log_agent_action("Agent A", f"📱 [TELEGRAM] Sending notification for project {i+1}...")
                        asyncio.create_task(self.telegram.send_project_notification(project))
                    
                    # Send to n8n workflow (Agent B)
                    log_agent_action("Agent A", f"🔗 [N8N] Sending project {i+1} to n8n workflow...")
                    asyncio.create_task(self.send_to_n8n(project))
                else:
                    log_agent_action("Agent A", f"❌ [EVALUATION] Project REJECTED: {project['title'][:50]}... (score: {score:.2f} < {config.EVALUATION_THRESHOLD})")

            except Exception as e:
                log_agent_action("Agent A", f"❌ [EVALUATION] Error evaluating project {i+1}: {str(e)}")

        self.found_projects.extend(suitable_projects)

        # Summary
        log_agent_action("Agent A", f"📈 [EVALUATION] Evaluation complete: {len(suitable_projects)}/{len(projects)} projects approved")
        log_agent_action("Agent A", f"📈 [EVALUATION] Total suitable projects in history: {len(self.found_projects)}")

    async def send_to_n8n(self, project: Dict[str, Any]):
        """Send suitable project to n8n workflow (Agent B)"""
        if not config.N8N_WEBHOOK_URL:
            log_agent_action("Agent A", "n8n webhook URL not configured - skipping")
            return

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "project_id": project.get("id"),
                    "title": project.get("title"),
                    "description": project.get("description"),
                    "budget": project.get("budget"),
                    "url": project.get("url"),
                    "evaluation": project.get("evaluation", {}),
                    "found_at": project.get("found_at"),
                    "status": "pending_review"  # Waiting for manual approval
                }

                async with session.post(
                    config.N8N_WEBHOOK_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        log_agent_action("Agent A", f"✅ Project sent to n8n: {project['title'][:50]}...")
                    else:
                        log_agent_action("Agent A", f"⚠️ n8n webhook returned status {response.status}")
        except Exception as e:
            log_agent_action("Agent A", f"❌ Error sending to n8n: {str(e)}")

    async def run_session(self):
        """Run one search session"""
        session_start = datetime.now()
        self.current_session_start = session_start
        self.session_steps = []
        
        log_agent_action("Agent A", f"🚀 [SESSION] Starting new search session at {session_start.strftime('%H:%M:%S')}")
        
        if not self.driver:
            step_start = datetime.now()
            log_agent_action("Agent A", "🔧 [SESSION] Setting up browser driver...")
            self.setup_driver()
            step_duration = (datetime.now() - step_start).total_seconds()
            log_agent_action("Agent A", f"⏱️ [SESSION] Browser setup completed in {step_duration:.2f}s")

        self.status = "running"
        self.last_run_time = datetime.now().isoformat()

        try:
            # Step 1: Search projects
            step_start = datetime.now()
            log_agent_action("Agent A", "🔍 [SESSION] Step 1/3: Searching projects...")
            projects = self.search_projects()
            step_duration = (datetime.now() - step_start).total_seconds()
            log_agent_action("Agent A", f"✅ [SESSION] Step 1/3 completed: Found {len(projects)} projects in {step_duration:.2f}s")

            if projects:
                # Step 2: Evaluate projects
                step_start = datetime.now()
                log_agent_action("Agent A", f"📊 [SESSION] Step 2/3: Evaluating {len(projects)} projects...")
                self.evaluate_and_notify(projects)
                step_duration = (datetime.now() - step_start).total_seconds()
                log_agent_action("Agent A", f"✅ [SESSION] Step 2/3 completed: Evaluation finished in {step_duration:.2f}s")
            else:
                log_agent_action("Agent A", "⚠️ [SESSION] No projects found in this session")

            # Session summary
            session_duration = (datetime.now() - session_start).total_seconds()
            self.current_session_end = datetime.now()
            log_agent_action("Agent A", f"✅ [SESSION] Session completed in {session_duration:.2f}s")
            log_agent_action("Agent A", f"📈 [SESSION] Summary: Found {len(projects)} projects, {len([p for p in projects if p.get('evaluation', {}).get('suitable', False)])} suitable")

        except Exception as e:
            session_duration = (datetime.now() - session_start).total_seconds()
            log_agent_action("Agent A", f"❌ [SESSION] Session error after {session_duration:.2f}s: {str(e)}")
        finally:
            self.status = "waiting"
            self.current_session_start = None
            self.current_session_end = None

    async def run_continuous(self):
        """Run continuous monitoring"""
        if self.running:
            return

        self.running = True
        log_agent_action("Agent A", "Starting continuous monitoring")

        try:
            while self.running:
                await self.run_session()

                if self.running:  # Check if still running after session
                    log_agent_action("Agent A", f"Waiting {config.PAUSE_BETWEEN_CHECKS} seconds until next check")
                    await asyncio.sleep(config.PAUSE_BETWEEN_CHECKS)

        except Exception as e:
            log_agent_action("Agent A", f"Continuous monitoring error: {str(e)}")
        finally:
            self.running = False
            self.status = "stopped"

    async def stop(self):
        """Stop the agent"""
        log_agent_action("Agent A", "Stopping agent")
        self.running = False
        self.status = "stopped"

        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
            except Exception as e:
                log_agent_action("Agent A", f"Error closing driver: {e}")
