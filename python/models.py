from typing import Optional
from pydantic import BaseModel, field_validator


class SearchRequest(BaseModel):
    keywords: str
    category: int = 41
    timeLeft: Optional[int] = None
    hiredMin: Optional[int] = None
    proposalsMax: Optional[int] = None
    limit: int = 20

    @field_validator("keywords")
    @classmethod
    def keywords_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("keywords must not be empty")
        return v.strip()

    @field_validator("category")
    @classmethod
    def category_valid(cls, v: int) -> int:
        from config import VALID_CATEGORY_IDS
        if v not in VALID_CATEGORY_IDS:
            raise ValueError(f"category {v} is not in allowed list")
        return v


class ParseRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def url_is_kwork(cls, v: str) -> str:
        import re
        pattern = r"^https://kwork\.ru/projects/(\d+)/view$"
        if not re.fullmatch(pattern, v.strip()):
            raise ValueError("url must match https://kwork.ru/projects/ID/view")
        return v.strip()


class Scores(BaseModel):
    relevance: int
    time: int
    proposals: int
    totalScore: int


class Project(BaseModel):
    id: str
    url: str
    title: str
    description: str
    price: Optional[int]
    timeLeft: Optional[int]
    hired: Optional[int]
    proposals: Optional[int]
    scores: Scores


class Meta(BaseModel):
    total: int
    took_ms: int


class SearchResponse(BaseModel):
    success: bool
    data: list[Project]
    meta: Meta
    error: Optional[str] = None


class ParseResponse(BaseModel):
    success: bool
    data: Optional[Project] = None
    error: Optional[str] = None
