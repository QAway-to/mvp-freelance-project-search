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
                log_agent_action("Agent A", "💡 [SELENIUM] Tip: Make sure Chrome is installed on the server")
                log_agent_action("Agent A", "💡 [SELENIUM] On Render, you may need to install Chrome in build command")
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
                log_agent_action("Agent A", f"⚠️ [SELENIUM] Proposal button text not found (proposal may already be sent)")
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
            log_agent_action("Agent A", f"⚠️ [SELENIUM] Proposal button text found but element not accessible, assuming available")
            return True
            
        except Exception as e:
            log_agent_action("Agent A", f"⚠️ [SELENIUM] Error checking proposal button: {str(e)[:100]}")
            # On error, assume button is available (to be safe)
            return True

    def _search_real_projects(self) -> List[Dict[str, Any]]:
        """Real search on Kwork with pagination, proposal button check, and semantic ranking"""
        log_agent_action("Agent A", "🌐 [SELENIUM] Real search mode: accessing Kwork")

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
        
        while page <= max_pages and len(all_projects) < max_relevant_projects:
            # Build search URL for current page
            search_url = f"{config.KWORK_PROJECTS_URL}?keyword={keywords_encoded}&page={page}&a=1"
            log_agent_action("Agent A", f"🌐 [SELENIUM] Navigating to page {page}: {search_url}")
            
            try:
                self.driver.get(search_url)
                log_agent_action("Agent A", f"✅ [SELENIUM] Page {page} loaded successfully")
            except Exception as e:
                log_agent_action("Agent A", f"❌ [SELENIUM] Error loading page {page}: {str(e)}")
                break

            # Wait for page to stabilize
            if page == 1:
                log_agent_action("Agent A", f"⏱️ [SELENIUM] Waiting for page {page} to stabilize...")
                delay = self.human_delay(2, 4)
                log_agent_action("Agent A", f"⏱️ [SELENIUM] Human delay: {delay:.2f}s")
                
                log_agent_action("Agent A", "👁️ [SELENIUM] Simulating human reading behavior...")
                self.simulate_reading()
                log_agent_action("Agent A", "✅ [SELENIUM] Reading simulation complete")
            else:
                # Shorter delay on subsequent pages
                delay = self.human_delay(1, 2)
                log_agent_action("Agent A", f"⏱️ [SELENIUM] Quick scan delay on page {page}: {delay:.2f}s")

            # Wait for projects to load
            try:
                log_agent_action("Agent A", f"🔍 [SELENIUM] Waiting for project elements on page {page}...")
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1 a[href*='/projects/']"))
                )
                log_agent_action("Agent A", f"✅ [SELENIUM] Project elements found on page {page}")
            except TimeoutException:
                log_agent_action("Agent A", f"⚠️ [SELENIUM] No projects found on page {page}, stopping pagination")
                break

            # Find all project elements on current page
            log_agent_action("Agent A", f"🔍 [SELENIUM] Searching for project links on page {page}...")
            project_elements = self.driver.find_elements(By.CSS_SELECTOR, "h1 a[href*='/projects/']")
            log_agent_action("Agent A", f"✅ [SELENIUM] Found {len(project_elements)} potential projects on page {page}")

            if len(project_elements) == 0:
                log_agent_action("Agent A", f"⚠️ [SELENIUM] No more projects on page {page}, stopping pagination")
                break

            # Collect project URLs and titles from current page
            page_projects = []
            filtered_count = 0
            log_agent_action("Agent A", f"📋 [SELENIUM] Collecting projects from page {page}...")
            
            for i, link_element in enumerate(project_elements):
                try:
                    title = link_element.text.strip()
                    url = link_element.get_attribute("href")
                    
                    # SOFT FILTERING - only skip obviously irrelevant projects
                    if not self._is_title_preliminary_relevant(title):
                        filtered_count += 1
                        log_agent_action("Agent A", f"🚫 [FILTER] Skipped irrelevant project: {title[:60]}...")
                        continue
                    
                    # Ensure URL has /view suffix
                    if url and '/projects/' in url:
                        if '?' in url:
                            url = url.split('?')[0]
                        if not url.endswith('/view'):
                            if url.endswith('/'):
                                url = url.rstrip('/') + '/view'
                            else:
                                url = url + '/view'
                    
                    # Extract project ID
                    project_id = ""
                    if '/' in url:
                        url_parts = url.split('/')
                        last_part = url_parts[-1].split('?')[0]
                        if last_part == 'view' and len(url_parts) >= 2:
                            project_id = url_parts[-2].split('?')[0]
                        else:
                            project_id = last_part.split('?')[0]
                    else:
                        project_id = f"page{page}_item{i}"
                    
                    page_projects.append({
                        "id": project_id,
                        "title": title,
                        "url": url,
                        "page": page,
                        "index_on_page": i + 1
                    })
                    log_agent_action("Agent A", f"✅ [FILTER] Accepted project from page {page}: {title[:60]}...")
                    
                except Exception as e:
                    log_agent_action("Agent A", f"⚠️ [SELENIUM] Error collecting project info: {str(e)[:100]}")
                    continue

            log_agent_action("Agent A", f"📊 [SELENIUM] Page {page}: Found {len(page_projects)} relevant projects (filtered {filtered_count})")
            
            # Process each project from current page
            for project_info in page_projects:
                if len(all_projects) >= max_relevant_projects:
                    log_agent_action("Agent A", f"📊 [SELENIUM] Reached max relevant projects limit ({max_relevant_projects}), stopping collection")
                    break
                    
                try:
                    project_id = project_info["id"]
                    title = project_info["title"]
                    url = project_info["url"]
                    page_num = project_info["page"]
                    
                    log_agent_action("Agent A", f"🔍 [SELENIUM] Processing project from page {page_num}: {title[:50]}...")
                    log_agent_action("Agent A", f"🔗 [SELENIUM] URL: {url}")

                    # Navigate to project page
                    log_agent_action("Agent A", f"🌐 [SELENIUM] Navigating to project page...")
                    try:
                        self.driver.get(url)
                        log_agent_action("Agent A", f"✅ [SELENIUM] Project page loaded")
                        
                        # Wait for page to load
                        delay = self.human_delay(2, 4)
                        log_agent_action("Agent A", f"⏱️ [SELENIUM] Waiting for page stabilization: {delay:.2f}s")
                    except Exception as e:
                        log_agent_action("Agent A", f"❌ [SELENIUM] Error navigating to project page: {str(e)[:200]}")
                        continue
                    
                    # CHECK: Is "Предложить услугу" button available?
                    try:
                        if not self._check_proposal_button_available():
                            log_agent_action("Agent A", f"⏭️ [SELENIUM] Skipping project (proposal button not available - proposal may already be sent)")
                            continue  # Skip this project - proposal already sent
                    except Exception as e:
                        log_agent_action("Agent A", f"⚠️ [SELENIUM] Error checking proposal button: {str(e)[:100]}")
                        # Assume button is available if we can't check
                    
                    log_agent_action("Agent A", f"✅ [SELENIUM] Proposal button available - project is eligible")
                    
                    try:
                        
                        # Get FULL description from project page
                        description = ""
                        log_agent_action("Agent A", f"📝 [SELENIUM] Extracting FULL description from project page...")
                        try:
                            # Try multiple selectors for full description
                            desc_selectors = [
                                ".wants-card__description-text",
                                ".task__description",
                                "[class*='description-text']",
                                "[class*='wants-card__text']",
                                ".project-description",
                                "[data-test-id='task-description']",
                                ".break-word"
                            ]
                            
                            for selector in desc_selectors:
                                try:
                                    desc_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                    if desc_elements:
                                        desc_texts = [elem.text.strip() for elem in desc_elements if elem.text.strip()]
                                        if desc_texts:
                                            description = '\n'.join(desc_texts)
                                            if len(description) > 100:
                                                break
                                except Exception:
                                    continue
                            
                            # Fallback: get all text from main content area
                            if not description or len(description) < 100:
                                try:
                                    main_content = self.driver.find_element(By.CSS_SELECTOR, "main, .content, .container, [class*='wants-card']")
                                    description = main_content.text.strip()
                                    if title in description:
                                        desc_start = description.find(title) + len(title)
                                        description = description[desc_start:].strip()
                                except Exception:
                                    pass
                            
                            log_agent_action("Agent A", f"✅ [SELENIUM] Full description extracted: {len(description)} chars")
                        except Exception as e:
                            log_agent_action("Agent A", f"⚠️ [SELENIUM] Error extracting full description: {str(e)}")

                        # Get budget from project page
                        budget = ""
                        log_agent_action("Agent A", f"💰 [SELENIUM] Extracting budget from project page...")
                        try:
                            budget_selectors = [
                                ".wants-card__header-price",
                                "[class*='price-text']",
                                "[class*='budget']",
                                "[class*='price']",
                                "[data-test-id='task-price']",
                                ".task__price",
                                ".project-price",
                            ]
                            for selector in budget_selectors:
                                try:
                                    budget_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                    for elem in budget_elements:
                                        budget_text = elem.text.strip()
                                        if budget_text and (re.search(r'\d', budget_text) or '₽' in budget_text or 'руб' in budget_text.lower()):
                                            budget = budget_text
                                            break
                                    if budget:
                                        break
                                except Exception:
                                    continue
                            
                            # If not found via selectors, try regex in page source
                            if not budget:
                                try:
                                    page_source = self.driver.page_source
                                    price_patterns = [
                                        r'(\d{1,3}(?:\s?\d{3})*)\s*[₽руб]',
                                        r'[₽руб]\s*(\d{1,3}(?:\s?\d{3})*)',
                                        r'цена[:\s]*(\d{1,3}(?:\s?\d{3})*)',
                                        r'бюджет[:\s]*(\d{1,3}(?:\s?\d{3})*)'
                                    ]
                                    for pattern in price_patterns:
                                        matches = re.findall(pattern, page_source, re.IGNORECASE)
                                        if matches:
                                            price_num = matches[0].replace(' ', '')
                                            budget = f"{price_num} ₽"
                                            break
                                except Exception as e:
                                    log_agent_action("Agent A", f"⚠️ [SELENIUM] Error in regex budget search: {str(e)[:100]}")
                            
                            if budget:
                                log_agent_action("Agent A", f"✅ [SELENIUM] Budget: {budget}")
                            else:
                                log_agent_action("Agent A", f"⚠️ [SELENIUM] Budget not found on project page")
                        except Exception as e:
                            log_agent_action("Agent A", f"⚠️ [SELENIUM] Error extracting budget: {str(e)[:100]}")

                        # Get proposals count from project page
                        proposals = 0
                        log_agent_action("Agent A", f"📊 [SELENIUM] Extracting proposals count from project page...")
                        try:
                            page_text = self.driver.page_source
                            proposals_patterns = [
                                r'(\d+)\s+предложен',
                                r'(\d+)\s+предложений',
                                r'(\d+)\s+отклик',
                                r'(\d+)\s+откликов',
                                r'откликов[:\s]+(\d+)',
                                r'предложений[:\s]+(\d+)'
                            ]
                            for pattern in proposals_patterns:
                                match = re.search(pattern, page_text, re.IGNORECASE)
                                if match:
                                    proposals = int(match.group(1))
                                    break
                            
                            # Try CSS selectors
                            if proposals == 0:
                                try:
                                    proposals_selectors = [
                                        "[class*='responses']",
                                        "[class*='proposals']",
                                        "[data-test-id='task-responses']"
                                    ]
                                    for selector in proposals_selectors:
                                        try:
                                            prop_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                                            prop_text = prop_element.text
                                            match = re.search(r'(\d+)', prop_text)
                                            if match:
                                                proposals = int(match.group(1))
                                                break
                                        except Exception:
                                            continue
                                except Exception:
                                    pass
                            
                            log_agent_action("Agent A", f"✅ [SELENIUM] Proposals: {proposals}")
                        except Exception as e:
                            log_agent_action("Agent A", f"⚠️ [SELENIUM] Error extracting proposals: {str(e)}")

                        # Get hired count from project page
                        hired = 0
                        log_agent_action("Agent A", f"👥 [SELENIUM] Extracting hired count from project page...")
                        try:
                            page_text = self.driver.page_source
                            hired_patterns = [
                                r'(\d+)\s+исполнител',
                                r'нанят[:\s]+(\d+)',
                                r'исполнитель.*нанят',
                                r'нанято[:\s]+(\d+)'
                            ]
                            for pattern in hired_patterns:
                                match = re.search(pattern, page_text, re.IGNORECASE)
                                if match:
                                    if match.lastindex:
                                        hired = int(match.group(1))
                                    else:
                                        hired = 1
                                    break
                            
                            # Check for hired badge/indicator
                            if hired == 0:
                                try:
                                    hired_indicators = [
                                        "[class*='executor']",
                                        "[class*='hired']",
                                        "[data-test-id='task-executor']"
                                    ]
                                    for selector in hired_indicators:
                                        try:
                                            hired_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                                            if hired_element:
                                                hired = 1
                                                break
                                        except Exception:
                                            continue
                                except Exception:
                                    pass
                            
                            log_agent_action("Agent A", f"✅ [SELENIUM] Hired: {hired}")
                        except Exception as e:
                            log_agent_action("Agent A", f"⚠️ [SELENIUM] Error extracting hired: {str(e)}")

                        # Create project data
                        project_data = {
                            "id": project_id,
                            "title": title,
                            "description": description,
                            "budget": budget,
                            "url": url,
                            "proposals": proposals,
                            "hired": hired,
                            "found_at": datetime.now().isoformat(),
                            "page": page_num
                        }

                        all_projects.append(project_data)
                        log_agent_action("Agent A", f"✅ [SELENIUM] Project added to collection ({len(all_projects)}/{max_relevant_projects}): {title[:50]}...")

                        # Human delay between projects
                        delay = self.human_delay(1, 3)
                        log_agent_action("Agent A", f"⏱️ [SELENIUM] Processing delay: {delay:.2f}s")
                        
                    except Exception as e:
                        log_agent_action("Agent A", f"❌ [SELENIUM] Error extracting project data: {str(e)[:200]}")
                        continue
                        
                except Exception as e:
                    log_agent_action("Agent A", f"❌ [SELENIUM] Error processing project: {str(e)[:200]}")
                    continue

            # Move to next page
            page += 1
            
            # Small delay before next page
            if page <= max_pages and len(all_projects) < max_relevant_projects:
                delay = self.human_delay(1, 2)
                log_agent_action("Agent A", f"⏱️ [SELENIUM] Delay before next page: {delay:.2f}s")

        log_agent_action("Agent A", f"✅ [SELENIUM] Collection complete: Found {len(all_projects)} projects with proposal button available")
        
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
