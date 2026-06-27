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
from collections.abc import Callable
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
_MIN_INTERVAL = float(os.getenv("KWORK_MIN_REQUEST_INTERVAL", "5"))    # sec between requests
_HOURLY_CAP = int(os.getenv("KWORK_HOURLY_CAP", "120"))                # max requests / hour
_CHALLENGE_COOLDOWN = float(os.getenv("KWORK_CHALLENGE_COOLDOWN", "900"))  # backoff on challenge
# Kwork lists projects newest-first, and a project's time-left shrinks the older it
# is — so the soonest-expiring jobs sit on the LAST pages. We fetch page 1 (to learn
# last_page), then walk from last_page backward (most-expiring first), collecting
# until a page's minimum time-left climbs out of the urgency window, then stop.
# _MAX_PAGES_PER_GROUP caps the worst case (wide / no urgency filter) to protect the
# request budget (see _MIN_INTERVAL / _HOURLY_CAP).
_MAX_PAGES_PER_GROUP = int(os.getenv("KWORK_MAX_PAGES_PER_GROUP", "20"))
# Keep scanning this many pages past the first one that's fully out of the window —
# a guard against time-left spread within a single page (pages aren't perfectly sorted).
_STOP_BUFFER = int(os.getenv("KWORK_STOP_BUFFER_PAGES", "1"))

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
             data: Optional[dict] = None, extra_headers: Optional[dict] = None,
             use_cookies: bool = True):
    """Single choke point for every Kwork request: rate-limited + challenge-aware.

    `use_cookies=False` makes the request anonymous (the project search needs no
    login, so it stays decoupled from the account — search can never get the
    account flagged). Returns the curl_cffi response, or None (rate-limited,
    error, non-200, or a detected anti-bot challenge — which also arms a cooldown).
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
    cookies = _cookies_dict() if use_cookies else None
    try:
        if method == "POST":
            r = _creq.post(url, headers=headers, cookies=cookies,
                           impersonate=_IMPERSONATE, data=data, timeout=40)
        else:
            r = _creq.get(url, headers=headers, cookies=cookies,
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
        budget_value = float(price) if price is not None else None
    except (TypeError, ValueError):
        budget_value = None
    budget = f"до {int(budget_value)} ₽" if budget_value is not None else "не указан"
    # proposals: coerce to int|None to match the Selenium path's schema.
    kc = want.get("kwork_count")
    try:
        proposals = int(kc) if kc is not None else None
    except (TypeError, ValueError):
        proposals = None
    # hired = the client's hire rate % (user.data.wants_hired_percent).
    udata = (want.get("user") or {}).get("data") or {}
    try:
        hired = int(udata["wants_hired_percent"]) if udata.get("wants_hired_percent") is not None else None
    except (TypeError, ValueError):
        hired = None
    time_left = want.get("timeLeft") or ""
    urgency_hours = _urgency_hours_from_timeleft(time_left)
    return {
        "id": str(wid),
        "title": want.get("name") or "",
        "url": f"https://kwork.ru/projects/{wid}/view",
        "urgency": time_left,
        "urgency_hours": urgency_hours,
        # Numeric hours-remaining for the UI (sortable). 999.0 is our "unknown"
        # sentinel from _urgency_hours_from_timeleft → map to None so the card hides it.
        "timeLeft": round(urgency_hours, 2) if urgency_hours < 999 else None,
        "budget": budget,
        "description": _clean_desc(want.get("description")),
        "proposals": proposals,
        "hired": hired,
        "budget_value": budget_value,
        "category_id": str(want.get("category_id") or ""),
        "files": [
            {"url": f.get("url"), "fname": f.get("fname")}
            for f in (want.get("files") or [])
            if f.get("url")
        ],
        "page": page,
        "found_at": datetime.now().isoformat(),
    }


def _build_url(params: Any, page: int) -> str:
    """Public projects listing URL. Search needs no auth; category filtering is
    done service-side (Kwork's own favourites filter can't be replicated over
    HTTP — it requires an un-forgeable Qrator behavioural beacon)."""
    keywords = ",".join(params.keywords_list) if getattr(params, "keywords_list", None) else ""
    if keywords:
        return f"{config.KWORK_PROJECTS_URL}?keyword={quote_plus(keywords)}&page={page}"
    return f"{config.KWORK_PROJECTS_URL}?page={page}"


def _fetch_html(url: str, use_cookies: bool = True) -> Optional[str]:
    r = _request("GET", url, expect_json=False, use_cookies=use_cookies)
    return r.text if r is not None else None


def _wl_from_url(url: str) -> Optional[dict]:
    """Fetch one public listing URL and return its wantsListData (or None)."""
    html = _fetch_html(url, use_cookies=False)
    if not html:
        return None
    return (_extract_state_data(html) or {}).get("wantsListData")


def _page_min_urgency(wants: list[dict[str, Any]]) -> float:
    """Smallest known time-left (hours) on a page; 999.0 if none are known."""
    hrs = [_urgency_hours_from_timeleft(w.get("timeLeft") or "") for w in wants]
    known = [h for h in hrs if h < 999]
    return min(known) if known else 999.0


def _collect_expiring(url_for_page: Callable[[int], str], max_urgency_hours: float, label: str) -> list[dict[str, Any]]:
    """Collect wants from a newest-first listing, prioritising soonest-expiring.

    Fetches page 1 (for `last_page`), then walks from the last page backward —
    where the most-expiring jobs live — accumulating wants until a page's minimum
    time-left rises above `max_urgency_hours` (earlier pages are even less urgent,
    so we stop, with a small buffer for within-page spread). Bounded by
    `_MAX_PAGES_PER_GROUP`. `url_for_page(page:int) -> str` builds each page URL.
    """
    wl1 = _wl_from_url(url_for_page(1))
    if not wl1:
        return []
    collected: list[dict[str, Any]] = list(wl1.get("wants") or [])
    pag = wl1.get("pagination") or {}
    try:
        last_page = int(pag.get("last_page") or 1)
    except (TypeError, ValueError):
        last_page = 1

    # No urgency filter → "show everything", just bounded by the page cap.
    filtering = 0 < max_urgency_hours < 9999
    fetched = 1
    misses = 0
    for p in range(last_page, 1, -1):
        if fetched >= _MAX_PAGES_PER_GROUP:
            log_agent_action(
                "KworkHTTP",
                f"⚠️ [HTTP] {label}: page cap {_MAX_PAGES_PER_GROUP} reached "
                f"(last_page={last_page}) — results may be incomplete for a wide filter",
                level="WARNING",
            )
            break
        wl = _wl_from_url(url_for_page(p))
        fetched += 1
        if not wl:
            continue
        page_wants = wl.get("wants") or []
        if not page_wants:
            continue  # empty page (maintenance / sparse tail) — don't penalise the miss counter
        collected.extend(page_wants)
        if filtering:
            if _page_min_urgency(page_wants) > max_urgency_hours:
                misses += 1
                if misses > _STOP_BUFFER:
                    break
            else:
                misses = 0
    log_agent_action("KworkHTTP", f"🌐 [HTTP] {label}: scanned {fetched}/{last_page} page(s), {len(collected)} raw wants")
    return collected


def fetch_listing(params: Any, max_urgency_hours: float = 9999) -> list[dict[str, Any]]:
    """Fetch projects in the user's categories over public HTTP (no Chrome, no
    login) and keep the exact selected subcategories within the urgency window.

    Kwork's public listing filters by ?c=<id>. We fetch by TOP GROUP (one request
    per group that contains a selected subcategory — at most 7), newest first,
    then keep only the selected subcategory ids. Keyword searches and the
    no-filter case fall back to the plain paged listing. [] on failure.
    """
    if not CURL_CFFI_AVAILABLE:
        log_agent_action("KworkHTTP", "curl_cffi unavailable — skipping HTTP path", level="WARNING")
        return []
    try:
        from agents.kwork_categories import groups_for

        categories = set(getattr(params, "categories", ()) or ())
        keywords = ",".join(params.keywords_list) if getattr(params, "keywords_list", None) else ""

        collected: list[dict[str, Any]] = []
        scanned: list = []

        if categories and not keywords:
            groups = sorted(groups_for(categories))
            log_agent_action("KworkHTTP", f"🌐 [HTTP] fetching {len(groups)} category group(s): {groups} (urgency≤{max_urgency_hours}h)")
            for g in groups:
                collected.extend(_collect_expiring(
                    lambda page, g=g: f"{config.KWORK_PROJECTS_URL}?c={g}&page={page}",
                    max_urgency_hours,
                    f"group {g}",
                ))
                scanned.append(g)
        else:
            # keyword search or no category filter — plain paged listing
            collected.extend(_collect_expiring(
                lambda page: _build_url(params, page),
                max_urgency_hours,
                "keyword/all" if keywords else "all",
            ))
            scanned.append("kw" if keywords else "all")

        if not collected:
            log_agent_action("KworkHTTP", "⚠️ [HTTP] nothing fetched — returning []", level="WARNING")
            return []

        projects = [m for m in (_map_want(w, 0) for w in collected) if m]

        # Dedupe by url (a project can appear under group + overlapping pages).
        seen: set = set()
        projects = [p for p in projects if not (p["url"] in seen or seen.add(p["url"]))]

        if categories:
            projects = [p for p in projects if p["category_id"] in categories]
        if 0 < max_urgency_hours < 9999:
            projects = [p for p in projects if p["urgency_hours"] <= max_urgency_hours]

        log_agent_action(
            "KworkHTTP",
            f"✅ [HTTP] {len(projects)} projects "
            f"(scanned={scanned}, categories={'all' if not categories else len(categories)})",
        )
        return projects
    except Exception as e:
        log_agent_action("KworkHTTP", f"❌ [HTTP] fetch_listing failed: {e}", level="ERROR")
        return []


def fetch_project(url_or_id: str) -> Optional[dict[str, Any]]:
    """Parse a single Kwork project over public HTTP (no Chrome). Accepts a
    /projects/<id>/view URL, a new_offer?project=<id> URL, or a bare id. Returns
    the project dict (same schema as the listing) or None."""
    if not CURL_CFFI_AVAILABLE:
        return None
    s = (url_or_id or "").strip()
    m = (re.search(r"/projects/(\d+)", s) or re.search(r"project=(\d+)", s)
         or re.fullmatch(r"\s*(\d+)\s*", s))
    if not m:
        log_agent_action("KworkHTTP", f"⚠️ [HTTP] no project id in {s!r}", level="WARNING")
        return None
    pid = m.group(1)
    try:
        html = _fetch_html(f"{config.KWORK_BASE_URL}/projects/{pid}/view", use_cookies=False)
        if not html:
            return None
        want = (_extract_state_data(html) or {}).get("wantData")
        if not want:
            log_agent_action("KworkHTTP", "⚠️ [HTTP] wantData missing (project closed/removed?)", level="WARNING")
            return None
        project = _map_want(want, 0)
        if not project:
            return None
        project.setdefault("evaluation", {"score": 1.0, "reasons": [], "suitable": True})
        log_agent_action("KworkHTTP", f"✅ [HTTP] parsed project {pid}: {project.get('title','')[:50]}")
        return project
    except Exception as e:
        log_agent_action("KworkHTTP", f"❌ [HTTP] fetch_project failed: {e}", level="ERROR")
        return None
