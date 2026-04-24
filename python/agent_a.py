import asyncio
import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings, REQUEST_HEADERS
from scoring import RawProject, compute_scores

logger = logging.getLogger(__name__)

SEMAPHORE = asyncio.Semaphore(3)


def _make_headers() -> dict:
    headers = dict(REQUEST_HEADERS)
    if settings.kwork_cookie:
        headers["Cookie"] = settings.kwork_cookie
    return headers


def _build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.request_timeout,
        headers=_make_headers(),
        follow_redirects=True,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
)
async def _fetch(client: httpx.AsyncClient, url: str) -> str:
    async with SEMAPHORE:
        response = await client.get(url)
        response.raise_for_status()
        await asyncio.sleep(1.0 / settings.kwork_rate_limit_rps)
        return response.text


def _parse_price(text: str) -> Optional[int]:
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None


def _parse_time_left(text: str) -> Optional[int]:
    """Convert Kwork time string to hours."""
    text = text.lower().strip()
    if not text:
        return None
    m = re.search(r"(\d+)\s*(д|дн|день|дней|сут)", text)
    if m:
        return int(m.group(1)) * 24
    m = re.search(r"(\d+)\s*(ч|час|часа|часов)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(мин|минут)", text)
    if m:
        return int(m.group(1)) // 60
    return None


def _extract_project_id(url: str) -> Optional[str]:
    m = re.search(r"/projects/(\d+)/view", url)
    return m.group(1) if m else None


