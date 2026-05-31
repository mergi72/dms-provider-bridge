from __future__ import annotations

from abc import ABC, abstractmethod

from edocat_bridge.models.item import DmsItem
from edocat_bridge.models.listing import ListingResult
from edocat_bridge.models.operation import OperationResult


class Provider(ABC):
    name: str
    upstream_auth_scheme: str = "unknown"

    @abstractmethod
    def list_items(self, path: str) -> ListingResult:
        raise NotImplementedError

    @abstractmethod
    def bridge_endpoint_for(self, operation: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def stat_item(self, path: str) -> DmsItem | None:
        raise NotImplementedError

    @abstractmethod
    def copy_item(self, source: str, destination: str) -> OperationResult:
        raise NotImplementedError

    @abstractmethod
    def rename_item(self, source: str, destination: str) -> OperationResult:
        raise NotImplementedError

    @abstractmethod
    def delete_item(self, target: str) -> OperationResult:
        raise NotImplementedError

    @abstractmethod
    def make_dir(self, path: str) -> OperationResult:
        raise NotImplementedError
