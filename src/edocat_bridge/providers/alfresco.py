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

    def _resolve_path(self, path: str) -> dict[str, str]:
        normalized = self.client.normalize_path(path)
        node_id = self.client.node_id_from_path(normalized)
        parent_path = self.client.parent_path(normalized)
        parent_id = self.client.node_id_from_path(parent_path)
        name = normalized.rstrip("/").split("/")[-1] or "/"
        return {
            "path": normalized,
            "node_id": node_id,
            "parent_path": parent_path,
            "parent_id": parent_id,
            "name": name,
        }

    def list_items(self, path: str) -> ListingResult:
        resolved = self._resolve_path(path)
        normalized = resolved["path"]
        folder_path = f"{normalized.rstrip('/')}/documents" if normalized != "/" else "/documents"
        file_path = f"{normalized.rstrip('/')}/sample.txt" if normalized != "/" else "/sample.txt"
        items = [
            DmsItem(
                id=self.client.node_id_from_path(folder_path),
                name="documents",
                path=folder_path,
                is_folder=True,
            ),
            DmsItem(
                id=self.client.node_id_from_path(file_path),
                name="sample.txt",
                path=file_path,
                is_folder=False,
                mime_type="text/plain",
            ),
        ]
        return ListingResult(provider=self.name, path=normalized, total=len(items), items=items)

    def bridge_endpoint_for(self, operation: str) -> str | None:
        mapping = {
            "list": self.client.search_nodes_url(),
            "stat": self.client.node_by_id_url("{nodeId}"),
            "copy": self.client.node_copy_url("{nodeId}"),
            "rename": self.client.node_move_url("{nodeId}"),
            "delete": self.client.node_delete_url("{nodeId}"),
            "mkdir": self.client.node_create_child_url("{parentId}"),
        }
        return mapping.get(operation)

    def stat_item(self, path: str) -> DmsItem | None:
        resolved = self._resolve_path(path)
        is_folder = resolved["path"] == "/" or path.endswith("/")
        return DmsItem(
            id=resolved["node_id"],
            name=resolved["name"],
            path=resolved["path"],
            is_folder=is_folder,
            mime_type=None if is_folder else "application/octet-stream",
        )

    def copy_item(self, source: str, destination: str) -> OperationResult:
        resolved = self._resolve_path(source)
        return OperationResult(
            success=True,
            operation="copy",
            provider=self.name,
            source=source,
            destination=destination,
            message=f"endpoint={self.client.node_copy_url(resolved['node_id'])}",
        )

    def rename_item(self, source: str, destination: str) -> OperationResult:
        resolved = self._resolve_path(source)
        return OperationResult(
            success=True,
            operation="rename",
            provider=self.name,
            source=source,
            destination=destination,
            message=f"endpoint={self.client.node_move_url(resolved['node_id'])}",
        )

    def delete_item(self, target: str) -> OperationResult:
        resolved = self._resolve_path(target)
        return OperationResult(
            success=True,
            operation="delete",
            provider=self.name,
            source=target,
            message=f"endpoint={self.client.node_delete_url(resolved['node_id'])}",
        )

    def make_dir(self, path: str) -> OperationResult:
        resolved = self._resolve_path(path)
        return OperationResult(
            success=True,
            operation="mkdir",
            provider=self.name,
            source=path,
            message=f"endpoint={self.client.node_create_child_url(resolved['parent_id'])}",
        )
