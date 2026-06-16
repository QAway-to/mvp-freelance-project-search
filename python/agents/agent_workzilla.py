import re
import time
import random
import os
import json
from typing import List, Dict, Any

from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException

from browser import create_driver
from config import config
from utils.logger import log_agent_action

BASE_URL = "https://client.work-zilla.com"
ORDERS_URL = f"{BASE_URL}/freelancer"


class AgentWorkzilla:
    def __init__(self):
        self.driver = None
        self.logged_in = False
        self._cached_cookies: List[Dict] = []
        self.status = "stopped"

    def _human_delay(self, lo: float = 1.0, hi: float = 2.5):
        time.sleep(random.uniform(lo, hi))

    # ── Google Drive ──────────────────────────────────────────────────────────

    def _fetch_gdrive_file(self, file_id: str) -> str:
        import urllib.request
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read().decode("utf-8")

    def _extract_magic_link(self, text: str) -> str | None:
        m = re.search(r'https://client\.work-zilla\.com/account/link-login\?[^\s>\]]+', text)
        return m.group(0) if m else None

    def _wait_for_magic_link(self, file_id: str, triggered_at: float, timeout: int = 120) -> str | None:
        from datetime import datetime, timezone
        deadline = time.time() + timeout
        last_seen_link = None
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
                link = self._extract_magic_link(content)
                if link and link != last_seen_link:
                    log_agent_action("Workzilla", f"✅ [AUTH] New magic link (poll {attempt})")
                    return link
            except Exception as e:
                log_agent_action("Workzilla", f"⚠️ [AUTH] Drive poll error: {e}", level="WARNING")
            log_agent_action("Workzilla", f"⏳ [AUTH] Waiting... ({int(deadline - time.time())}s left)")
        return None

    # ── Login (ephemeral Chrome) ──────────────────────────────────────────────

    def login(self) -> bool:
        """Login via ephemeral Chrome, save cookies for subsequent scraping."""
        if self.logged_in and self._cached_cookies:
            return True

        file_id = os.getenv("GDRIVE_VERIFY_FILE_ID")
        email = os.getenv("WORKZILLA_EMAIL")
        if not file_id or not email:
            log_agent_action("Workzilla", "❌ [AUTH] Set GDRIVE_VERIFY_FILE_ID + WORKZILLA_EMAIL", level="ERROR")
            return False

        log_agent_action("Workzilla", "🔧 [AUTH] Starting ephemeral Chrome for login...")
        driver = create_driver()
        try:
            login_url = f"{BASE_URL}/account/login?ReturnUrl=%2Ffreelancer"
            driver.get(login_url)
            self._human_delay(2, 3)

            # Find email field
            field = None
            for sel in ["input#email", "input[name='email']", "input[type='email']", "input.large"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    field = els[0]
                    break
            if not field:
                log_agent_action("Workzilla", "❌ [AUTH] Email field not found", level="ERROR")
                return False

            field.clear()
            field.send_keys(email)
            self._human_delay(0.5, 1)

            # Click submit link
            for sel in ["a.wz-button.single-auth-btn", "a.single-auth-btn", "a.wz-button"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    driver.execute_script("arguments[0].click();", els[0])
                    break

            self._human_delay(1, 2)
            log_agent_action("Workzilla", "📨 [AUTH] Login submitted — waiting for email...")

            triggered_at = time.time()
            magic_link = self._wait_for_magic_link(file_id, triggered_at - 5, timeout=90)
            if not magic_link:
                log_agent_action("Workzilla", "❌ [AUTH] No magic link received", level="ERROR")
                return False

            log_agent_action("Workzilla", "🔗 [AUTH] Navigating to magic link...")
            driver.get(magic_link)
            self._human_delay(2, 3)

            if "login" in driver.current_url:
                log_agent_action("Workzilla", "⚠️ [AUTH] Magic link navigation failed", level="WARNING")
                return False

            # Save cookies for reuse
            self._cached_cookies = driver.get_cookies()
            self.logged_in = True
            log_agent_action("Workzilla", f"✅ [AUTH] Logged in, saved {len(self._cached_cookies)} cookies")
            return True

        except Exception as e:
            log_agent_action("Workzilla", f"❌ [AUTH] Login error: {e}", level="ERROR")
            return False
        finally:
            driver.quit()
            log_agent_action("Workzilla", "🔧 [AUTH] Login Chrome closed")

    # ── Scraping (ephemeral Chrome + cached cookies) ──────────────────────────

    def scrape_orders(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.logged_in:
            if not self.login():
                return []

        log_agent_action("Workzilla", "🔧 [SCRAPE] Starting ephemeral Chrome for scraping...")
        driver = create_driver()
        try:
            # Inject saved cookies
            driver.get(BASE_URL)
            self._human_delay(1, 2)
            injected = 0
            for c in self._cached_cookies:
                try:
                    driver.add_cookie({
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c.get("domain", ".work-zilla.com"),
                        "path": c.get("path", "/"),
                    })
                    injected += 1
                except Exception:
                    pass
            log_agent_action("Workzilla", f"🍪 [SCRAPE] Injected {injected} cookies")

            driver.get(ORDERS_URL)
            self._human_delay(2, 3)

            # Session expired?
            if "login" in driver.current_url:
                log_agent_action("Workzilla", "⚠️ [SCRAPE] Session expired — need re-login", level="WARNING")
                self.logged_in = False
                self._cached_cookies = []
                return []

            # Step 1: collect all order URLs from listing page
            links = driver.find_elements(By.CSS_SELECTOR, "a.order-in-list-link")
            log_agent_action("Workzilla", f"📋 [SCRAPE] Found {len(links)} order links, taking first {limit}")

            order_urls: List[str] = []
            for link in links[:limit]:
                href = link.get_attribute("href") or ""
                url = href if href.startswith("http") else BASE_URL + href
                if url and url != BASE_URL:
                    order_urls.append(url)

            if not order_urls:
                log_agent_action("Workzilla", "⚠️ [SCRAPE] No order URLs found", level="WARNING")
                return []

            # Step 2: visit each order page individually
            projects = []
            for i, url in enumerate(order_urls):
                try:
                    driver.get(url)
                    self._human_delay(1.0, 2.0)

                    order_id = re.search(r'/freelancer/(\d+)', url)
                    order_id = order_id.group(1) if order_id else str(i)

                    # Title
                    title = ""
                    for sel in ["h1", ".order-title", ".title"]:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        if els and els[0].text.strip():
                            title = els[0].text.strip()
                            break

                    # Description
                    description = ""
                    for sel in [".external-links-wrapper span", ".order-description", ".task-description", ".description"]:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        texts = [e.text.strip() for e in els if e.text.strip()]
                        if texts:
                            description = "\n".join(texts)
                            break

                    # Budget
                    budget = ""
                    for sel in [".price-order .param-title", ".order-price", "[class*='price']"]:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        if els and els[0].text.strip():
                            budget = els[0].text.strip() + " ₽"
                            break

                    # Time left
                    time_left = ""
                    for sel in [".time-title", "[class*='time']"]:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        if els and els[0].text.strip():
                            time_left = els[0].text.strip()
                            break

                    if not title:
                        log_agent_action("Workzilla", f"⚠️ [SCRAPE] Order {i+1}: no title, skipping")
                        continue

                    log_agent_action("Workzilla", f"📋 [SCRAPE] {i+1}/{len(order_urls)}: {title[:50]}")
                    projects.append({
                        "id": order_id,
                        "title": title,
                        "description": description,
                        "budget": budget,
                        "url": url,
                        "timeLeft": time_left,
                        "proposals": None,
                        "hired": None,
                        "platform": "workzilla",
                    })
                except Exception as e:
                    log_agent_action("Workzilla", f"⚠️ [SCRAPE] Order {i+1} error: {e}", level="WARNING")

            log_agent_action("Workzilla", f"✅ [SCRAPE] Collected {len(projects)} projects")
            return projects

        except Exception as e:
            log_agent_action("Workzilla", f"❌ [SCRAPE] Fatal error: {e}", level="ERROR")
            return []
        finally:
            driver.quit()
            log_agent_action("Workzilla", "🔧 [SCRAPE] Scraping Chrome closed")

    # ── Submit response (ephemeral Chrome) ───────────────────────────────────

    def submit_response(self, url: str, cp_text: str) -> bool:
        if not self.logged_in:
            if not self.login():
                return False

        log_agent_action("Workzilla", f"📨 [RESPOND] Starting ephemeral Chrome for {url}")
        driver = create_driver()
        try:
            driver.get(BASE_URL)
            self._human_delay(1, 1.5)
            for c in self._cached_cookies:
                try:
                    driver.add_cookie({
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c.get("domain", ".work-zilla.com"),
                        "path": c.get("path", "/"),
                    })
                except Exception:
                    pass

            driver.get(url)
            self._human_delay(2, 3)

            btn = None
            for sel in ["a.wz-button.answer-accept", ".answer-accept", "a[class*='answer']"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    btn = els[0]
                    break
            if not btn:
                log_agent_action("Workzilla", "❌ [RESPOND] Accept button not found", level="ERROR")
                return False

            driver.execute_script("arguments[0].click();", btn)
            self._human_delay(1, 2)

            for sel in ["textarea", "textarea[name='comment']", ".modal textarea"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    els[0].clear()
                    els[0].send_keys(cp_text)
                    self._human_delay(0.5, 1)
                    break

            for sel in ["button[type='submit']", ".modal button.wz-button", "input[type='submit']"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    driver.execute_script("arguments[0].click();", els[0])
                    self._human_delay(1, 2)
                    break

            log_agent_action("Workzilla", "✅ [RESPOND] Done")
            return True

        except Exception as e:
            log_agent_action("Workzilla", f"❌ [RESPOND] Error: {e}", level="ERROR")
            return False
        finally:
            driver.quit()
            log_agent_action("Workzilla", "🔧 [RESPOND] Chrome closed")

    async def stop(self):
        self.driver = None
        self.status = "stopped"


agent_workzilla = AgentWorkzilla()
