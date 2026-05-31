from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import cast
from urllib.parse import unquote
from urllib import request


def _join_url(*parts: str) -> str:
    clean = [p.strip("/") for p in parts if p]
    if not clean:
        return ""
    return f"{clean[0]}" + ("/" + "/".join(clean[1:]) if len(clean) > 1 else "")


@dataclass(slots=True)
class AlfrescoClient:
    base_url: str
    api_roots: dict[str, str]
    endpoints: dict[str, str]
    doc_library: str

    @classmethod
    def from_config(cls, config: dict) -> "AlfrescoClient":
        return cls(
            base_url=str(config.get("base_url", "")),
            api_roots=dict(config.get("api", {})),
            endpoints=dict(config.get("endpoints", {})),
            doc_library=str(config.get("doc_library", "/")),
        )

    def ping(self) -> bool:
        return bool(self.base_url)

    def endpoint_url(self, endpoint_key: str, api_root_key: str) -> str:
        root = self.api_roots.get(api_root_key, "")
        suffix = self.endpoints.get(endpoint_key, "")
        return _join_url(self.base_url, root, suffix)

    def _repo_url(self, relative_path: str) -> str:
        return _join_url(self.base_url, self.api_roots.get("repo_root", ""), relative_path)

    def _search_url(self, relative_path: str) -> str:
        return _join_url(self.base_url, self.api_roots.get("search_root", ""), relative_path)

    def normalize_path(self, path: str) -> str:
        if not path or path == "/":
            return "/"
        normalized = unquote(path).replace("\\", "/")
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized.rstrip("/") or "/"

    def node_id_from_path(self, path: str) -> str:
        normalized = self.normalize_path(path)
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
        return f"alf-{digest}"

    def parent_path(self, path: str) -> str:
        normalized = self.normalize_path(path)
        if normalized == "/":
            return "/"
        parent = normalized.rsplit("/", 1)[0]
        return parent or "/"

    def node_by_id_url(self, node_id: str) -> str:
        return self._repo_url(f"nodes/{node_id}")

    def node_children_url(self, node_id: str) -> str:
        return self._repo_url(f"nodes/{node_id}/children")

    def node_copy_url(self, node_id: str) -> str:
        return self._repo_url(f"nodes/{node_id}/copy")

    def node_move_url(self, node_id: str) -> str:
        return self._repo_url(f"nodes/{node_id}/move")

    def node_delete_url(self, node_id: str) -> str:
        return self._repo_url(f"nodes/{node_id}")

    def node_create_child_url(self, parent_id: str) -> str:
        return self._repo_url(f"nodes/{parent_id}/children")

    def node_content_url(self, node_id: str) -> str:
        return self._repo_url(f"nodes/{node_id}/content")

    def search_nodes_url(self) -> str:
        return self._search_url("search")

    def ticket_login_url(self) -> str:
        return _join_url(self.base_url, "alfresco/api/-default-/public/authentication/versions/1/tickets")

    def _request_json(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        payload: dict | None = None,
        timeout: int = 30,
    ) -> dict:
        body = None
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        req = request.Request(url=url, data=body, headers=request_headers, method=method)
        with request.urlopen(req, timeout=timeout) as response:
            content = response.read().decode("utf-8")
            return json.loads(content) if content else {}

    def _request_bytes(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> tuple[bytes, str | None]:
        request_headers = {}
        if headers:
            request_headers.update(headers)
        req = request.Request(url=url, headers=request_headers, method=method)
        with request.urlopen(req, timeout=timeout) as response:
            data = response.read()
            mime = cast(str | None, response.headers.get("Content-Type"))
            return data, mime

    def create_ticket(self, username: str, password: str) -> str:
        response = self._request_json(
            "POST",
            self.ticket_login_url(),
            payload={"userId": username, "password": password},
        )
        entry = response.get("entry", {})
        ticket = entry.get("id")
        if not ticket:
            raise ValueError("Alfresco ticket login returned no ticket id.")
        return str(ticket)

    def auth_headers(self, ticket: str) -> dict[str, str]:
        return {"Authorization": f"Basic {ticket}"}

    def search_nodes(self, ticket: str, query: str, max_items: int = 200, skip_count: int = 0) -> dict:
        payload = {
            "query": {
                "language": "afts",
                "query": query,
            },
            "paging": {
                "maxItems": max_items,
                "skipCount": skip_count,
            },
            "include": ["path", "properties"],
        }
        return self._request_json("POST", self.search_nodes_url(), headers=self.auth_headers(ticket), payload=payload)

    def first_search_entry(self, ticket: str, query: str) -> dict | None:
        response = self.search_nodes(ticket, query, max_items=1)
        entries = response.get("list", {}).get("entries", [])
        if not entries:
            return None
        first = entries[0]
        if isinstance(first, dict):
            return first.get("entry") if isinstance(first.get("entry"), dict) else None
        return None

    def get_node(self, ticket: str, node_id: str) -> dict:
        return self._request_json("GET", self.node_by_id_url(node_id), headers=self.auth_headers(ticket))

    def get_children(self, ticket: str, node_id: str) -> dict:
        return self._request_json("GET", self.node_children_url(node_id), headers=self.auth_headers(ticket))

    def child_by_name(self, ticket: str, parent_id: str, name: str) -> dict | None:
        response = self.get_children(ticket, parent_id)
        entries = response.get("list", {}).get("entries", [])
        for item in entries:
            entry = item.get("entry", {}) if isinstance(item, dict) else {}
            if str(entry.get("name", "")) == name:
                return entry
        return None

    def resolve_doc_library_node(self, ticket: str) -> dict | None:
        # doc_library is expected in Alfresco PATH format (for example /app:company_home/st:sites).
        query = f'PATH:"{self.doc_library}"'
        return self.first_search_entry(ticket, query)

    def resolve_node_by_relative_path(self, ticket: str, relative_path: str) -> dict | None:
        normalized = self.normalize_path(relative_path)
        root = self.resolve_doc_library_node(ticket)
        if not root:
            return None
        current = root
        if normalized == "/":
            return current

        for segment in [part for part in normalized.split("/") if part]:
            child = self.child_by_name(ticket, str(current.get("id", "")), segment)
            if not child:
                return None
            current = child
        return current

    def copy_node(self, ticket: str, node_id: str, target_parent_id: str, name: str | None = None) -> dict:
        payload: dict[str, str] = {"targetParentId": target_parent_id}
        if name:
            payload["name"] = name
        return self._request_json("POST", self.node_copy_url(node_id), headers=self.auth_headers(ticket), payload=payload)

    def move_node(self, ticket: str, node_id: str, target_parent_id: str, name: str | None = None) -> dict:
        payload: dict[str, str] = {"targetParentId": target_parent_id}
        if name:
            payload["name"] = name
        return self._request_json("POST", self.node_move_url(node_id), headers=self.auth_headers(ticket), payload=payload)

    def create_child_node(
        self,
        ticket: str,
        parent_id: str,
        name: str,
        is_folder: bool = False,
        content_base64: str | None = None,
    ) -> dict:
        payload: dict[str, object] = {
            "name": name,
            "nodeType": "cm:folder" if is_folder else "cm:content",
        }
        if content_base64:
            payload["properties"] = {"cm:description": "Uploaded via edocat-bridge"}
        return self._request_json(
            "POST",
            self.node_create_child_url(parent_id),
            headers=self.auth_headers(ticket),
            payload=payload,
        )

    def delete_node(self, ticket: str, node_id: str) -> dict:
        return self._request_json("DELETE", self.node_delete_url(node_id), headers=self.auth_headers(ticket))

    def download_node_content(self, ticket: str, node_id: str) -> tuple[bytes, str | None]:
        return self._request_bytes("GET", self.node_content_url(node_id), headers=self.auth_headers(ticket))
