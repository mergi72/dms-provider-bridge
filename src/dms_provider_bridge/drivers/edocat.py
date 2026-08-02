from __future__ import annotations

import base64
import os
from urllib.error import HTTPError
from urllib.parse import quote

from dms_provider_bridge.clients.alfresco_client import AlfrescoClient
from dms_provider_bridge.core.debug import (
    connection_debug_logger,
    log_connection_operation_done,
    log_connection_operation_failed,
    log_connection_operation_start,
)
from dms_provider_bridge.core.errors import AuthenticationError, ConnectionOperationError
from dms_provider_bridge.clients.edocat_client import EdocatClient
from dms_provider_bridge.core.config_loader import load_driver_config
from dms_provider_bridge.models.bridge import BridgeAuthContext
from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.models.search import SearchResult, select_unique_items
from dms_provider_bridge.drivers.tc_vfs_contract import TcVfsContract
from dms_provider_bridge.drivers import alfresco_versioning
from dms_provider_bridge.drivers import edocat_config, edocat_items, edocat_nodes, edocat_paths, edocat_tree
from dms_provider_bridge.services.auth_resolver import resolve_effective_auth


class EdocatProvider(TcVfsContract):
    name = "edocat"
    upstream_auth_scheme = "basic"

    def __init__(self, name: str | None = None, config: dict | None = None) -> None:
        self.name = name or self.name
        self.config = config or load_driver_config("edocat")
        self.client = EdocatClient.from_config(self.config)
        self.debug_logger = connection_debug_logger(self.name, self.config)
        self._alfresco_version_client: AlfrescoClient | None = None
        self._alfresco_version_cache: dict[str, dict[str, str | None]] = {}

    def _browse_root(self) -> str:
        return edocat_paths.browse_root(self.config)

    def _resolve_path(self, path: str) -> str:
        return edocat_paths.resolve_path(path, self._browse_root())

    def _public_path(self, path: str) -> str:
        return edocat_paths.public_path(path, self._browse_root())

    def _runtime_credentials(self, auth: BridgeAuthContext | None) -> tuple[str | None, str | None]:
        credentials = resolve_effective_auth(
            self.config,
            auth,
            default_scheme=self.upstream_auth_scheme,
            validate_required=False,
        )
        return credentials.username, credentials.password or credentials.token

    def _parent_and_name(self, path: str) -> tuple[str, str]:
        return edocat_paths.parent_and_name(path, self._browse_root())

    def _encode_if_needed(self, content: str | None) -> str | None:
        if content is None:
            return None
        if content == "":
            return ""
        return content

    def _node_type_config(self) -> dict[str, str]:
        return edocat_config.node_type_config(self.config)

    def _document_node_type(self) -> str:
        return edocat_config.document_node_type(self.config)

    def versioning_capabilities(self) -> dict[str, object]:
        capabilities = self.config.get("capabilities")
        versioning = capabilities.get("versioning") if isinstance(capabilities, dict) else None
        if isinstance(versioning, dict):
            return {
                "supported": bool(versioning.get("supported")),
                "existing_upload": versioning.get("existing_upload") or "version_required",
                "modes": versioning.get("modes") or ["version"],
                "majorVersion": bool(versioning.get("majorVersion", False)),
                "comment_supported": bool(versioning.get("comment_supported", True)),
            }
        return {
            "supported": True,
            "existing_upload": "version_required",
            "modes": ["version"],
            "majorVersion": False,
            "comment_supported": True,
        }

    def search_capabilities(self) -> dict[str, object]:
        if self.client.endpoint_url("query"):
            return {"supported": True, "mode": "native_full_text", "max_results": 100}
        return {"supported": False, "mode": None}

    def supports_share_url(self) -> bool:
        return bool(self.client.base_url)

    def share_url_to_path(self, share_url: str) -> str:
        return self.client.resolve_share_url(share_url)

    @staticmethod
    def _search_query(query: str) -> str:
        escaped = query.replace("\\", "\\\\").replace('"', '\\"')
        return f'(cm:name:"*{escaped}*" OR TEXT:"{escaped}")'

    @staticmethod
    def _response_total(response: dict, fallback: int) -> int:
        pagination = response.get("pagination")
        if isinstance(pagination, dict):
            total = pagination.get("totalItems")
            if isinstance(total, int) and total >= 0:
                return total
        return fallback

    def _versioning_choice(self, versioning: dict | None) -> tuple[bool, str | None] | None:
        return alfresco_versioning.versioning_choice(versioning)

    def _copy_max_nodes(self) -> int:
        return edocat_config.copy_max_nodes(self.config)

    def _delete_max_nodes(self) -> int:
        return edocat_config.delete_max_nodes(self.config)

    def _download_max_bytes(self) -> int:
        return edocat_config.download_max_bytes(self.config)

    def _upload_max_bytes(self) -> int:
        return edocat_config.upload_max_bytes(self.config)

    def _download_max_nodes(self) -> int:
        return edocat_config.download_max_nodes(self.config)

    def _download_zip_endpoint(self) -> str | None:
        return edocat_config.download_zip_endpoint(self.config)

    def _download_zip_method(self) -> str:
        return edocat_config.download_zip_method(self.config)

    def _download_zip_content_type(self) -> str:
        return edocat_config.download_zip_content_type(self.config)

    def _download_zip_url(self, endpoint: str) -> str:
        base_url = str(getattr(self.client, "base_url", "") or "").rstrip("/")
        api_root = str(getattr(self.client, "api_root", "") or "").strip("/")
        return edocat_config.download_zip_url(base_url, api_root, endpoint)

    def _download_zip_payload(self, node_uuid: str) -> dict[str, object]:
        return edocat_config.download_zip_payload(self.config, node_uuid)

    def _download_zip_for_node(self, node_uuid: str, resolved_path: str, auth: BridgeAuthContext | None) -> OperationResult:
        endpoint = self._download_zip_endpoint()
        if not endpoint:
            raise ConnectionOperationError(
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
            raise ConnectionOperationError(f"eDoCat ZIP download failed for {resolved_path}: {exc}") from exc

        if not raw_zip:
            raise ConnectionOperationError(f"eDoCat ZIP download failed for {resolved_path}: empty ZIP payload.")

        mime_type = content_type or self._download_zip_content_type()
        return OperationResult(
            success=True,
            operation="download",
            provider=self.name,
            connection=self.name,
            source=resolved_path,
            message=f"endpoint={request_url};content=zip;mode=live",
            content_base64=base64.b64encode(raw_zip).decode("ascii"),
            mime_type=mime_type,
            size=len(raw_zip),
        )

    def _folder_node_type(self) -> str:
        return edocat_config.folder_node_type(self.config)

    def _normalize_node_path(self, node: dict) -> str:
        return edocat_paths.normalize_node_path(node)

    def _find_exact_node(self, nodes: list[dict], resolved_path: str) -> dict | None:
        return edocat_paths.find_exact_node(nodes, resolved_path)

    def _query_nodes(self, path: str, auth: BridgeAuthContext | None, include_content: bool = False) -> list[dict]:
        query_path = self._resolve_path(path).lstrip("/")
        username, password = self._runtime_credentials(auth)
        started = log_connection_operation_start(
            self.debug_logger,
            self.name,
            "query_nodes",
            query_path,
            include_content=include_content,
        )
        try:
            response = self.client.query_nodes(query_path, username=username, password=password, include_content=include_content)
        except HTTPError as exc:
            log_connection_operation_failed(
                self.debug_logger,
                self.name,
                "query_nodes",
                started,
                query_path,
                error=f"HTTP {exc.code}",
                include_content=include_content,
            )
            if exc.code in {401, 403}:
                raise AuthenticationError(f"eDoCat access denied for {path}: HTTP {exc.code}.", status_code=exc.code) from exc
            raise ConnectionOperationError(f"eDoCat query failed for {path}: HTTP {exc.code}.", status_code=exc.code) from exc
        except ConnectionOperationError as exc:
            log_connection_operation_failed(
                self.debug_logger,
                self.name,
                "query_nodes",
                started,
                query_path,
                error=exc,
                include_content=include_content,
            )
            raise
        except Exception as exc:
            log_connection_operation_failed(
                self.debug_logger,
                self.name,
                "query_nodes",
                started,
                query_path,
                error=exc,
                include_content=include_content,
            )
            raise ConnectionOperationError(f"eDoCat query failed for {path}: {exc}") from exc

        nodes = response.get("nodes", [])
        if not isinstance(nodes, list):
            log_connection_operation_failed(
                self.debug_logger,
                self.name,
                "query_nodes",
                started,
                query_path,
                error="invalid nodes payload",
                include_content=include_content,
            )
            raise ConnectionOperationError("eDoCat query response has invalid 'nodes' payload.")
        result_nodes = [node for node in nodes if isinstance(node, dict)]
        log_connection_operation_done(
            self.debug_logger,
            self.name,
            "query_nodes",
            started,
            query_path,
            include_content=include_content,
            nodes=len(result_nodes),
            raw_nodes=len(nodes),
        )
        return result_nodes

    def _query_node_by_uuid(self, uuid: str, auth: BridgeAuthContext | None, include_content: bool = False) -> dict | None:
        username, password = self._runtime_credentials(auth)
        started = log_connection_operation_start(
            self.debug_logger,
            self.name,
            "query_node_by_uuid",
            uuid,
            include_content=include_content,
        )
        try:
            response = self.client.query_nodes_by_uuids([uuid], username=username, password=password, include_content=include_content)
        except HTTPError as exc:
            log_connection_operation_failed(
                self.debug_logger,
                self.name,
                "query_node_by_uuid",
                started,
                uuid,
                error=f"HTTP {exc.code}",
                include_content=include_content,
            )
            if exc.code in {401, 403}:
                raise AuthenticationError(f"eDoCat access denied for uuid {uuid}: HTTP {exc.code}.", status_code=exc.code) from exc
            raise ConnectionOperationError(f"eDoCat query failed for uuid {uuid}: HTTP {exc.code}.", status_code=exc.code) from exc
        except Exception as exc:
            log_connection_operation_failed(
                self.debug_logger,
                self.name,
                "query_node_by_uuid",
                started,
                uuid,
                error=str(exc),
                include_content=include_content,
            )
            raise ConnectionOperationError(f"eDoCat query failed for uuid {uuid}: {exc}") from exc

        nodes = response.get("nodes", [])
        if not isinstance(nodes, list):
            log_connection_operation_failed(
                self.debug_logger,
                self.name,
                "query_node_by_uuid",
                started,
                uuid,
                error="invalid nodes payload",
                include_content=include_content,
            )
            raise ConnectionOperationError("eDoCat query-by-uuid response has invalid 'nodes' payload.")
        result_nodes = [node for node in nodes if isinstance(node, dict)]
        log_connection_operation_done(
            self.debug_logger,
            self.name,
            "query_node_by_uuid",
            started,
            uuid,
            include_content=include_content,
            nodes=len(result_nodes),
            raw_nodes=len(nodes),
        )
        return result_nodes[0] if result_nodes else None

    def _query_single_node(self, path: str, auth: BridgeAuthContext | None, include_content: bool = False) -> dict | None:
        resolved_path = self._resolve_path(path)
        try:
            nodes = self._query_nodes(path, auth, include_content=include_content)
        except ConnectionOperationError as exc:
            if exc.status_code not in {400, 404}:
                raise
            parent_path = resolved_path.rsplit("/", 1)[0] or "/"
            self.debug_logger.debug(
                "provider_resolution_fallback provider=%s operation=query_single_node path=%s status_code=%s fallback_parent=%s include_content=%s",
                self.name,
                resolved_path,
                exc.status_code,
                parent_path,
                include_content,
            )
        else:
            exact = self._find_exact_node(nodes, resolved_path)
            if exact is not None:
                return exact

        if resolved_path == "/":
            return None

        parent_path = resolved_path.rsplit("/", 1)[0] or "/"
        parent_nodes = self._query_nodes(parent_path, auth, include_content=include_content)

        return self._find_exact_node(parent_nodes, resolved_path)

    def _alfresco_version_config(self) -> dict[str, object]:
        configured = self.config.get("alfresco")
        base_config: dict[str, object] = {}
        if isinstance(configured, dict):
            base_config.update(configured)

        base_url = str(base_config.get("base_url") or self.config.get("alfresco_base_url") or self.config.get("base_url") or "").rstrip("/")
        if base_url and not base_url.lower().rstrip("/").endswith("/alfresco"):
            base_url = f"{base_url}/alfresco"

        return {
            "base_url": base_url,
            "api": base_config.get("api") or {
                "search_root": "/api/-default-/public/search/versions/1",
                "repo_root": "/api/-default-/public/alfresco/versions/1",
            },
            "endpoints": base_config.get("endpoints") or {
                "search": "/search",
                "nodes": "/nodes",
                "people_me": "/people/-me-",
            },
            "doc_library": base_config.get("doc_library") or self.config.get("doc_library") or "/",
            "nodeType": base_config.get("nodeType") or {},
            "timeouts": base_config.get("timeouts") or self.config.get("timeouts") or {},
        }

    def _alfresco_version_metadata_from_uuid(self, uuid: str, auth: BridgeAuthContext | None, *, use_cache: bool = True) -> dict[str, str | None]:
        cached = self._alfresco_version_cache.get(uuid)
        if use_cache and cached is not None:
            return cached

        username, password = self._runtime_credentials(auth)
        if not (username and password):
            return {}

        if self._alfresco_version_client is None:
            self._alfresco_version_client = AlfrescoClient.from_config(self._alfresco_version_config())

        try:
            ticket = self._alfresco_version_client.basic_auth_token(username, password)
            detail = self._alfresco_version_client.get_node(ticket, uuid, include=["aspectNames", "properties"])
        except Exception as exc:
            self.debug_logger.debug(
                "provider_version_fallback_failed provider=%s uuid=%s error=%s",
                self.name,
                uuid,
                exc,
            )
            return {}

        entry = detail.get("entry") if isinstance(detail, dict) else None
        if not isinstance(entry, dict):
            return {}

        metadata = {
            "version_label": alfresco_versioning.version_label_from_entry(entry),
            "version_type": alfresco_versioning.version_type_from_entry(entry),
        }
        self._alfresco_version_cache[uuid] = metadata
        return metadata

    def _item_from_node(self, node: dict, fallback_path: str, auth: BridgeAuthContext | None = None, *, use_version_cache: bool = True) -> DmsItem:
        node_path = self._normalize_node_path(node) or fallback_path
        normalized_node = dict(node)
        normalized_node["_normalized_path"] = node_path
        item = edocat_items.item_from_node(normalized_node, fallback_path, self._public_path)
        if item.is_folder or item.version_label:
            return item

        uuid = self._node_uuid(node)
        if not uuid:
            return item

        version_metadata = self._alfresco_version_metadata_from_uuid(uuid, auth, use_cache=use_version_cache)
        version_label = version_metadata.get("version_label")
        version_type = version_metadata.get("version_type")
        if not (version_label or version_type):
            return item

        return item.model_copy(update={"version_label": version_label, "version_type": version_type})

    def _node_uuid(self, node: dict | None) -> str:
        return edocat_nodes.node_uuid(node)

    def _is_folder_node(self, node: dict | None) -> bool:
        return edocat_nodes.is_folder_node(node)

    def _delete_folder_tree(self, folder_path: str, auth: BridgeAuthContext | None, username: str | None, password: str | None, visited: set[str] | None = None) -> None:
        normalized_folder = self._resolve_path(folder_path).rstrip("/") or "/"
        seen = visited if visited is not None else set()
        if normalized_folder in seen:
            return
        seen.add(normalized_folder)

        children = self._query_nodes(normalized_folder, auth, include_content=False)
        descendant_paths = edocat_tree.descendant_paths(children, normalized_folder, self._normalize_node_path)

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
        return edocat_tree.direct_child_nodes(nodes, normalized_folder, self._normalize_node_path)

    def _copy_payload(self, source_node: dict, destination_path: str) -> dict[str, object]:
        parent, name = self._parent_and_name(destination_path)
        return edocat_items.copy_payload(
            source_node,
            parent,
            name,
            self._folder_node_type(),
            self._document_node_type(),
        )

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
            child_destination_path = edocat_tree.child_destination_path(destination_folder_path, child_source_path)

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
                raise ConnectionOperationError(f"eDoCat copy failed: source child not found: {child_source_path}")

            full_child_path = self._normalize_node_path(full_child_node)
            if full_child_path != child_source_path:
                raise ConnectionOperationError(
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
        items = [self._item_from_node(node, resolved_path, auth) for node in nodes if isinstance(node, dict)]
        return ListingResult(provider=self.name, connection=self.name, path=self._public_path(resolved_path), total=len(items), items=items)

    def search_items(
        self,
        query: str,
        path: str = "/",
        max_results: int = 20,
        auth: BridgeAuthContext | None = None,
        *,
        files_only: bool = True,
    ) -> SearchResult:
        resolved_path = self._resolve_path(path).rstrip("/") or "/"
        username, password = self._runtime_credentials(auth)
        try:
            response = self.client.search_nodes(
                self._search_query(query),
                max_items=100,
                username=username,
                password=password,
            )
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise AuthenticationError(
                    f"eDoCat access denied while searching {path}: HTTP {exc.code}.",
                    status_code=exc.code,
                ) from exc
            raise ConnectionOperationError(
                f"eDoCat search failed for {path}: HTTP {exc.code}.",
                status_code=exc.code,
            ) from exc
        except ConnectionOperationError:
            raise
        except Exception as exc:
            raise ConnectionOperationError(f"eDoCat search failed for {path}: {exc}") from exc

        nodes = response.get("nodes", [])
        if not isinstance(nodes, list):
            raise ConnectionOperationError("eDoCat search returned invalid nodes data.")

        prefix = resolved_path.rstrip("/") + "/"
        matching_nodes = [
            node
            for node in nodes
            if isinstance(node, dict)
            and (
                resolved_path == "/"
                or self._normalize_node_path(node) == resolved_path
                or self._normalize_node_path(node).startswith(prefix)
            )
        ]
        items = [self._item_from_node(node, resolved_path, auth) for node in matching_nodes]
        selected = select_unique_items(items, max_results, files_only)
        upstream_total = self._response_total(response, len(nodes))
        total = len(matching_nodes) if resolved_path != "/" else upstream_total
        return SearchResult(
            connection=self.name,
            path=self._public_path(resolved_path),
            query=query,
            total=total,
            returned=len(selected),
            items=selected,
            truncated=total > len(selected) or upstream_total > len(nodes),
        )

    def bridge_endpoint_for(self, operation: str) -> str | None:
        mapping = {
            "list": self.client.endpoint_url("query"),
            "stat": self.client.endpoint_url("query"),
            "copy": self.client.endpoint_url("node"),
            "rename": self.client.endpoint_url("node"),
            "delete": self.client.endpoint_url("node"),
            "mkdir": self.client.endpoint_url("node"),
            "download": self.client.endpoint_url("query"),
            "search": self.client.endpoint_url("query"),
            "upload": self.client.endpoint_url("node"),
        }
        return mapping.get(operation)

    def stat_item(self, path: str, auth: BridgeAuthContext | None = None) -> DmsItem | None:
        resolved_path = self._resolve_path(path)
        node = self._query_single_node(resolved_path, auth, include_content=False)
        if node is not None:
            return self._item_from_node(node, resolved_path, auth, use_version_cache=False)

        if self._public_path(resolved_path) == "/":
            return DmsItem(id="edo-root", name="/", path="/", is_folder=True)
        return None

    def copy_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        source_path = self._resolve_path(source)
        destination_path = self._resolve_path(destination)
        source_node = self._query_single_node(source_path, auth, include_content=True)
        if source_node is None:
            raise ConnectionOperationError(f"eDoCat copy failed: source not found: {source_path}")

        source_node_path = self._normalize_node_path(source_node)
        if source_node_path != source_path:
            raise ConnectionOperationError(
                f"eDoCat copy failed: source path mismatch (requested={source_path}, resolved={source_node_path or 'none'})"
            )

        try:
            if self._is_folder_node(source_node):
                total_nodes = self._count_folder_tree_nodes(source_path, auth)
                max_nodes = self._copy_max_nodes()
                if total_nodes > max_nodes:
                    raise ConnectionOperationError(
                        f"eDoCat copy failed: folder tree has {total_nodes} nodes, safety limit is {max_nodes}."
                    )
            else:
                total_nodes = 1
                max_nodes = self._copy_max_nodes()
            if total_nodes > max_nodes:
                raise ConnectionOperationError(
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
            raise ConnectionOperationError(f"eDoCat copy failed for {source_path} -> {destination_path}: {exc}") from exc

        copied = response if isinstance(response, dict) else {}
        target_uuid = str(copied.get("uuid") or copied.get("id") or copied.get("name") or source_node.get("name") or "")
        return OperationResult(
            success=True,
            operation="copy",
            provider=self.name,
            connection=self.name,
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
            raise ConnectionOperationError(f"eDoCat rename failed: source not found: {source_path}")

        source_node_path = self._normalize_node_path(source_node)
        if source_node_path != source_path:
            raise ConnectionOperationError(
                f"eDoCat rename failed: source path mismatch (requested={source_path}, resolved={source_node_path or 'none'})"
            )

        source_uuid = str(source_node.get("uuid") or source_node.get("id") or "")
        if not source_uuid:
            raise ConnectionOperationError(f"eDoCat rename failed: source has no uuid/id: {source_path}")

        parent, name = self._parent_and_name(destination_path)
        source_parent, _ = self._parent_and_name(source_path)
        if parent != source_parent:
            raise ConnectionOperationError(
                f"eDoCat rename supports only name/metadata changes in the same parent "
                f"(source_parent={source_parent}, destination_parent={parent})"
            )

        # 2) Update node description metadata (name) on the same UUID
        # NOTE: do NOT include "path" - eDoCat interprets path in updateNode as
        # a move/copy operation, not a metadata-only update.
        payload: dict[str, object] = {
            "uuid": source_uuid,
            "name": name,
            "autoRename": False,
        }
        try:
            response = self.client.update_node(payload, username=username, password=password)
        except Exception as exc:
            raise ConnectionOperationError(f"eDoCat rename failed for {source_path} -> {destination_path}: {exc}") from exc

        renamed = response if isinstance(response, dict) else {}
        target_uuid = str(renamed.get("uuid") or source_node.get("uuid") or source_node.get("id"))
        return OperationResult(
            success=True,
            operation="rename",
            provider=self.name,
            connection=self.name,
            source=self._public_path(source_path),
            destination=self._public_path(destination_path),
            message=f"endpoint={self.bridge_endpoint_for('rename')};uuid={target_uuid};mode=live",
        )

    def delete_item(self, target: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        target_path = self._resolve_path(target)
        target_node = self._query_single_node(target_path, auth, include_content=False)
        if target_node is None:
            raise ConnectionOperationError(f"eDoCat delete failed: target not found: {target_path}")

        target_node_path = self._normalize_node_path(target_node)
        if target_node_path != target_path:
            raise ConnectionOperationError(
                f"eDoCat delete failed: target path mismatch (requested={target_path}, resolved={target_node_path or 'none'})"
            )

        uuid = str(target_node.get("uuid") or target_node.get("id") or "")
        try:
            if self._is_folder_node(target_node):
                total_nodes = self._count_folder_tree_nodes(target_path, auth)
                max_nodes = self._delete_max_nodes()
                if total_nodes > max_nodes:
                    raise ConnectionOperationError(
                        f"eDoCat delete failed: folder tree has {total_nodes} nodes, safety limit is {max_nodes}."
                    )
                self._delete_folder_tree(target_path, auth, username, password)
            else:
                if not uuid:
                    raise ConnectionOperationError(f"eDoCat delete failed: target has no uuid/id: {target_path}")
                self.client.delete_nodes([uuid], username=username, password=password)
        except Exception as exc:
            raise ConnectionOperationError(f"eDoCat delete failed for {target_path}: {exc}") from exc
        return OperationResult(
            success=True,
            operation="delete",
            provider=self.name,
            connection=self.name,
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
            raise ConnectionOperationError(f"eDoCat mkdir failed for {resolved_path}: {exc}") from exc

        created = response if isinstance(response, dict) else {}
        target_uuid = str(created.get("uuid") or created.get("id") or created.get("name") or name)
        return OperationResult(
            success=True,
            operation="mkdir",
            provider=self.name,
            connection=self.name,
            source=self._public_path(resolved_path),
            message=f"endpoint={self.bridge_endpoint_for('mkdir')};uuid={target_uuid};mode=live",
        )

    def download_item(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        resolved_path = self._resolve_path(path)
        node = self._query_single_node(resolved_path, auth, include_content=False)
        if node is None:
            raise ConnectionOperationError(f"eDoCat download found no document for {resolved_path}.")

        node_path = self._normalize_node_path(node)
        if node_path != resolved_path:
            raise ConnectionOperationError(
                f"eDoCat download failed: path mismatch (requested={resolved_path}, resolved={node_path or 'none'})"
            )

        if self._is_folder_node(node):
            total_nodes = self._count_folder_tree_nodes(resolved_path, auth)
            max_nodes = self._download_max_nodes()
            if total_nodes > max_nodes:
                raise ConnectionOperationError(
                    f"eDoCat download blocked: folder tree has {total_nodes} nodes, safety limit is {max_nodes}."
                )
            uuid = self._node_uuid(node)
            if not uuid:
                raise ConnectionOperationError(f"eDoCat download failed: target has no uuid/id: {resolved_path}")
            return self._download_zip_for_node(uuid, resolved_path, auth)

        uuid = self._node_uuid(node)
        if not uuid:
            raise ConnectionOperationError(f"eDoCat download failed: target has no uuid/id: {resolved_path}")

        content_node = self._query_node_by_uuid(uuid, auth, include_content=True)
        if content_node is None:
            raise ConnectionOperationError(f"eDoCat download found no content node for {resolved_path}.")

        content_node_path = self._normalize_node_path(content_node)
        if content_node_path and content_node_path != resolved_path:
            raise ConnectionOperationError(
                f"eDoCat download failed: content path mismatch (requested={resolved_path}, resolved={content_node_path})"
            )

        content = content_node.get("content")
        if not isinstance(content, str):
            raise ConnectionOperationError(f"eDoCat download returned no content for {resolved_path}.")

        try:
            binary_content = base64.b64decode(content, validate=True)
        except Exception as exc:
            raise ConnectionOperationError(f"eDoCat download returned invalid base64 content for {resolved_path}: {exc}") from exc

        size = len(binary_content)
        max_bytes = self._download_max_bytes()
        if size > max_bytes:
            raise ConnectionOperationError(
                f"eDoCat download blocked: payload size {size} B exceeds limit {max_bytes} B."
            )

        mime_type = str(content_node.get("mimeType") or node.get("mimeType")) if content_node.get("mimeType") or node.get("mimeType") else None
        self.debug_logger.debug(
            "provider_download_payload provider=%s path=%s base64_chars=%s binary_bytes=%s mime_type=%s",
            self.name,
            resolved_path,
            len(content),
            size,
            mime_type,
        )
        return OperationResult(
            success=True,
            operation="download",
            provider=self.name,
            connection=self.name,
            source=self._public_path(resolved_path),
            message=f"endpoint={self.client.endpoint_url('query')};content=live",
            content_base64=content,
            mime_type=mime_type,
            size=size,
        )

    def upload_item(self, destination: str, file_name: str, content_base64: str | None = None, source_path: str | None = None, overwrite: bool = False, auth: BridgeAuthContext | None = None, versioning: dict | None = None) -> OperationResult:
        username, password = self._runtime_credentials(auth)
        resolved_destination = self._resolve_path(destination)
        target = f"{resolved_destination.rstrip('/')}/{file_name}" if resolved_destination != "/" else f"/{file_name}"
        parent, name = self._parent_and_name(target)
        if source_path is not None:
            try:
                file_size = os.path.getsize(source_path)
                max_bytes = self._upload_max_bytes()
                if file_size > max_bytes:
                    raise ConnectionOperationError(
                        f"eDoCat upload blocked: payload size {file_size} B exceeds limit {max_bytes} B."
                    )
                with open(source_path, "rb") as handle:
                    encoded_content = base64.b64encode(handle.read()).decode("ascii")
            except ConnectionOperationError:
                raise
            except Exception as exc:
                raise ConnectionOperationError(f"eDoCat upload failed: source file is not accessible: {source_path}") from exc
        else:
            encoded_content = self._encode_if_needed(content_base64)
        payload: dict[str, object] = {
            "path": parent.lstrip("/"),
            "name": name,
            "content": encoded_content,
            "nodeType": self._document_node_type(),
        }
        version_choice = self._versioning_choice(versioning)
        if version_choice is not None:
            existing_node = self._query_single_node(target, auth, include_content=False)
            if existing_node is None:
                raise ConnectionOperationError(f"eDoCat version upload failed: target does not exist: {target}")
            existing_uuid = self._node_uuid(existing_node)
            if not existing_uuid:
                raise ConnectionOperationError(f"eDoCat version upload failed: existing node uuid is missing for {target}")
            major_version, comment = version_choice
            try:
                if self._alfresco_version_client is None:
                    self._alfresco_version_client = AlfrescoClient.from_config(self._alfresco_version_config())
                if not (username and password):
                    raise ConnectionOperationError("eDoCat version upload failed: credentials are missing.")
                ticket = self._alfresco_version_client.basic_auth_token(username, password)
                response = self._alfresco_version_client.update_node_content(
                    ticket,
                    existing_uuid,
                    name,
                    content_base64=encoded_content,
                    source_path=source_path,
                    major_version=major_version,
                    comment=comment,
                )
            except Exception as exc:
                raise ConnectionOperationError(f"eDoCat version upload failed for {target}: {exc}") from exc

            updated = response if isinstance(response, dict) else {}
            entry = updated.get("entry") if isinstance(updated.get("entry"), dict) else updated
            target_uuid = str(entry.get("id") or entry.get("uuid") or existing_uuid) if isinstance(entry, dict) else existing_uuid
            self._alfresco_version_cache.pop(existing_uuid, None)
            self._alfresco_version_cache.pop(target_uuid, None)
            version_label = alfresco_versioning.version_label_from_entry(entry if isinstance(entry, dict) else None)
            version_type = alfresco_versioning.version_type_from_entry(entry if isinstance(entry, dict) else None)
            return OperationResult(
                success=True,
                operation="upload",
                provider=self.name,
                connection=self.name,
                source=file_name,
                destination=self._public_path(target),
                message=f"endpoint={self._alfresco_version_client.node_content_url(target_uuid)};uuid={target_uuid};mode=version",
                metadata={
                    "action": "version",
                    "node_id": target_uuid,
                    "major_version": major_version,
                    "comment": comment,
                    "version": version_label,
                    "version_type": version_type,
                },
            )
        if overwrite:
            payload["autoRename"] = False
        try:
            response = self.client.create_node(payload, username=username, password=password)
        except Exception as exc:
            raise ConnectionOperationError(f"eDoCat upload failed for {target}: {exc}") from exc

        created = response if isinstance(response, dict) else {}
        target_uuid = str(created.get("uuid") or created.get("id") or created.get("name") or name)
        return OperationResult(
            success=True,
            operation="upload",
            provider=self.name,
            connection=self.name,
            source=file_name,
            destination=self._public_path(target),
            message=f"endpoint={self.client.endpoint_url('node')};uuid={target_uuid};mode=live",
        )