def _parse_listing_cards(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.wants-card")
    if not cards:
        # Fallback selector — Kwork sometimes uses different class names
        cards = soup.select("div[class*='wants-card']")

    projects = []
    for card in cards:
        try:
            title_el = card.select_one("a.wants-card__header-title, h2 a, .project-title a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if not href.startswith("http"):
                href = base_url.rstrip("/") + href

            pid = _extract_project_id(href)
            if not pid:
                continue

            desc_el = card.select_one(".wants-card__description, .project-description")
            description = desc_el.get_text(strip=True) if desc_el else ""

            price_el = card.select_one(".wants-card__price, .project-price")
            price = _parse_price(price_el.get_text()) if price_el else None

            time_el = card.select_one(".wants-card__time, .project-time, [class*='time-left']")
            time_left = _parse_time_left(time_el.get_text()) if time_el else None

            proposals_el = card.select_one(".wants-card__stats, [class*='proposals']")
            proposals = None
            if proposals_el:
                m = re.search(r"(\d+)", proposals_el.get_text())
                proposals = int(m.group(1)) if m else None

            projects.append({
                "id": pid,
                "url": href,
                "title": title,
                "description": description,
                "price": price,
                "time_left": time_left,
                "hired": None,
                "proposals": proposals,
            })
        except Exception as exc:
            logger.warning("Failed to parse listing card: %s", exc)

    return projects


def _parse_project_page(html: str, url: str, pid: str) -> Optional[dict]:
    soup = BeautifulSoup(html, "lxml")

    try:
        title_el = soup.select_one("h1.wants-view__header, h1[class*='header'], .breadcrumbs__h1")
        title = title_el.get_text(strip=True) if title_el else ""

        desc_el = soup.select_one(".wants-view__description, .project-description, [class*='description']")
        description = desc_el.get_text(strip=True) if desc_el else ""

        price_el = soup.select_one(".wants-view__price, [class*='price']")
        price = _parse_price(price_el.get_text()) if price_el else None

        time_el = soup.select_one("[class*='time-left'], .wants-view__time")
        time_left = _parse_time_left(time_el.get_text()) if time_el else None

        hired = None
        hired_el = soup.select_one("[class*='hired'], [class*='percent']")
        if hired_el:
            m = re.search(r"(\d+)", hired_el.get_text())
            hired = int(m.group(1)) if m else None

        proposals_el = soup.select_one("[class*='proposals'], [class*='отклик']")
        proposals = None
        if proposals_el:
            m = re.search(r"(\d+)", proposals_el.get_text())
            proposals = int(m.group(1)) if m else None

        if not title:
            logger.warning("PARSE_FAILED: no title found at %s", url)
            return None

        return {
            "id": pid,
            "url": url,
            "title": title,
            "description": description,
            "price": price,
            "time_left": time_left,
            "hired": hired,
            "proposals": proposals,
        }
    except Exception as exc:
        logger.warning("PARSE_FAILED at %s: %s", url, exc)
        return None


async def search(
    keywords: str,
    category: int = 41,
    time_left_filter: Optional[int] = None,
    hired_min: Optional[int] = None,
    proposals_max: Optional[int] = None,
    limit: int = 20,
) -> list[dict]:
    params = {"c": category, "keyword": keywords}
    search_url = str(httpx.URL(f"{settings.kwork_base_url}/projects", params=params))

    async with _build_client() as client:
        try:
            html = await _fetch(client, search_url)
        except Exception as exc:
            logger.error("Search fetch failed: %s", exc)
            return []

        cards = _parse_listing_cards(html, settings.kwork_base_url)
        logger.info("Found %d cards for query=%r category=%d", len(cards), keywords, category)

        # Enrich top cards with full project page for hired %
        enrich_tasks = []
        for card in cards[:min(limit, len(cards))]:
            enrich_tasks.append(_enrich_card(client, card))

        enriched = await asyncio.gather(*enrich_tasks, return_exceptions=True)

    results = []
    for raw in enriched:
        if isinstance(raw, Exception) or raw is None:
            continue

        rp = RawProject(
            id=raw["id"],
            url=raw["url"],
            title=raw["title"],
            description=raw["description"],
            price=raw.get("price"),
            time_left=raw.get("time_left"),
            hired=raw.get("hired"),
            proposals=raw.get("proposals"),
        )

        if time_left_filter is not None and rp.time_left is not None:
            if rp.time_left > time_left_filter:
                continue
        if hired_min is not None and rp.hired is not None:
            if rp.hired < hired_min:
                continue
        if proposals_max is not None and rp.proposals is not None:
            if rp.proposals > proposals_max:
                continue

        scores = compute_scores(rp, keywords, time_left_filter, proposals_max)
        results.append({
            "id": rp.id,
            "url": rp.url,
            "title": rp.title,
            "description": rp.description,
            "price": rp.price,
            "timeLeft": rp.time_left,
            "hired": rp.hired,
            "proposals": rp.proposals,
            "scores": scores,
        })

    results.sort(key=lambda p: p["scores"]["totalScore"], reverse=True)
    return results


async def _enrich_card(client: httpx.AsyncClient, card: dict) -> Optional[dict]:
    pid = card["id"]
    url = card["url"]
    try:
        html = await _fetch(client, url)
        enriched = _parse_project_page(html, url, pid)
        if enriched:
            return enriched
    except Exception as exc:
        logger.warning("Enrich failed for %s: %s", url, exc)
    return card


async def parse_project(url: str) -> Optional[dict]:
    pid = _extract_project_id(url)
    if not pid:
        return None

    async with _build_client() as client:
        try:
            html = await _fetch(client, url)
        except Exception as exc:
            logger.error("Parse fetch failed for %s: %s", url, exc)
            return None

    raw = _parse_project_page(html, url, pid)
    if not raw:
        return None

    rp = RawProject(
        id=raw["id"],
        url=raw["url"],
        title=raw["title"],
        description=raw["description"],
        price=raw.get("price"),
        time_left=raw.get("time_left"),
        hired=raw.get("hired"),
        proposals=raw.get("proposals"),
    )
    scores = compute_scores(rp, "")

    return {
        "id": rp.id,
        "url": rp.url,
        "title": rp.title,
        "description": rp.description,
        "price": rp.price,
        "timeLeft": rp.time_left,
        "hired": rp.hired,
        "proposals": rp.proposals,
        "scores": scores,
    }
