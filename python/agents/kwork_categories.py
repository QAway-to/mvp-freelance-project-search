"""Kwork category taxonomy — top group id -> its subcategory ids.

Kwork's public listing filters by ?c=<id>: a subcategory id returns just that
subcategory, a top-group id returns the whole group. We fetch by group (few
requests) and then keep only the exact subcategories the user selected. Mirrors
the UI taxonomy in src/constants/kworkCategories.js.
"""

GROUP_SUBCATS: dict[str, set[str]] = {
    "17": {"44", "43", "273", "71", "59", "56", "72"},          # SEO и трафик
    "7": {"20", "76", "78", "300", "77", "23", "106"},          # Аудио, видео, съемка
    "83": {"64", "262", "55", "84", "265", "114", "65", "63"},  # Бизнес и жизнь
    "15": {"28", "24", "306", "90", "25", "286", "272", "68", "27", "270", "250"},  # Дизайн
    "11": {"79", "80", "38", "40", "39", "255", "41", "37", "81"},  # Разработка и IT
    "45": {"108", "113", "49", "47", "112", "46"},              # Соцсети и маркетинг
    "5": {"303", "75", "35", "74", "235", "73"},                # Тексты и переводы
}

_SUBCAT_TO_GROUP: dict[str, str] = {
    sub: group for group, subs in GROUP_SUBCATS.items() for sub in subs
}


def groups_for(subcat_ids) -> set[str]:
    """Top-group ids that contain any of the given subcategory ids."""
    return {_SUBCAT_TO_GROUP[s] for s in subcat_ids if s in _SUBCAT_TO_GROUP}
