from __future__ import annotations

from edocat_bridge.models.item import DmsItem
from edocat_bridge.models.listing import ListingResult
from edocat_bridge.models.operation import OperationResult
from edocat_bridge.providers.base import Provider


class FsoProvider(Provider):
    name = "fso"
    upstream_auth_scheme = "none"

    def list_items(self, path: str) -> ListingResult:
        return ListingResult(provider=self.name, path=path, total=0, items=[])

    def bridge_endpoint_for(self, operation: str) -> str | None:
        return None

    def stat_item(self, path: str) -> DmsItem | None:
        if path == "/":
            return DmsItem(id="fso-root", name="/", path="/", is_folder=True)
        name = path.rstrip("/").split("/")[-1] or "/"
        return DmsItem(id=f"fso-{name}", name=name, path=path, is_folder=path.endswith("/"))

    def copy_item(self, source: str, destination: str) -> OperationResult:
        return OperationResult(success=True, operation="copy", provider=self.name, source=source, destination=destination)

    def rename_item(self, source: str, destination: str) -> OperationResult:
        return OperationResult(success=True, operation="rename", provider=self.name, source=source, destination=destination)

    def delete_item(self, target: str) -> OperationResult:
        return OperationResult(success=True, operation="delete", provider=self.name, source=target)

    def make_dir(self, path: str) -> OperationResult:
        return OperationResult(success=True, operation="mkdir", provider=self.name, source=path)
