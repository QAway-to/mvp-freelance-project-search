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
                except:
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

    def _search_real_projects(self) -> List[Dict[str, Any]]:
        """Real search on Kwork"""
        log_agent_action("Agent A", "🌐 [SELENIUM] Real search mode: accessing Kwork")

        # Use first keyword for primary search (Kwork URL supports single query param)
        # We'll filter results by all keywords later
        primary_keyword = config.SEARCH_KEYWORD
        log_agent_action("Agent A", f"📋 [SELENIUM] Using primary keyword for search: '{primary_keyword}'")
        log_agent_action("Agent A", f"📋 [SELENIUM] All keywords for filtering: {', '.join(config.SEARCH_KEYWORDS_LIST)}")

        # Navigate to search URL (Kwork uses single query parameter)
        search_url = f"{config.KWORK_PROJECTS_URL}?query={primary_keyword}"
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

            # Find all project elements and collect URLs/titles first
            # This avoids stale element reference after navigation
            log_agent_action("Agent A", "🔍 [SELENIUM] Searching for project links...")
            project_elements = self.driver.find_elements(By.CSS_SELECTOR, "h1 a[href*='/projects/']")
            log_agent_action("Agent A", f"✅ [SELENIUM] Found {len(project_elements)} potential projects")

            # First, collect all URLs and titles from the list page (before navigation)
            project_info_list = []
            filtered_count = 0
            log_agent_action("Agent A", "📋 [SELENIUM] Collecting project URLs and titles from list page...")
            log_agent_action("Agent A", f"🔍 [FILTER] Applying soft filter (only removes obviously irrelevant: лифт, дизайн, текст, etc.)")
            
            for i, link_element in enumerate(project_elements):
                try:
                    title = link_element.text.strip()
                    url = link_element.get_attribute("href")
                    
                    # PRELIMINARY TITLE FILTERING - skip obviously irrelevant projects
                    if not self._is_title_preliminary_relevant(title):
                        filtered_count += 1
                        log_agent_action("Agent A", f"🚫 [FILTER] Skipped irrelevant project {i+1}: {title[:60]}...")
                        continue  # Skip this project
                    
                    # Ensure URL has /view suffix for correct endpoint
                    if url and '/projects/' in url:
                        # Remove query parameters if any
                        if '?' in url:
                            url = url.split('?')[0]
                        # Ensure /view suffix
                        if not url.endswith('/view'):
                            if url.endswith('/'):
                                url = url.rstrip('/') + '/view'
                            else:
                                url = url + '/view'
                    
                    # Extract project ID from URL
                    project_id = ""
                    if '/' in url:
                        url_parts = url.split('/')
                        last_part = url_parts[-1].split('?')[0]
                        if last_part == 'view' and len(url_parts) >= 2:
                            project_id = url_parts[-2].split('?')[0]
                        else:
                            project_id = last_part.split('?')[0]
                    else:
                        project_id = str(i)
                    
                    project_info_list.append({
                        "id": project_id,
                        "title": title,
                        "url": url,
                        "index": i + 1
                    })
                    log_agent_action("Agent A", f"✅ [FILTER] Accepted relevant project {len(project_info_list)+1}: {title[:60]}...")
                    log_agent_action("Agent A", f"📋 [SELENIUM] Collected project {len(project_info_list)+1}: {title[:50]}... -> {url}")
                    
                    # Stop if we have enough projects
                    if len(project_info_list) >= config.MAX_PROJECTS_PER_SESSION:
                        log_agent_action("Agent A", f"📊 [SELENIUM] Reached max projects limit ({config.MAX_PROJECTS_PER_SESSION}), stopping collection")
                        break
                        
                except Exception as e:
                    log_agent_action("Agent A", f"⚠️ [SELENIUM] Error collecting project {i+1} info: {str(e)}")
                    continue

            log_agent_action("Agent A", f"✅ [SELENIUM] Collected {len(project_info_list)} projects to process")
            if filtered_count > 0:
                log_agent_action("Agent A", f"🚫 [FILTER] Filtered out {filtered_count} obviously irrelevant projects")
                log_agent_action("Agent A", f"📊 [FILTER] Filter efficiency: {len(project_info_list)}/{len(project_info_list) + filtered_count} projects passed soft filter")
            else:
                log_agent_action("Agent A", f"📊 [FILTER] All {len(project_info_list)} projects passed soft filter (no obvious irrelevant projects)")

            # Now process each project by navigating directly to its URL
            log_agent_action("Agent A", f"📊 [SELENIUM] Processing {len(project_info_list)} projects...")
            for project_info in project_info_list:
                try:
                    i = project_info["index"]
                    project_id = project_info["id"]
                    title = project_info["title"]
                    url = project_info["url"]
                    
                    log_agent_action("Agent A", f"🔍 [SELENIUM] Parsing project {i}/{len(project_info_list)}...")
                    log_agent_action("Agent A", f"📄 [SELENIUM] Title: {title[:50]}...")
                    log_agent_action("Agent A", f"🔗 [SELENIUM] URL: {url}")

                    # Navigate to project page to get FULL description and details
                    log_agent_action("Agent A", f"🌐 [SELENIUM] Navigating to project page for full details...")
                    try:
                        self.driver.get(url)
                        log_agent_action("Agent A", f"✅ [SELENIUM] Project page loaded")
                        
                        # Wait for page to load
                        delay = self.human_delay(2, 4)
                        log_agent_action("Agent A", f"⏱️ [SELENIUM] Waiting for page stabilization: {delay:.2f}s")
                        
                        # Get FULL description from project page
                        description = ""
                        log_agent_action("Agent A", f"📝 [SELENIUM] Extracting FULL description from project page...")
                        try:
                            # Try multiple selectors for full description on project page
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
                                        # Get text from all matching elements (in case description is split)
                                        desc_texts = [elem.text.strip() for elem in desc_elements if elem.text.strip()]
                                        if desc_texts:
                                            description = '\n'.join(desc_texts)
                                            if len(description) > 100:  # Valid full description
                                                break
                                except:
                                    continue
                            
                            # Fallback: get all text from main content area
                            if not description or len(description) < 100:
                                try:
                                    main_content = self.driver.find_element(By.CSS_SELECTOR, "main, .content, .container, [class*='wants-card']")
                                    description = main_content.text.strip()
                                    # Remove title and metadata
                                    if title in description:
                                        desc_start = description.find(title) + len(title)
                                        description = description[desc_start:].strip()
                                except:
                                    pass
                            
                            log_agent_action("Agent A", f"✅ [SELENIUM] Full description extracted: {len(description)} chars")
                        except Exception as e:
                            log_agent_action("Agent A", f"⚠️ [SELENIUM] Error extracting full description: {str(e)}")

                        # Get budget from project page
                        budget = ""
                        log_agent_action("Agent A", f"💰 [SELENIUM] Extracting budget from project page...")
                        try:
                            # First try CSS selectors
                            budget_selectors = [
                                ".wants-card__header-price",
                                "[class*='price-text']",
                                "[class*='budget']",
                                "[class*='price']",
                                "[data-test-id='task-price']",
                                ".task__price",
                                ".project-price",
                                "[class*='wants-card'][class*='price']"
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
                                except:
                                    continue
                            
                            # If not found via selectors, try regex in page source
                            if not budget:
                                try:
                                    page_source = self.driver.page_source
                                    # Look for price patterns: "5000 ₽", "10 000 руб", etc.
                                    price_patterns = [
                                        r'(\d{1,3}(?:\s?\d{3})*)\s*[₽руб]',
                                        r'[₽руб]\s*(\d{1,3}(?:\s?\d{3})*)',
                                        r'цена[:\s]*(\d{1,3}(?:\s?\d{3})*)',
                                        r'бюджет[:\s]*(\d{1,3}(?:\s?\d{3})*)'
                                    ]
                                    for pattern in price_patterns:
                                        matches = re.findall(pattern, page_source, re.IGNORECASE)
                                        if matches:
                                            # Get first match and format it
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
                                r'откликов[:\s]+(\d+)'
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
                                        except:
                                            continue
                                except:
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
                                r'исполнитель.*нанят'
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
                                        except:
                                            continue
                                except:
                                    pass
                            
                            log_agent_action("Agent A", f"✅ [SELENIUM] Hired: {hired}")
                        except Exception as e:
                            log_agent_action("Agent A", f"⚠️ [SELENIUM] Error extracting hired: {str(e)}")

                        # No need to go back - we'll navigate directly to next project URL
                        # This avoids stale element issues
                        
                    except Exception as e:
                        log_agent_action("Agent A", f"❌ [SELENIUM] Error navigating to project page: {str(e)}")
                        # If we can't get to project page, skip this project
                        continue

                    project_data = {
                        "id": project_id,
                        "title": title,
                        "description": description,  # FULL description from project page
                        "budget": budget,
                        "url": url,  # Real URL with /view
                        "proposals": proposals,
                        "hired": hired,
                        "found_at": datetime.now().isoformat()
                    }

                    projects.append(project_data)
                    log_agent_action("Agent A", f"✅ [SELENIUM] Project {i}/{len(project_info_list)} parsed successfully with full description ({len(description)} chars)")

                    # Human delay between projects (before navigating to next)
                    delay = self.human_delay(1, 3)
                    log_agent_action("Agent A", f"⏱️ [SELENIUM] Processing delay: {delay:.2f}s")

                except Exception as e:
                    log_agent_action("Agent A", f"❌ [SELENIUM] Error parsing project {project_info.get('index', '?')}: {str(e)[:200]}")
                    # Continue to next project - don't break the loop
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
