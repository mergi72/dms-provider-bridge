from __future__ import annotations

from edocat_bridge.clients.alfresco_client import AlfrescoClient
from edocat_bridge.core.config_loader import load_provider_config
from edocat_bridge.models.item import DmsItem
from edocat_bridge.models.listing import ListingResult
from edocat_bridge.models.operation import OperationResult
from edocat_bridge.providers.base import Provider


class AlfrescoProvider(Provider):
    name = "alfresco"
    upstream_auth_scheme = "ticket"

    def __init__(self) -> None:
        self.config = load_provider_config(self.name)
        self.client = AlfrescoClient.from_config(self.config)

    def list_items(self, path: str) -> ListingResult:
        sample = DmsItem(id="alf-1", name="sample.txt", path=f"{path.rstrip('/')}/sample.txt")
        return ListingResult(provider=self.name, path=path, total=1, items=[sample])

    def bridge_endpoint_for(self, operation: str) -> str | None:
        mapping = {
            "list": self.client.endpoint_url("nodes", "repo_root"),
            "stat": self.client.endpoint_url("nodes", "repo_root"),
            "copy": self.client.endpoint_url("nodes", "repo_root"),
            "rename": self.client.endpoint_url("nodes", "repo_root"),
            "delete": self.client.endpoint_url("nodes", "repo_root"),
            "mkdir": self.client.endpoint_url("nodes", "repo_root"),
        }
        return mapping.get(operation)

    def stat_item(self, path: str) -> DmsItem | None:
        if path == "/":
            return DmsItem(id="alf-root", name="/", path="/", is_folder=True)
        name = path.rstrip("/").split("/")[-1] or "/"
        return DmsItem(id=f"alf-{name}", name=name, path=path, is_folder=path.endswith("/"))

    def copy_item(self, source: str, destination: str) -> OperationResult:
        return OperationResult(
            success=True,
            operation="copy",
            provider=self.name,
            source=source,
            destination=destination,
            message=f"endpoint={self.bridge_endpoint_for('copy')}",
        )

    def rename_item(self, source: str, destination: str) -> OperationResult:
        return OperationResult(
            success=True,
            operation="rename",
            provider=self.name,
            source=source,
            destination=destination,
            message=f"endpoint={self.bridge_endpoint_for('rename')}",
        )

    def delete_item(self, target: str) -> OperationResult:
        return OperationResult(
            success=True,
            operation="delete",
            provider=self.name,
            source=target,
            message=f"endpoint={self.bridge_endpoint_for('delete')}",
        )

    def make_dir(self, path: str) -> OperationResult:
        return OperationResult(
            success=True,
            operation="mkdir",
            provider=self.name,
            source=path,
            message=f"endpoint={self.bridge_endpoint_for('mkdir')}",
        )
