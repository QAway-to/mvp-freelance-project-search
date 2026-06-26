"""Download Kwork attachments with an authenticated Selenium browser.

Kwork serves files only to a real logged-in browser — the direct file URL
returns the project HTML page to any plain HTTP client (auth + Qrator/Webvisor
gate). A real headless Chrome carrying the session cookies passes that gate.
We download into a temp dir, read the bytes, then reap Chrome immediately
(memory matters on the 512MB tier). Used only when generating a КП for a
project that has attachments — deliberate and low-volume, like offer submission.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time

import undetected_chromedriver as uc
from webdriver_manager.chrome import ChromeDriverManager

from config import config
from browser import _build_options, _chrome_bin, reap_driver
from agents.agent_a import _normalize_cookie
from utils.logger import log_agent_action

_MAX_FILES = int(os.getenv("ATTACH_MAX_FILES", "3"))


def _cookies() -> list:
    if not config.KWORK_COOKIES:
        return []
    try:
        raw = re.sub(r"[\x00-\x1f\x7f]", "", config.KWORK_COOKIES)
        return json.loads(raw)
    except Exception as e:
        log_agent_action("SeleniumDL", f"⚠️ bad KWORK_COOKIES: {e}", level="WARNING")
        return []


def _wait_download(dl_dir: str, before: set, timeout: int) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        new = set(os.listdir(dl_dir)) - before
        done = [f for f in new if not f.endswith(".crdownload")]
        if done:
            newest = max(done, key=lambda f: os.path.getmtime(os.path.join(dl_dir, f)))
            return os.path.join(dl_dir, newest)
        time.sleep(0.5)
    return None


def download_attachments(specs: list[dict], timeout: int = 60) -> dict:
    """specs: [{"url","fname"}]. Returns {fname: bytes} for files that downloaded."""
    specs = [s for s in (specs or []) if s.get("url")][:_MAX_FILES]
    if not specs:
        return {}

    dl_dir = tempfile.mkdtemp(prefix="kwork_dl_")
    driver = None
    out: dict = {}
    try:
        options = _build_options()
        options.add_experimental_option("prefs", {
            "download.default_directory": dl_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
            "safebrowsing.enabled": True,
        })
        driver = uc.Chrome(
            options=options,
            driver_executable_path=ChromeDriverManager().install(),
            browser_executable_path=_chrome_bin(),
            headless=True,
        )
        driver.set_page_load_timeout(40)
        # Headless Chrome needs explicit permission to write downloads.
        try:
            driver.execute_cdp_cmd("Page.setDownloadBehavior",
                                   {"behavior": "allow", "downloadPath": dl_dir})
        except Exception:
            pass

        driver.get("https://kwork.ru/")
        time.sleep(1)
        for c in _cookies():
            cc = _normalize_cookie(c)
            if cc:
                try:
                    driver.add_cookie(cc)
                except Exception:
                    pass
        log_agent_action("SeleniumDL", f"🔐 authenticated, downloading {len(specs)} file(s)")

        for sp in specs:
            url, fname = sp["url"], (sp.get("fname") or "file")
            before = set(os.listdir(dl_dir))
            try:
                driver.get(url)  # navigation to a file URL triggers the download
            except Exception:
                pass  # page "load" of a download often errors; the file still saves
            path = _wait_download(dl_dir, before, timeout)
            if path:
                try:
                    with open(path, "rb") as fh:
                        out[fname] = fh.read()
                    log_agent_action("SeleniumDL", f"✅ «{fname}» ({len(out[fname])} bytes)")
                except Exception as e:
                    log_agent_action("SeleniumDL", f"❌ read «{fname}»: {e}", level="ERROR")
            else:
                log_agent_action("SeleniumDL", f"⏱️ «{fname}» timed out", level="WARNING")
        return out
    except Exception as e:
        log_agent_action("SeleniumDL", f"❌ session failed: {e}", level="ERROR")
        return out
    finally:
        if driver is not None:
            reap_driver(driver)
        shutil.rmtree(dl_dir, ignore_errors=True)
