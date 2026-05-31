from __future__ import annotations

from edocat_bridge.clients.edocat_client import EdocatClient
from edocat_bridge.core.config_loader import load_provider_config
from edocat_bridge.models.item import DmsItem
from edocat_bridge.models.listing import ListingResult
from edocat_bridge.models.operation import OperationResult
from edocat_bridge.providers.base import Provider


class EdocatProvider(Provider):
    name = "edocat"
    upstream_auth_scheme = "basic"

    def __init__(self) -> None:
        self.config = load_provider_config(self.name)
        self.client = EdocatClient.from_config(self.config)

    def list_items(self, path: str) -> ListingResult:
        sample = DmsItem(id="edo-1", name="welcome.pdf", path=f"{path.rstrip('/')}/welcome.pdf")
        return ListingResult(provider=self.name, path=path, total=1, items=[sample])

    def bridge_endpoint_for(self, operation: str) -> str | None:
        mapping = {
            "list": self.client.endpoint_url("query"),
            "stat": self.client.endpoint_url("query"),
            "copy": self.client.endpoint_url("node"),
            "rename": self.client.endpoint_url("node"),
            "delete": self.client.endpoint_url("node"),
            "mkdir": self.client.endpoint_url("node"),
            "download": self.client.endpoint_url("query"),
            "upload": self.client.endpoint_url("node"),
        }
        return mapping.get(operation)

    def stat_item(self, path: str) -> DmsItem | None:
        if path == "/":
            return DmsItem(id="edo-root", name="/", path="/", is_folder=True)
        name = path.rstrip("/").split("/")[-1] or "/"
        return DmsItem(id=f"edo-{name}", name=name, path=path, is_folder=path.endswith("/"))

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

    def download_item(self, path: str) -> OperationResult:
        return OperationResult(
            success=True,
            operation="download",
            provider=self.name,
            source=path,
            message=f"endpoint={self.client.endpoint_url('query')}",
        )

    def upload_item(self, destination: str, file_name: str, content_base64: str | None = None, overwrite: bool = False) -> OperationResult:
        target = f"{destination.rstrip('/')}/{file_name}" if destination != "/" else f"/{file_name}"
        suffix = ";overwrite=true" if overwrite else ""
        content_state = "inline-base64" if content_base64 else "external-stream"
        return OperationResult(
            success=True,
            operation="upload",
            provider=self.name,
            source=file_name,
            destination=target,
            message=f"endpoint={self.client.endpoint_url('node')}{suffix};content={content_state}",
        )
