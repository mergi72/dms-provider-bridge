from __future__ import annotations

from pydantic import BaseModel, Field

from dms_provider_bridge.models.item import DmsItem


class SearchResult(BaseModel):
    connection: str
    path: str
    query: str
    total: int = Field(ge=0)
    returned: int = Field(ge=0)
    items: list[DmsItem]
    truncated: bool = False


def select_unique_items(items: list[DmsItem], max_results: int, files_only: bool) -> list[DmsItem]:
    selected: list[DmsItem] = []
    seen: set[str] = set()
    for item in items:
        if files_only and item.is_folder:
            continue
        identity = item.id.strip() or item.path.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        selected.append(item)
        if len(selected) >= max_results:
            break
    return selected
