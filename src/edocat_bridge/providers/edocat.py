from __future__ import annotations

import base64
from urllib.error import HTTPError
from urllib.parse import quote

from edocat_bridge.core.errors import AuthenticationError, ProviderOperationError
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

    def _public_path(self, path: str) -> str:
        normalized = (path or "").strip() or "/"
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        normalized = normalized.rstrip("/") or "/"

        root = self._browse_root()
        if normalized == root:
            return "/"
        if root != "/" and normalized.startswith(f"{root}/"):
            public_path = normalized[len(root):]
            return public_path if public_path.startswith("/") else f"/{public_path}"
        return normalized

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

    def _node_type_config(self) -> dict[str, str]:
        value = self.config.get("nodeType", {})
        return value if isinstance(value, dict) else {}

    def _document_node_type(self) -> str:
        node_type_cfg = self._node_type_config()
        return (
            node_type_cfg.get("baseDoc")
            or node_type_cfg.get("file")
            or "ctbd:baseDoc"
        )

    def _copy_max_nodes(self) -> int:
        copy_cfg = self.config.get("copy", {})
        if isinstance(copy_cfg, dict):
            value = copy_cfg.get("maxNodes")
            if isinstance(value, int) and value > 0:
                return value
        return 200

    def _delete_max_nodes(self) -> int:
        delete_cfg = self.config.get("delete", {})
        if isinstance(delete_cfg, dict):
            value = delete_cfg.get("maxNodes")
            if isinstance(value, int) and value > 0:
                return value
        return self._copy_max_nodes()

    def _download_max_bytes(self) -> int:
        download_cfg = self.config.get("download", {})
        if isinstance(download_cfg, dict):
            value = download_cfg.get("maxBase64Bytes")
            if isinstance(value, int) and value > 0:
                return value

        transfer_cfg = self.config.get("transfer", {})
        if isinstance(transfer_cfg, dict):
            value = transfer_cfg.get("maxBase64Bytes")
            if isinstance(value, int) and value > 0:
                return value
        return 20 * 1024 * 1024

    def _download_max_nodes(self) -> int:
        download_cfg = self.config.get("download", {})
        if isinstance(download_cfg, dict):
            value = download_cfg.get("maxNodes")
            if isinstance(value, int) and value > 0:
                return value

        transfer_cfg = self.config.get("transfer", {})
        if isinstance(transfer_cfg, dict):
            value = transfer_cfg.get("maxNodes")
            if isinstance(value, int) and value > 0:
                return value
        return 500

    def _download_zip_endpoint(self) -> str | None:
        download_cfg = self.config.get("download", {})
        if not isinstance(download_cfg, dict):
            return None
        endpoint = download_cfg.get("zipEndpoint")
        if isinstance(endpoint, str):
            endpoint = endpoint.strip()
            if endpoint:
                return endpoint
        return None

    def _download_zip_method(self) -> str:
        download_cfg = self.config.get("download", {})
        if isinstance(download_cfg, dict):
            method = str(download_cfg.get("zipMethod") or "POST").strip().upper()
            if method in {"GET", "POST"}:
                return method
        return "POST"

    def _download_zip_content_type(self) -> str:
        download_cfg = self.config.get("download", {})
        if isinstance(download_cfg, dict):
            content_type = download_cfg.get("zipContentType")
            if isinstance(content_type, str) and content_type.strip():
                return content_type.strip()
        return "application/zip"

    def _download_zip_url(self, endpoint: str) -> str:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        base_url = str(getattr(self.client, "base_url", "") or "").rstrip("/")
        if not base_url:
            return endpoint
        if endpoint.startswith("/"):
            return f"{base_url}{endpoint}"
        api_root = str(getattr(self.client, "api_root", "") or "").strip("/")
        prefix = f"/{api_root}" if api_root else ""
        return f"{base_url}{prefix}/{endpoint}"

    def _download_zip_payload(self, node_uuid: str) -> dict[str, object]:
        download_cfg = self.config.get("download", {})
        if isinstance(download_cfg, dict):
            payload_mode = str(download_cfg.get("zipPayloadMode") or "uuids").strip().lower()
            if payload_mode == "uuid":
                return {"uuid": node_uuid}
            if payload_mode == "path":
                return {"path": node_uuid}
        return {"uuids": [node_uuid]}

    def _download_zip_for_node(self, node_uuid: str, resolved_path: str, auth: BridgeAuthContext | None) -> OperationResult:
        endpoint = self._download_zip_endpoint()
        if not endpoint:
            raise ProviderOperationError(
                "eDoCat folder download is not supported by the documented node/query includeContent API. "
                "Set download.zipEndpoint to enable server-side ZIP download."
            )

        method = self._download_zip_method()
        request_url = self._download_zip_url(endpoint)
        if "{uuid}" in request_url:
            request_url = request_url.replace("{uuid}", quote(node_uuid, safe=""))
        if "{path}" in request_url:
            request_url = request_url.replace("{path}", quote(resolved_path.lstrip("/"), safe=""))

        payload = None
        if method == "POST":
            payload = self._download_zip_payload(node_uuid)

        username, password = self._runtime_credentials(auth)
        try:
            raw_zip, content_type = self.client.request_bytes(method, request_url, username=username, password=password, payload=payload)
        except Exception as exc:
            raise ProviderOperationError(f"eDoCat ZIP download failed for {resolved_path}: {exc}") from exc

        if not raw_zip:
            raise ProviderOperationError(f"eDoCat ZIP download failed for {resolved_path}: empty ZIP payload.")

        mime_type = content_type or self._download_zip_content_type()
        return OperationResult(
            success=True,
            operation="download",
            provider=self.name,
            source=resolved_path,
            message=f"endpoint={request_url};content=zip;mode=live",
            content_base64=base64.b64encode(raw_zip).decode("ascii"),
            mime_type=mime_type,
            size=len(raw_zip),
        )

    def _folder_node_type(self) -> str:
        node_type_cfg = self._node_type_config()
        return (
            node_type_cfg.get("folder")
            or node_type_cfg.get("baseFolder")
            or "com.onlio.edocat.BaseFolder"
        )

    def _normalize_node_path(self, node: dict) -> str:
        node_path = str(node.get("path") or "").strip()
        node_name = str(node.get("name") or "").strip()

        if node_path and not node_path.startswith("/"):
            node_path = f"/{node_path}"

        normalized_path = node_path.rstrip("/") or "/" if node_path else ""
        if not node_name:
            return normalized_path

        # eDoCat returns folder/file name separately from the parent path.
        # If the path already contains the last segment, keep it as-is.
        if normalized_path:
            last_segment = normalized_path.split("/")[-1] if normalized_path != "/" else ""
            if last_segment == node_name:
                return normalized_path
            if normalized_path == "/":
                return f"/{node_name}"
            return f"{normalized_path}/{node_name}"

        return f"/{node_name}"

    def _find_exact_node(self, nodes: list[dict], resolved_path: str) -> dict | None:
        normalized_target = resolved_path.rstrip("/") or "/"
        target_parent = normalized_target.rsplit("/", 1)[0] or "/"
        target_name = normalized_target.split("/")[-1] or "/"

        for node in nodes:
            if self._normalize_node_path(node) == normalized_target:
                return node

        for node in nodes:
            if str(node.get("name") or "") != target_name:
                continue
            node_path = self._normalize_node_path(node)
            node_parent = node_path.rsplit("/", 1)[0] or "/" if node_path else ""
            if node_parent == target_parent:
                return node

        return None

    def _query_nodes(self, path: str, auth: BridgeAuthContext | None, include_content: bool = False) -> list[dict]:
        query_path = self._resolve_path(path).lstrip("/")
        username, password = self._runtime_credentials(auth)
        try:
            response = self.client.query_nodes(query_path, username=username, password=password, include_content=include_content)
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise AuthenticationError(f"eDoCat access denied for {path}: HTTP {exc.code}.") from exc
            raise ProviderOperationError(f"eDoCat query failed for {path}: HTTP {exc.code}.") from exc
        except Exception as exc:
            raise ProviderOperationError(f"eDoCat query failed for {path}: {exc}") from exc

        nodes = response.get("nodes", [])
        if not isinstance(nodes, list):
            raise ProviderOperationError("eDoCat query response has invalid 'nodes' payload.")
        return [node for node in nodes if isinstance(node, dict)]

    def _query_single_node(self, path: str, auth: BridgeAuthContext | None, include_content: bool = False) -> dict | None:
        resolved_path = self._resolve_path(path)
        nodes = self._query_nodes(path, auth, include_content=include_content)
        exact = self._find_exact_node(nodes, resolved_path)
        if exact is not None:
            return exact

        if resolved_path == "/":
            return None

        parent_path = resolved_path.rsplit("/", 1)[0] or "/"
        parent_nodes = self._query_nodes(parent_path, auth, include_content=include_content)

        return self._find_exact_node(parent_nodes, resolved_path)

    def _item_from_node(self, node: dict, fallback_path: str) -> DmsItem:
        node_path = self._normalize_node_path(node) or fallback_path
        public_path = self._public_path(node_path)
        name = str(node.get("name") or node_path.rstrip("/").split("/")[-1] or "/")
        node_type = str(node.get("nodeType") or "")
        is_folder = node_type.lower().endswith("folder") or node_type.lower().endswith("basefolder")
        size = node.get("size")
        if not isinstance(size, int):
            size = None
        modified_at = (
            node.get("modifiedAt")
            or node.get("lastModified")
            or node.get("modified")
            or node.get("lastModificationDate")
        )
        if modified_at is not None:
            modified_at = str(modified_at)
        read_only_flag = node.get("readOnly")
        if not isinstance(read_only_flag, bool):
            read_only_flag = None
        return DmsItem(
            id=str(node.get("uuid") or node.get("id") or name),
            name=name,
            path=public_path,
            is_folder=is_folder,
            size=size,
            mime_type=str(node.get("mimeType")) if node.get("mimeType") else None,
            modified_at=modified_at,
            is_read_only=read_only_flag,
        )

    def _node_uuid(self, node: dict | None) -> str:
        if not isinstance(node, dict):
            return ""
        return str(node.get("uuid") or node.get("id") or "")

    def _is_folder_node(self, node: dict | None) -> bool:
        if not isinstance(node, dict):
            return False
        node_type = str(node.get("nodeType") or "").lower()
        return node_type.endswith("folder") or node_type.endswith("basefolder")

    def _delete_folder_tree(self, folder_path: str, auth: BridgeAuthContext | None, username: str | None, password: str | None, visited: set[str] | None = None) -> None:
        normalized_folder = self._resolve_path(folder_path).rstrip("/") or "/"
        seen = visited if visited is not None else set()
        if normalized_folder in seen:
            return
        seen.add(normalized_folder)

        children = self._query_nodes(normalized_folder, auth, include_content=False)
        descendant_paths: set[str] = set()
        for child in children:
            child_path = self._normalize_node_path(child)
            if not child_path or child_path == normalized_folder:
                continue
            if child_path.startswith(f"{normalized_folder}/"):
                descendant_paths.add(child_path)

        for child_path in sorted(descendant_paths, key=lambda p: p.count("/"), reverse=True):
            child_node = self._query_single_node(child_path, auth, include_content=False)
            if child_node is None:
                continue
            child_uuid = self._node_uuid(child_node)
            if not child_uuid:
                continue
            if self._is_folder_node(child_node):
                self._delete_folder_tree(child_path, auth, username, password, seen)
            else:
                self.client.delete_nodes([child_uuid], username=username, password=password)

        folder_node = self._query_single_node(normalized_folder, auth, include_content=False)
        folder_uuid = self._node_uuid(folder_node)
        if folder_uuid:
            self.client.delete_nodes([folder_uuid], username=username, password=password)

    def _direct_child_nodes(self, folder_path: str, auth: BridgeAuthContext | None, include_content: bool = False) -> list[dict]:
        normalized_folder = self._resolve_path(folder_path).rstrip("/") or "/"
        nodes = self._query_nodes(normalized_folder, auth, include_content=include_content)
        direct_children: list[dict] = []
        seen_paths: set[str] = set()
        for node in nodes:
            child_path = self._normalize_node_path(node)
            if not child_path or child_path == normalized_folder:
                continue
            child_parent = child_path.rsplit("/", 1)[0] or "/"
            if child_parent != normalized_folder or child_path in seen_paths:
                continue
            direct_children.append(node)
            seen_paths.add(child_path)
        return direct_children

    def _copy_payload(self, source_node: dict, destination_path: str) -> dict[str, object]:
        parent, name = self._parent_and_name(destination_path)
        is_folder = self._is_folder_node(source_node)
        payload: dict[str, object] = {
            "path": parent.lstrip("/"),
            "name": name,
            "nodeType": self._folder_node_type() if is_folder else self._document_node_type(),
        }
        if not is_folder:
            if isinstance(source_node.get("content"), str):
                payload["content"] = source_node.get("content")
            if source_node.get("mimeType"):
                payload["mimeType"] = source_node.get("mimeType")
        return payload

    def _count_folder_tree_nodes(self, folder_path: str, auth: BridgeAuthContext | None) -> int:
        total = 1
        for child_node in self._direct_child_nodes(folder_path, auth, include_content=False):
            child_source_path = self._normalize_node_path(child_node)
            if not child_source_path:
                continue
            if self._is_folder_node(child_node):
                total += self._count_folder_tree_nodes(child_source_path, auth)
            else:
                total += 1
        return total

    def _copy_folder_contents(
        self,
        source_folder_path: str,
        destination_folder_path: str,
        auth: BridgeAuthContext | None,
        username: str | None,
        password: str | None,
    ) -> None:
        for child_node in self._direct_child_nodes(source_folder_path, auth, include_content=False):
            child_source_path = self._normalize_node_path(child_node)
            if not child_source_path:
                continue
            child_destination_path = (
                f"{destination_folder_path.rstrip('/')}/{child_source_path.rsplit('/', 1)[-1]}"
                if destination_folder_path != "/"
                else f"/{child_source_path.rsplit('/', 1)[-1]}"
            )

            if self._is_folder_node(child_node):
                self.client.create_node(
                    self._copy_payload(child_node, child_destination_path),
                    username=username,
                    password=password,
                )
                self._copy_folder_contents(child_source_path, child_destination_path, auth, username, password)
                continue

            full_child_node = self._query_single_node(child_source_path, auth, include_content=True)
            if full_child_node is None:
                raise ProviderOperationError(f"eDoCat copy failed: source child not found: {child_source_path}")

            full_child_path = self._normalize_node_path(full_child_node)
            if full_child_path != child_source_path:
                raise ProviderOperationError(
                    f"eDoCat copy failed: source child path mismatch (requested={child_source_path}, resolved={full_child_path or 'none'})"
                )

            self.client.create_node(
                self._copy_payload(full_child_node, child_destination_path),
                username=username,
                password=password,
            )

    def list_items(self, path: str, auth: BridgeAuthContext | None = None) -> ListingResult:
        resolved_path = self._resolve_path(path)
        nodes = self._direct_child_nodes(resolved_path, auth, include_content=False)
        items = [self._item_from_node(node, resolved_path) for node in nodes if isinstance(node, dict)]
        return ListingResult(provider=self.name, path=self._public_path(resolved_path), total=len(items), items=items)

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

        if self._public_path(resolved_path) == "/":
            return DmsItem(id="edo-root", name="/", path="/", is_folder=True)
        return None

    def copy_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        source_path = self._resolve_path(source)
        destination_path = self._resolve_path(destination)
        source_node = self._query_single_node(source_path, auth, include_content=True)
        if source_node is None:
            raise ProviderOperationError(f"eDoCat copy failed: source not found: {source_path}")

        source_node_path = self._normalize_node_path(source_node)
        if source_node_path != source_path:
            raise ProviderOperationError(
                f"eDoCat copy failed: source path mismatch (requested={source_path}, resolved={source_node_path or 'none'})"
            )

        try:
            if self._is_folder_node(source_node):
                total_nodes = self._count_folder_tree_nodes(source_path, auth)
                max_nodes = self._copy_max_nodes()
                if total_nodes > max_nodes:
                    raise ProviderOperationError(
                        f"eDoCat copy failed: folder tree has {total_nodes} nodes, safety limit is {max_nodes}."
                    )
            else:
                total_nodes = 1
                max_nodes = self._copy_max_nodes()
            if total_nodes > max_nodes:
                raise ProviderOperationError(
                    f"eDoCat copy failed: folder tree has {total_nodes} nodes, safety limit is {max_nodes}."
                )
            response = self.client.create_node(
                self._copy_payload(source_node, destination_path),
                username=username,
                password=password,
            )
            if self._is_folder_node(source_node):
                self._copy_folder_contents(source_path, destination_path, auth, username, password)
        except Exception as exc:
            raise ProviderOperationError(f"eDoCat copy failed for {source_path} -> {destination_path}: {exc}") from exc

        copied = response if isinstance(response, dict) else {}
        target_uuid = str(copied.get("uuid") or copied.get("id") or copied.get("name") or source_node.get("name") or "")
        return OperationResult(
            success=True,
            operation="copy",
            provider=self.name,
            source=self._public_path(source_path),
            destination=self._public_path(destination_path),
            message=f"endpoint={self.bridge_endpoint_for('copy')};uuid={target_uuid};mode=live",
        )

    def rename_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        source_path = self._resolve_path(source)
        destination_path = self._resolve_path(destination)
        # 1) Read source node attributes (identity is UUID, path/name are metadata)
        source_node = self._query_single_node(source_path, auth, include_content=False)
        if source_node is None:
            raise ProviderOperationError(f"eDoCat rename failed: source not found: {source_path}")

        source_node_path = self._normalize_node_path(source_node)
        if source_node_path != source_path:
            raise ProviderOperationError(
                f"eDoCat rename failed: source path mismatch (requested={source_path}, resolved={source_node_path or 'none'})"
            )

        source_uuid = str(source_node.get("uuid") or source_node.get("id") or "")
        if not source_uuid:
            raise ProviderOperationError(f"eDoCat rename failed: source has no uuid/id: {source_path}")

        parent, name = self._parent_and_name(destination_path)
        source_parent, _ = self._parent_and_name(source_path)
        if parent != source_parent:
            raise ProviderOperationError(
                f"eDoCat rename supports only name/metadata changes in the same parent "
                f"(source_parent={source_parent}, destination_parent={parent})"
            )

        # 2) Update node description metadata (name) on the same UUID
        # NOTE: do NOT include "path" – eDoCat interprets path in updateNode as
        # a move/copy operation, not a metadata-only update.
        payload: dict[str, object] = {
            "uuid": source_uuid,
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
            source=self._public_path(source_path),
            destination=self._public_path(destination_path),
            message=f"endpoint={self.bridge_endpoint_for('rename')};uuid={target_uuid};mode=live",
        )

    def delete_item(self, target: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        target_path = self._resolve_path(target)
        target_node = self._query_single_node(target_path, auth, include_content=False)
        if target_node is None:
            raise ProviderOperationError(f"eDoCat delete failed: target not found: {target_path}")

        target_node_path = self._normalize_node_path(target_node)
        if target_node_path != target_path:
            raise ProviderOperationError(
                f"eDoCat delete failed: target path mismatch (requested={target_path}, resolved={target_node_path or 'none'})"
            )

        uuid = str(target_node.get("uuid") or target_node.get("id") or "")
        try:
            if self._is_folder_node(target_node):
                total_nodes = self._count_folder_tree_nodes(target_path, auth)
                max_nodes = self._delete_max_nodes()
                if total_nodes > max_nodes:
                    raise ProviderOperationError(
                        f"eDoCat delete failed: folder tree has {total_nodes} nodes, safety limit is {max_nodes}."
                    )
                self._delete_folder_tree(target_path, auth, username, password)
            else:
                if not uuid:
                    raise ProviderOperationError(f"eDoCat delete failed: target has no uuid/id: {target_path}")
                self.client.delete_nodes([uuid], username=username, password=password)
        except Exception as exc:
            raise ProviderOperationError(f"eDoCat delete failed for {target_path}: {exc}") from exc
        return OperationResult(
            success=True,
            operation="delete",
            provider=self.name,
            source=self._public_path(target_path),
            message=f"endpoint={self.bridge_endpoint_for('delete')};uuid={uuid};mode=live",
        )

    def make_dir(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        resolved_path = self._resolve_path(path)
        parent, name = self._parent_and_name(resolved_path)
        node_type_cfg = self._node_type_config()
        folder_node_type = (
            node_type_cfg.get("folder")
            or node_type_cfg.get("baseFolder")
            or "com.onlio.edocat.BaseFolder"
        )
        payload: dict[str, object] = {
            "path": parent.lstrip("/"),
            "name": name,
            "nodeType": folder_node_type,
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
            source=self._public_path(resolved_path),
            message=f"endpoint={self.bridge_endpoint_for('mkdir')};uuid={target_uuid};mode=live",
        )

    def download_item(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        resolved_path = self._resolve_path(path)
        node = self._query_single_node(resolved_path, auth, include_content=True)
        if node is None:
            raise ProviderOperationError(f"eDoCat download found no document for {resolved_path}.")

        node_path = self._normalize_node_path(node)
        if node_path != resolved_path:
            raise ProviderOperationError(
                f"eDoCat download failed: path mismatch (requested={resolved_path}, resolved={node_path or 'none'})"
            )

        if self._is_folder_node(node):
            total_nodes = self._count_folder_tree_nodes(resolved_path, auth)
            max_nodes = self._download_max_nodes()
            if total_nodes > max_nodes:
                raise ProviderOperationError(
                    f"eDoCat download blocked: folder tree has {total_nodes} nodes, safety limit is {max_nodes}."
                )
            uuid = self._node_uuid(node)
            if not uuid:
                raise ProviderOperationError(f"eDoCat download failed: target has no uuid/id: {resolved_path}")
            return self._download_zip_for_node(uuid, resolved_path, auth)

        content = node.get("content")
        if not isinstance(content, str):
            raise ProviderOperationError(f"eDoCat download returned no content for {resolved_path}.")

        try:
            binary_content = base64.b64decode(content, validate=True)
        except Exception as exc:
            raise ProviderOperationError(f"eDoCat download returned invalid base64 content for {resolved_path}: {exc}") from exc

        size = len(binary_content)
        max_bytes = self._download_max_bytes()
        if size > max_bytes:
            raise ProviderOperationError(
                f"eDoCat download blocked: payload size {size} B exceeds limit {max_bytes} B."
            )

        mime_type = str(node.get("mimeType")) if node.get("mimeType") else None
        return OperationResult(
            success=True,
            operation="download",
            provider=self.name,
            source=self._public_path(resolved_path),
            message=f"endpoint={self.client.endpoint_url('query')};content=live",
            content_base64=content,
            mime_type=mime_type,
            size=size,
        )

    def upload_item(self, destination: str, file_name: str, content_base64: str | None = None, source_path: str | None = None, overwrite: bool = False, auth: BridgeAuthContext | None = None) -> OperationResult:
        if source_path is not None:
            raise ProviderOperationError(
                "eDoCat upload blocked: upstream API requires base64 content in JSON; raw stream mode is not supported."
            )
        username, password = self._runtime_credentials(auth)
        resolved_destination = self._resolve_path(destination)
        target = f"{resolved_destination.rstrip('/')}/{file_name}" if resolved_destination != "/" else f"/{file_name}"
        parent, name = self._parent_and_name(target)
        encoded_content = self._encode_if_needed(content_base64)
        payload: dict[str, object] = {
            "path": parent.lstrip("/"),
            "name": name,
            "content": encoded_content,
            "nodeType": self._document_node_type(),
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
            destination=self._public_path(target),
            message=f"endpoint={self.client.endpoint_url('node')};uuid={target_uuid};mode=live",
        )
