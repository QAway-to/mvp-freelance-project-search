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

    def setup_driver(self):
        """Setup stealth browser"""
        log_agent_action("Agent A", "Setting up stealth browser")

        if config.MODE == "demo":
            # In demo mode, skip browser setup entirely
            log_agent_action("Agent A", "Demo mode: skipping browser setup")
            self.driver = None
            return

        options = Options()

        # Basic options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Random User-Agent
        ua = UserAgent()
        options.add_argument(f"--user-agent={ua.random}")

        # Disable WebRTC
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=VizDisplayCompositor")

        # Headless for server deployment
        if config.MODE == "demo":
            options.add_argument("--headless")

        # Create driver - let Selenium Manager handle it
        try:
            # Selenium 4.15+ has built-in manager
            self.driver = webdriver.Chrome(options=options)
        except Exception as e:
            log_agent_action("Agent A", f"Chrome driver setup failed: {e}")
            # Try with explicit service
            try:
                service = Service()
                self.driver = webdriver.Chrome(service=service, options=options)
            except Exception as e2:
                log_agent_action("Agent A", f"Service setup also failed: {e2}")
                raise Exception("Could not setup Chrome driver")

        # Apply stealth
        try:
            stealth(self.driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=True)
        except Exception as e:
            log_agent_action("Agent A", f"Stealth setup failed: {e}")

        log_agent_action("Agent A", "Browser setup complete")

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
        log_agent_action("Agent A", "Demo mode: generating fake projects")

        # Simulate browser activity (without actual browser)
        log_agent_action("Agent A", "Demo mode: simulating browser navigation")
        self.human_delay()
        self.simulate_reading()

        # Fake projects data - include "бот" keyword for better demo
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
        found_projects = []
        for i, project in enumerate(fake_projects[:config.MAX_PROJECTS_PER_SESSION]):
            log_agent_action("Agent A", f"Found demo project: {project['title'][:50]}...")
            found_projects.append(project)
            self.human_delay(1, 3)  # Simulate processing time

        log_agent_action("Agent A", f"Demo search complete: {len(found_projects)} projects generated")
        return found_projects

    def _search_real_projects(self) -> List[Dict[str, Any]]:
        """Real search on Kwork"""
        log_agent_action("Agent A", "Real search mode: accessing Kwork")

        # Navigate to search URL
        search_url = f"{config.KWORK_PROJECTS_URL}?query={config.SEARCH_KEYWORD}"
        self.driver.get(search_url)

        self.human_delay()
        self.simulate_reading()

        projects = []

        try:
            # Wait for projects to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1 a[href*='/projects/']"))
            )

            # Find all project elements
            project_elements = self.driver.find_elements(By.CSS_SELECTOR, "h1 a[href*='/projects/']")

            log_agent_action("Agent A", f"Found {len(project_elements)} potential projects")

            for i, link_element in enumerate(project_elements[:config.MAX_PROJECTS_PER_SESSION]):
                try:
                    # Extract project data
                    title = link_element.text.strip()
                    url = link_element.get_attribute("href")

                    # Get description (usually in the same container)
                    project_container = link_element.find_element(By.XPATH, "../../../..")

                    # Try different selectors for description
                    description = ""
                    try:
                        desc_element = project_container.find_element(By.CSS_SELECTOR, ".project-description, .task__description")
                        description = desc_element.text.strip()
                    except:
                        # Fallback: get text from container
                        container_text = project_container.text
                        # Remove title and get next meaningful text
                        desc_start = container_text.find(title) + len(title)
                        description = container_text[desc_start:].strip().split('\n')[0][:200]

                    # Get budget information
                    budget = ""
                    try:
                        budget_element = project_container.find_element(By.CSS_SELECTOR, "[class*='price'], [class*='budget']")
                        budget = budget_element.text.strip()
                    except:
                        pass

                    project_data = {
                        "id": url.split('/')[-1] if '/' in url else str(i),
                        "title": title,
                        "description": description,
                        "budget": budget,
                        "url": url,
                        "found_at": datetime.now().isoformat()
                    }

                    projects.append(project_data)
                    log_agent_action("Agent A", f"Parsed project: {title[:50]}...")

                    # Human delay between projects
                    self.human_delay(1, 3)

                except Exception as e:
                    log_agent_action("Agent A", f"Error parsing project {i}: {str(e)}")
                    continue

        except TimeoutException:
            log_agent_action("Agent A", "Timeout waiting for projects to load")
        except Exception as e:
            log_agent_action("Agent A", f"Error during search: {str(e)}")

        return projects

    def evaluate_and_notify(self, projects: List[Dict[str, Any]]):
        """Evaluate projects and send notifications"""
        log_agent_action("Agent A", f"Evaluating {len(projects)} projects")

        suitable_projects = []

        for project in projects:
            try:
                # Evaluate relevance
                score, reasons = self.evaluator.evaluate_project(project)

                project["evaluation"] = {
                    "score": score,
                    "reasons": reasons,
                    "suitable": score >= config.EVALUATION_THRESHOLD
                }

                if project["evaluation"]["suitable"]:
                    suitable_projects.append(project)
                    log_agent_action("Agent A", f"✅ Suitable project: {project['title'][:50]} (score: {score:.2f})")

                    # Send to Telegram if configured
                    if self.telegram:
                        asyncio.create_task(self.telegram.send_project_notification(project))
                    
                    # Send to n8n workflow (Agent B)
                    asyncio.create_task(self.send_to_n8n(project))
                else:
                    log_agent_action("Agent A", f"❌ Not suitable: {project['title'][:50]} (score: {score:.2f})")

            except Exception as e:
                log_agent_action("Agent A", f"Error evaluating project: {str(e)}")

        self.found_projects.extend(suitable_projects)

        # Summary
        log_agent_action("Agent A", f"Session complete: {len(suitable_projects)} suitable projects found")

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
        if not self.driver:
            self.setup_driver()

        self.status = "running"
        self.last_run_time = datetime.now().isoformat()

        try:
            log_agent_action("Agent A", "Starting search session")

            # Search projects
            projects = self.search_projects()

            if projects:
                # Evaluate and notify
                self.evaluate_and_notify(projects)
            else:
                log_agent_action("Agent A", "No projects found")

        except Exception as e:
            log_agent_action("Agent A", f"Session error: {str(e)}")
        finally:
            self.status = "waiting"

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
