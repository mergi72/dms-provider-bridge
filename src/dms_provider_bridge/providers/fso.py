from __future__ import annotations

import base64
from datetime import datetime, timezone
import mimetypes
import os
import shutil

from dms_provider_bridge.core.config_loader import load_provider_config
from dms_provider_bridge.core.errors import ProviderOperationError
from dms_provider_bridge.models.bridge import BridgeAuthContext
from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.providers.base import Provider


class FsoProvider(Provider):
    name = "fso"
    upstream_auth_scheme = "none"

    def __init__(self, config: dict | None = None) -> None:
        self.config = config if isinstance(config, dict) else load_provider_config(self.name)
        self.allowed_roots = self._parse_allowed_roots(self.config)

    def _normalize_virtual_path(self, path: str) -> str:
        raw = (path or "").strip() or "/"
        normalized = raw.replace("\\", "/")
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized

    def _to_local_path(self, path: str) -> str:
        normalized = self._normalize_virtual_path(path)
        if os.name == "nt" and len(normalized) >= 3 and normalized[0] == "/" and normalized[2] == ":":
            normalized = normalized[1:]
        return os.path.abspath(os.path.normpath(normalized))

    def _parse_allowed_roots(self, config: dict) -> list[str]:
        raw_roots = config.get("allowed_roots")
        if raw_roots is None:
            raw_roots = config.get("allowedRoots")
        if not isinstance(raw_roots, list):
            return []

        roots: list[str] = []
        for value in raw_roots:
            if not isinstance(value, str):
                continue
            cleaned = value.strip()
            if not cleaned:
                continue
            roots.append(self._to_local_path(cleaned))
        return roots

    def _is_under_allowed_roots(self, local_path: str) -> bool:
        if not self.allowed_roots:
            return True
        target = os.path.abspath(local_path)
        for root in self.allowed_roots:
            try:
                if os.path.commonpath([target, root]) == root:
                    return True
            except ValueError:
                continue
        return False

    def _ensure_allowed(self, local_path: str, operation: str, virtual_path: str) -> None:
        if self._is_under_allowed_roots(local_path):
            return
        roots = ", ".join(self.allowed_roots)
        raise ProviderOperationError(
            f"FSO {operation} failed: path '{virtual_path}' is outside allowed roots ({roots})."
        )

    def _child_virtual_path(self, parent: str, name: str) -> str:
        normalized_parent = self._normalize_virtual_path(parent).rstrip("/") or "/"
        return f"{normalized_parent}/{name}" if normalized_parent != "/" else f"/{name}"

    def _modified_at_iso(self, stat_result: os.stat_result | None) -> str | None:
        if stat_result is None:
            return None
        try:
            return datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except (OSError, OverflowError, ValueError):
            return None

    def list_items(self, path: str, auth: BridgeAuthContext | None = None) -> ListingResult:
        virtual_path = self._normalize_virtual_path(path)
        local_path = self._to_local_path(virtual_path)
        self._ensure_allowed(local_path, "list", virtual_path)
        if not os.path.isdir(local_path):
            return ListingResult(provider=self.name, path=virtual_path, total=0, items=[])

        items: list[DmsItem] = []
        for entry in os.scandir(local_path):
            child_virtual = self._child_virtual_path(virtual_path, entry.name)
            is_folder = entry.is_dir()
            size = None
            mime_type = None
            stat_result = None
            try:
                stat_result = entry.stat()
            except OSError:
                stat_result = None
            if not is_folder:
                size = stat_result.st_size if stat_result is not None else None
                mime_type = mimetypes.guess_type(entry.name)[0]
            items.append(
                DmsItem(
                    id=child_virtual,
                    name=entry.name,
                    path=child_virtual,
                    is_folder=is_folder,
                    size=size,
                    mime_type=mime_type,
                    modified_at=self._modified_at_iso(stat_result),
                    is_read_only=not os.access(entry.path, os.W_OK),
                )
            )

        return ListingResult(provider=self.name, path=virtual_path, total=len(items), items=items)

    def bridge_endpoint_for(self, operation: str) -> str | None:
        return None

    def stat_item(self, path: str, auth: BridgeAuthContext | None = None) -> DmsItem | None:
        virtual_path = self._normalize_virtual_path(path)
        if virtual_path == "/":
            return DmsItem(id="fso-root", name="/", path="/", is_folder=True)

        local_path = self._to_local_path(virtual_path)
        self._ensure_allowed(local_path, "stat", virtual_path)
        if not os.path.exists(local_path):
            return None

        is_folder = os.path.isdir(local_path)
        stat_result = os.stat(local_path)
        size = None if is_folder else stat_result.st_size
        mime_type = None if is_folder else mimetypes.guess_type(local_path)[0]
        name = os.path.basename(local_path.rstrip("\\/")) or "/"
        return DmsItem(
            id=virtual_path,
            name=name,
            path=virtual_path,
            is_folder=is_folder,
            size=size,
            mime_type=mime_type,
            modified_at=self._modified_at_iso(stat_result),
            is_read_only=not os.access(local_path, os.W_OK),
        )

    def copy_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        src_virtual = self._normalize_virtual_path(source)
        dst_virtual = self._normalize_virtual_path(destination)
        src_local = self._to_local_path(src_virtual)
        dst_local = self._to_local_path(dst_virtual)
        self._ensure_allowed(src_local, "copy", src_virtual)
        self._ensure_allowed(dst_local, "copy", dst_virtual)

        if not os.path.exists(src_local):
            raise ProviderOperationError(f"FSO copy failed: source not found: {src_virtual}")

        if os.path.isdir(src_local):
            shutil.copytree(src_local, dst_local, dirs_exist_ok=False)
        else:
            os.makedirs(os.path.dirname(dst_local) or ".", exist_ok=True)
            shutil.copy2(src_local, dst_local)

        return OperationResult(success=True, operation="copy", provider=self.name, source=src_virtual, destination=dst_virtual)

    def rename_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        src_virtual = self._normalize_virtual_path(source)
        dst_virtual = self._normalize_virtual_path(destination)
        src_local = self._to_local_path(src_virtual)
        dst_local = self._to_local_path(dst_virtual)
        self._ensure_allowed(src_local, "rename", src_virtual)
        self._ensure_allowed(dst_local, "rename", dst_virtual)
        if not os.path.exists(src_local):
            raise ProviderOperationError(f"FSO rename failed: source not found: {src_virtual}")
        os.makedirs(os.path.dirname(dst_local) or ".", exist_ok=True)
        shutil.move(src_local, dst_local)
        return OperationResult(success=True, operation="rename", provider=self.name, source=src_virtual, destination=dst_virtual)

    def delete_item(self, target: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        target_virtual = self._normalize_virtual_path(target)
        target_local = self._to_local_path(target_virtual)
        self._ensure_allowed(target_local, "delete", target_virtual)
        if not os.path.exists(target_local):
            raise ProviderOperationError(f"FSO delete failed: target not found: {target_virtual}")
        if os.path.isdir(target_local):
            shutil.rmtree(target_local)
        else:
            os.remove(target_local)
        return OperationResult(success=True, operation="delete", provider=self.name, source=target_virtual)

    def make_dir(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        virtual_path = self._normalize_virtual_path(path)
        local_path = self._to_local_path(virtual_path)
        self._ensure_allowed(local_path, "mkdir", virtual_path)
        os.makedirs(local_path, exist_ok=True)
        return OperationResult(success=True, operation="mkdir", provider=self.name, source=virtual_path)

    def download_item(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        virtual_path = self._normalize_virtual_path(path)
        local_path = self._to_local_path(virtual_path)
        self._ensure_allowed(local_path, "download", virtual_path)
        if not os.path.exists(local_path) or os.path.isdir(local_path):
            raise ProviderOperationError(f"FSO download failed: file not found: {virtual_path}")
        with open(local_path, "rb") as handle:
            data = handle.read()
        return OperationResult(
            success=True,
            operation="download",
            provider=self.name,
            source=virtual_path,
            content_base64=base64.b64encode(data).decode("ascii"),
            mime_type=mimetypes.guess_type(local_path)[0],
            size=len(data),
        )

    def upload_item(self, destination: str, file_name: str, content_base64: str | None = None, source_path: str | None = None, overwrite: bool = False, auth: BridgeAuthContext | None = None) -> OperationResult:
        destination_virtual = self._normalize_virtual_path(destination)
        destination_local = self._to_local_path(destination_virtual)
        self._ensure_allowed(destination_local, "upload", destination_virtual)
        os.makedirs(destination_local, exist_ok=True)
        target_local = os.path.join(destination_local, file_name)
        self._ensure_allowed(target_local, "upload", self._child_virtual_path(destination_virtual, file_name))
        if os.path.exists(target_local) and not overwrite:
            raise ProviderOperationError(f"FSO upload failed: target exists and overwrite is false: {target_local}")

        if source_path:
            with open(source_path, "rb") as source_handle, open(target_local, "wb") as target_handle:
                while True:
                    chunk = source_handle.read(1024 * 1024)
                    if not chunk:
                        break
                    target_handle.write(chunk)
            size = os.path.getsize(target_local)
        else:
            data = base64.b64decode(content_base64) if content_base64 else b""
            with open(target_local, "wb") as handle:
                handle.write(data)
            size = len(data)

        target_virtual = self._child_virtual_path(destination_virtual, file_name)
        return OperationResult(success=True, operation="upload", provider=self.name, source=file_name, destination=target_virtual, size=size, mime_type=mimetypes.guess_type(file_name)[0])

