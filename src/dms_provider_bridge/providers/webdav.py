from __future__ import annotations

import base64
import mimetypes
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib import request
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree

from dms_provider_bridge.core.config_loader import load_provider_config
from dms_provider_bridge.core.debug import provider_debug_logger
from dms_provider_bridge.core.errors import ProviderOperationError
from dms_provider_bridge.models.bridge import BridgeAuthContext
from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.providers.base import Provider
from dms_provider_bridge.services.auth_resolver import resolve_effective_auth


DAV_NS = "{DAV:}"


class WebdavProvider(Provider):
    name = "webdav"
    upstream_auth_scheme = "basic"

    def __init__(self, name: str | None = None, config: dict | None = None) -> None:
        self.name = name or self.name
        self.config = config or load_provider_config("webdav")
        self.upstream_auth_scheme = self._configured_auth_scheme()
        self.debug_logger = provider_debug_logger(self.name, self.config)

    def _configured_auth_scheme(self) -> str:
        credentials = self.config.get("credentials")
        scheme = None
        if isinstance(credentials, dict):
            scheme = credentials.get("authScheme") or credentials.get("scheme") or credentials.get("type")
        if not isinstance(scheme, str) or not scheme.strip():
            webdav_cfg = self.config.get("webdav")
            if isinstance(webdav_cfg, dict):
                scheme = webdav_cfg.get("authScheme") or webdav_cfg.get("auth_scheme")
        normalized = str(scheme or "basic").strip().lower().replace("-", "_")
        if normalized in {"bearer", "bearer_token", "oauth2"}:
            return "bearer"
        return "basic"

    def bridge_endpoint_for(self, operation: str) -> str | None:
        methods = self.config.get("methods", {})
        if isinstance(methods, dict):
            method = methods.get(operation)
            if isinstance(method, str) and method.strip():
                return method.strip()
        endpoints = self.config.get("endpoints", {})
        if isinstance(endpoints, dict):
            endpoint = endpoints.get(operation)
            if isinstance(endpoint, str) and endpoint.strip():
                return endpoint.strip()
        return None

    def _timeout(self) -> int:
        limits = self.config.get("limits", {})
        timeouts = limits.get("timeouts") if isinstance(limits, dict) else None
        value = timeouts.get("requestSeconds") if isinstance(timeouts, dict) else None
        return int(value) if isinstance(value, int) and value > 0 else 60

    def _base_url(self) -> str:
        base_url = str(self.config.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            raise ProviderOperationError("WebDAV base_url is not configured.")
        return base_url

    def _path_url(self, path: str, *, directory: bool = False) -> str:
        base_url = self._base_url()
        root_path = str(self.config.get("root_path") or "/").strip()
        resource_path = ""
        webdav_cfg = self.config.get("webdav")
        if isinstance(webdav_cfg, dict):
            resource_path = str(webdav_cfg.get("resource_path") or "").strip()

        pieces = [root_path, resource_path, path or "/"]
        raw_path = "/".join(piece.strip("/") for piece in pieces if piece and piece != "/")
        encoded = "/".join(quote(unquote(piece), safe="") for piece in raw_path.split("/") if piece)
        url = base_url if not encoded else f"{base_url}/{encoded}"
        if directory and not url.endswith("/"):
            url = f"{url}/"
        return url

    def _auth_headers(self, auth: BridgeAuthContext | None) -> dict[str, str]:
        effective_auth = resolve_effective_auth(
            self.config,
            auth,
            default_scheme=self.upstream_auth_scheme,
            validate_required=False,
        )
        return effective_auth.authorization_headers()

    def _request_bytes(
        self,
        method: str,
        url: str,
        auth: BridgeAuthContext | None,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> tuple[bytes, int, dict[str, str]]:
        request_headers = {"Accept": "*/*"}
        request_headers.update(self._auth_headers(auth))
        if headers:
            request_headers.update(headers)
        req = request.Request(url=url, data=body, headers=request_headers, method=method)
        try:
            with request.urlopen(req, timeout=self._timeout()) as response:
                return response.read(), int(response.status), dict(response.headers)
        except HTTPError as exc:
            content = exc.read()
            raise ProviderOperationError(
                f"WebDAV {method} failed for {url}: HTTP {exc.code}; {content[:200]!r}",
                status_code=int(exc.code),
            ) from exc

    def _request_no_content(
        self,
        method: str,
        url: str,
        auth: BridgeAuthContext | None,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> tuple[int, dict[str, str]]:
        _content, status, response_headers = self._request_bytes(method, url, auth, headers=headers, body=body)
        return status, response_headers

    def _propfind(
        self,
        path: str,
        auth: BridgeAuthContext | None,
        depth: str,
        *,
        directory: bool = False,
    ) -> list[ElementTree.Element]:
        body = b"""<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:displayname/>
    <d:resourcetype/>
    <d:getcontentlength/>
    <d:getcontenttype/>
    <d:getlastmodified/>
    <d:getetag/>
    <d:creationdate/>
  </d:prop>
</d:propfind>
"""
        url = self._path_url(path, directory=directory)
        content, _status, _headers = self._request_bytes(
            "PROPFIND",
            url,
            auth,
            headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"},
            body=body,
        )
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as exc:
            raise ProviderOperationError(f"WebDAV PROPFIND returned invalid XML for {path}: {exc}") from exc
        return list(root.findall(f"{DAV_NS}response"))

    def _href_to_path(self, href: str) -> str:
        parsed_href = urlparse(href)
        href_path = unquote(parsed_href.path or href).rstrip("/")
        base_path = unquote(urlparse(self._base_url()).path).rstrip("/")
        if base_path and href_path.startswith(base_path):
            relative = href_path[len(base_path):]
        else:
            relative = href_path
        relative = relative.strip("/")
        return f"/{relative}" if relative else "/"

    def _response_to_item(self, response: ElementTree.Element) -> DmsItem:
        href = response.findtext(f"{DAV_NS}href") or "/"
        prop = response.find(f"{DAV_NS}propstat/{DAV_NS}prop")
        if prop is None:
            prop = ElementTree.Element("empty")

        path = self._href_to_path(href)
        display_name = prop.findtext(f"{DAV_NS}displayname")
        name = (display_name or path.rstrip("/").rsplit("/", 1)[-1] or "/").strip()

        resource_type = prop.find(f"{DAV_NS}resourcetype")
        is_folder = resource_type is not None and resource_type.find(f"{DAV_NS}collection") is not None

        size_text = prop.findtext(f"{DAV_NS}getcontentlength")
        try:
            size = int(size_text) if size_text else None
        except ValueError:
            size = None

        modified_at = prop.findtext(f"{DAV_NS}getlastmodified")
        if modified_at:
            try:
                modified_at = parsedate_to_datetime(modified_at).isoformat()
            except (TypeError, ValueError):
                pass
        if not modified_at:
            created_at = prop.findtext(f"{DAV_NS}creationdate")
            if created_at:
                try:
                    modified_at = datetime.fromisoformat(created_at.replace("Z", "+00:00")).isoformat()
                except ValueError:
                    modified_at = created_at

        etag = prop.findtext(f"{DAV_NS}getetag")
        return DmsItem(
            id=etag.strip('"') if etag else path,
            name=name,
            path=path,
            is_folder=is_folder,
            size=size,
            mime_type=prop.findtext(f"{DAV_NS}getcontenttype"),
            modified_at=modified_at,
        )

    def _not_implemented(self, operation: str) -> ProviderOperationError:
        return ProviderOperationError(f"WebDAV driver operation '{operation}' is not implemented yet.")

    def list_items(self, path: str, auth: BridgeAuthContext | None = None) -> ListingResult:
        normalized = path or "/"
        current = self._href_to_path(self._path_url(normalized, directory=True))
        items = [self._response_to_item(response) for response in self._propfind(normalized, auth, "1", directory=True)]
        children = [item for item in items if item.path.rstrip("/") != current.rstrip("/")]
        children.sort(key=lambda item: (not item.is_folder, item.name.casefold()))
        return ListingResult(provider=self.name, path=normalized, total=len(children), items=children)

    def stat_item(self, path: str, auth: BridgeAuthContext | None = None) -> DmsItem | None:
        try:
            items = [self._response_to_item(response) for response in self._propfind(path or "/", auth, "0")]
        except ProviderOperationError as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            raise
        return items[0] if items else None

    def copy_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        source_url = self._path_url(source)
        destination_url = self._path_url(destination)
        self._request_no_content(
            "COPY",
            source_url,
            auth,
            headers={
                "Destination": destination_url,
                "Overwrite": "F",
            },
        )
        return OperationResult(success=True, operation="copy", provider=self.name, source=source, destination=destination)

    def rename_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        source_url = self._path_url(source)
        destination_url = self._path_url(destination)
        self._request_no_content(
            "MOVE",
            source_url,
            auth,
            headers={
                "Destination": destination_url,
                "Overwrite": "F",
            },
        )
        return OperationResult(success=True, operation="move", provider=self.name, source=source, destination=destination)

    def delete_item(self, target: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        self._request_no_content("DELETE", self._path_url(target), auth)
        return OperationResult(success=True, operation="delete", provider=self.name, source=target)

    def make_dir(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        self._request_no_content("MKCOL", self._path_url(path, directory=True), auth)
        return OperationResult(success=True, operation="mkdir", provider=self.name, destination=path)

    def download_item(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        content, _status, headers = self._request_bytes("GET", self._path_url(path), auth)
        content_type = headers.get("Content-Type") or headers.get("content-type")
        return OperationResult(
            success=True,
            operation="download",
            provider=self.name,
            source=path,
            content_base64=base64.b64encode(content).decode("ascii"),
            mime_type=content_type,
            size=len(content),
        )

    def upload_item(
        self,
        destination: str,
        file_name: str,
        content_base64: str | None = None,
        source_path: str | None = None,
        overwrite: bool = False,
        auth: BridgeAuthContext | None = None,
        versioning: dict | None = None,
    ) -> OperationResult:
        _ = versioning
        if source_path:
            with open(source_path, "rb") as handle:
                payload = handle.read()
        elif content_base64:
            payload = base64.b64decode(content_base64)
        else:
            payload = b""

        target_folder = destination.rstrip("/")
        target_path = f"{target_folder}/{file_name}" if target_folder else f"/{file_name}"
        content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        self._request_no_content(
            "PUT",
            self._path_url(target_path),
            auth,
            headers={
                "Content-Type": content_type,
                "Overwrite": "T" if overwrite else "F",
            },
            body=payload,
        )
        return OperationResult(
            success=True,
            operation="upload",
            provider=self.name,
            destination=target_path,
            size=len(payload),
            mime_type=content_type,
        )
