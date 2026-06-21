from __future__ import annotations

from abc import ABC, abstractmethod

from dms_provider_bridge.models.bridge import BridgeAuthContext
from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.models.operation import OperationResult


class Provider(ABC):
    name: str
    upstream_auth_scheme: str = "unknown"

    def versioning_capabilities(self) -> dict[str, object]:
        return {"supported": False}

    def supports_share_url(self) -> bool:
        return False

    def share_url_to_path(self, share_url: str) -> str:
        raise NotImplementedError(f"Provider '{self.name}' does not support Share URL resolution.")

    @abstractmethod
    def list_items(self, path: str, auth: BridgeAuthContext | None = None) -> ListingResult:
        raise NotImplementedError

    @abstractmethod
    def bridge_endpoint_for(self, operation: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def stat_item(self, path: str, auth: BridgeAuthContext | None = None) -> DmsItem | None:
        raise NotImplementedError

    @abstractmethod
    def copy_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        raise NotImplementedError

    @abstractmethod
    def rename_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        raise NotImplementedError

    @abstractmethod
    def delete_item(self, target: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        raise NotImplementedError

    @abstractmethod
    def make_dir(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        raise NotImplementedError

    @abstractmethod
    def download_item(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        raise NotImplementedError

    @abstractmethod
    def upload_item(self, destination: str, file_name: str, content_base64: str | None = None, source_path: str | None = None, overwrite: bool = False, auth: BridgeAuthContext | None = None, versioning: dict | None = None) -> OperationResult:
        raise NotImplementedError

