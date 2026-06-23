import os
import subprocess
import undetected_chromedriver as uc
from webdriver_manager.chrome import ChromeDriverManager
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
    options.page_load_strategy = "eager"
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
    chrome_bin = _chrome_bin()
    try:
        ver = subprocess.check_output([chrome_bin or "google-chrome", "--version"],
                                      stderr=subprocess.DEVNULL, timeout=5).decode().strip()
        log_agent_action("Browser", f"🔧 Starting Chrome... binary={chrome_bin} version={ver}")
    except Exception as ve:
        log_agent_action("Browser", f"🔧 Starting Chrome... binary={chrome_bin} version=unknown ({ve})")
    log_agent_action("Browser", "🔧 Downloading matching chromedriver via webdriver-manager...")
    driver_path = ChromeDriverManager().install()
    log_agent_action("Browser", f"🔧 Chromedriver path: {driver_path}")
    driver = uc.Chrome(
        options=_build_options(),
        driver_executable_path=driver_path,
        browser_executable_path=chrome_bin,
        headless=True,
    )
    driver.set_page_load_timeout(30)
    log_agent_action("Browser", "✅ Chrome ready")
    return driver


def reap_driver(driver) -> None:
    """Quit a driver AND kill any orphaned Chrome/chromedriver process tree.

    undetected-chromedriver's .quit() frequently leaves orphaned `chrome`
    processes alive on Linux; across repeated searches these accumulate and
    exhaust RAM (OOM on 512MB Render). We capture the pids before quitting,
    then forcibly reap the whole tree.
    """
    if driver is None:
        return
    pids = []
    try:
        bp = getattr(driver, "browser_pid", None)
        if bp:
            pids.append(bp)
    except Exception:
        pass
    try:
        svc_proc = getattr(getattr(driver, "service", None), "process", None)
        if svc_proc and getattr(svc_proc, "pid", None):
            pids.append(svc_proc.pid)
    except Exception:
        pass

    try:
        driver.quit()
    except Exception:
        pass

    # Kill leftover process trees (renderers, zombie chrome) that quit() missed.
    try:
        import psutil
        for pid in pids:
            try:
                parent = psutil.Process(pid)
            except psutil.NoSuchProcess:
                continue
            procs = parent.children(recursive=True) + [parent]
            for p in procs:
                try:
                    p.kill()
                except Exception:
                    pass
            psutil.wait_procs(procs, timeout=5)
    except Exception as e:
        # psutil missing or failed — best-effort os.kill fallback
        import os
        import signal
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        log_agent_action("Browser", f"⚠️ psutil reap failed, used os.kill: {e}", level="WARNING")


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
        reap_driver(_driver)
        _driver = None
        log_agent_action("Browser", "🛑 Chrome stopped")
