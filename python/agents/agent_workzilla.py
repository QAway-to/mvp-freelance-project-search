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

    def login(self) -> bool:
        if self.logged_in:
            return True
        if not self.driver:
            self.setup_driver()

        # Try magic link auth via Google Drive file
        file_id = os.getenv("GDRIVE_VERIFY_FILE_ID")
        if file_id:
            log_agent_action("Workzilla", "📧 [AUTH] Reading verification code from Google Drive...")
            try:
                content = self._fetch_gdrive_file(file_id)
                if not self._is_fresh(content):
                    log_agent_action("Workzilla", "⚠️ [AUTH] Drive file is stale (>25 min) — waiting for fresh code", level="WARNING")
                    return False
                magic_link = self._extract_magic_link(content)
                if magic_link:
                    log_agent_action("Workzilla", "🔗 [AUTH] Magic link found — navigating...")
                    self.driver.get(magic_link)
                    self._human_delay(2, 3)
                    # Verify we're logged in by checking URL
                    if "login" not in self.driver.current_url:
                        log_agent_action("Workzilla", "✅ [AUTH] Logged in via magic link")
                        self.logged_in = True
                        return True
                    log_agent_action("Workzilla", "⚠️ [AUTH] Magic link redirect failed", level="WARNING")
                else:
                    log_agent_action("Workzilla", "⚠️ [AUTH] No magic link found in Drive file", level="WARNING")
            except Exception as e:
                log_agent_action("Workzilla", f"⚠️ [AUTH] Drive read failed: {e}", level="WARNING")

        # Fallback: cookie injection
        raw_cookies = os.getenv("WORKZILLA_COOKIES")
        if not raw_cookies:
            log_agent_action("Workzilla", "❌ [AUTH] No auth method available (GDRIVE_VERIFY_FILE_ID or WORKZILLA_COOKIES)", level="ERROR")
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

    def scrape_orders(self) -> List[Dict[str, Any]]:
        if not self.logged_in:
            if not self.login():
                return []

        log_agent_action("Workzilla", f"🌐 [SCRAPE] Loading {ORDERS_URL}")
        self.driver.get(ORDERS_URL)
        self._human_delay(2, 4)

        # Collect all order links
        links = self.driver.find_elements(By.CSS_SELECTOR, "a.order-in-list-link")
        hrefs = []
        for el in links:
            href = el.get_attribute("href")
            if href:
                hrefs.append(href if href.startswith("http") else BASE_URL + href)

        log_agent_action("Workzilla", f"📋 [SCRAPE] Found {len(hrefs)} order links")

        projects = []
        for i, href in enumerate(hrefs):
            try:
                project = self._scrape_order_page(href, i + 1, len(hrefs))
                if project:
                    projects.append(project)
            except Exception as e:
                log_agent_action("Workzilla", f"⚠️ [SCRAPE] Error on {href}: {e}", level="WARNING")
            self._human_delay(1.5, 3)

        log_agent_action("Workzilla", f"✅ [SCRAPE] Collected {len(projects)} projects")
        return projects

    def _scrape_order_page(self, url: str, idx: int, total: int) -> Dict[str, Any] | None:
        log_agent_action("Workzilla", f"🔗 [SCRAPE] {idx}/{total} {url}")
        self.driver.get(url)
        self._human_delay(1.5, 3)

        # Extract order ID from URL
        m = re.search(r'/freelancer/(\d+)', url)
        order_id = m.group(1) if m else "unknown"

        try:
            title = ""
            for sel in [".title .text-wrapper", ".title-container .text-wrapper", "h3.title", "h1"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els and els[0].text.strip():
                    title = els[0].text.strip()
                    break

            budget = ""
            for sel in [".price-order-in-list .param-title", ".order-money-icon .param-title", ".param-title"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els and els[0].text.strip():
                    budget = els[0].text.strip() + " ₽"
                    break

            time_left = ""
            for sel in [".time-title", ".order-time-container .time-title"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els and els[0].text.strip():
                    time_left = els[0].text.strip()
                    break

            description = ""
            for sel in [".external-links-wrapper span", ".order-description", ".description span", ".description"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    texts = [e.text.strip() for e in els if e.text.strip()]
                    if texts:
                        description = "\n".join(texts)
                        break

            if not title:
                return None

            return {
                "id": order_id,
                "title": title,
                "description": description,
                "budget": budget,
                "url": url,
                "timeLeft": time_left,
                "proposals": None,
                "hired": None,
                "platform": "workzilla",
            }
        except Exception as e:
            log_agent_action("Workzilla", f"❌ [SCRAPE] Extraction error: {e}", level="ERROR")
            return None

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
