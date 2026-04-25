import asyncio
import time
import re
import os
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
from urllib.parse import quote_plus

from config import config
from utils.logger import logger, log_agent_action
from evaluation.evaluator import ProjectEvaluator
from telegram_bot import TelegramNotifier

class AgentA:
    def __init__(self):
        self.driver = None
        self.logged_in = False
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

        # Headless mode for server deployment (Render/Linux)
        # Always use headless on server to avoid display issues
        log_agent_action("Agent A", "🔧 [SELENIUM] Configuring headless mode for server deployment...")
        options.add_argument("--headless=new")  # Use new headless mode
        options.add_argument("--disable-gpu")  # Disable GPU acceleration
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-features=TranslateUI")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--window-size=1920,1080")  # Set window size
        options.add_argument("--start-maximized")
        # Additional Linux-specific arguments
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-seccomp-filter-sandbox")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-sync")
        options.add_argument("--metrics-recording-only")
        options.add_argument("--mute-audio")
        options.add_argument("--no-first-run")
        options.add_argument("--safebrowsing-disable-auto-update")
        options.add_argument("--disable-component-update")
        
        # Set binary location if CHROME_BIN env var is set (for Render)
        chrome_bin = os.getenv("CHROME_BIN") or os.getenv("GOOGLE_CHROME_BIN")
        if chrome_bin:
            options.binary_location = chrome_bin
            log_agent_action("Agent A", f"🔧 [SELENIUM] Using Chrome binary from env: {chrome_bin}")
        
        log_agent_action("Agent A", "✅ [SELENIUM] Headless mode configured")

        # Create driver - let Selenium Manager handle it
        log_agent_action("Agent A", "🔧 [SELENIUM] Initializing Chrome driver...")
        
        # Try multiple Chrome binary locations (common on Render/Linux servers)
        chrome_paths = [
            os.getenv("CHROME_BIN"),
            os.getenv("GOOGLE_CHROME_BIN"),
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]
        
        # Find available Chrome binary
        chrome_found = None
        if options.binary_location:
            chrome_found = options.binary_location
        else:
            for path in chrome_paths:
                if path and os.path.exists(path):
                    chrome_found = path
                    options.binary_location = path
                    log_agent_action("Agent A", f"🔧 [SELENIUM] Found Chrome at: {path}")
                    break
        
        if not chrome_found:
            log_agent_action("Agent A", "⚠️ [SELENIUM] Chrome binary not found in standard locations, Selenium will try to find it")
        
        try:
            # Selenium 4.15+ has built-in manager
            self.driver = webdriver.Chrome(options=options)
            log_agent_action("Agent A", "✅ [SELENIUM] Chrome driver initialized successfully")
        except Exception as e:
            log_agent_action("Agent A", f"⚠️ [SELENIUM] Chrome driver setup failed: {str(e)[:200]}")
            # Try with explicit service and log level
            try:
                log_agent_action("Agent A", "🔧 [SELENIUM] Retrying with explicit service...")
                service = Service()
                service.service_args = ['--verbose']  # Enable verbose logging
                self.driver = webdriver.Chrome(service=service, options=options)
                log_agent_action("Agent A", "✅ [SELENIUM] Chrome driver initialized with service")
            except Exception as e2:
                error_msg = str(e2)[:500]  # Limit error message length
                log_agent_action("Agent A", f"❌ [SELENIUM] Service setup also failed: {error_msg}")
                log_agent_action("Agent A", "💡 [SELENIUM] Tip: Make sure Chrome is installed on the server", level="WARNING")
                log_agent_action("Agent A", "💡 [SELENIUM] On Windows, ensure Chrome is in PATH or specify location", level="WARNING")
                # Log environment variables for debugging
                log_agent_action("Agent A", f"🔍 [DEBUG] GOOGLE_CHROME_BIN: {os.getenv('GOOGLE_CHROME_BIN')}", level="DEBUG")
                log_agent_action("Agent A", f"🔍 [DEBUG] Current PATH: {os.getenv('PATH')[:100]}...", level="DEBUG")
                raise Exception(f"Could not setup Chrome driver: {error_msg}")

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

    def login(self):
        """Log in to Kwork"""
        if self.logged_in:
            return True

        if not self.driver:
            self.setup_driver()

        if not config.KWORK_EMAIL or not config.KWORK_PASSWORD:
            log_agent_action("Agent A", "⚠️ [AUTH] Credentials missing, skipping login", level="WARNING")
            return False

        log_agent_action("Agent A", f"🔐 [AUTH] Attempting login to Kwork as {config.KWORK_EMAIL}...")
        
        try:
            self.driver.get(config.KWORK_LOGIN_URL)
            self.human_delay(2, 4)

            # Find login fields
            email_field = self.driver.find_element(By.NAME, "login")
            password_field = self.driver.find_element(By.NAME, "password")
            
            email_field.send_keys(config.KWORK_EMAIL)
            self.human_delay(0.5, 1.5)
            password_field.send_keys(config.KWORK_PASSWORD)
            self.human_delay(0.5, 1.5)

            # Find and click submit button
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button.js-login-submit")
            submit_btn.click()
            
            self.human_delay(3, 5)

            # Check if login success (no longer on login page or see user icon)
            if "login" not in self.driver.current_url.lower():
                log_agent_action("Agent A", "✅ [AUTH] Successfully logged in to Kwork")
                self.logged_in = True
                return True
            else:
                log_agent_action("Agent A", "❌ [AUTH] Login failed (still on login page)", level="ERROR")
                return False

        except Exception as e:
            log_agent_action("Agent A", f"❌ [AUTH] Login error: {str(e)}", level="ERROR")
            return False

    def parse_urgency(self, text: str) -> float:
        """Parse 'Time Left' string to hours. Example: 'Осталось: 2 ч. 5 мин.' -> 2.08"""
        if not text or 'Осталось' not in text:
            return 999.0
        
        try:
            cleaned = text.replace('Осталось:', '').strip()
            # Regex to find days, hours, mins
            days = 0
            hours = 0
            mins = 0
            
            d_match = re.search(r'(\d+)\s*д', cleaned)
            h_match = re.search(r'(\d+)\s*ч', cleaned)
            m_match = re.search(r'(\d+)\s*мин', cleaned)
            
            if d_match: days = int(d_match.group(1))
            if h_match: hours = int(h_match.group(1))
            if m_match: mins = int(m_match.group(1))
            
            total_hours = (days * 24) + hours + (mins / 60)
            return total_hours
        except Exception as e:
            log_agent_action("Agent A", f"⚠️ Error parsing urgency '{text}': {e}", level="DEBUG")
            return 999.0

    def human_delay(self, min_sec: float = None, max_sec: float = None):
        """Human-like delay between actions"""
        if min_sec is None:
            min_sec = config.DELAY_BETWEEN_ACTIONS_MIN
        if max_sec is None:
            max_sec = config.DELAY_BETWEEN_ACTIONS_MAX

        delay = min_sec + (max_sec - min_sec) * (time.time() % 1)  # Pseudo-random
        time.sleep(delay)
        return delay

    def _is_title_preliminary_relevant(self, title: str) -> bool:
        """
        Preliminary title filtering - only filters out obviously irrelevant projects.
        Since we're already searching by relevant keywords on Kwork, most results should be relevant.
        We only filter out clearly unrelated projects (like 'лифт', 'дизайн', etc.).
        """
        if not title:
            return False

        title_lower = title.lower()

        # Hard filter: Must NOT contain obviously irrelevant words
        # These are projects that have nothing to do with bots/data/scripts/parsing
        irrelevant_words = [
            'лифт', 'проект лифта', 'строительств', 'ремонт', 'мебель',
            'дизайн', 'логотип', 'баннер', 'фото', 'видео', 'монтаж', 'графика',
            'текст', 'копирайтинг', 'копирайт', 'перевод', 'статья', 'презентация',
            'верстка', 'html', 'css', 'фронтенд', 'ui/ux', 'анимация',
            'чертеж', 'чертежи', 'ванна', 'столик', 'выдвижные ящики',  # Example from logs
            'экспертные тексты', 'блог wordpress'  # Content writing
        ]

        # Check for irrelevant words (hard filter)
        has_irrelevant = any(word in title_lower for word in irrelevant_words)
        if has_irrelevant:
            return False

        # Since we're already searching by relevant keywords on Kwork,
        # we assume that most results are relevant unless they contain irrelevant words.
        # This allows more projects to pass through for detailed evaluation.
        return True

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
                except Exception:
                    break

        time.sleep(duration % 2)  # Remaining time

    def search_projects(self) -> List[Dict[str, Any]]:
        """Search for projects with keywords"""
        keywords_str = ", ".join(config.SEARCH_KEYWORDS_LIST)
        log_agent_action("Agent A", f"Searching projects with keywords: {keywords_str}")

        if config.MODE == "demo":
            # Demo mode: generate fake projects
            return self._generate_demo_projects()
        else:
            # Full mode: real search on Kwork
            return self._search_real_projects()

    def _generate_demo_projects(self) -> List[Dict[str, Any]]:
        """Generate demo projects - DISABLED: Returns empty list"""
        log_agent_action("Agent A", "🎭 [DEMO] Demo mode: Fake projects are disabled")
        log_agent_action("Agent A", "🎭 [DEMO] To get real projects, set MODE=full and provide Kwork credentials")
        log_agent_action("Agent A", "🎭 [DEMO] Agent will only process real projects from Kwork with browser automation")
        return []

    def _check_proposal_button_available(self) -> bool:
        """Check if 'Предложить услугу' button is available on project page"""
        try:
            # Check page source for button text
            page_source = self.driver.page_source.lower()
            
            # Look for proposal button text
            proposal_keywords = ['предложить услугу', 'предложить', 'отправить предложение']
            has_proposal_text = any(keyword in page_source for keyword in proposal_keywords)
            
            if not has_proposal_text:
                log_agent_action("Agent A", f"⚠️ [SELENIUM] Proposal button text ('предложить услугу') NOT found in page source", level="WARNING")
                # Log a snippet of the page source for debugging
                source_snippet = page_source[:500].replace('\n', ' ')
                log_agent_action("Agent A", f"🔍 [DEBUG] Page source snippet: {source_snippet}...", level="DEBUG")
                return False
            
            # Try to find button element by various methods
            try:
                # Method 1: XPath with text content
                proposal_button = self.driver.find_element(By.XPATH, 
                    "//button[contains(translate(text(), 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ', 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'), 'предложить услугу')] | " +
                    "//a[contains(translate(text(), 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ', 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'), 'предложить услугу')]")
                
                if proposal_button and proposal_button.is_displayed():
                    # Check if button is enabled (not disabled)
                    if proposal_button.is_enabled():
                        log_agent_action("Agent A", f"✅ [SELENIUM] Proposal button found and enabled")
                        return True
                    else:
                        log_agent_action("Agent A", f"⚠️ [SELENIUM] Proposal button found but disabled")
                        return False
            except NoSuchElementException:
                pass
            
            # Method 2: Try common button selectors
            try:
                buttons = self.driver.find_elements(By.CSS_SELECTOR, "button, a.btn, a[class*='button']")
                for button in buttons:
                    button_text = button.text.lower()
                    if any(keyword in button_text for keyword in proposal_keywords):
                        if button.is_displayed() and button.is_enabled():
                            log_agent_action("Agent A", f"✅ [SELENIUM] Proposal button found via CSS selector")
                            return True
            except Exception:
                pass
            
            # If button text exists but element not found, assume it might be available
            # (could be dynamically loaded or hidden)
            log_agent_action("Agent A", f"⚠️ [SELENIUM] Proposal button text exists but element not found by selectors, assuming available as fallback", level="WARNING")
            return True
            
        except Exception as e:
            log_agent_action("Agent A", f"❌ [SELENIUM] Error checking proposal button: {str(e)}", level="ERROR")
            # On error, assume button is available (to be safe)
            return True

    def _search_real_projects(self) -> List[Dict[str, Any]]:
        """Real search on Kwork with pagination, proposal button check, and semantic ranking"""
        log_agent_action("Agent A", "🌐 [SELENIUM] Real search mode: accessing Kwork")

        log_agent_action("Agent A", f"[SEARCH] _search_real_projects start: driver={self.driver is not None} logged_in={self.logged_in}")

        if not self.driver:
            log_agent_action("Agent A", "[SEARCH] driver is None — calling setup_driver()")
            try:
                self.setup_driver()
                log_agent_action("Agent A", f"[SEARCH] setup_driver done: driver={self.driver is not None}")
            except Exception as e:
                log_agent_action("Agent A", f"[SEARCH] setup_driver FAILED: {e}", level="ERROR")
                return []

        if not self.logged_in:
            log_agent_action("Agent A", "[SEARCH] not logged in — calling login()")
            try:
                result = self.login()
                log_agent_action("Agent A", f"[SEARCH] login returned: {result}, logged_in={self.logged_in}")
            except Exception as e:
                log_agent_action("Agent A", f"[SEARCH] login FAILED: {e}", level="ERROR")

        # Build search URL with all keywords (comma-separated, URL-encoded)
        # Format: ?keyword=бот,данные,скрипт&page=1&a=1
        keywords_str = ','.join(config.SEARCH_KEYWORDS_LIST)
        keywords_encoded = quote_plus(keywords_str)
        
        log_agent_action("Agent A", f"📋 [SELENIUM] Search keywords: {keywords_str}")
        log_agent_action("Agent A", f"📋 [SELENIUM] Target: Find up to 10 relevant projects with proposal button available, output top 5")

        # Search parameters
        max_pages = 3  # Maximum pages to search
        max_relevant_projects = 10  # Search for up to 10 relevant projects
        output_limit = 5  # Output top 5 most relevant
        
        all_projects = []  # All projects found (with full details)
        page = 1
        scraped_listing_pages = 0
        reverse_page_set = False  # guard: reverse-pagination redirect fires only once

        while scraped_listing_pages < max_pages and len(all_projects) < max_relevant_projects:
            # Build search URL for current page
            # Inject budget filters if they exist
            budget_params = "&".join([f"prices-filters[]={f}" for f in config.BUDGET_FILTERS])
            search_url = f"{config.KWORK_PROJECTS_URL}?keyword={keywords_encoded}&page={page}&a=1"
            if budget_params:
                search_url += f"&{budget_params}"
                
            log_agent_action("Agent A", f"🌐 [SELENIUM] Navigating to page {page}: {search_url}")
            
            try:
                self.driver.get(search_url)
                log_agent_action("Agent A", f"✅ [SELENIUM] Page {page} loaded successfully")
                
                # Logic for reverse pagination (on first page load, only once)
                if page == 1 and not reverse_page_set:
                    try:
                        pagination_items = self.driver.find_elements(By.CSS_SELECTOR, ".pagination__item")
                        if pagination_items:
                            # Filter only numeric items and find max
                            pages = []
                            for item in pagination_items:
                                if item.text.isdigit():
                                    pages.append(int(item.text))
                            
                            if pages:
                                max_p = max(pages)
                                log_agent_action("Agent A", f"📑 [SELENIUM] Found {max_p} total pages. Switching to last page for reverse search.")
                                # Redirect to last page instead of continuing from p1
                                page = max_p
                                reverse_page_set = True
                                self.driver.get(f"{search_url.replace('page=1', f'page={max_p}')}")
                                log_agent_action("Agent A", f"🔄 [SELENIUM] Switched to last page {max_p}")
                    except Exception as pg_e:
                        log_agent_action("Agent A", f"⚠️ Error finding max page: {pg_e}", level="DEBUG")

            except Exception as e:
                log_agent_action("Agent A", f"❌ [SELENIUM] Error loading page {page}: {str(e)}", level="ERROR")
                break

            # ... [Rest of stability and reading simulation remains similar] ...

            # Find all project elements on current page
            log_agent_action("Agent A", f"🔍 [SELENIUM] Searching for projects on page {page}...")
            project_cards = self.driver.find_elements(By.CSS_SELECTOR, ".want-card")
            log_agent_action("Agent A", f"✅ [SELENIUM] Found {len(project_cards)} projects on page {page}")

            if len(project_cards) == 0:
                log_agent_action("Agent A", f"⚠️ [SELENIUM] No projects on page {page}, stopping search")
                break

            # Collect all data from listing cards — no detail page navigation needed
            page_projects = []
            proposals_re = re.compile(
                r'(?:(\d+)\s*(?:предложен\w*|отклик\w*|заяв\w*|ставо?к?|оффер\w*)'
                r'|(?:предложен\w*|отклик\w*|заяв\w*)\s*[:\-]?\s*(\d+))',
                re.IGNORECASE
            )
            budget_re = re.compile(r'(от\s+[\d\s]+|до\s+[\d\s]+|[\d\s]{3,})\s*₽', re.IGNORECASE)

            for card in project_cards:
                try:
                    # Urgency check
                    urgency_element = card.find_element(By.CSS_SELECTOR, ".want-card__informers-row span.mr8")
                    urgency_text = urgency_element.text.strip()
                    urgency_hours = self.parse_urgency(urgency_text)

                    if urgency_hours > config.MAX_URGENCY_HOURS:
                        continue

                    # Title and link
                    link_element = card.find_element(By.CSS_SELECTOR, "h1 a[href*='/projects/']")
                    title = link_element.text.strip()
                    url = link_element.get_attribute("href")
                    if url and '/projects/' in url:
                        if '?' in url: url = url.split('?')[0]
                        if not url.endswith('/view'): url = url.rstrip('/') + '/view'

                    card_text = card.text

                    # Budget from card element, then regex fallback
                    budget = None
                    for sel in [".wants-card__header-price", "[class*='price']", "[class*='budget']"]:
                        try:
                            el = card.find_element(By.CSS_SELECTOR, sel)
                            t = el.text.strip()
                            if t and (re.search(r'\d', t) or '₽' in t):
                                budget = t
                                break
                        except Exception:
                            pass
                    if not budget:
                        bm = budget_re.search(card_text)
                        if bm:
                            budget = bm.group(0).strip()

                    # Description snippet from card
                    description = ""
                    for sel in [".wants-card__description-text", "[class*='description']"]:
                        try:
                            el = card.find_element(By.CSS_SELECTOR, sel)
                            t = el.text.strip()
                            if t and len(t) > 20:
                                description = t
                                break
                        except Exception:
                            pass

                    # Proposals: try card sub-elements first, then regex on card text
                    proposals = None
                    for sel in ["[class*='count']", "[class*='responses']", "[class*='offers']", "[class*='informer']"]:
                        try:
                            for el in card.find_elements(By.CSS_SELECTOR, sel):
                                t = el.text.strip()
                                m = re.search(r'\d+', t)
                                if m:
                                    proposals = int(m.group(0))
                                    break
                            if proposals is not None:
                                break
                        except Exception:
                            pass
                    if proposals is None:
                        pm = proposals_re.search(card_text)
                        if pm:
                            proposals = int(pm.group(1) if pm.group(1) is not None else pm.group(2))

                    log_agent_action("Agent A", f"📋 [LISTING] {title[:45]} | budget={budget} | proposals={proposals}")

                    page_projects.append({
                        "id": url.split('/')[-2] if '/' in url else "unknown",
                        "title": title,
                        "url": url,
                        "urgency": urgency_text,
                        "urgency_hours": urgency_hours,
                        "budget": budget,
                        "description": description,
                        "proposals": proposals,
                        "page": page,
                        "found_at": datetime.now().isoformat(),
                    })

                except Exception:
                    continue

            all_projects.extend(page_projects[:max_relevant_projects - len(all_projects)])

            scraped_listing_pages += 1
            log_agent_action("Agent A", f"📄 [LISTING] Page scraped: {len(page_projects)} cards, total collected: {len(all_projects)}")

            # Reverse pagination: go backwards page by page
            if page > 1:
                page -= 1
            else:
                break  # Reached page 1, done

        log_agent_action("Agent A", f"✅ [LISTING] Collection complete: {len(all_projects)} projects")
        
        # Now evaluate all projects and rank by semantic similarity
        if len(all_projects) > 0:
            log_agent_action("Agent A", f"🤖 [SEMANTIC] Evaluating {len(all_projects)} projects for semantic relevance...")
            
            # Evaluate each project and add semantic score
            evaluated_projects = []
            for project in all_projects:
                try:
                    score, reasons = self.evaluator.evaluate_project(project)
                    project["evaluation"] = {
                        "score": score,
                        "reasons": reasons,
                        "suitable": score >= config.EVALUATION_THRESHOLD
                    }
                    
                    # Extract semantic similarity if available
                    semantic_score = 0.0
                    for reason in reasons:
                        if "Similarity:" in reason:
                            try:
                                semantic_score = float(reason.split("Similarity:")[1].strip().split()[0])
                            except Exception:
                                pass
                    
                    project["semantic_score"] = semantic_score
                    evaluated_projects.append(project)
                    
                except Exception as e:
                    log_agent_action("Agent A", f"⚠️ [EVALUATION] Error evaluating project: {str(e)[:100]}")
                    continue
            
            # Sort by semantic score (highest first), then by total score
            evaluated_projects.sort(key=lambda x: (x.get("semantic_score", 0.0), x.get("evaluation", {}).get("score", 0.0)), reverse=True)
            
            # Return top N most relevant projects
            top_projects = evaluated_projects[:output_limit]
            log_agent_action("Agent A", f"📊 [SEMANTIC] Selected top {len(top_projects)} most relevant projects out of {len(evaluated_projects)}")
            
            return top_projects
        else:
            log_agent_action("Agent A", f"⚠️ [SELENIUM] No projects found with proposal button available")
            return []

    def evaluate_and_notify(self, projects: List[Dict[str, Any]]):
        """Evaluate projects and send notifications - projects are already evaluated in _search_real_projects"""
        log_agent_action("Agent A", f"📊 [EVALUATION] Processing {len(projects)} pre-evaluated projects...")
        log_agent_action("Agent A", f"📊 [EVALUATION] Threshold: {config.EVALUATION_THRESHOLD}")

        suitable_projects = []

        for i, project in enumerate(projects):
            try:
                evaluation = project.get("evaluation", {})
                score = evaluation.get("score", 0.0)
                reasons = evaluation.get("reasons", [])
                suitable = evaluation.get("suitable", False)
                
                log_agent_action("Agent A", f"📊 [EVALUATION] Project {i+1}/{len(projects)}: {project['title'][:50]}...")
                log_agent_action("Agent A", f"📊 [EVALUATION] Score: {score:.2f}/1.0 | Threshold: {config.EVALUATION_THRESHOLD}")

                if suitable:
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
                log_agent_action("Agent A", f"❌ [EVALUATION] Error processing project {i+1}: {str(e)}")

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
                    "description": project.get("description"),  # Full description
                    "budget": project.get("budget"),
                    "url": project.get("url"),
                    "proposals": project.get("proposals"),  # Number of proposals
                    "hired": project.get("hired"),  # Number of hired freelancers
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
            # Step 1: Search projects (includes semantic evaluation and ranking)
            step_start = datetime.now()
            log_agent_action("Agent A", "🔍 [SESSION] Step 1/2: Searching and evaluating projects...")
            projects = self.search_projects()
            step_duration = (datetime.now() - step_start).total_seconds()
            log_agent_action("Agent A", f"✅ [SESSION] Step 1/2 completed: Found {len(projects)} relevant projects in {step_duration:.2f}s")

            if projects:
                # Step 2: Send notifications for suitable projects
                step_start = datetime.now()
                log_agent_action("Agent A", f"📊 [SESSION] Step 2/2: Sending notifications for {len(projects)} projects...")
                self.evaluate_and_notify(projects)
                step_duration = (datetime.now() - step_start).total_seconds()
                log_agent_action("Agent A", f"✅ [SESSION] Step 2/2 completed: Notifications sent in {step_duration:.2f}s")
            else:
                log_agent_action("Agent A", "⚠️ [SESSION] No relevant projects found in this session")

            # Session summary
            session_duration = (datetime.now() - session_start).total_seconds()
            self.current_session_end = datetime.now()
            log_agent_action("Agent A", f"✅ [SESSION] Session completed in {session_duration:.2f}s")
            suitable_count = len([p for p in projects if p.get('evaluation', {}).get('suitable', False)])
            log_agent_action("Agent A", f"📈 [SESSION] Summary: Found {len(projects)} projects, {suitable_count} suitable")

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

    def parse_single_url(self, url: str) -> dict | None:
        """Parse a single Kwork project URL and return project data."""
        if not self.driver:
            self.setup_driver()
        if not self.logged_in:
            self.login()

        log_agent_action("Agent A", f"🔗 [PARSE] Navigating to {url}")
        try:
            self.driver.get(url)
            self.human_delay(2, 4)
        except Exception as e:
            log_agent_action("Agent A", f"❌ [PARSE] Failed to load URL: {e}", level="ERROR")
            return None

        import re as _re
        pid_match = _re.search(r"/projects/(\d+)/view", url)
        project_id = pid_match.group(1) if pid_match else "unknown"

        try:
            title_el = self.driver.find_elements(By.CSS_SELECTOR, "h1")
            title = title_el[0].text.strip() if title_el else ""

            desc = ""
            for sel in [".wants-card__description-text", ".task__description", ".break-word", "[class*='description']"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    texts = [e.text.strip() for e in els if e.text.strip()]
                    if texts:
                        desc = "\n".join(texts)
                        if len(desc) > 100:
                            break

            budget = ""
            for sel in [".wants-card__header-price", "[class*='price']", "[class*='budget']"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    t = el.text.strip()
                    if t and (_re.search(r"\d", t) or "₽" in t):
                        budget = t
                        break
                if budget:
                    break

            urgency_text = ""
            for sel in [".want-card__informers-row span.mr8", "[class*='time']", "[class*='urgency']"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    urgency_text = els[0].text.strip()
                    break
            time_left = self.parse_urgency(urgency_text) if urgency_text else None
            if time_left == 999.0:
                time_left = None

            proposals = 0
            page_src = self.driver.page_source
            for pat in [r"(\d+)\s+предложен", r"(\d+)\s+отклик", r"откликов[:\s]+(\d+)"]:
                m = _re.search(pat, page_src, _re.IGNORECASE)
                if m:
                    proposals = int(m.group(1))
                    break

            if not title:
                log_agent_action("Agent A", "⚠️ [PARSE] No title found", level="WARNING")
                return None

            project = {
                "id": project_id,
                "title": title,
                "description": desc,
                "budget": budget,
                "url": url,
                "proposals": proposals,
                "hired": 0,
                "timeLeft": time_left,
            }

            score, reasons = self.evaluator.evaluate_project(project)
            project["evaluation"] = {
                "score": score,
                "reasons": reasons,
                "suitable": score >= config.EVALUATION_THRESHOLD,
            }
            return project

        except Exception as e:
            log_agent_action("Agent A", f"❌ [PARSE] Extraction error: {e}", level="ERROR")
            return None

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
