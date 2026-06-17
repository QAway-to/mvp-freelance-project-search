import os
import undetected_chromedriver as uc
from utils.logger import log_agent_action

_driver = None


def _build_options() -> uc.ChromeOptions:
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--mute-audio")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--no-first-run")
    return options


def _chrome_bin() -> str | None:
    path = os.getenv("CHROME_BIN") or os.getenv("GOOGLE_CHROME_BIN")
    if path:
        return path
    for candidate in ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/usr/bin/chromium"]:
        if os.path.exists(candidate):
            return candidate
    return None


def create_driver():
    """Create a fresh Chrome instance. Caller must call .quit() when done."""
    log_agent_action("Browser", "🔧 Starting Chrome...")
    driver = uc.Chrome(
        options=_build_options(),
        browser_executable_path=_chrome_bin(),
        headless=True,
    )
    driver.set_page_load_timeout(30)
    log_agent_action("Browser", "✅ Chrome ready")
    return driver


def get_driver():
    """Shared Chrome singleton for Kwork agent."""
    global _driver
    if _driver is not None:
        try:
            _ = _driver.current_url
            return _driver
        except Exception:
            _driver = None

    _driver = create_driver()
    return _driver


def quit_driver():
    global _driver
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None
        log_agent_action("Browser", "🛑 Chrome stopped")
