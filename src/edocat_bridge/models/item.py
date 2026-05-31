from __future__ import annotations

from pydantic import BaseModel


class DmsItem(BaseModel):
    id: str
    name: str
    path: str
    is_folder: bool = False
    size: int | None = None
    mime_type: str | None = None
