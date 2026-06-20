from __future__ import annotations

import base64
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib import request
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree

from dms_provider_bridge.core.config_loader import load_provider_config
from dms_provider_bridge.core.credentials import load_windows_credential
from dms_provider_bridge.core.debug import provider_debug_logger
from dms_provider_bridge.core.errors import AuthenticationError, ProviderOperationError
from dms_provider_bridge.models.bridge import BridgeAuthContext
from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.providers.base import Provider


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
        username = auth.username if auth else None
        password = auth.password if auth else None
        token = auth.token if auth else None

        if auth and auth.credential_id and not (username and password):
            try:
                credential = load_windows_credential(auth.credential_id)
            except AuthenticationError:
                credential = None
            if credential is not None:
                username = username or credential.username
                password = password or credential.password
                token = token or credential.token

        if token:
            normalized = token.strip()
            if normalized.lower().startswith(("basic ", "bearer ")):
                return {"Authorization": normalized}
            return {"Authorization": f"Bearer {normalized}"}

        if self.upstream_auth_scheme == "bearer" and password:
            normalized = password.strip()
            if normalized.lower().startswith("bearer "):
                return {"Authorization": normalized}
            return {"Authorization": f"Bearer {normalized}"}

        if username:
            encoded = base64.b64encode(f"{username}:{password or ''}".encode("utf-8")).decode("ascii")
            return {"Authorization": f"Basic {encoded}"}

        raise ProviderOperationError("WebDAV credentials are missing; live operation cannot continue.")

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
            raise ProviderOperationError(f"WebDAV {method} failed for {url}: HTTP {exc.code}; {content[:200]!r}") from exc

    def _propfind(self, path: str, auth: BridgeAuthContext | None, depth: str) -> list[ElementTree.Element]:
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
        url = self._path_url(path, directory=True)
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
        items = [self._response_to_item(response) for response in self._propfind(normalized, auth, "1")]
        children = [item for item in items if item.path.rstrip("/") != current.rstrip("/")]
        children.sort(key=lambda item: (not item.is_folder, item.name.casefold()))
        return ListingResult(provider=self.name, path=normalized, total=len(children), items=children)

    def stat_item(self, path: str, auth: BridgeAuthContext | None = None) -> DmsItem | None:
        items = [self._response_to_item(response) for response in self._propfind(path or "/", auth, "0")]
        return items[0] if items else None

    def copy_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        raise self._not_implemented("copy")

    def rename_item(self, source: str, destination: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        raise self._not_implemented("move")

    def delete_item(self, target: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        raise self._not_implemented("delete")

    def make_dir(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        raise self._not_implemented("mkdir")

    def download_item(self, path: str, auth: BridgeAuthContext | None = None) -> OperationResult:
        raise self._not_implemented("download")

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
        raise self._not_implemented("upload")
