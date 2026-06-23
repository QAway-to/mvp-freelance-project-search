import asyncio
import random
import time
import re
import os
from collections import deque
from datetime import datetime
from typing import List, Dict, Any
import aiohttp
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from urllib.parse import quote_plus

from agents.search_params import SearchParams
from browser import get_driver

from config import config
from utils.logger import logger, log_agent_action
from evaluation.evaluator import ProjectEvaluator

# Inline expand-link text Kwork renders at the end of a clamped description.
# .get_attribute("textContent") flattens these anchors into the text, so strip them.
_EXPAND_MARKERS = (
    "Показать полностью", "Показать ещё", "Показать еще",
    "Читать полностью", "Развернуть", "Подробнее",
)


def _clean_description(text: str) -> str:
    """Strip Kwork's inline expand-link text and a trailing ellipsis from a description."""
    if not text:
        return ""
    cleaned = text
    for marker in _EXPAND_MARKERS:
        idx = cleaned.find(marker)
        if idx != -1:
            cleaned = cleaned[:idx]
    cleaned = cleaned.strip()
    for ellipsis in ("…", "..."):
        if cleaned.endswith(ellipsis):
            cleaned = cleaned[:-len(ellipsis)].strip()
    return cleaned


class AgentA:
    def __init__(self):
        self.driver = None
        self.logged_in = False
        self._evaluator = None  # lazy: only created when parse_single_url is called
        self.status = "stopped"
        self.last_run_time = None
        # Bounded history: keep only the most recent N suitable projects so the list
        # cannot grow unbounded across searches (memory-leak guard on 512MB Render).
        self.found_projects: deque = deque(maxlen=200)
        self.running = False
        self.current_session_start = None
        self.current_session_end = None
        self.session_steps: List[Dict[str, Any]] = []

    def setup_driver(self):
        """Acquire the shared Chrome instance."""
        log_agent_action("Agent A", "🔧 [SELENIUM] Acquiring shared browser...")
        if config.MODE == "demo":
            log_agent_action("Agent A", "🔧 [SELENIUM] Demo mode: skipping browser setup")
            self.driver = None
            return
        try:
            self.driver = get_driver()
            log_agent_action("Agent A", "✅ [SELENIUM] Shared browser acquired")
        except Exception as e:
            log_agent_action("Agent A", f"❌ [SELENIUM] Driver setup failed: {str(e)[:300]}", level="ERROR")
            raise

    def _inject_cookies_from_env(self) -> bool:
        """Load cookies from KWORK_COOKIES env var and inject into Selenium."""
        if not config.KWORK_COOKIES:
            return False
        try:
            import json
            import re
            raw = re.sub(r'[\x00-\x1f\x7f]', '', config.KWORK_COOKIES)
            cookies = json.loads(raw)
            self.driver.get(config.KWORK_BASE_URL)
            self.human_delay(1, 2)
            injected = 0
            for c in cookies:
                try:
                    # Selenium expects specific keys only
                    self.driver.add_cookie({
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c.get("domain", ".kwork.ru"),
                        "path": c.get("path", "/"),
                    })
                    injected += 1
                except Exception:
                    pass
            log_agent_action("Agent A", f"🍪 [AUTH] Injected {injected}/{len(cookies)} cookies from KWORK_COOKIES env")
            self.logged_in = True
            return True
        except Exception as e:
            log_agent_action("Agent A", f"❌ [AUTH] Failed to load KWORK_COOKIES: {e}", level="ERROR")
            return False

    def login(self):
        """Login via Selenium on kwork.ru/login dedicated page."""
        if self.logged_in:
            return True

        if not self.driver:
            self.setup_driver()

        # Try cookie-based auth first (no captcha)
        if config.KWORK_COOKIES:
            log_agent_action("Agent A", "🍪 [AUTH] KWORK_COOKIES found — using cookie auth instead of login form")
            return self._inject_cookies_from_env()

        if not config.KWORK_EMAIL or not config.KWORK_PASSWORD:
            log_agent_action("Agent A", "⚠️ [AUTH] Credentials missing, skipping login", level="WARNING")
            return False

        log_agent_action("Agent A", f"🔐 [AUTH] Logging in as {config.KWORK_EMAIL} via Selenium /login page...")

        try:
            self.driver.get(config.KWORK_LOGIN_URL)
            self.human_delay(2, 3)

            actual_url = self.driver.current_url
            log_agent_action("Agent A", f"🔐 [AUTH] Login page URL: {actual_url}")

            # Log what's on the page
            page_title = self.driver.title
            log_agent_action("Agent A", f"🔐 [AUTH] Page title: {page_title}")

            # Find login/email field
            login_field = None
            for sel in ['input[placeholder="Электронная почта или логин"]', 'input.input-style',
                        'input[name="username"]', 'input[name="login"]', 'input[name="email"]']:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    login_field = els[0]
                    log_agent_action("Agent A", f"🔐 [AUTH] Found login field: {sel}")
                    break

            # Find password field
            pass_field = None
            for sel in ['input[name="password"]', 'input[type="password"]']:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    pass_field = els[0]
                    log_agent_action("Agent A", f"🔐 [AUTH] Found password field: {sel}")
                    break

            if not login_field or not pass_field:
                # Log all inputs for diagnostics
                all_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input")
                log_agent_action("Agent A", f"🔐 [AUTH] All inputs on page: {[(i.get_attribute('name'), i.get_attribute('type')) for i in all_inputs]}", level="ERROR")
                log_agent_action("Agent A", "❌ [AUTH] Login/password fields not found on /login page", level="ERROR")
                return False

            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.common.keys import Keys

            def fill_field(field, value, label):
                """Scroll into view, click, type — JS fallback if not interactable."""
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", field)
                    self.human_delay(0.2, 0.4)
                    ActionChains(self.driver).move_to_element(field).click().send_keys(value).perform()
                    log_agent_action("Agent A", f"🔐 [AUTH] Filled {label} via ActionChains")
                except Exception as fe:
                    log_agent_action("Agent A", f"🔐 [AUTH] ActionChains failed for {label}: {fe} — using JS", level="WARNING")
                    self.driver.execute_script(
                        "var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
                        "s.call(arguments[0],arguments[1]);"
                        "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
                        "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
                        field, value
                    )
                    log_agent_action("Agent A", f"🔐 [AUTH] Filled {label} via JS native setter")

            fill_field(login_field, config.KWORK_EMAIL, "login")
            self.human_delay(0.5, 1.0)
            fill_field(pass_field, config.KWORK_PASSWORD, "password")
            self.human_delay(0.5, 1.0)

            # Log all buttons for diagnostics
            all_btns = self.driver.find_elements(By.CSS_SELECTOR, "button, input[type='submit']")
            log_agent_action("Agent A", f"🔐 [AUTH] Buttons on page: {[(b.get_attribute('type'), b.get_attribute('class'), b.text[:30]) for b in all_btns]}")

            # Submit — try multiple selectors, fallback to Enter key
            submitted = False
            for sel in ['button.auth-form__button', 'button.kw-button--green',
                        'button[type="submit"]', 'button.js-login-submit', 'button.signin__btn',
                        '[class*="auth-form"] button', 'form button', 'input[type="submit"]']:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    els[0].click()
                    submitted = True
                    log_agent_action("Agent A", f"🔐 [AUTH] Clicked submit: {sel}")
                    break
            if not submitted:
                # Press Enter on password field — most natural and reliable
                pass_field.send_keys(Keys.RETURN)
                log_agent_action("Agent A", "🔐 [AUTH] Submitted via Enter key on password field")

            self.human_delay(3, 5)

            final_url = self.driver.current_url
            log_agent_action("Agent A", f"🔐 [AUTH] Post-login URL: {final_url}")

            if "login" not in final_url:
                log_agent_action("Agent A", "✅ [AUTH] Login successful — redirected away from /login")
                self.logged_in = True
                return True
            else:
                log_agent_action("Agent A", "❌ [AUTH] Still on /login — check credentials or captcha", level="ERROR")
                # Log page source snippet for diagnostics
                src = self.driver.page_source[:500].replace("\n", " ")
                log_agent_action("Agent A", f"🔐 [AUTH] Page snippet: {src}")
                return False

        except Exception as e:
            log_agent_action("Agent A", f"❌ [AUTH] Login error: {e}", level="ERROR")
            return False

    def parse_urgency(self, text: str) -> float:
        """Parse a 'time left' string to hours. Handles 'Осталось: 2 ч. 5 мин.',
        bare '3 ч. 57 мин.', '1 д. 4 ч.', '45 мин.'. Returns 999.0 only when no
        time tokens are present (treated as 'no deadline'). Does NOT require the
        word 'Осталось' — Kwork renders the timer in several formats."""
        if not text:
            return 999.0

        try:
            d_match = re.search(r'(\d+)\s*д', text)
            h_match = re.search(r'(\d+)\s*ч', text)
            m_match = re.search(r'(\d+)\s*мин', text)

            # No numeric time tokens at all → unknown deadline.
            # "< 1 ч." / "меньше часа" style strings still mean very urgent.
            if not (d_match or h_match or m_match):
                if 'ч' in text or 'мин' in text:
                    return 0.5
                return 999.0

            days = int(d_match.group(1)) if d_match else 0
            hours = int(h_match.group(1)) if h_match else 0
            mins = int(m_match.group(1)) if m_match else 0
            return (days * 24) + hours + (mins / 60)
        except Exception as e:
            log_agent_action("Agent A", f"⚠️ Error parsing urgency '{text}': {e}", level="DEBUG")
            return 999.0

    def human_delay(self, min_sec: float = None, max_sec: float = None):
        """Human-like delay between actions"""
        if min_sec is None:
            min_sec = config.DELAY_BETWEEN_ACTIONS_MIN
        if max_sec is None:
            max_sec = config.DELAY_BETWEEN_ACTIONS_MAX

        delay = random.uniform(min_sec, max_sec)
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

    def search_projects(self, params: SearchParams) -> List[Dict[str, Any]]:
        """Search for projects with keywords"""
        keywords_str = ", ".join(params.keywords_list)
        log_agent_action("Agent A", f"Searching projects with keywords: {keywords_str}")

        if config.MODE == "demo":
            return self._generate_demo_projects()
        else:
            return self._search_real_projects(params)

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

    def _search_real_projects(self, params: SearchParams) -> List[Dict[str, Any]]:
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

        keywords_str = ','.join(params.keywords_list)
        keywords_encoded = quote_plus(keywords_str) if keywords_str else ""
        log_agent_action("Agent A", f"📋 [SELENIUM] Search keywords: {keywords_str or '(none — filter only)'}")
        favorites_mode = not keywords_encoded
        log_agent_action("Agent A", f"📋 [SELENIUM] Mode: {'favorites' if favorites_mode else 'keyword'} | Target: Find up to 10 relevant projects")

        # Search parameters
        max_pages = 3
        max_relevant_projects = 300  # effectively unlimited
        
        all_projects = []  # All projects found (with full details)
        page = 1
        scraped_listing_pages = 0
        reverse_page_set = False  # guard: reverse-pagination redirect fires only once

        while scraped_listing_pages < max_pages and len(all_projects) < max_relevant_projects:
            # Build search URL for current page
            # Inject budget filters if they exist
            budget_params = "&".join([f"prices-filters[]={f}" for f in params.budget_filters])
            if keywords_encoded:
                # plain HTML keyword search — public, no auth needed
                search_url = f"{config.KWORK_PROJECTS_URL}?keyword={keywords_encoded}&page={page}"
            else:
                # personal favourites — AJAX mode (a=1), requires auth
                # kworks-filters[]=0,1 = task types; prices-filters[]=3,4 = 10k-30k and 30k+
                search_url = (
                    f"{config.KWORK_PROJECTS_URL}?type=favourite&a=1"
                    f"&kworks-filters[]=0&kworks-filters[]=1"
                    f"&prices-filters[]=3&prices-filters[]=4"
                    f"&page={page}"
                )
            if budget_params:
                search_url += f"&{budget_params}"
                
            log_agent_action("Agent A", f"🌐 [SELENIUM] Navigating to page {page}: {search_url}")
            
            try:
                self.driver.get(search_url)
                log_agent_action("Agent A", f"✅ [SELENIUM] Page {page} loaded successfully")
                
                # Reverse pagination: find last page, jump to it (both keyword and favourites)
                if page == 1 and not reverse_page_set:
                    try:
                        pagination_items = self.driver.find_elements(By.CSS_SELECTOR, ".pagination__item")
                        if pagination_items:
                            pages = [int(item.text) for item in pagination_items if item.text.isdigit()]
                            if pages:
                                max_p = max(pages)
                                log_agent_action("Agent A", f"📑 [SELENIUM] Found {max_p} total pages. Jumping to last page.")
                                page = max_p
                                reverse_page_set = True
                                if keywords_encoded:
                                    last_page_url = f"{config.KWORK_PROJECTS_URL}?keyword={keywords_encoded}&page={max_p}"
                                else:
                                    last_page_url = (
                                        f"{config.KWORK_PROJECTS_URL}?type=favourite&a=1"
                                        f"&kworks-filters[]=0&kworks-filters[]=1"
                                        f"&prices-filters[]=3&prices-filters[]=4"
                                        f"&page={max_p}"
                                    )
                                if budget_params:
                                    last_page_url += f"&{budget_params}"
                                self.driver.get(last_page_url)
                                log_agent_action("Agent A", f"🔄 [SELENIUM] Jumped to last page {max_p}")
                    except Exception as pg_e:
                        log_agent_action("Agent A", f"⚠️ Error finding max page: {pg_e}", level="DEBUG")

            except Exception as e:
                log_agent_action("Agent A", f"❌ [SELENIUM] Error loading page {page}: {str(e)}", level="ERROR")
                break

            # ... [Rest of stability and reading simulation remains similar] ...

            # Diagnostic: confirm URL and page state after navigation
            actual_url = self.driver.current_url
            log_agent_action("Agent A", f"🔗 [SELENIUM] Actual URL after nav: {actual_url}")
            if "login" in actual_url or "auth" in actual_url or "not_access" in actual_url:
                log_agent_action("Agent A", f"❌ [SELENIUM] Auth redirect detected ({actual_url}) — session invalid", level="ERROR")
                break

            # Find all project elements on current page
            log_agent_action("Agent A", f"🔍 [SELENIUM] Searching for projects on page {page}...")
            project_cards = self.driver.find_elements(By.CSS_SELECTOR, ".want-card")
            log_agent_action("Agent A", f"✅ [SELENIUM] Found {len(project_cards)} projects on page {page}")
            if project_cards:
                log_agent_action("Agent A", f"🃏 [SELENIUM] First card text snippet: {project_cards[0].text[:150].replace(chr(10), ' ')}")

            if len(project_cards) == 0:
                log_agent_action("Agent A", f"⚠️ [SELENIUM] No projects on page {page}, stopping search")
                break

            # Collect all data from listing cards — no detail page navigation needed
            page_projects = []
            _skipped_urgency = 0
            _skipped_err = 0
            proposals_re = re.compile(
                r'(?:(\d+)\s*(?:предложен\w*|отклик\w*|заяв\w*|ставо?к?|оффер\w*)'
                r'|(?:предложен\w*|отклик\w*|заяв\w*)\s*[:\-]?\s*(\d+))',
                re.IGNORECASE
            )
            budget_re = re.compile(r'(от\s+[\d\s]+|до\s+[\d\s]+|[\d\s]{3,})\s*₽', re.IGNORECASE)

            for card in project_cards:
                try:
                    # Urgency check — resilient: if selector not found, treat as no deadline
                    urgency_text = ""
                    urgency_hours = 999.0
                    for _u_sel in [
                        ".want-card__informers-row span.mr8",
                        ".want-card__informers-row span",
                        "[class*='informers'] span",
                        "[class*='deadline']",
                        "[class*='urgency']",
                    ]:
                        _u_els = card.find_elements(By.CSS_SELECTOR, _u_sel)
                        for _u_el in _u_els:
                            _t = _u_el.text.strip()
                            if "Осталось" in _t or "ч." in _t or "мин." in _t:
                                urgency_text = _t
                                urgency_hours = self.parse_urgency(_t)
                                break
                        if urgency_text:
                            break

                    if urgency_hours > params.max_urgency_hours:
                        _skipped_urgency += 1
                        continue

                    # Title and link — try multiple selectors
                    title = None
                    url = None
                    for _t_sel in [
                        "h1 a[href*='/projects/']",
                        "h2 a[href*='/projects/']",
                        "h3 a[href*='/projects/']",
                        "[class*='title'] a[href*='/projects/']",
                        "[class*='name'] a[href*='/projects/']",
                        "a[href*='/projects/']",
                    ]:
                        try:
                            _el = card.find_element(By.CSS_SELECTOR, _t_sel)
                            _t = _el.text.strip()
                            if _t:
                                title = _t
                                url = _el.get_attribute("href")
                                break
                        except Exception:
                            continue

                    if not title or not url:
                        _skipped_err += 1
                        continue

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

                    # Description from card — read textContent (captures the full text even
                    # when Kwork clamps it client-side; .text only returns visible chars),
                    # fall back to visible .text, then strip the inline "Показать полностью".
                    description = ""
                    for sel in [".wants-card__description-text", "[class*='description']"]:
                        try:
                            el = card.find_element(By.CSS_SELECTOR, sel)
                            raw = (el.get_attribute("textContent") or "").strip() or el.text.strip()
                            cleaned = _clean_description(raw)
                            if cleaned and len(cleaned) > 20:
                                description = cleaned
                                break
                        except Exception:
                            pass

                    # Proposals: only look at informers-row spans that are NOT the urgency span
                    proposals = None
                    try:
                        informer_spans = card.find_elements(By.CSS_SELECTOR, ".want-card__informers-row span")
                        for span in informer_spans:
                            t = span.text.strip()
                            if not t or t == urgency_text:
                                continue
                            if any(kw in t.lower() for kw in ('предложен', 'отклик', 'заяв', 'оффер', 'ставк')):
                                m = re.search(r'\d+', t)
                                if m:
                                    proposals = int(m.group(0))
                                    break
                    except Exception:
                        pass
                    if proposals is None:
                        pm = proposals_re.search(card_text)
                        if pm:
                            proposals = int(pm.group(1) if pm.group(1) is not None else pm.group(2))

                    # Hired count (client reputation): "Нанял X" in card text
                    hired = None
                    hm = re.search(r'[Нн]анял[:\s]*(\d+)|(\d+)\s+[Нн]аним', card_text)
                    if hm:
                        hired = int(hm.group(1) if hm.group(1) is not None else hm.group(2))

                    log_agent_action("Agent A", f"📋 [LISTING] {title[:45]} | urgency={urgency_hours}h | budget={budget} | proposals={proposals} | hired={hired}")

                    page_projects.append({
                        "id": url.split('/')[-2] if '/' in url else "unknown",
                        "title": title,
                        "url": url,
                        "urgency": urgency_text,
                        "urgency_hours": urgency_hours,
                        "budget": budget,
                        "description": description,
                        "proposals": proposals,
                        "hired": hired,
                        "page": page,
                        "found_at": datetime.now().isoformat(),
                    })

                except Exception:
                    _skipped_err += 1
                    continue

            all_projects.extend(page_projects[:max_relevant_projects - len(all_projects)])

            scraped_listing_pages += 1
            log_agent_action("Agent A", f"📄 [LISTING] Page scraped: {len(page_projects)} added | urgency_filtered={_skipped_urgency} | other_err={_skipped_err} | total={len(all_projects)}")

            # Reverse pagination for both modes: last → last-1 → last-2
            if page > 1:
                page -= 1
            else:
                    break

        log_agent_action("Agent A", f"✅ [LISTING] Collection complete: {len(all_projects)} projects")

        # Free Chrome memory — cookies will be re-injected on next search
        from browser import quit_driver
        quit_driver()
        self.driver = None
        self.logged_in = False

        # Deduplicate by URL (keep first occurrence — avoids nested .want-card duplicates)
        seen_urls: set = set()
        unique: list = []
        for p in all_projects:
            url = p.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique.append(p)
        if len(unique) < len(all_projects):
            log_agent_action("Agent A", f"🔁 [LISTING] Removed {len(all_projects) - len(unique)} duplicates, {len(unique)} unique projects")
        all_projects = unique

        # Semantic scoring disabled — all found projects pass through
        if all_projects:
            for p in all_projects:
                p.setdefault("evaluation", {"score": 1.0, "reasons": [], "suitable": True})
            log_agent_action("Agent A", f"📋 Returning {len(all_projects)} projects")
            return all_projects

        log_agent_action("Agent A", "⚠️ [SELENIUM] No projects found")
        return []

    async def notify_suitable_projects(self, projects: List[Dict[str, Any]]) -> int:
        """Send suitable projects to Telegram for КП confirmation."""
        from telegram_bot import telegram_bot
        suitable = [p for p in projects if p.get("evaluation", {}).get("suitable", False)]
        if not suitable:
            return 0
        try:
            await telegram_bot.send_projects_for_confirmation(suitable)
            log_agent_action("Agent A", f"📱 [TELEGRAM] Sent {len(suitable)} projects for КП confirmation")
            return len(suitable)
        except Exception as e:
            log_agent_action("Agent A", f"📱 [TELEGRAM] Failed to send: {e}", level="ERROR")
            return 0

    async def evaluate_and_notify(self, projects: List[Dict[str, Any]]):
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

                    # Send to n8n workflow (Agent B)
                    log_agent_action("Agent A", f"🔗 [N8N] Sending project {i+1} to n8n workflow...")
                    asyncio.create_task(self.send_to_n8n(project))
                else:
                    log_agent_action("Agent A", f"❌ [EVALUATION] Project REJECTED: {project['title'][:50]}... (score: {score:.2f} < {config.EVALUATION_THRESHOLD})")

            except Exception as e:
                log_agent_action("Agent A", f"❌ [EVALUATION] Error processing project {i+1}: {str(e)}")

        self.found_projects.extend(suitable_projects)

        if suitable_projects:
            notified = await self.notify_suitable_projects(suitable_projects)
            log_agent_action("Agent A", f"📱 [TELEGRAM] Notified {notified}/{len(suitable_projects)} suitable projects")

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

    async def run_session(self, budget_filters: tuple[int, ...] = ()):
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
            session_params = SearchParams(
                keywords_list=tuple(config.SEARCH_KEYWORDS_LIST),
                max_urgency_hours=config.MAX_URGENCY_HOURS,
                budget_filters=budget_filters,
            )
            projects = self.search_projects(session_params)
            step_duration = (datetime.now() - step_start).total_seconds()
            log_agent_action("Agent A", f"✅ [SESSION] Step 1/2 completed: Found {len(projects)} relevant projects in {step_duration:.2f}s")

            if projects:
                # Step 2: Send notifications for suitable projects
                step_start = datetime.now()
                log_agent_action("Agent A", f"📊 [SESSION] Step 2/2: Sending notifications for {len(projects)} projects...")
                await self.evaluate_and_notify(projects)
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

            if self._evaluator is None:
                self._evaluator = ProjectEvaluator()
            score, reasons = self._evaluator.evaluate_project(project)
            project["evaluation"] = {
                "score": score,
                "reasons": reasons,
                "suitable": score >= config.EVALUATION_THRESHOLD,
            }
            return project

        except Exception as e:
            log_agent_action("Agent A", f"❌ [PARSE] Extraction error: {e}", level="ERROR")
            return None

    def submit_response(self, url: str, cp_text: str) -> bool:
        """Submit a response (отклик) on a Kwork project page via Selenium."""
        if not self.driver:
            self.setup_driver()
        if not self.logged_in:
            self.login()

        log_agent_action("Agent A", f"📨 [RESPOND] Navigating to {url}")
        try:
            self.driver.get(url)
            self.human_delay(2, 4)
        except Exception as e:
            log_agent_action("Agent A", f"❌ [RESPOND] Failed to load page: {e}", level="ERROR")
            return False

        try:
            # Click "Откликнуться" button
            respond_btn = None
            for sel in [
                "button.want-card__respond-btn",
                "button[class*='respond']",
                "a[class*='respond']",
                ".want-card__footer button",
            ]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    respond_btn = els[0]
                    break

            if not respond_btn:
                # Try by text content
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    if "откликнуться" in btn.text.lower() or "отклик" in btn.text.lower():
                        respond_btn = btn
                        break

            if not respond_btn:
                log_agent_action("Agent A", "❌ [RESPOND] Could not find respond button", level="ERROR")
                return False

            self.driver.execute_script("arguments[0].click();", respond_btn)
            self.human_delay(1, 2)

            # Find textarea and fill CP text
            textarea = None
            for sel in ["textarea[name='description']", "textarea[class*='respond']", "textarea"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    textarea = els[0]
                    break

            if not textarea:
                log_agent_action("Agent A", "❌ [RESPOND] Could not find textarea", level="ERROR")
                return False

            textarea.clear()
            self.human_delay(0.5, 1)
            textarea.send_keys(cp_text)
            self.human_delay(1, 2)

            # Click submit
            submit_btn = None
            for sel in [
                "button[type='submit']",
                "button.js-respond-form-submit",
                "button[class*='submit']",
            ]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    submit_btn = els[0]
                    break

            if not submit_btn:
                log_agent_action("Agent A", "❌ [RESPOND] Could not find submit button", level="ERROR")
                return False

            self.driver.execute_script("arguments[0].click();", submit_btn)
            self.human_delay(2, 3)

            log_agent_action("Agent A", f"✅ [RESPOND] Response submitted to {url}")
            return True

        except Exception as e:
            log_agent_action("Agent A", f"❌ [RESPOND] Error submitting response: {e}", level="ERROR")
            return False

    async def stop(self):
        """Stop the agent (shared browser is managed by browser.py)."""
        log_agent_action("Agent A", "Stopping agent")
        self.running = False
        self.status = "stopped"
        self.driver = None


agent_a_instance = None  # set by main.py after instantiation
