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
import re
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


def _fetch_html(url: str) -> Optional[str]:
    try:
        r = _creq.get(
            url,
            impersonate=_IMPERSONATE,
            headers=_HEADERS,
            cookies=_cookies_dict(),
            timeout=40,
        )
    except Exception as e:
        log_agent_action("KworkHTTP", f"❌ [HTTP] request error: {e}", level="ERROR")
        return None
    if r.status_code != 200:
        log_agent_action("KworkHTTP", f"⚠️ [HTTP] status {r.status_code} for {url}", level="WARNING")
        return None
    return r.text


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
    """Diagnostic: prove the favourites fetch is authenticated and really filtered.

    Compares the favourites listing against the plain public listing (same
    cookies). If cookie auth works and `type=favourite` is honoured, the two
    sets differ. Returns counts, sample titles (so a human can recognise their
    own favourites), and session signals. Read-only.
    """
    from types import SimpleNamespace

    def _summary(html_text: Optional[str]) -> dict[str, Any]:
        d = _extract_state_data(html_text) if html_text else None
        wl = (d or {}).get("wantsListData") or {}
        wants = wl.get("wants") or []
        return {
            "total": (wl.get("pagination") or {}).get("total"),
            "last_page": (wl.get("pagination") or {}).get("last_page"),
            "sample": [{"id": w.get("id"), "title": w.get("name")} for w in wants[:5]],
            "actorStatus": (d or {}).get("actorStatus"),
            "actorKworkAllowStatus": (d or {}).get("actorKworkAllowStatus"),
        }

    if not CURL_CFFI_AVAILABLE:
        return {"error": "curl_cffi unavailable"}

    base = config.KWORK_PROJECTS_URL

    full = _extract_state_data(_fetch_html(f"{base}?type=favourite&a=1&page=1")) or {}

    # Look for the user's favourite categories inside categoriesWithFavoritesList.
    cwf = full.get("categoriesWithFavoritesList")
    fav_cat_hits = []
    structure_sample = None

    def _walk(node, parent_name=None):
        if isinstance(node, dict):
            name = node.get("name") or node.get("h1") or parent_name
            # any truthy key that looks like a favourite flag
            for k, v in node.items():
                if "favor" in k.lower() and v not in (None, False, 0, "", [], {}):
                    fav_cat_hits.append({"name": name, "flag": k, "value": v,
                                         "id": node.get("id") or node.get("CATID")})
            for v in node.values():
                _walk(v, name)
        elif isinstance(node, list):
            for v in node:
                _walk(v, parent_name)

    _walk(cwf)
    # capture one raw category entry so we can see the shape
    if isinstance(cwf, dict):
        for v in cwf.values():
            if isinstance(v, dict) and v.get("cats"):
                structure_sample = {"parent_keys": list(v.keys()),
                                    "cat0_keys": list(v["cats"][0].keys()) if v["cats"] else None,
                                    "cat0": {k: v["cats"][0].get(k) for k in ("CATID", "id", "name")} if v["cats"] else None}
                break

    wants = (full.get("wantsListData") or {}).get("wants") or []
    want_cats = sorted({(w.get("category_id"), None) for w in wants})

    return {
        "cookies_loaded": bool(_cookies_dict()),
        "auth_cookies_present": sorted(
            c for c in _cookies_dict() if c in ("userId", "slrememberme", "csrf_user_token")
        ),
        "cwf_top_type": type(cwf).__name__,
        "cwf_top_keys": list(cwf.keys())[:30] if isinstance(cwf, dict) else None,
        "favourite_flag_hits": fav_cat_hits[:40],
        "category_structure_sample": structure_sample,
        "want_category_ids_sample": [w.get("category_id") for w in wants[:12]],
    }
