from __future__ import annotations

from pydantic import BaseModel


class DmsItem(BaseModel):
    id: str
    name: str
    path: str
    is_folder: bool = False
    size: int | None = None
    mime_type: str | None = None
    modified_at: str | None = None
    is_read_only: bool | None = None
    version_label: str | None = None
    version_type: str | None = None
