import os
import undetected_chromedriver as uc
from utils.logger import log_agent_action

_driver = None


def get_driver():
    global _driver
    if _driver is not None:
        try:
            _ = _driver.current_url  # probe — raises if dead
            return _driver
        except Exception:
            _driver = None

    log_agent_action("Browser", "🔧 Starting shared Chrome instance...")
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--mute-audio")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--no-first-run")

    chrome_bin = os.getenv("CHROME_BIN") or os.getenv("GOOGLE_CHROME_BIN")
    if not chrome_bin:
        for path in ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/usr/bin/chromium"]:
            if os.path.exists(path):
                chrome_bin = path
                break

    _driver = uc.Chrome(
        options=options,
        browser_executable_path=chrome_bin,
        headless=True,
        use_subprocess=False,
    )
    _driver.set_page_load_timeout(30)
    log_agent_action("Browser", "✅ Shared Chrome ready")
    return _driver


def quit_driver():
    global _driver
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None
        log_agent_action("Browser", "🛑 Shared Chrome stopped")
