"""HTTP-based Kwork listing scraper — no headless Chrome.

Fetches the projects listing over plain HTTP with a *real Chrome TLS
fingerprint* (curl_cffi impersonation) and parses the `stateData` JSON that
Kwork embeds in the page. This replaces the Selenium/undetected-chromedriver
DOM scrape for listings, which OOM-killed the 512MB Render instance (Chrome
alone took 300-400MB).

Anti-detect is preserved at the network layer — without a browser there is no
JS surface to fingerprint, so detection reduces to: Chrome TLS fingerprint
(curl_cffi `impersonate`) + browser headers + the same KWORK_COOKIES session.

Chrome is still used elsewhere (offer submission) where real JS interaction is
required; only the listing scrape moves to HTTP.
"""
from __future__ import annotations

import functools
import html as _html
import json
import os
import random
import re
import threading
import time as _time
from collections import deque
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote_plus

from config import config
from utils.logger import log_agent_action

try:
    from curl_cffi import requests as _creq
    CURL_CFFI_AVAILABLE = True
except ImportError as _e:  # degraded path: caller falls back to Selenium
    CURL_CFFI_AVAILABLE = False
    _creq = None
    log_agent_action("KworkHTTP", f"curl_cffi unavailable: {_e}", level="WARNING")

# Pin a recent Chrome fingerprint; curl_cffi maps this to the matching JA3/TLS.
_IMPERSONATE = "chrome"
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Referer": "https://kwork.ru/projects",
    "Upgrade-Insecure-Requests": "1",
}

_TAG_RE = re.compile(r"<[^>]+>")

# --- Rate limiting + anti-bot (Qrator) challenge backoff --------------------
# Kwork sits behind Qrator. We can't fake the behavioural beacons, so the only
# safe lever is to look like a low-volume human: space requests out, cap volume
# per hour, and — critically — STOP (cooldown) the moment we see a challenge
# instead of hammering it (retries under a challenge are what gets you flagged).
_MIN_INTERVAL = float(os.getenv("KWORK_MIN_REQUEST_INTERVAL", "12"))   # sec between requests
_HOURLY_CAP = int(os.getenv("KWORK_HOURLY_CAP", "60"))                 # max requests / hour
_CHALLENGE_COOLDOWN = float(os.getenv("KWORK_CHALLENGE_COOLDOWN", "900"))  # backoff on challenge

_rl_lock = threading.Lock()
_last_request_ts = 0.0
_request_times: deque = deque()   # request timestamps within the trailing hour
_cooldown_until = 0.0

_CHALLENGE_MARKERS = (
    "qrator", "captcha", "ddos-guard", "проверка браузера",
    "checking your browser", "are you a robot", "doctype html public",
)


class RateLimited(Exception):
    """Raised internally when the hourly cap is hit or we are in cooldown."""


def _respect_rate_limit() -> None:
    """Block until it is polite to make the next request, or refuse (RateLimited)."""
    global _last_request_ts
    with _rl_lock:
        now = _time.time()
        if now < _cooldown_until:
            raise RateLimited(f"anti-bot cooldown, {int(_cooldown_until - now)}s left")
        while _request_times and now - _request_times[0] > 3600:
            _request_times.popleft()
        if len(_request_times) >= _HOURLY_CAP:
            raise RateLimited(f"hourly cap {_HOURLY_CAP} reached")
        wait = (_last_request_ts + _MIN_INTERVAL) - now
    if wait > 0:
        _time.sleep(wait + random.uniform(0.5, 2.5))  # jitter — avoid clockwork timing
    with _rl_lock:
        _last_request_ts = _time.time()
        _request_times.append(_last_request_ts)


def _trigger_cooldown(reason: str) -> None:
    global _cooldown_until
    with _rl_lock:
        _cooldown_until = _time.time() + _CHALLENGE_COOLDOWN
    log_agent_action(
        "KworkHTTP",
        f"🛑 [ANTI-BOT] challenge detected ({reason}) — backing off {int(_CHALLENGE_COOLDOWN)}s, no retries",
        level="ERROR",
    )


def _looks_like_challenge(status: int, text: str, expect_json: bool) -> Optional[str]:
    if status in (403, 429, 503):
        return f"status={status}"
    head = (text or "")[:2000].lower()
    for m in _CHALLENGE_MARKERS:
        if m in head:
            return f"marker:{m}"
    if expect_json:
        stripped = (text or "").lstrip()
        if stripped and stripped[0] not in "{[":
            return "expected-json-got-other"
    return None


