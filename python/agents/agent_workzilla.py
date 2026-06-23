import re
import time
import random
import os
import asyncio
import threading
from typing import List, Dict, Any

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from browser import create_driver, reap_driver
from config import config
from utils.logger import log_agent_action

BASE_URL = "https://client.work-zilla.com"
ORDERS_URL = f"{BASE_URL}/freelancer"


class AgentWorkzilla:
    # Restart Chrome every N scrapes to bound RSS growth (OOM guard on 512MB Render).
    _RESTART_EVERY = 8

    def __init__(self):
        self.driver = None
        self.logged_in = False
        self.status = "stopped"
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._scrape_count = 0
        self._last_scrape_ts = 0.0

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

    # JS: how many cards are present (capped to limit) — cheap count for the per-card loop
    _COUNT_JS = """
        var headers = document.querySelectorAll('.order-header');
        var links   = document.querySelectorAll('a.order-in-list-link');
        return Math.min(arguments[0], headers.length, links.length);
    """

    # JS: extract metadata + description for ONE card by index (re-queries the DOM each
    # call so it is resilient to SPA re-renders — never cache WebElement handles in Python).
    _META_ONE_JS = """
        var i = arguments[0];
        var headers = document.querySelectorAll('.order-header');
        var links   = document.querySelectorAll('a.order-in-list-link');
        if (i >= headers.length || i >= links.length) return null;
        var h = headers[i], lnk = links[i];
        var t  = h.querySelector('.title .text-wrapper, .title-container .text-wrapper, .text-wrapper');
        var b  = h.querySelector('.price-order-in-list .param-title');
        var tm = h.querySelector('.time-title');
        var descSels = ['.external-links-wrapper span', '.order-description span',
                        '.order-body span', '.task-description span', '.description'];
        var parent = lnk.closest('li, article, .order-item, .order-wrapper') || lnk.parentElement;
        var desc = '';
        if (parent) {
            for (var s = 0; s < descSels.length; s++) {
                var el = parent.querySelector(descSels[s]);
                if (el && el.textContent.trim()) { desc = el.textContent.trim(); break; }
            }
        }
        return {
            title:    t  ? t.textContent.trim()  : '',
            budget:   b  ? b.textContent.trim() + ' ₽' : '',
            timeLeft: tm ? tm.textContent.trim() : '',
            href:     lnk.href || '',
            description: desc
        };
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
            # Clear cancellation only once we own the lock, so we never un-cancel a
            # previous scrape that is still unwinding (see /api/workzilla/search).
            self._cancel.clear()
            # Refresh the idle timer up front so the reaper measures from the start of
            # any scrape activity — not only fully-completed ones (cancelled/failed
            # scrapes still touched Chrome and must keep it alive).
            self._last_scrape_ts = time.time()

            # Periodically recycle Chrome to bound RSS growth (OOM guard on 512MB Render).
            self._scrape_count += 1
            if self.driver is not None and self._scrape_count > self._RESTART_EVERY:
                log_agent_action("Workzilla", f"♻️ [SELENIUM] Recycling Chrome after {self._RESTART_EVERY} scrapes")
                reap_driver(self.driver)
                self.driver = None
                self.logged_in = False
                self._scrape_count = 1

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

            # Count cards once, then extract+yield ONE card at a time so they stream
            # incrementally (genuine per-card cadence) instead of bursting all at once.
            n = self.driver.execute_script(self._COUNT_JS, limit) or 0
            log_agent_action("Workzilla", f"📋 [SCRAPE] Found {n} cards, streaming one by one...")

            # Pass 1: per-card extraction — _META_ONE_JS re-queries the DOM each call,
            # so a mid-loop SPA re-render shifts indices but never yields a stale handle.
            empties = []  # (index, order_id) for cards needing expand to get description
            yielded = 0
            for i in range(n):
                if self._cancel.is_set():
                    log_agent_action("Workzilla", "🛑 [SCRAPE] Cancelled by client — stopping", level="WARNING")
                    break
                try:
                    meta = self.driver.execute_script(self._META_ONE_JS, i)
                except Exception as e:
                    log_agent_action("Workzilla", f"⚠️ [SCRAPE] card {i+1} extract failed: {e}", level="WARNING")
                    continue
                if not meta:
                    continue
                title = meta.get("title", "")
                if not title:
                    continue
                href = meta.get("href", "")
                url = href if href.startswith("http") else BASE_URL + href
                m = re.search(r'/freelancer/(\d+)', url)
                order_id = m.group(1) if m else str(i)
                description = meta.get("description", "")
                if not description:
                    empties.append((i, order_id))

                yielded += 1
                log_agent_action("Workzilla", f"📋 [SCRAPE] {i+1}/{n}: {title[:40]} | desc={len(description)}ch")
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
                # Small pause so cards visibly arrive one by one rather than in a burst.
                time.sleep(random.uniform(0.12, 0.35))

            log_agent_action("Workzilla", f"✅ [SCRAPE] Streamed {yielded} cards "
                                          f"({len(empties)} need description enrich)")

            # Pass 2 (only if descriptions weren't in the collapsed DOM):
            # expand each empty card one at a time and push a description update.
            if empties:
                self.driver.set_script_timeout(15)
                for i, order_id in empties:
                    if self._cancel.is_set():
                        log_agent_action("Workzilla", "🛑 [SCRAPE] Cancelled by client — stopping enrich", level="WARNING")
                        break
                    description = ""
                    try:
                        self.driver.execute_script(self._CLICK_ONE_JS, i)
                        time.sleep(1.0)
                        description = self.driver.execute_script(self._DESC_ONE_JS, i) or ""
                    except Exception as e:
                        log_agent_action("Workzilla", f"⚠️ [SCRAPE] enrich card {i+1}: {e}", level="WARNING")
                    if description:
                        log_agent_action("Workzilla", f"📝 [SCRAPE] enriched {order_id}: {len(description)}ch")
                        yield {"_update": order_id, "description": description}

            self._last_scrape_ts = time.time()
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

    def quit_driver(self):
        """Quit Chrome and reset session state. Safe to call from any thread (takes lock)."""
        with self._lock:
            if self.driver:
                reap_driver(self.driver)
                self.driver = None
                log_agent_action("Workzilla", "🛑 [SELENIUM] Chrome stopped (idle/explicit)")
            # Must reset logged_in too: next scrape recreates the driver and would
            # otherwise skip login (logged_in still True) → driver.get on None → crash.
            self.logged_in = False
            self._scrape_count = 0
            self.status = "stopped"

    async def stop(self):
        await asyncio.to_thread(self.quit_driver)


agent_workzilla = AgentWorkzilla()
