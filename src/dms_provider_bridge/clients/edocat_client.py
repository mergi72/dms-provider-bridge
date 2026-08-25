from __future__ import annotations

import base64
import json
from dataclasses import dataclass
import re
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib import request


def _join_url(*parts: str) -> str:
    clean = [p.strip("/") for p in parts if p]
    if not clean:
        return ""
    return f"{clean[0]}" + ("/" + "/".join(clean[1:]) if len(clean) > 1 else "")


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


@dataclass(slots=True)
class EdocatClient:
    base_url: str
    api_root: str
    endpoints: dict[str, str]
    doc_library: str
    request_timeout: int = 30
    upload_timeout: int = 300

    @classmethod
    def from_config(cls, config: dict) -> "EdocatClient":
        timeouts = config.get("timeouts", {})
        request_timeout = 30
        upload_timeout = 300
        if isinstance(timeouts, dict):
            configured_request = timeouts.get("requestSeconds")
            configured_upload = timeouts.get("uploadSeconds")
            if isinstance(configured_request, int) and configured_request > 0:
                request_timeout = configured_request
            if isinstance(configured_upload, int) and configured_upload > 0:
                upload_timeout = configured_upload
        return cls(
            base_url=str(config.get("base_url", "")),
            api_root=str(config.get("api", "")),
            endpoints=dict(config.get("endpoints", {})),
            doc_library=str(config.get("doc_library", "/deals")),
            request_timeout=request_timeout,
            upload_timeout=upload_timeout,
        )

    def ping(self) -> bool:
        return bool(self.base_url)

    def endpoint_url(self, endpoint_key: str) -> str:
        suffix = self.endpoints.get(endpoint_key, "")
        return _join_url(self.base_url, self.api_root, suffix)

    def resolve_share_url(self, share_url: str) -> str:
        parsed = urlparse(share_url.strip())
        configured = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("eDoCat Share URL must use HTTP or HTTPS.")
        if parsed.hostname.casefold() != (configured.hostname or "").casefold() or parsed.port != configured.port:
            raise ValueError("eDoCat Share URL host does not match the configured connection host.")
        if not re.fullmatch(r"/share/page/browse/DIR-[A-Za-z0-9_-]+", parsed.path):
            raise ValueError("eDoCat Share URL must use /share/page/browse/DIR-... format.")

        req = request.Request(share_url.strip(), method="GET", headers={"Accept": "text/html"})
        opener = request.build_opener(_NoRedirect())
        try:
            with opener.open(req, timeout=self.request_timeout) as response:
                location = response.headers.get("Location")
        except HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise
            location = exc.headers.get("Location")
        if not location:
            raise ValueError("eDoCat Share URL did not return a redirect path.")

        redirected = urlparse(urljoin(share_url, location))
        if redirected.hostname.casefold() != parsed.hostname.casefold() or redirected.port != parsed.port:
            raise ValueError("eDoCat Share URL redirected outside the configured host.")
        paths = parse_qs(redirected.query).get("path", [])
        if len(paths) != 1 or not paths[0].strip():
            raise ValueError("eDoCat Share URL redirect does not contain one path parameter.")
        normalized = paths[0].replace("\\", "/").strip()
        return normalized if normalized.startswith("/") else f"/{normalized}"

    def _request_json(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        req = request.Request(url=url, data=body, headers=request_headers, method=method)
        with request.urlopen(req, timeout=timeout or self.request_timeout) as response:
            content = response.read().decode("utf-8")
            return json.loads(content) if content else {}

    def _request_bytes(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> tuple[bytes, str | None]:
        request_headers = {"Accept": "*/*"}
        if headers:
            request_headers.update(headers)
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        req = request.Request(url=url, data=body, headers=request_headers, method=method)
        with request.urlopen(req, timeout=60) as response:
            content_type = response.headers.get("Content-Type")
            content = response.read()
            return content, content_type

    def basic_auth_headers(self, username: str | None, password: str | None = None) -> dict[str, str]:
        if not username:
            return {}
        token = base64.b64encode(f"{username}:{password or ''}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    def _extract_page_size(self, response: dict[str, Any], default_size: int) -> int:
        candidates = (
            response.get("pageSize"),
            response.get("size"),
            response.get("limit"),
            (response.get("pagination") or {}).get("size") if isinstance(response.get("pagination"), dict) else None,
            (response.get("page") or {}).get("size") if isinstance(response.get("page"), dict) else None,
        )
        for value in candidates:
            if isinstance(value, int) and value > 0:
                return value
        return default_size

    def _extract_total(self, response: dict[str, Any]) -> int | None:
        candidates = (
            response.get("total"),
            response.get("totalCount"),
            response.get("totalElements"),
            (response.get("pagination") or {}).get("total") if isinstance(response.get("pagination"), dict) else None,
            (response.get("page") or {}).get("totalElements") if isinstance(response.get("page"), dict) else None,
        )
        for value in candidates:
            if isinstance(value, int) and value >= 0:
                return value
        return None

    def _extract_has_next(self, response: dict[str, Any]) -> bool | None:
        candidates = (
            response.get("hasNext"),
            response.get("hasMore"),
            (response.get("pagination") or {}).get("hasNext") if isinstance(response.get("pagination"), dict) else None,
            (response.get("page") or {}).get("hasNext") if isinstance(response.get("page"), dict) else None,
        )
        for value in candidates:
            if isinstance(value, bool):
                return value
        return None

    def _page_signature(self, nodes: list[Any]) -> tuple[tuple[str, str, str, str], ...]:
        signature: list[tuple[str, str, str, str]] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            signature.append((
                str(node.get("uuid") or ""),
                str(node.get("id") or ""),
                str(node.get("path") or ""),
                str(node.get("name") or ""),
            ))
        return tuple(signature)

    def query_nodes(self, path: str, username: str | None = None, password: str | None = None, include_content: bool = False) -> dict[str, Any]:
        headers = self.basic_auth_headers(username, password)
        endpoint = self.endpoint_url("query")
        page = 0
        page_size = 100
        max_pages = 1000
        aggregated_nodes: list[dict[str, Any]] = []
        first_response: dict[str, Any] | None = None
        seen_page_signatures: set[tuple[tuple[str, str, str, str], ...]] = set()

        while page < max_pages:
            params: dict[str, str] = {
                "path": path,
                "page": str(page),
                "size": str(page_size),
            }
            if include_content:
                params["includeContent"] = "true"

            url = f"{endpoint}?{urlencode(params)}"
            response = self._request_json("GET", url, headers=headers)
            if first_response is None:
                first_response = response

            nodes = response.get("nodes", [])
            if not isinstance(nodes, list):
                break

            page_signature = self._page_signature(nodes)
            if page_signature and page_signature in seen_page_signatures:
                break
            seen_page_signatures.add(page_signature)

            aggregated_nodes.extend(node for node in nodes if isinstance(node, dict))
            has_next = self._extract_has_next(response)
            total = self._extract_total(response)
            effective_size = self._extract_page_size(response, page_size)

            if has_next is False:
                break
            if total is not None and len(aggregated_nodes) >= total:
                break
            if len(nodes) < effective_size:
                break

            page += 1
            page_size = effective_size

        if first_response is None:
            return {"nodes": []}

        merged = dict(first_response)
        merged["nodes"] = aggregated_nodes
        return merged

    def query_nodes_by_uuids(
        self,
        uuids: list[str],
        username: str | None = None,
        password: str | None = None,
        include_content: bool = False,
    ) -> dict[str, Any]:
        headers = self.basic_auth_headers(username, password)
        endpoint = self.endpoint_url("query")
        params: list[tuple[str, str]] = [("uuids", uuid) for uuid in uuids if uuid]
        if include_content:
            params.append(("includeContent", "true"))
        url = f"{endpoint}?{urlencode(params)}" if params else endpoint
        return self._request_json("GET", url, headers=headers)

    def search_nodes(
        self,
        query: str,
        max_items: int = 20,
        username: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        """Search through eDoCat's Alfresco FTS query endpoint."""
        payload = {
            "query": query,
            "includeContent": False,
            "paging": {"maxItems": max_items, "skipCount": 0},
        }
        return self._request_json(
            "POST",
            self.endpoint_url("query"),
            headers=self.basic_auth_headers(username, password),
            payload=payload,
        )

    def search_metadata_nodes(
        self,
        function: str,
        field: str | None,
        value: str,
        node_type: str,
        max_items: int = 20,
        username: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        clause = [function, value] if field is None else [function, field, value]
        payload = {
            "nodeType": node_type,
            "query": [clause],
            "includeContent": False,
            "paging": {"maxItems": max_items, "skipCount": 0},
        }
        return self._request_json(
            "POST",
            self.endpoint_url("search"),
            headers=self.basic_auth_headers(username, password),
            payload=payload,
        )

    def create_node(self, payload: dict[str, Any], username: str | None = None, password: str | None = None) -> dict[str, Any]:
        return self._request_json(
            "POST",
            self.endpoint_url("node"),
            headers=self.basic_auth_headers(username, password),
            payload=payload,
            timeout=self.upload_timeout,
        )

    def update_node(self, payload: dict[str, Any], username: str | None = None, password: str | None = None) -> dict[str, Any]:
        return self._request_json("PUT", self.endpoint_url("node"), headers=self.basic_auth_headers(username, password), payload=payload)

    def delete_nodes(self, uuids: list[str], username: str | None = None, password: str | None = None) -> dict[str, Any]:
        params = [("uuids", uuid) for uuid in uuids if uuid]
        url = f"{self.endpoint_url('node')}?{urlencode(params)}" if params else self.endpoint_url("node")
        return self._request_json("DELETE", url, headers=self.basic_auth_headers(username, password))

    def request_bytes(
        self,
        method: str,
        url: str,
        username: str | None = None,
        password: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> tuple[bytes, str | None]:
        return self._request_bytes(method, url, headers=self.basic_auth_headers(username, password), payload=payload)
