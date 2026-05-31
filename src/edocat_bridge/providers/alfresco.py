from __future__ import annotations

import base64

from edocat_bridge.clients.alfresco_client import AlfrescoClient
from edocat_bridge.core.config_loader import load_provider_config
from edocat_bridge.core.credentials import resolve_alfresco_credentials
from edocat_bridge.core.errors import ProviderOperationError
from edocat_bridge.models.bridge import BridgeAuthContext
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

    def _runtime_credentials(self, auth: BridgeAuthContext | None) -> tuple[str | None, str | None, str | None]:
        credentials = resolve_alfresco_credentials(auth, self.client.base_url)
        return credentials.username, credentials.password, credentials.token

    def _ticket(self, auth: BridgeAuthContext | None) -> str | None:
        username, password, token = self._runtime_credentials(auth)
        if token:
            return token
        if username and password:
            try:
                return self.client.create_ticket(username, password)
            except Exception:
                return None
        return None

    def _live_node(self, path: str, auth: BridgeAuthContext | None, ticket: str | None = None) -> dict | None:
        ticket = ticket or self._ticket(auth)
        if not ticket:
            return None
        resolved = self._resolve_path(path)
        try:
            return self.client.get_node(ticket, resolved["node_id"])
        except Exception:
            return None

    def _target_parent_and_name(self, destination: str, ticket: str | None = None) -> tuple[str, str | None, str]:
        resolved = self._resolve_path(destination, ticket)
        is_file_like = "." in resolved["name"] and not destination.endswith("/")
        if is_file_like:
            return resolved["parent_id"], resolved["name"], resolved["path"]
        return resolved["node_id"], None, resolved["path"]

    def _item_from_entry(self, entry: dict, fallback_path: str | None = None) -> DmsItem:
        props = entry.get("properties", {}) if isinstance(entry, dict) else {}
        name = entry.get("name") or (fallback_path.rstrip("/").split("/")[-1] if fallback_path else "") or "/"
        path = fallback_path or entry.get("path", {}).get("name", "/") or "/"
        is_folder = entry.get("isFolder") if isinstance(entry.get("isFolder"), bool) else str(entry.get("nodeType", "")).endswith("folder")
        return DmsItem(
            id=str(entry.get("id") or self.client.node_id_from_path(path)),
            name=str(name),
            path=self.client.normalize_path(path),
            is_folder=bool(is_folder),
            size=entry.get("content", {}).get("sizeInBytes") if isinstance(entry.get("content"), dict) else None,
            mime_type=entry.get("content", {}).get("mimeType") if isinstance(entry.get("content"), dict) else props.get("cm:content.mimetype"),
        )

    def _resolve_path(self, path: str, ticket: str | None = None) -> dict[str, str]:
        normalized = self.client.normalize_path(path)
        parent_path = self.client.parent_path(normalized)
        node_id = self.client.node_id_from_path(normalized)
        parent_id = self.client.node_id_from_path(parent_path)
        name = normalized.rstrip("/").split("/")[-1] or "/"

        if ticket:
            try:
                live_node = self.client.resolve_node_by_relative_path(ticket, normalized)
                if live_node and live_node.get("id"):
                    node_id = str(live_node["id"])
            except Exception:
                pass
            try:
                live_parent = self.client.resolve_node_by_relative_path(ticket, parent_path)
                if live_parent and live_parent.get("id"):
                    parent_id = str(live_parent["id"])
            except Exception:
                pass

        return {
            "path": normalized,
            "node_id": node_id,
            "parent_path": parent_path,
            "parent_id": parent_id,
            "name": name,
        }

    def list_items(self, path: str, auth: BridgeAuthContext | None = None) -> ListingResult:
        ticket = self._ticket(auth)
        if ticket:
            resolved = self._resolve_path(path, ticket)
            try:
                response = self.client.get_children(ticket, resolved["node_id"])
                entries = response.get("list", {}).get("entries", [])
                items = [self._item_from_entry(item.get("entry", {}), None) for item in entries]
                return ListingResult(provider=self.name, path=resolved["path"], total=len(items), items=items)
            except Exception:
                pass
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
            "download": self.client.node_content_url("{nodeId}"),
            "upload": self.client.node_create_child_url("{parentId}"),
        }
        return mapping.get(operation)

    def stat_item(self, path: str, auth: BridgeAuthContext | None = None) -> DmsItem | None:
        ticket = self._ticket(auth)
        live_node = self._live_node(path, auth, ticket)
        if live_node and isinstance(live_node.get("entry"), dict):
            return self._item_from_entry(live_node["entry"], self.client.normalize_path(path))
        resolved = self._resolve_path(path, ticket)
        is_folder = resolved["path"] == "/" or path.endswith("/")
        return DmsItem(
            id=resolved["node_id"],
            name=resolved["name"],
            path=resolved["path"],
            is_folder=is_folder,
            mime_type=None if is_folder else "application/octet-stream",
        )

    def copy_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        ticket = self._ticket(auth)
        resolved = self._resolve_path(source, ticket)
        target_parent_id, target_name, destination_path = self._target_parent_and_name(destination, ticket)
        message = f"endpoint={self.client.node_copy_url(resolved['node_id'])};mode=preview"
        if ticket:
            try:
                self.client.copy_node(ticket, resolved["node_id"], target_parent_id, target_name)
                message = f"endpoint={self.client.node_copy_url(resolved['node_id'])};mode=live"
            except Exception as exc:
                message = f"endpoint={self.client.node_copy_url(resolved['node_id'])};mode=preview;warning={type(exc).__name__}"
        return OperationResult(
            success=True,
            operation="copy",
            provider=self.name,
            source=source,
            destination=destination_path,
            message=message,
        )

    def rename_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        ticket = self._ticket(auth)
        resolved = self._resolve_path(source, ticket)
        target_parent_id, target_name, destination_path = self._target_parent_and_name(destination, ticket)
        message = f"endpoint={self.client.node_move_url(resolved['node_id'])};mode=preview"
        if ticket:
            try:
                self.client.move_node(ticket, resolved["node_id"], target_parent_id, target_name)
                message = f"endpoint={self.client.node_move_url(resolved['node_id'])};mode=live"
            except Exception as exc:
                message = f"endpoint={self.client.node_move_url(resolved['node_id'])};mode=preview;warning={type(exc).__name__}"
        return OperationResult(
            success=True,
            operation="rename",
            provider=self.name,
            source=source,
            destination=destination_path,
            message=message,
        )

    def delete_item(self, target: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        ticket = self._ticket(auth)
        resolved = self._resolve_path(target, ticket)
        message = f"endpoint={self.client.node_delete_url(resolved['node_id'])};mode=preview"
        if ticket:
            try:
                self.client.delete_node(ticket, resolved["node_id"])
                message = f"endpoint={self.client.node_delete_url(resolved['node_id'])};mode=live"
            except Exception as exc:
                message = f"endpoint={self.client.node_delete_url(resolved['node_id'])};mode=preview;warning={type(exc).__name__}"
        return OperationResult(
            success=True,
            operation="delete",
            provider=self.name,
            source=target,
            message=message,
        )

    def make_dir(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        ticket = self._ticket(auth)
        resolved = self._resolve_path(path, ticket)
        message = f"endpoint={self.client.node_create_child_url(resolved['parent_id'])};mode=preview"
        if ticket:
            try:
                self.client.create_child_node(ticket, resolved["parent_id"], resolved["name"], is_folder=True)
                message = f"endpoint={self.client.node_create_child_url(resolved['parent_id'])};mode=live"
            except Exception as exc:
                message = f"endpoint={self.client.node_create_child_url(resolved['parent_id'])};mode=preview;warning={type(exc).__name__}"
        return OperationResult(
            success=True,
            operation="mkdir",
            provider=self.name,
            source=path,
            message=message,
        )

    def download_item(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        ticket = self._ticket(auth)
        resolved = self._resolve_path(path, ticket)
        message = f"endpoint={self.client.node_content_url(resolved['node_id'])};mode=preview"
        content_base64 = None
        mime_type = None
        size = None
        if ticket:
            try:
                raw_content, detected_mime = self.client.download_node_content(ticket, resolved["node_id"])
                content_base64 = base64.b64encode(raw_content).decode("ascii")
                mime_type = detected_mime
                size = len(raw_content)
                message = f"endpoint={self.client.node_content_url(resolved['node_id'])};mode=live"
            except Exception as exc:
                message = f"endpoint={self.client.node_content_url(resolved['node_id'])};mode=preview;warning={type(exc).__name__}"
        return OperationResult(
            success=True,
            operation="download",
            provider=self.name,
            source=resolved["path"],
            message=message,
            content_base64=content_base64,
            mime_type=mime_type,
            size=size,
        )

    def upload_item(self, destination: str, file_name: str, content_base64: str | None = None, overwrite: bool = False, auth: BridgeAuthContext | None = None) -> OperationResult:
        ticket = self._ticket(auth)
        resolved = self._resolve_path(destination, ticket)
        target_parent_id = resolved["parent_id"] if resolved["path"] != "/" and "." in resolved["name"] else resolved["node_id"]
        target_destination = f"{resolved['path'].rstrip('/')}/{file_name}" if resolved["path"] != "/" and "." not in resolved["name"] else resolved["path"]
        suffix = "?overwrite=true" if overwrite else ""
        content_state = "inline-base64" if content_base64 else "external-stream"
        message = f"endpoint={self.client.node_create_child_url(target_parent_id)}{suffix};content={content_state};mode=preview"
        if ticket:
            try:
                self.client.create_child_node(ticket, target_parent_id, file_name, is_folder=False, content_base64=content_base64)
                message = f"endpoint={self.client.node_create_child_url(target_parent_id)}{suffix};content={content_state};mode=live"
            except Exception as exc:
                message = f"endpoint={self.client.node_create_child_url(target_parent_id)}{suffix};content={content_state};mode=preview;warning={type(exc).__name__}"
        return OperationResult(
            success=True,
            operation="upload",
            provider=self.name,
            source=file_name,
            destination=target_destination,
            message=message,
        )
