from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib import request


def _join_url(*parts: str) -> str:
    clean = [p.strip("/") for p in parts if p]
    if not clean:
        return ""
    return f"{clean[0]}" + ("/" + "/".join(clean[1:]) if len(clean) > 1 else "")


@dataclass(slots=True)
class EdocatClient:
    base_url: str
    api_root: str
    endpoints: dict[str, str]
    doc_library: str

    @classmethod
    def from_config(cls, config: dict) -> "EdocatClient":
        return cls(
            base_url=str(config.get("base_url", "")),
            api_root=str(config.get("api", "")),
            endpoints=dict(config.get("endpoints", {})),
            doc_library=str(config.get("doc_library", "/deals")),
        )

    def ping(self) -> bool:
        return bool(self.base_url)

    def endpoint_url(self, endpoint_key: str) -> str:
        suffix = self.endpoints.get(endpoint_key, "")
        return _join_url(self.base_url, self.api_root, suffix)

    def _request_json(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        req = request.Request(url=url, data=body, headers=request_headers, method=method)
        with request.urlopen(req, timeout=30) as response:
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
        page_size = 200
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

    def create_node(self, payload: dict[str, Any], username: str | None = None, password: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", self.endpoint_url("node"), headers=self.basic_auth_headers(username, password), payload=payload)

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
