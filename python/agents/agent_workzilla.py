import re
import time
import random
import os
import json
import asyncio
from typing import List, Dict, Any

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from config import config
from utils.logger import log_agent_action

BASE_URL = "https://client.work-zilla.com"
ORDERS_URL = f"{BASE_URL}/freelancer"


class AgentWorkzilla:
    def __init__(self):
        self.driver = None
        self.logged_in = False
        self.status = "stopped"

    def _human_delay(self, lo: float = 1.0, hi: float = 3.0):
        time.sleep(random.uniform(lo, hi))

    def setup_driver(self):
        log_agent_action("Workzilla", "🔧 [SELENIUM] Starting browser...")
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--mute-audio")

        chrome_bin = os.getenv("CHROME_BIN") or os.getenv("GOOGLE_CHROME_BIN")
        if not chrome_bin:
            for path in ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/usr/bin/chromium"]:
                if os.path.exists(path):
                    chrome_bin = path
                    break

        self.driver = uc.Chrome(
            options=options,
            browser_executable_path=chrome_bin,
            headless=True,
            use_subprocess=False,
        )
        self.driver.set_page_load_timeout(30)
        log_agent_action("Workzilla", "✅ [SELENIUM] Browser ready")

    def _fetch_gdrive_file(self, file_id: str) -> str:
        """Download plain text file from Google Drive (must be shared publicly)."""
        import urllib.request
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read().decode("utf-8")

    def _extract_magic_link(self, text: str) -> str | None:
        """Extract Workzilla magic login link from email text."""
        m = re.search(r'https://client\.work-zilla\.com/account/link-login\?[^\s>\]]+', text)
        return m.group(0) if m else None

    def _is_fresh(self, text: str, max_age_minutes: int = 25) -> bool:
        """Check TIMESTAMP line is recent enough."""
        m = re.search(r'TIMESTAMP:(.+)', text)
        if not m:
            return True  # no timestamp — assume fresh
        from datetime import datetime, timezone
        try:
            ts = datetime.fromisoformat(m.group(1).strip())
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
            return age <= max_age_minutes
        except Exception:
            return True

    def _trigger_login_email(self) -> bool:
        """Open Workzilla login page, enter email, submit to trigger verification email."""
        email = os.getenv("WORKZILLA_EMAIL")
        if not email:
            log_agent_action("Workzilla", "❌ [AUTH] WORKZILLA_EMAIL not set", level="ERROR")
            return False

        login_url = "https://client.work-zilla.com/account/login?ReturnUrl=%2Ffreelancer"
        log_agent_action("Workzilla", f"🌐 [AUTH] Opening login page...")
        self.driver.get(login_url)
        self._human_delay(2, 3)

        try:
            field = None
            for sel in ["input[type='email']", "input[name='email']", "input[name='Login']",
                        "input[placeholder*='mail']", "input[placeholder*='почт']", "input.form-control"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    field = els[0]
                    break

            if not field:
                log_agent_action("Workzilla", "❌ [AUTH] Email field not found", level="ERROR")
                return False

            field.clear()
            field.send_keys(email)
            self._human_delay(0.5, 1)

            # Submit
            for sel in ["button[type='submit']", "input[type='submit']", "button.btn-primary", "button.login-btn"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    self.driver.execute_script("arguments[0].click();", els[0])
                    break

            self._human_delay(1, 2)
            log_agent_action("Workzilla", "📨 [AUTH] Login form submitted — waiting for email...")
            return True

        except Exception as e:
            log_agent_action("Workzilla", f"❌ [AUTH] Login form error: {e}", level="ERROR")
            return False

    def _wait_for_magic_link(self, file_id: str, triggered_at: float, timeout: int = 120) -> str | None:
        """Poll Google Drive file until a fresh magic link appears."""
        from datetime import datetime, timezone
        deadline = time.time() + timeout
        last_seen_link = None

        # Read whatever is in the file right now (before our trigger)
        try:
            content = self._fetch_gdrive_file(file_id)
            last_seen_link = self._extract_magic_link(content)
        except Exception:
            pass

        attempt = 0
        while time.time() < deadline:
            attempt += 1
            time.sleep(8)
            try:
                content = self._fetch_gdrive_file(file_id)

                # Try timestamp-based freshness first
                ts_match = re.search(r'TIMESTAMP:(.+)', content)
                if ts_match:
                    try:
                        ts = datetime.fromisoformat(ts_match.group(1).strip())
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        if ts.timestamp() > triggered_at:
                            link = self._extract_magic_link(content)
                            if link:
                                log_agent_action("Workzilla", f"✅ [AUTH] Fresh link via timestamp (poll {attempt})")
                                return link
                    except Exception:
                        pass

                # Fallback: detect link change (no TIMESTAMP in file)
                link = self._extract_magic_link(content)
                if link and link != last_seen_link:
                    log_agent_action("Workzilla", f"✅ [AUTH] New magic link detected (poll {attempt})")
                    return link

            except Exception as e:
                log_agent_action("Workzilla", f"⚠️ [AUTH] Drive poll error: {e}", level="WARNING")

            remaining = int(deadline - time.time())
            log_agent_action("Workzilla", f"⏳ [AUTH] Waiting for email... ({remaining}s left)")

        return None

    def login(self) -> bool:
        if self.logged_in:
            return True
        if not self.driver:
            self.setup_driver()

        file_id = os.getenv("GDRIVE_VERIFY_FILE_ID")
        if file_id and os.getenv("WORKZILLA_EMAIL"):
            triggered_at = time.time()
            if self._trigger_login_email():
                magic_link = self._wait_for_magic_link(file_id, triggered_at, timeout=90)
                if magic_link:
                    log_agent_action("Workzilla", "🔗 [AUTH] Navigating to magic link...")
                    self.driver.get(magic_link)
                    self._human_delay(2, 3)
                    if "login" not in self.driver.current_url:
                        log_agent_action("Workzilla", "✅ [AUTH] Logged in successfully")
                        self.logged_in = True
                        return True
                    log_agent_action("Workzilla", "⚠️ [AUTH] Magic link navigation failed", level="WARNING")
                else:
                    log_agent_action("Workzilla", "❌ [AUTH] No magic link received within timeout", level="ERROR")
            return False

        # Fallback: cookie injection
        raw_cookies = os.getenv("WORKZILLA_COOKIES")
        if not raw_cookies:
            log_agent_action("Workzilla", "❌ [AUTH] Set GDRIVE_VERIFY_FILE_ID + WORKZILLA_EMAIL or WORKZILLA_COOKIES", level="ERROR")
            return False

        try:
            cleaned = re.sub(r'[\x00-\x1f\x7f]', '', raw_cookies)
            cookies = json.loads(cleaned)
        except Exception as e:
            log_agent_action("Workzilla", f"❌ [AUTH] Failed to parse WORKZILLA_COOKIES: {e}", level="ERROR")
            return False

        self.driver.get(BASE_URL)
        self._human_delay(1, 2)
        injected = 0
        for c in cookies:
            try:
                self.driver.add_cookie({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ".work-zilla.com"),
                    "path": c.get("path", "/"),
                })
                injected += 1
            except Exception:
                pass
        log_agent_action("Workzilla", f"🍪 [AUTH] Injected {injected}/{len(cookies)} cookies")
        self.logged_in = True
        return True

    def scrape_orders(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.logged_in:
            if not self.login():
                return []

        log_agent_action("Workzilla", f"🌐 [SCRAPE] Loading {ORDERS_URL}")
        self.driver.get(ORDERS_URL)
        self._human_delay(2, 4)

        # Check we're actually logged in (not redirected to login page)
        if "login" in self.driver.current_url:
            log_agent_action("Workzilla", "⚠️ [SCRAPE] Session expired — re-authenticating...", level="WARNING")
            self.logged_in = False
            if not self.login():
                return []
            self.driver.get(ORDERS_URL)
            self._human_delay(2, 4)

        cards = self.driver.find_elements(By.CSS_SELECTOR, ".order-header")
        log_agent_action("Workzilla", f"📋 [SCRAPE] Found {len(cards)} cards on page, taking first {limit}")

        projects = []
        links = self.driver.find_elements(By.CSS_SELECTOR, "a.order-in-list-link")

        for i, (card, link) in enumerate(zip(cards[:limit], links[:limit])):
            try:
                href = link.get_attribute("href") or ""
                url = href if href.startswith("http") else BASE_URL + href
                order_id = re.search(r'/freelancer/(\d+)', url)
                order_id = order_id.group(1) if order_id else str(i)

                title = ""
                for sel in [".title .text-wrapper", ".title-container .text-wrapper"]:
                    els = card.find_elements(By.CSS_SELECTOR, sel)
                    if els and els[0].text.strip():
                        title = els[0].text.strip()
                        break

                budget = ""
                els = card.find_elements(By.CSS_SELECTOR, ".price-order-in-list .param-title")
                if els:
                    budget = els[0].text.strip() + " ₽"

                time_left = ""
                els = card.find_elements(By.CSS_SELECTOR, ".time-title")
                if els:
                    time_left = els[0].text.strip()

                if not title:
                    continue

                projects.append({
                    "id": order_id,
                    "title": title,
                    "description": "",
                    "budget": budget,
                    "url": url,
                    "timeLeft": time_left,
                    "proposals": None,
                    "hired": None,
                    "platform": "workzilla",
                })
            except Exception as e:
                log_agent_action("Workzilla", f"⚠️ [SCRAPE] Card {i+1} error: {e}", level="WARNING")

        log_agent_action("Workzilla", f"✅ [SCRAPE] Collected {len(projects)} projects")
        return projects

    def submit_response(self, url: str, cp_text: str) -> bool:
        if not self.logged_in:
            self.login()

        log_agent_action("Workzilla", f"📨 [RESPOND] {url}")
        self.driver.get(url)
        self._human_delay(2, 3)

        try:
            # Click "Согласиться" button
            btn = None
            for sel in ["a.wz-button.answer-accept", ".answer-accept", "a[class*='answer']"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    btn = els[0]
                    break

            if not btn:
                log_agent_action("Workzilla", "❌ [RESPOND] Button not found", level="ERROR")
                return False

            self.driver.execute_script("arguments[0].click();", btn)
            self._human_delay(1, 2)

            # Try to fill in CP text if a textarea appears
            for sel in ["textarea", "textarea[name='comment']", ".modal textarea", "textarea[name='message']"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    els[0].clear()
                    els[0].send_keys(cp_text)
                    self._human_delay(0.5, 1)
                    break

            # Submit
            for sel in ["button[type='submit']", ".modal button.wz-button", "input[type='submit']"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    self.driver.execute_script("arguments[0].click();", els[0])
                    self._human_delay(1, 2)
                    break

            log_agent_action("Workzilla", f"✅ [RESPOND] Done")
            return True

        except Exception as e:
            log_agent_action("Workzilla", f"❌ [RESPOND] Error: {e}", level="ERROR")
            return False

    async def stop(self):
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
            except Exception:
                pass
        self.status = "stopped"


agent_workzilla = AgentWorkzilla()
