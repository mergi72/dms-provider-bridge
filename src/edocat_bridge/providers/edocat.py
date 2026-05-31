from __future__ import annotations

import base64

from edocat_bridge.core.errors import ProviderOperationError
from edocat_bridge.clients.edocat_client import EdocatClient
from edocat_bridge.core.config_loader import load_provider_config
from edocat_bridge.models.bridge import BridgeAuthContext
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

    def _browse_root(self) -> str:
        root = str(self.config.get("doc_library", "/deals")).strip() or "/deals"
        if not root.startswith("/"):
            root = f"/{root}"
        return root.rstrip("/") or "/"

    def _resolve_path(self, path: str) -> str:
        normalized = path.strip() or "/"
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"

        root = self._browse_root()
        if normalized == "/":
            return root
        if normalized == root or normalized.startswith(f"{root}/"):
            return normalized
        return f"{root}{normalized}"

    def _runtime_credentials(self, auth: BridgeAuthContext | None) -> tuple[str | None, str | None]:
        if auth is None:
            return None, None
        username = auth.username or auth.credential_id
        password = auth.password or auth.token
        return username, password

    def _parent_and_name(self, path: str) -> tuple[str, str]:
        resolved = self._resolve_path(path).rstrip("/") or "/"
        if resolved == "/":
            return "/", ""
        parent = resolved.rsplit("/", 1)[0] or "/"
        name = resolved.split("/")[-1]
        return parent, name

    def _encode_if_needed(self, content: str | None) -> str | None:
        if content is None:
            return None
        if content == "":
            return ""
        return content

    def _normalize_node_path(self, node: dict) -> str:
        node_path = str(node.get("path") or "").strip()
        if not node_path:
            return ""
        if not node_path.startswith("/"):
            node_path = f"/{node_path}"
        return node_path.rstrip("/") or "/"

    def _find_exact_node(self, nodes: list[dict], resolved_path: str) -> dict | None:
        normalized_target = resolved_path.rstrip("/") or "/"
        target_name = normalized_target.split("/")[-1] or "/"

        for node in nodes:
            if self._normalize_node_path(node) == normalized_target:
                return node

        for node in nodes:
            if str(node.get("name") or "") == target_name:
                return node

        return None

    def _query_nodes(self, path: str, auth: BridgeAuthContext | None, include_content: bool = False) -> list[dict]:
        query_path = self._resolve_path(path).lstrip("/")
        username, password = self._runtime_credentials(auth)
        try:
            response = self.client.query_nodes(query_path, username=username, password=password, include_content=include_content)
        except Exception as exc:
            raise ProviderOperationError(f"eDoCat query failed for {path}: {exc}") from exc

        nodes = response.get("nodes", [])
        if not isinstance(nodes, list):
            raise ProviderOperationError("eDoCat query response has invalid 'nodes' payload.")
        return [node for node in nodes if isinstance(node, dict)]

    def _query_single_node(self, path: str, auth: BridgeAuthContext | None, include_content: bool = False) -> dict | None:
        resolved_path = self._resolve_path(path)
        try:
            nodes = self._query_nodes(path, auth, include_content=include_content)
            exact = self._find_exact_node(nodes, resolved_path)
            if exact is not None:
                return exact
        except ProviderOperationError:
            pass

        if resolved_path == "/":
            return None

        parent_path = resolved_path.rsplit("/", 1)[0] or "/"
        try:
            parent_nodes = self._query_nodes(parent_path, auth, include_content=include_content)
        except ProviderOperationError:
            return None

        return self._find_exact_node(parent_nodes, resolved_path)

    def _item_from_node(self, node: dict, fallback_path: str) -> DmsItem:
        node_path = str(node.get("path") or fallback_path)
        if node_path and not node_path.startswith("/"):
            node_path = f"/{node_path}"
        name = str(node.get("name") or node_path.rstrip("/").split("/")[-1] or "/")
        node_type = str(node.get("nodeType") or "")
        is_folder = node_type.lower().endswith("folder") or node_type.lower().endswith("basefolder")
        size = node.get("size")
        if not isinstance(size, int):
            size = None
        return DmsItem(
            id=str(node.get("uuid") or node.get("id") or name),
            name=name,
            path=node_path,
            is_folder=is_folder,
            size=size,
            mime_type=str(node.get("mimeType")) if node.get("mimeType") else None,
        )

    def list_items(self, path: str, auth: BridgeAuthContext | None = None) -> ListingResult:
        resolved_path = self._resolve_path(path)
        nodes = self._query_nodes(resolved_path, auth, include_content=False)
        items = [self._item_from_node(node, resolved_path) for node in nodes if isinstance(node, dict)]
        return ListingResult(provider=self.name, path=resolved_path, total=len(items), items=items)

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

    def stat_item(self, path: str, auth: BridgeAuthContext | None = None) -> DmsItem | None:
        resolved_path = self._resolve_path(path)
        node = self._query_single_node(resolved_path, auth, include_content=False)
        if node is not None:
            return self._item_from_node(node, resolved_path)

        if resolved_path == "/":
            return DmsItem(id="edo-root", name="/", path="/", is_folder=True)
        name = resolved_path.rstrip("/").split("/")[-1] or "/"
        return DmsItem(id=f"edo-{name}", name=name, path=resolved_path, is_folder=resolved_path.endswith("/"))

    def copy_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        source_path = self._resolve_path(source)
        destination_path = self._resolve_path(destination)
        source_node = self._query_single_node(source_path, auth, include_content=True)
        if source_node is None:
            raise ProviderOperationError(f"eDoCat copy failed: source not found: {source_path}")

        parent, name = self._parent_and_name(destination_path)
        payload: dict[str, object] = {
            "path": parent.lstrip("/"),
            "name": name,
            "nodeType": source_node.get("nodeType") or "ctbd:baseDoc",
            "props": source_node.get("props") or {},
            "tags": source_node.get("tags") or [],
        }
        if isinstance(source_node.get("content"), str):
            payload["content"] = source_node.get("content")
        if source_node.get("mimeType"):
            payload["mimeType"] = source_node.get("mimeType")
        if source_node.get("attachment"):
            payload["attachment"] = source_node.get("attachment")
        if source_node.get("relatedDocs"):
            payload["relatedDocs"] = source_node.get("relatedDocs")

        try:
            response = self.client.create_node(payload, username=username, password=password)
        except Exception as exc:
            raise ProviderOperationError(f"eDoCat copy failed for {source_path} -> {destination_path}: {exc}") from exc

        copied = response if isinstance(response, dict) else {}
        target_uuid = str(copied.get("uuid") or copied.get("id") or copied.get("name") or name)
        return OperationResult(
            success=True,
            operation="copy",
            provider=self.name,
            source=source_path,
            destination=destination_path,
            message=f"endpoint={self.bridge_endpoint_for('copy')};uuid={target_uuid};mode=live",
        )

    def rename_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        source_path = self._resolve_path(source)
        destination_path = self._resolve_path(destination)
        source_node = self._query_single_node(source_path, auth, include_content=False)
        if source_node is None:
            raise ProviderOperationError(f"eDoCat rename failed: source not found: {source_path}")

        parent, name = self._parent_and_name(destination_path)
        payload: dict[str, object] = {
            "uuid": str(source_node.get("uuid") or source_node.get("id") or ""),
            "path": parent.lstrip("/"),
            "name": name,
        }
        try:
            response = self.client.update_node(payload, username=username, password=password)
        except Exception as exc:
            raise ProviderOperationError(f"eDoCat rename failed for {source_path} -> {destination_path}: {exc}") from exc

        renamed = response if isinstance(response, dict) else {}
        target_uuid = str(renamed.get("uuid") or source_node.get("uuid") or source_node.get("id"))
        return OperationResult(
            success=True,
            operation="rename",
            provider=self.name,
            source=source_path,
            destination=destination_path,
            message=f"endpoint={self.bridge_endpoint_for('rename')};uuid={target_uuid};mode=live",
        )

    def delete_item(self, target: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        target_path = self._resolve_path(target)
        target_node = self._query_single_node(target_path, auth, include_content=False)
        if target_node is None:
            raise ProviderOperationError(f"eDoCat delete failed: target not found: {target_path}")

        uuid = str(target_node.get("uuid") or target_node.get("id") or "")
        try:
            self.client.delete_nodes([uuid], username=username, password=password)
        except Exception as exc:
            raise ProviderOperationError(f"eDoCat delete failed for {target_path}: {exc}") from exc
        return OperationResult(
            success=True,
            operation="delete",
            provider=self.name,
            source=target_path,
            message=f"endpoint={self.bridge_endpoint_for('delete')};uuid={uuid};mode=live",
        )

    def make_dir(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        resolved_path = self._resolve_path(path)
        parent, name = self._parent_and_name(resolved_path)
        payload: dict[str, object] = {
            "path": parent.lstrip("/"),
            "name": name,
            "nodeType": self.config.get("nodeType", {}).get("folder", "ctfd:baseFolder"),
        }
        try:
            response = self.client.create_node(payload, username=username, password=password)
        except Exception as exc:
            raise ProviderOperationError(f"eDoCat mkdir failed for {resolved_path}: {exc}") from exc

        created = response if isinstance(response, dict) else {}
        target_uuid = str(created.get("uuid") or created.get("id") or created.get("name") or name)
        return OperationResult(
            success=True,
            operation="mkdir",
            provider=self.name,
            source=resolved_path,
            message=f"endpoint={self.bridge_endpoint_for('mkdir')};uuid={target_uuid};mode=live",
        )

    def download_item(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        resolved_path = self._resolve_path(path)
        node = self._query_single_node(resolved_path, auth, include_content=True)
        if node is None:
            raise ProviderOperationError(f"eDoCat download found no document for {resolved_path}.")

        content = node.get("content")
        if not isinstance(content, str):
            raise ProviderOperationError(f"eDoCat download returned no content for {resolved_path}.")

        mime_type = str(node.get("mimeType")) if node.get("mimeType") else None
        size = len(content)
        return OperationResult(
            success=True,
            operation="download",
            provider=self.name,
            source=resolved_path,
            message=f"endpoint={self.client.endpoint_url('query')};content=live",
            content_base64=content,
            mime_type=mime_type,
            size=size,
        )

    def upload_item(self, destination: str, file_name: str, content_base64: str | None = None, overwrite: bool = False, auth: BridgeAuthContext | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        resolved_destination = self._resolve_path(destination)
        target = f"{resolved_destination.rstrip('/')}/{file_name}" if resolved_destination != "/" else f"/{file_name}"
        parent, name = self._parent_and_name(target)
        payload: dict[str, object] = {
            "path": parent.lstrip("/"),
            "name": name,
            "content": self._encode_if_needed(content_base64),
            "nodeType": "ctbd:baseDoc",
        }
        if overwrite:
            payload["autoRename"] = False
        try:
            response = self.client.create_node(payload, username=username, password=password)
        except Exception as exc:
            raise ProviderOperationError(f"eDoCat upload failed for {target}: {exc}") from exc

        created = response if isinstance(response, dict) else {}
        target_uuid = str(created.get("uuid") or created.get("id") or created.get("name") or name)
        return OperationResult(
            success=True,
            operation="upload",
            provider=self.name,
            source=file_name,
            destination=target,
            message=f"endpoint={self.client.endpoint_url('node')};uuid={target_uuid};mode=live",
        )
