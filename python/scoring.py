from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RawProject:
    id: str
    url: str
    title: str
    description: str
    price: Optional[int]
    time_left: Optional[int]
    hired: Optional[int]
    proposals: Optional[int]


def compute_scores(
    project: RawProject,
    keywords: str,
    time_left_filter: Optional[int] = None,
    proposals_max_filter: Optional[int] = None,
) -> dict:
    relevance = _relevance_score(project.title, project.description, keywords)
    time = _time_score(project.time_left, time_left_filter)
    proposals = _proposals_score(project.proposals, proposals_max_filter)
    total = round((relevance * 0.5) + (time * 0.3) + (proposals * 0.2))

    return {
        "relevance": relevance,
        "time": time,
        "proposals": proposals,
        "totalScore": total,
    }


def _relevance_score(title: str, description: str, keywords: str) -> int:
    kws = [k.strip().lower() for k in keywords.split() if k.strip()]
    text = f"{title} {description}".lower()
    if not kws:
        return 50
    matches = sum(1 for kw in kws if kw in text)
    ratio = matches / len(kws)
    return min(100, round(40 + ratio * 60))


def _time_score(time_left: Optional[int], filter_max: Optional[int]) -> int:
    if time_left is None:
        return 50
    # More time left = worse urgency score (we want urgent projects high)
    if time_left <= 6:
        base = 95
    elif time_left <= 12:
        base = 85
    elif time_left <= 24:
        base = 70
    elif time_left <= 48:
        base = 55
    else:
        base = 40

    if filter_max is not None and time_left <= filter_max:
        base = min(100, base + 10)

    return base


def _proposals_score(proposals: Optional[int], filter_max: Optional[int]) -> int:
    if proposals is None:
        return 50
    # Fewer proposals = better (less competition)
    if proposals == 0:
        base = 100
    elif proposals <= 3:
        base = 90
    elif proposals <= 7:
        base = 70
    elif proposals <= 15:
        base = 50
    else:
        base = 30

    if filter_max is not None and proposals <= filter_max:
        base = min(100, base + 5)

    return base