def _request(method: str, url: str, *, expect_json: bool = False,
             data: Optional[dict] = None, extra_headers: Optional[dict] = None):
    """Single choke point for every Kwork request: rate-limited + challenge-aware.

    Returns the curl_cffi response, or None (rate-limited, error, non-200, or a
    detected anti-bot challenge — in which case a cooldown is also armed).
    """
    if not CURL_CFFI_AVAILABLE:
        return None
    try:
        _respect_rate_limit()
    except RateLimited as e:
        log_agent_action("KworkHTTP", f"⏳ [RATE] request skipped: {e}", level="WARNING")
        return None
    headers = dict(_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    try:
        if method == "POST":
            r = _creq.post(url, headers=headers, cookies=_cookies_dict(),
                           impersonate=_IMPERSONATE, data=data, timeout=40)
        else:
            r = _creq.get(url, headers=headers, cookies=_cookies_dict(),
                          impersonate=_IMPERSONATE, timeout=40)
    except Exception as e:
        log_agent_action("KworkHTTP", f"❌ [HTTP] {method} error: {e}", level="ERROR")
        return None
    challenge = _looks_like_challenge(r.status_code, r.text, expect_json)
    if challenge:
        _trigger_cooldown(challenge)
        return None
    if r.status_code != 200:
        log_agent_action("KworkHTTP", f"⚠️ [HTTP] {method} status {r.status_code} for {url}", level="WARNING")
        return None
    return r


@functools.lru_cache(maxsize=1)
def _cookies_dict() -> dict[str, str]:
    """Parse KWORK_COOKIES (Selenium-style JSON array) into a name->value dict.

    Memoised: KWORK_COOKIES is static at runtime and fetch_listing makes two
    requests per call. The returned dict is treated as read-only by callers.
    """
    if not config.KWORK_COOKIES:
        return {}
    try:
        raw = re.sub(r"[\x00-\x1f\x7f]", "", config.KWORK_COOKIES)
        cookies = json.loads(raw)
        return {
            c["name"]: c["value"]
            for c in cookies
            if c.get("name") and c.get("value") is not None
        }
    except Exception as e:
        log_agent_action("KworkHTTP", f"⚠️ Failed to parse KWORK_COOKIES: {e}", level="WARNING")
        return {}


def _extract_state_data(html_text: str) -> Optional[dict[str, Any]]:
    """Extract the `window.stateData={...}` object that Kwork embeds in the page.

    Uses ``json.JSONDecoder.raw_decode`` starting at the opening brace: it parses
    exactly one JSON value (correctly handling all string escapes) and stops at
    its end, ignoring the trailing JS/HTML. Returns None if absent or malformed.
    """
    idx = html_text.find("stateData=")
    if idx == -1:
        return None
    start = html_text.find("{", idx)
    if start == -1:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(html_text, start)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _clean_desc(text: Optional[str]) -> str:
    text = _html.unescape(text or "")
    text = _TAG_RE.sub(" ", text)
    text = text.replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _urgency_hours_from_timeleft(time_left: str) -> float:
    """Parse Kwork's 'timeLeft' ('1 д. 5 ч.', '5 ч.', '30 мин.') into hours.

    timeLeft is authoritative and timezone-free, so we use it instead of
    differencing date_expire (which would need MSK/UTC handling).
    """
    if not time_left:
        return 999.0
    days = hours = minutes = 0
    m = re.search(r"(\d+)\s*д", time_left)
    if m:
        days = int(m.group(1))
    m = re.search(r"(\d+)\s*ч", time_left)
    if m:
        hours = int(m.group(1))
    m = re.search(r"(\d+)\s*мин", time_left)
    if m:
        minutes = int(m.group(1))
    total = days * 24 + hours + minutes / 60.0
    return total if total > 0 else 999.0


def _map_want(want: dict[str, Any], page: int) -> Optional[dict[str, Any]]:
    """Map one Kwork `want` JSON object into the project dict schema used downstream.

    Returns None for an unusable record (no id) so the caller can drop it.
    """
    wid = want.get("id")
    if not wid:
        return None
    price = want.get("priceLimit")
    try:
        budget = f"до {int(float(price))} ₽" if price is not None else "не указан"
    except (TypeError, ValueError):
        budget = str(price) if price is not None else "не указан"
    # proposals: coerce to int|None to match the Selenium path's schema.
    kc = want.get("kwork_count")
    try:
        proposals = int(kc) if kc is not None else None
    except (TypeError, ValueError):
        proposals = None
    time_left = want.get("timeLeft") or ""
    return {
        "id": str(wid),
        "title": want.get("name") or "",
        "url": f"https://kwork.ru/projects/{wid}/view",
        "urgency": time_left,
        "urgency_hours": _urgency_hours_from_timeleft(time_left),
        "budget": budget,
        "description": _clean_desc(want.get("description")),
        "proposals": proposals,
        "hired": None,
        "page": page,
        "found_at": datetime.now().isoformat(),
    }


def _build_url(params: Any, page: int) -> str:
    keywords = ",".join(params.keywords_list) if getattr(params, "keywords_list", None) else ""
    if keywords:
        return f"{config.KWORK_PROJECTS_URL}?keyword={quote_plus(keywords)}&page={page}"
    # Favourites listing as a full HTML page (no a=1) so stateData is embedded.
    url = (
        f"{config.KWORK_PROJECTS_URL}?type=favourite"
        f"&kworks-filters[]=0&kworks-filters[]=1"
        f"&prices-filters[]=3&prices-filters[]=4&page={page}"
    )
    # Forward any extra budget filters, matching the Selenium path.
    budget_qs = "&".join(
        f"prices-filters[]={f}" for f in (getattr(params, "budget_filters", None) or ())
    )
    if budget_qs:
        url += f"&{budget_qs}"
    return url


def _fetch_html(url: str, extra_headers: Optional[dict[str, str]] = None) -> Optional[str]:
    r = _request("GET", url, expect_json=False, extra_headers=extra_headers)
    return r.text if r is not None else None


def fetch_listing(params: Any, max_urgency_hours: float = 9999) -> list[dict[str, Any]]:
    """Fetch the LAST listing page (most-expiring jobs) over HTTP, no Chrome.

    Returns a list of project dicts, or [] on any failure (caller falls back to
    the Selenium scrape). Kwork orders projects oldest-first, so the last page
    holds the most-expiring jobs — exactly the ones worth bidding on early.
    """
    if not CURL_CFFI_AVAILABLE:
        log_agent_action("KworkHTTP", "curl_cffi unavailable — skipping HTTP path", level="WARNING")
        return []
    try:
        # 1) page 1 to discover the last page number.
        html1 = _fetch_html(_build_url(params, 1))
        if not html1:
            return []
        data = _extract_state_data(html1)
        wl = (data or {}).get("wantsListData")
        if not wl:
            log_agent_action(
                "KworkHTTP",
                "stateData.wantsListData missing — cookies invalid or layout changed",
                level="WARNING",
            )
            return []
        last_page = (wl.get("pagination") or {}).get("last_page") or 1
        log_agent_action("KworkHTTP", f"🌐 [HTTP] page 1 ok — last_page={last_page}")

        # 2) fetch the last page (the expiring ones). On any failure here, return
        # [] so the caller falls back to Selenium — never serve stale page-1 data.
        if last_page > 1:
            html_last = _fetch_html(_build_url(params, last_page))
            if not html_last:
                log_agent_action("KworkHTTP", "⚠️ [HTTP] last-page fetch failed — returning []", level="WARNING")
                return []
            wl_last = (_extract_state_data(html_last) or {}).get("wantsListData")
            if not wl_last:
                log_agent_action("KworkHTTP", "⚠️ [HTTP] last-page stateData missing — returning []", level="WARNING")
                return []
            wl = wl_last

        wants = wl.get("wants") or []
        projects = [m for m in (_map_want(w, last_page) for w in wants) if m]

        if max_urgency_hours and max_urgency_hours < 9999:
            projects = [p for p in projects if p["urgency_hours"] <= max_urgency_hours]

        log_agent_action(
            "KworkHTTP",
            f"✅ [HTTP] Parsed {len(projects)} projects from last page (no Chrome)",
        )
        return projects
    except Exception as e:
        log_agent_action("KworkHTTP", f"❌ [HTTP] fetch_listing failed: {e}", level="ERROR")
        return []


def auth_probe() -> dict[str, Any]:
    """Diagnostic (conservative): ONE request through the rate limiter to find
    the favourites feed. Tries POST /projects (XHR + JSON accept, no body) and
    reports whether it returns the user's favouriteCategories + filtered wants.
    Read-only.
    """
    if not CURL_CFFI_AVAILABLE:
        return {"error": "curl_cffi unavailable"}

    base = "https://kwork.ru/projects"
    xhr = {
        "x-requested-with": "XMLHttpRequest",
        "accept": "application/json, text/plain, */*",
        "origin": "https://kwork.ru",
        "referer": f"{base}?a=1",
    }
    r = _request("POST", base, expect_json=True, extra_headers=xhr)  # single request

    info: dict[str, Any] = {"userId_cookie": _cookies_dict().get("userId"),
                            "request": "POST /projects (XHR, no body)"}
    if r is None:
        info["result"] = "no response (rate-limited, error, or anti-bot cooldown)"
        return info
    info["status"] = r.status_code
    info["ctype"] = (r.headers.get("content-type") or "")[:40]
    try:
        j = r.json()
    except Exception:
        info["is_json"] = False
        info["len"] = len(r.text or "")
        info["head"] = (r.text or "")[:200]
        return info
    info["is_json"] = True
    data = j.get("data", j) if isinstance(j, dict) else {}
    fc = data.get("favouriteCategories")
    info["fav_cat_count"] = len(fc) if isinstance(fc, (list, dict)) else fc
    info["fav_cat_ids"] = sorted(fc.keys()) if isinstance(fc, dict) else None
    info["wants_count"] = len(data.get("wants") or [])
    info["total"] = (data.get("pagination") or {}).get("total")
    info["sample"] = [{"id": w.get("id"), "title": w.get("name")} for w in (data.get("wants") or [])[:5]]
    return info
