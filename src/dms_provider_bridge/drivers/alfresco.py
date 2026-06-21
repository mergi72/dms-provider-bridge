from __future__ import annotations

import base64
from collections.abc import Callable
from typing import IO
from urllib.error import HTTPError

from dms_provider_bridge.clients.alfresco_client import AlfrescoClient
from dms_provider_bridge.core.config_loader import load_provider_config
from dms_provider_bridge.core.debug import (
    log_provider_operation_done,
    log_provider_operation_failed,
    log_provider_operation_start,
    provider_debug_logger,
)
from dms_provider_bridge.core.errors import AuthenticationError, ProviderOperationError, VersionRequiredError
from dms_provider_bridge.models.bridge import BridgeAuthContext
from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.drivers.base import Provider
from dms_provider_bridge.drivers import alfresco_config, alfresco_items, alfresco_share, alfresco_versioning
from dms_provider_bridge.services.auth_resolver import resolve_effective_auth


class AlfrescoProvider(Provider):
    name = "alfresco"
    upstream_auth_scheme = "ticket"

    def __init__(self, name: str | None = None, config: dict | None = None) -> None:
        self.name = name or self.name
        self.config = config or load_provider_config("alfresco")
        self.client = AlfrescoClient.from_config(self.config)
        self.debug_logger = provider_debug_logger(self.name, self.config)

    def _runtime_credentials(self, auth: BridgeAuthContext | None) -> tuple[str | None, str | None, str | None]:
        credentials = resolve_effective_auth(
            self.config,
            auth,
            default_scheme=self.upstream_auth_scheme,
            validate_required=False,
        ).as_credentials(self.client.base_url)
        return credentials.username, credentials.password, credentials.token

    def versioning_capabilities(self) -> dict[str, object]:
        return {
            "supported": True,
            "existing_upload": "version_required",
            "modes": ["version"],
            "majorVersion": False,
            "comment_supported": True,
        }

    def supports_share_url(self) -> bool:
        return True

    def share_url_to_path(self, share_url: str) -> str:
        return alfresco_share.share_url_to_path(share_url)

    def _download_max_bytes(self) -> int:
        return alfresco_config.download_max_bytes(self.config)

    def _ticket(self, auth: BridgeAuthContext | None) -> str:
        username, password, token = self._runtime_credentials(auth)
        if token:
            normalized = token.strip()
            if normalized.lower().startswith("basic "):
                return normalized.split(" ", 1)[1].strip()
            return normalized
        if username and password:
            return self.client.basic_auth_token(username, password)
        raise ProviderOperationError("Alfresco credentials are missing; live operation cannot continue.")

    def _refresh_ticket(self, auth: BridgeAuthContext | None) -> str | None:
        try:
            username, password, _token = self._runtime_credentials(auth)
        except Exception:
            return None
        if not (username and password):
            return None
        try:
            return self.client.create_ticket(username, password)
        except Exception:
            return None

    def _run_with_ticket_retry(self, auth: BridgeAuthContext | None, operation: str, fn: Callable[[str], object]):
        started = log_provider_operation_start(self.debug_logger, self.name, operation)
        ticket = self._ticket(auth)
        try:
            result = fn(ticket)
            log_provider_operation_done(self.debug_logger, self.name, operation, started)
            return result
        except HTTPError as exc:
            if exc.code not in {401, 403}:
                log_provider_operation_failed(self.debug_logger, self.name, operation, started, error=f"HTTP {exc.code}")
                raise
            refreshed = self._refresh_ticket(auth)
            if not refreshed:
                log_provider_operation_failed(self.debug_logger, self.name, operation, started, error=f"HTTP {exc.code}")
                raise AuthenticationError(f"Alfresco access denied for {operation}: HTTP {exc.code}.") from exc
            try:
                result = fn(refreshed)
                log_provider_operation_done(self.debug_logger, self.name, operation, started, retry=True)
                return result
            except HTTPError as retry_exc:
                if retry_exc.code in {401, 403}:
                    log_provider_operation_failed(self.debug_logger, self.name, operation, started, error=f"HTTP {retry_exc.code}", retry=True)
                    raise AuthenticationError(f"Alfresco access denied for {operation}: HTTP {retry_exc.code}.") from retry_exc
                log_provider_operation_failed(self.debug_logger, self.name, operation, started, error=f"HTTP {retry_exc.code}", retry=True)
                raise
        except Exception as exc:
            log_provider_operation_failed(self.debug_logger, self.name, operation, started, error=exc)
            raise

    def _live_node(self, path: str, auth: BridgeAuthContext | None, ticket: str | None = None) -> dict:
        ticket = ticket or self._ticket(auth)
        resolved = self._resolve_path(path, ticket, strict=True)
        try:
            return self.client.get_node(ticket, resolved["node_id"])
        except Exception as exc:
            raise ProviderOperationError(f"Alfresco node lookup failed for {resolved['path']}: {exc}") from exc

    def _target_parent_and_name(self, destination: str, ticket: str | None = None) -> tuple[str, str | None, str]:
        normalized = self.client.normalize_path(destination)
        name = normalized.rstrip("/").split("/")[-1] or "/"
        is_file_like = "." in name and not destination.endswith("/")

        if is_file_like:
            parent_path = self.client.parent_path(normalized)
            parent = self._resolve_path(parent_path, ticket, strict=bool(ticket))
            return parent["node_id"], name, normalized

        resolved = self._resolve_path(normalized, ticket, strict=bool(ticket))
        return resolved["node_id"], None, resolved["path"]

    def _item_from_entry(self, entry: dict, fallback_path: str | None = None) -> DmsItem:
        return alfresco_items.item_from_entry(
            entry,
            fallback_path,
            self.client.normalize_path,
            lambda path: self.client.node_id_from_path(path),
        )

    def _version_label_from_entry(self, entry: dict | None) -> str | None:
        return alfresco_versioning.version_label_from_entry(entry)

    def _version_type_from_entry(self, entry: dict | None) -> str | None:
        return alfresco_versioning.version_type_from_entry(entry)

    def _user_name_from_entry(self, entry: dict | None, field: str) -> str | None:
        return alfresco_versioning.user_name_from_entry(entry, field)

    def _audit_from_entry(self, entry: dict | None) -> dict[str, object | None]:
        return alfresco_versioning.audit_from_entry(entry)

    def _node_detail_entry(self, ticket: str, node_id: str) -> dict | None:
        try:
            detail = self.client.get_node(ticket, node_id, include=["aspectNames", "properties"])
        except Exception:
            return None
        entry = detail.get("entry") if isinstance(detail, dict) else None
        return entry if isinstance(entry, dict) else None

    def _versioning_choice(self, versioning: dict | None) -> tuple[bool, str | None] | None:
        return alfresco_versioning.versioning_choice(versioning)

    def _existing_upload_metadata(self, target_destination: str, existing: dict) -> dict[str, object]:
        return alfresco_versioning.existing_upload_metadata(self.name, target_destination, existing)

    def _resolve_path(self, path: str, ticket: str | None = None, strict: bool = False) -> dict[str, str]:
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
                elif strict:
                    raise ProviderOperationError(f"Unable to resolve Alfresco path: {normalized}")
            except HTTPError:
                raise
            except Exception:
                if strict:
                    raise ProviderOperationError(f"Unable to resolve Alfresco path: {normalized}")
            try:
                live_parent = self.client.resolve_node_by_relative_path(ticket, parent_path)
                if live_parent and live_parent.get("id"):
                    parent_id = str(live_parent["id"])
                elif strict:
                    raise ProviderOperationError(f"Unable to resolve Alfresco parent path: {parent_path}")
            except HTTPError:
                raise
            except Exception:
                if strict:
                    raise ProviderOperationError(f"Unable to resolve Alfresco parent path: {parent_path}")

        return {
            "path": normalized,
            "node_id": node_id,
            "parent_path": parent_path,
            "parent_id": parent_id,
            "name": name,
        }

    def list_items(self, path: str, auth: BridgeAuthContext | None = None) -> ListingResult:
        try:
            def _run(ticket: str) -> ListingResult:
                resolved = self._resolve_path(path, ticket, strict=True)
                response = self.client.get_children(ticket, resolved["node_id"])
                entries = response.get("list", {}).get("entries", [])
                items = [self._item_from_entry(item.get("entry", {}), None) for item in entries]
                self.debug_logger.debug(
                    "provider_list_payload provider=%s path=%s entries=%s items=%s",
                    self.name,
                    resolved["path"],
                    len(entries) if isinstance(entries, list) else "invalid",
                    len(items),
                )
                return ListingResult(provider=self.name, path=resolved["path"], total=len(items), items=items)

            return self._run_with_ticket_retry(auth, f"list {self.client.normalize_path(path)}", _run)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise ProviderOperationError(f"Alfresco list failed for {self.client.normalize_path(path)}: {exc}") from exc

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
        try:
            live_node = self._live_node(path, auth, ticket)
        except ProviderOperationError:
            live_node = None

        if live_node and isinstance(live_node.get("entry"), dict):
            return self._item_from_entry(live_node["entry"], self.client.normalize_path(path))

        resolved = self._resolve_path(path, ticket, strict=False)
        try:
            parent = self._resolve_path(resolved["parent_path"], ticket, strict=True)
            child = self.client.child_by_name(ticket, parent["node_id"], resolved["name"])
        except Exception:
            child = None

        if child is None:
            return None

        resolved = self._resolve_path(path, ticket, strict=True)
        is_folder = resolved["path"] == "/" or resolved["path"].endswith("/") or "." not in resolved["name"]
        return DmsItem(
            id=resolved["node_id"],
            name=resolved["name"],
            path=resolved["path"],
            is_folder=is_folder,
            mime_type=None if is_folder else "application/octet-stream",
        )

    def copy_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        try:
            def _run(ticket: str) -> tuple[dict[str, str], str]:
                resolved = self._resolve_path(source, ticket, strict=True)
                target_parent_id, target_name, destination_path = self._target_parent_and_name(destination, ticket)
                self.client.copy_node(ticket, resolved["node_id"], target_parent_id, target_name)
                return resolved, destination_path

            resolved, destination_path = self._run_with_ticket_retry(auth, f"copy {source}", _run)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise ProviderOperationError(f"Alfresco copy failed for {source} -> {destination}: {exc}") from exc
        return OperationResult(
            success=True,
            operation="copy",
            provider=self.name,
            source=source,
            destination=destination_path,
            message=f"endpoint={self.client.node_copy_url(resolved['node_id'])};mode=live",
        )

    def rename_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        try:
            def _run(ticket: str) -> tuple[dict[str, str], str]:
                resolved = self._resolve_path(source, ticket, strict=True)
                destination_resolved = self._resolve_path(destination, ticket, strict=False)
                target_parent_id = destination_resolved["parent_id"]
                target_name = destination_resolved["name"]
                destination_path = destination_resolved["path"]
                if not target_name or destination_path == "/":
                    raise ProviderOperationError(
                        f"Alfresco rename failed for {resolved['path']} -> {destination_path}: destination name is missing."
                    )
                self.client.move_node(ticket, resolved["node_id"], target_parent_id, target_name)
                return resolved, destination_path

            resolved, destination_path = self._run_with_ticket_retry(auth, f"rename {source}", _run)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise ProviderOperationError(f"Alfresco rename failed for {source} -> {destination}: {exc}") from exc
        return OperationResult(
            success=True,
            operation="rename",
            provider=self.name,
            source=source,
            destination=destination_path,
            message=f"endpoint={self.client.node_move_url(resolved['node_id'])};mode=live",
        )

    def delete_item(self, target: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        try:
            def _run(ticket: str) -> dict[str, str]:
                resolved = self._resolve_path(target, ticket, strict=True)
                self.client.delete_node(ticket, resolved["node_id"])
                return resolved

            resolved = self._run_with_ticket_retry(auth, f"delete {target}", _run)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise ProviderOperationError(f"Alfresco delete failed for {target}: {exc}") from exc
        return OperationResult(
            success=True,
            operation="delete",
            provider=self.name,
            source=target,
            message=f"endpoint={self.client.node_delete_url(resolved['node_id'])};mode=live",
        )

    def make_dir(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        endpoint = self.client.node_create_child_url("{parentId}")
        try:
            def _run(ticket: str) -> tuple[str, str]:
                nonlocal endpoint
                resolved = self._resolve_path(path, ticket, strict=False)
                parent = self._resolve_path(resolved["parent_path"], ticket, strict=True)
                endpoint = self.client.node_create_child_url(parent["node_id"])
                self.client.create_child_node(ticket, parent["node_id"], resolved["name"], is_folder=True)
                return endpoint, resolved["path"]

            endpoint, _resolved_path = self._run_with_ticket_retry(auth, f"mkdir {path}", _run)
        except AuthenticationError:
            raise
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise AuthenticationError(f"Alfresco access denied for {self.client.normalize_path(path)}: HTTP {exc.code}.") from exc
            if exc.code == 409:
                return OperationResult(
                    success=True,
                    operation="mkdir",
                    provider=self.name,
                    source=path,
                    message=f"endpoint={endpoint};mode=live;status=exists",
                )
            raise ProviderOperationError(f"Alfresco mkdir failed for {self.client.normalize_path(path)}: HTTP Error {exc.code}") from exc
        except Exception as exc:
            raise ProviderOperationError(f"Alfresco mkdir failed for {self.client.normalize_path(path)}: {exc}") from exc
        return OperationResult(
            success=True,
            operation="mkdir",
            provider=self.name,
            source=path,
            message=f"endpoint={endpoint};mode=live",
        )

    def download_item(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        max_bytes = self._download_max_bytes()
        try:
            def _run(ticket: str) -> tuple[dict[str, str], bytes, str | None]:
                resolved = self._resolve_path(path, ticket, strict=True)
                raw_content, detected_mime = self.client.download_node_content(ticket, resolved["node_id"], max_bytes=max_bytes)
                return resolved, raw_content, detected_mime

            resolved, raw_content, detected_mime = self._run_with_ticket_retry(auth, f"download {path}", _run)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise ProviderOperationError(f"Alfresco download failed for {self.client.normalize_path(path)}: {exc}") from exc
        encoded = base64.b64encode(raw_content).decode("ascii")
        self.debug_logger.debug(
            "provider_download_payload provider=%s path=%s base64_chars=%s binary_bytes=%s mime_type=%s",
            self.name,
            resolved["path"],
            len(encoded),
            len(raw_content),
            detected_mime,
        )
        return OperationResult(
            success=True,
            operation="download",
            provider=self.name,
            source=resolved["path"],
            message=f"endpoint={self.client.node_content_url(resolved['node_id'])};mode=live",
            content_base64=encoded,
            mime_type=detected_mime,
            size=len(raw_content),
        )

    def stream_item(self, path: str, auth: BridgeAuthContext | None = None) -> dict[str, object]:
        try:
            def _run(ticket: str) -> tuple[dict[str, str], IO[bytes], str | None, int | None]:
                resolved = self._resolve_path(path, ticket, strict=True)
                stream, detected_mime, content_length = self.client.open_node_content_stream(ticket, resolved["node_id"])
                return resolved, stream, detected_mime, content_length

            resolved, stream, detected_mime, content_length = self._run_with_ticket_retry(auth, f"stream {path}", _run)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise ProviderOperationError(f"Alfresco stream failed for {self.client.normalize_path(path)}: {exc}") from exc
        self.debug_logger.debug(
            "provider_stream_payload provider=%s path=%s content_length=%s mime_type=%s",
            self.name,
            resolved["path"],
            content_length,
            detected_mime,
        )
        return {
            "success": True,
            "operation": "download",
            "provider": self.name,
            "source": resolved["path"],
            "stream": stream,
            "size": content_length,
            "mime_type": detected_mime or "application/octet-stream",
        }

    def upload_item(self, destination: str, file_name: str, content_base64: str | None = None, source_path: str | None = None, overwrite: bool = False, auth: BridgeAuthContext | None = None, versioning: dict | None = None) -> OperationResult:
        _ = overwrite
        content_state = "source-path" if source_path else ("inline-base64" if content_base64 else "external-stream")
        try:
            def _run(ticket: str) -> tuple[str, str, dict[str, object] | None]:
                resolved = self._resolve_path(destination, ticket, strict=True)
                target_parent_id = resolved["parent_id"] if resolved["path"] != "/" and "." in resolved["name"] else resolved["node_id"]
                target_destination = (
                    f"{resolved['path'].rstrip('/')}/{file_name}" if resolved["path"] != "/" and "." not in resolved["name"] else resolved["path"]
                )
                existing = self.client.child_by_name(ticket, target_parent_id, file_name)
                if existing is not None:
                    existing_node_id = str(existing.get("id") or "")
                    if not existing_node_id:
                        raise ProviderOperationError(f"Alfresco version upload failed: existing node id is missing for {target_destination}")
                    existing_detail = self._node_detail_entry(ticket, existing_node_id) or existing
                    metadata = self._existing_upload_metadata(target_destination, existing_detail)
                    choice = self._versioning_choice(versioning)
                    if choice is None:
                        raise VersionRequiredError(
                            f"Alfresco document already exists and requires version choice: {target_destination}",
                            metadata=metadata,
                        )

                    major_version, comment = choice
                    self.client.update_node_content(
                        ticket,
                        existing_node_id,
                        file_name,
                        content_base64=content_base64,
                        source_path=source_path,
                        major_version=major_version,
                        comment=comment,
                    )
                    updated_entry = self._node_detail_entry(ticket, existing_node_id)
                    metadata["action"] = "version"
                    metadata["major_version"] = major_version
                    metadata["comment"] = comment
                    metadata["version"] = self._version_label_from_entry(updated_entry if isinstance(updated_entry, dict) else None)
                    metadata["version_type"] = self._version_type_from_entry(updated_entry if isinstance(updated_entry, dict) else None)
                    updated_audit = self._audit_from_entry(updated_entry if isinstance(updated_entry, dict) else None)
                    metadata["changed_at"] = updated_audit["modified_at"]
                    metadata["changed_by"] = updated_audit["modified_by"]
                    return self.client.node_content_url(existing_node_id), target_destination, metadata

                self.client.create_child_node(ticket, target_parent_id, file_name, is_folder=False, content_base64=content_base64, source_path=source_path)
                return self.client.node_create_child_url(target_parent_id), target_destination, {"action": "create_document"}

            endpoint, target_destination, metadata = self._run_with_ticket_retry(auth, f"upload {destination}", _run)
        except AuthenticationError:
            raise
        except VersionRequiredError:
            raise
        except Exception as exc:
            raise ProviderOperationError(f"Alfresco upload failed for {destination} -> {file_name}: {exc}") from exc
        return OperationResult(
            success=True,
            operation="upload",
            provider=self.name,
            source=file_name,
            destination=target_destination,
            message=f"endpoint={endpoint};content={content_state};mode=live;action={metadata.get('action') if isinstance(metadata, dict) else 'upload'}",
            metadata=metadata,
        )

