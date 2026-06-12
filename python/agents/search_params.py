from dataclasses import dataclass


@dataclass(frozen=True)
class SearchParams:
    keywords_list: tuple[str, ...]
    max_urgency_hours: int
    budget_filters: tuple[int, ...] = ()

    @property
    def keyword(self) -> str:
        return self.keywords_list[0] if self.keywords_list else ""
