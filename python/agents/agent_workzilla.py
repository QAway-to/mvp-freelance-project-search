import re
import time
import random
import os
import threading
from typing import List, Dict, Any

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from browser import create_driver
from config import config
from utils.logger import log_agent_action

BASE_URL = "https://client.work-zilla.com"
ORDERS_URL = f"{BASE_URL}/freelancer"


class AgentWorkzilla:
    def __init__(self):
        self.driver = None
        self.logged_in = False
        self.status = "stopped"
        self._lock = threading.Lock()

    def _human_delay(self, lo: float = 1.0, hi: float = 2.5):
        time.sleep(random.uniform(lo, hi))

    def setup_driver(self):
        log_agent_action("Workzilla", "🔧 [SELENIUM] Starting browser...")
        self.driver = create_driver()
        log_agent_action("Workzilla", "✅ [SELENIUM] Browser ready")

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

    # ── Login ─────────────────────────────────────────────────────────────────

    def login(self) -> bool:
        if self.logged_in:
            return True
        if not self.driver:
            self.setup_driver()

        file_id = os.getenv("GDRIVE_VERIFY_FILE_ID")
        email = os.getenv("WORKZILLA_EMAIL")
        if not file_id or not email:
            log_agent_action("Workzilla", "❌ [AUTH] Set GDRIVE_VERIFY_FILE_ID + WORKZILLA_EMAIL", level="ERROR")
            return False

        login_url = f"{BASE_URL}/account/login?ReturnUrl=%2Ffreelancer"
        log_agent_action("Workzilla", "🌐 [AUTH] Opening login page...")
        self.driver.get(login_url)
        self._human_delay(2, 3)

        try:
            field = None
            for sel in ["input#email", "input[name='email']", "input[type='email']", "input.large"]:
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

            for sel in ["a.wz-button.single-auth-btn", "a.single-auth-btn", "a.wz-button"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    self.driver.execute_script("arguments[0].click();", els[0])
                    break

            self._human_delay(1, 2)
            log_agent_action("Workzilla", "📨 [AUTH] Login submitted — waiting for email...")

            triggered_at = time.time()
            magic_link = self._wait_for_magic_link(file_id, triggered_at - 5, timeout=90)
            if not magic_link:
                log_agent_action("Workzilla", "❌ [AUTH] No magic link received", level="ERROR")
                return False

            log_agent_action("Workzilla", "🔗 [AUTH] Navigating to magic link...")
            try:
                self.driver.get(magic_link)
            except TimeoutException:
                log_agent_action("Workzilla", "⚠️ [AUTH] Page load timeout on magic link — checking auth state...", level="WARNING")
            self._human_delay(2, 3)

            if "login" in self.driver.current_url:
                log_agent_action("Workzilla", "⚠️ [AUTH] Magic link navigation failed", level="WARNING")
                return False

            self.logged_in = True
            log_agent_action("Workzilla", "✅ [AUTH] Logged in successfully")
            return True

        except Exception as e:
            log_agent_action("Workzilla", f"❌ [AUTH] Login error: {e}", level="ERROR")
            return False

    # ── Scraping ──────────────────────────────────────────────────────────────

    # JS: extract list-level metadata for all cards (no expand needed)
    _META_JS = """
        var headers = document.querySelectorAll('.order-header');
        var links   = document.querySelectorAll('a.order-in-list-link');
        var n = Math.min(arguments[0], headers.length, links.length);
        var out = [];
        for (var i = 0; i < n; i++) {
            var h = headers[i], lnk = links[i];
            var t  = h.querySelector('.title .text-wrapper, .title-container .text-wrapper, .text-wrapper');
            var b  = h.querySelector('.price-order-in-list .param-title');
            var tm = h.querySelector('.time-title');
            out.push({
                title:    t  ? t.textContent.trim()  : '',
                budget:   b  ? b.textContent.trim() + ' ₽' : '',
                timeLeft: tm ? tm.textContent.trim() : '',
                href:     lnk.href || ''
            });
        }
        return out;
    """

    # JS: click one card by index (expands it via AJAX)
    _CLICK_ONE_JS = """
        var links = document.querySelectorAll('a.order-in-list-link');
        if (links[arguments[0]]) { links[arguments[0]].click(); return true; }
        return false;
    """

    # JS: read the description of one expanded card by index
    _DESC_ONE_JS = """
        var links = document.querySelectorAll('a.order-in-list-link');
        var lnk = links[arguments[0]];
        if (!lnk) return '';
        var parent = lnk.closest('li, article, .order-item, .order-wrapper') || lnk.parentElement;
        if (!parent) return '';
        var sels = ['.external-links-wrapper span', '.order-description span',
                    '.order-body span', '.task-description span', '.description'];
        for (var s = 0; s < sels.length; s++) {
            var el = parent.querySelector(sels[s]);
            if (el && el.textContent.trim()) return el.textContent.trim();
        }
        return '';
    """

    def scrape_orders(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Backward-compatible: collect all projects into a list."""
        return list(self.scrape_orders_iter(limit))

    def scrape_orders_iter(self, limit: int = 15):
        """Generator: yields each project as soon as it is scraped (for SSE streaming)."""
        with self._lock:
            if not self.driver:
                self.setup_driver()
            if not self.logged_in:
                if not self.login():
                    return

            self.driver.set_script_timeout(60)

            log_agent_action("Workzilla", f"🌐 [SCRAPE] Loading {ORDERS_URL}")
            try:
                self.driver.get(ORDERS_URL)
            except TimeoutException:
                log_agent_action("Workzilla", "⚠️ [SCRAPE] Page load timeout — checking state...", level="WARNING")

            if "login" in self.driver.current_url:
                log_agent_action("Workzilla", "⚠️ [SCRAPE] Session expired — re-authenticating...", level="WARNING")
                self.logged_in = False
                if not self.login():
                    return
                try:
                    self.driver.get(ORDERS_URL)
                except TimeoutException:
                    log_agent_action("Workzilla", "⚠️ [SCRAPE] Page load timeout on retry...", level="WARNING")

            # SPA renders cards AFTER DOMContentLoaded — wait for them explicitly
            try:
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a.order-in-list-link"))
                )
            except TimeoutException:
                log_agent_action("Workzilla", "⚠️ [SCRAPE] Cards did not render in 30s", level="WARNING")
                return

            # Extract list metadata for all cards in one fast call (no expand)
            metas = self.driver.execute_script(self._META_JS, limit) or []
            log_agent_action("Workzilla", f"📋 [SCRAPE] Found {len(metas)} cards, streaming...")

            yielded = 0
            for i, meta in enumerate(metas):
                title = meta.get("title", "")
                if not title:
                    continue
                href = meta.get("href", "")
                url = href if href.startswith("http") else BASE_URL + href
                m = re.search(r'/freelancer/(\d+)', url)
                order_id = m.group(1) if m else str(i)

                # Expand THIS card only — one AJAX at a time, no flood
                description = ""
                try:
                    self.driver.execute_script(self._CLICK_ONE_JS, i)
                    time.sleep(1.2)
                    description = self.driver.execute_script(self._DESC_ONE_JS, i) or ""
                except Exception as e:
                    log_agent_action("Workzilla", f"⚠️ [SCRAPE] card {i+1} expand error: {e}", level="WARNING")

                yielded += 1
                log_agent_action("Workzilla", f"📋 [SCRAPE] {i+1}/{len(metas)}: {title[:50]} | desc={len(description)}ch")
                yield {
                    "id": order_id,
                    "title": title,
                    "description": description,
                    "budget": meta.get("budget", ""),
                    "url": url,
                    "timeLeft": meta.get("timeLeft", ""),
                    "proposals": None,
                    "hired": None,
                    "platform": "workzilla",
                }

            log_agent_action("Workzilla", f"✅ [SCRAPE] Streamed {yielded} projects")
            try:
                self.driver.get("about:blank")
            except Exception:
                pass

    # ── Submit response ───────────────────────────────────────────────────────

    def submit_response(self, url: str, cp_text: str) -> bool:
        with self._lock:
            return self._submit_response_locked(url, cp_text)

    def _submit_response_locked(self, url: str, cp_text: str) -> bool:
        if not self.logged_in:
            if not self.login():
                return False

        order_id_match = re.search(r'/freelancer/(\d+)', url)
        order_id = order_id_match.group(1) if order_id_match else None
        log_agent_action("Workzilla", f"📨 [RESPOND] order_id={order_id}")

        self.driver.get(ORDERS_URL)
        self._human_delay(2, 3)

        # Find and expand the target card
        if order_id:
            links = self.driver.find_elements(By.CSS_SELECTOR, "a.order-in-list-link")
            for link in links:
                href = link.get_attribute("href") or ""
                if order_id in href:
                    self.driver.execute_script("arguments[0].click();", link)
                    self._human_delay(1.5, 2.5)
                    break
        else:
            self.driver.get(url)
            self._human_delay(2, 3)

        try:
            btn = None
            for sel in ["a.wz-button.answer-accept", ".answer-accept", "a[class*='answer-accept']"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    btn = els[0]
                    break
            if not btn:
                log_agent_action("Workzilla", "❌ [RESPOND] Accept button not found", level="ERROR")
                return False

            self.driver.execute_script("arguments[0].click();", btn)
            self._human_delay(1, 2)

            for sel in ["textarea", "textarea[name='comment']", "textarea[name='message']"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    els[0].clear()
                    els[0].send_keys(cp_text)
                    self._human_delay(0.5, 1)
                    break

            for sel in ["button[type='submit']", ".modal button.wz-button", "input[type='submit']"]:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    self.driver.execute_script("arguments[0].click();", els[0])
                    self._human_delay(1, 2)
                    break

            log_agent_action("Workzilla", "✅ [RESPOND] Done")
            return True

        except Exception as e:
            log_agent_action("Workzilla", f"❌ [RESPOND] Error: {e}", level="ERROR")
            return False

    async def stop(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        self.status = "stopped"


agent_workzilla = AgentWorkzilla()
