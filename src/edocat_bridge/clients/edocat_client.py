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

    def basic_auth_headers(self, username: str | None, password: str | None = None) -> dict[str, str]:
        if not username:
            return {}
        token = base64.b64encode(f"{username}:{password or ''}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    def query_nodes(self, path: str, username: str | None = None, password: str | None = None, include_content: bool = False) -> dict[str, Any]:
        params: dict[str, str] = {"path": path}
        if include_content:
            params["includeContent"] = "true"
        url = f"{self.endpoint_url('query')}?{urlencode(params)}"
        return self._request_json("GET", url, headers=self.basic_auth_headers(username, password))

    def create_node(self, payload: dict[str, Any], username: str | None = None, password: str | None = None) -> dict[str, Any]:
        return self._request_json("POST", self.endpoint_url("node"), headers=self.basic_auth_headers(username, password), payload=payload)

    def update_node(self, payload: dict[str, Any], username: str | None = None, password: str | None = None) -> dict[str, Any]:
        return self._request_json("PUT", self.endpoint_url("node"), headers=self.basic_auth_headers(username, password), payload=payload)

    def delete_nodes(self, uuids: list[str], username: str | None = None, password: str | None = None) -> dict[str, Any]:
        params = [("uuids", uuid) for uuid in uuids if uuid]
        url = f"{self.endpoint_url('node')}?{urlencode(params)}" if params else self.endpoint_url("node")
        return self._request_json("DELETE", url, headers=self.basic_auth_headers(username, password))
