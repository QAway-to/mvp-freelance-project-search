from dataclasses import dataclass


@dataclass(frozen=True)
class SearchParams:
    keywords_list: tuple[str, ...]
    max_urgency_hours: int
    budget_filters: tuple[int, ...] = ()
    # Kwork category ids to keep (service-side filter, driven by the UI). Empty = all.
    categories: tuple[str, ...] = ()

    @property
    def keyword(self) -> str:
        return self.keywords_list[0] if self.keywords_list else ""
