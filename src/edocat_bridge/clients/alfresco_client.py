from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from dataclasses import field
from typing import cast
from urllib.parse import unquote
from urllib.parse import urlencode
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
    node_types: dict[str, object] = field(default_factory=dict)
    _doclib_cache: dict[str, dict] = field(default_factory=dict)
    _path_cache: dict[str, dict] = field(default_factory=dict)
    _child_cache: dict[str, dict | None] = field(default_factory=dict)
    _cache_limit: int = 4096

    @classmethod
    def from_config(cls, config: dict) -> "AlfrescoClient":
        return cls(
            base_url=str(config.get("base_url", "")),
            api_roots=dict(config.get("api", {})),
            endpoints=dict(config.get("endpoints", {})),
            doc_library=str(config.get("doc_library", "/")),
            node_types=dict(config.get("nodeType", {})),
        )

    def _configured_node_type(self, key: str, fallback: str) -> str:
        value = self.node_types.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
        return fallback

    def ping(self) -> bool:
        return bool(self.base_url)

    def _ticket_key(self, ticket: str) -> str:
        return hashlib.sha1(ticket.encode("utf-8")).hexdigest()[:16]

    def _cache_get(self, store: dict, key: str):
        return store.get(key)

    def _cache_set(self, store: dict, key: str, value) -> None:
        if key in store:
            store[key] = value
            return
        if len(store) >= self._cache_limit:
            store.pop(next(iter(store)))
        store[key] = value

    def _invalidate_structure_cache(self, ticket: str) -> None:
        ticket_prefix = f"{self._ticket_key(ticket)}|"
        for store in (self._path_cache, self._child_cache):
            keys = [key for key in store if key.startswith(ticket_prefix)]
            for key in keys:
                store.pop(key, None)

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
        return _join_url(self.base_url, "api/-default-/public/authentication/versions/1/tickets")

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
        max_bytes: int | None = None,
    ) -> tuple[bytes, str | None]:
        request_headers = {}
        if headers:
            request_headers.update(headers)
        req = request.Request(url=url, headers=request_headers, method=method)
        with request.urlopen(req, timeout=timeout) as response:
            if isinstance(max_bytes, int) and max_bytes > 0:
                buffer = bytearray()
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    if len(buffer) > max_bytes:
                        raise ValueError(f"Alfresco download payload exceeds limit {max_bytes} B.")
                data = bytes(buffer)
            else:
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

    def basic_auth_token(self, username: str, password: str) -> str:
        return base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")

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

    def get_children(self, ticket: str, node_id: str, max_items: int = 200, skip_count: int = 0) -> dict:
        params = urlencode({"maxItems": max_items, "skipCount": skip_count})
        return self._request_json("GET", f"{self.node_children_url(node_id)}?{params}", headers=self.auth_headers(ticket))

    def child_by_name(self, ticket: str, parent_id: str, name: str) -> dict | None:
        expected = str(name)
        expected_folded = expected.casefold()
        cache_key = f"{self._ticket_key(ticket)}|{parent_id}|{expected_folded}"
        cached = self._cache_get(self._child_cache, cache_key)
        if cached is not None or cache_key in self._child_cache:
            return cached

        skip_count = 0
        max_items = 200

        while True:
            response = self.get_children(ticket, parent_id, max_items=max_items, skip_count=skip_count)
            entries = response.get("list", {}).get("entries", [])
            if not isinstance(entries, list) or not entries:
                return None

            for item in entries:
                entry = item.get("entry", {}) if isinstance(item, dict) else {}
                actual_name = str(entry.get("name", ""))
                if actual_name == expected or actual_name.casefold() == expected_folded:
                    self._cache_set(self._child_cache, cache_key, entry)
                    return entry

            if len(entries) < max_items:
                self._cache_set(self._child_cache, cache_key, None)
                return None
            skip_count += max_items

    def _decode_qname_segment(self, segment: str) -> str:
        raw = segment.strip()
        if not raw:
            return raw

        if ":" in raw:
            raw = raw.split(":", 1)[1]

        def replace_code(match: re.Match[str]) -> str:
            value = match.group(1)
            return chr(int(value, 16))

        return re.sub(r"_x([0-9A-Fa-f]{4})_", replace_code, raw)

    def _doc_library_segment_candidates(self, decoded_segment: str) -> list[str]:
        segment = decoded_segment.strip()
        folded = segment.casefold()

        if folded == "company_home":
            return ["Company Home", "company_home", "company home", "app:company_home"]
        if folded == "sites":
            return ["Sites", "sites", "st:sites"]
        if folded == "documentlibrary":
            return ["documentLibrary", "Document Library", "documentlibrary", "cm:documentLibrary"]
        return [segment, f"cm:{segment}"]

    def _resolve_doc_library_by_walk(self, ticket: str) -> dict | None:
        raw_path = str(self.doc_library or "").strip()
        if not raw_path:
            return None

        segments = [self._decode_qname_segment(part) for part in raw_path.strip("/").split("/") if part]
        if not segments:
            return None

        current: dict[str, str] = {"id": "-root-", "name": "/"}
        for segment in segments:
            candidates = self._doc_library_segment_candidates(segment)
            resolved = None
            for candidate in candidates:
                resolved = self.child_by_name(ticket, str(current.get("id", "")), candidate)
                if resolved is not None:
                    break
            if resolved is None:
                return None
            current = resolved
        return current

    def resolve_doc_library_node(self, ticket: str) -> dict | None:
        cache_key = f"{self._ticket_key(ticket)}|{self.doc_library}"
        cached = self._cache_get(self._doclib_cache, cache_key)
        if cached is not None:
            return cached

        # Prefer SEARCH API for speed, but some deployments return 500 here.
        query = f'PATH:"{self.doc_library}"'
        try:
            entry = self.first_search_entry(ticket, query)
            if entry is not None:
                self._cache_set(self._doclib_cache, cache_key, entry)
                return entry
        except Exception:
            pass
        fallback = self._resolve_doc_library_by_walk(ticket)
        if fallback is not None:
            self._cache_set(self._doclib_cache, cache_key, fallback)
        return fallback

    def resolve_node_by_relative_path(self, ticket: str, relative_path: str) -> dict | None:
        normalized = self.normalize_path(relative_path)
        path_cache_key = f"{self._ticket_key(ticket)}|{normalized}"
        cached = self._cache_get(self._path_cache, path_cache_key)
        if cached is not None:
            return cached

        root = self.resolve_doc_library_node(ticket)
        if not root:
            return None
        current = root
        if normalized == "/":
            self._cache_set(self._path_cache, path_cache_key, current)
            return current

        def walk(segments: list[str]) -> dict | None:
            node = root
            current_path = ""
            for segment in segments:
                current_path = f"{current_path}/{segment}"
                segment_cache_key = f"{self._ticket_key(ticket)}|{current_path}"
                segment_cached = self._cache_get(self._path_cache, segment_cache_key)
                if segment_cached is not None:
                    node = segment_cached
                    continue
                child = self.child_by_name(ticket, str(node.get("id", "")), segment)
                if not child:
                    return None
                node = child
                self._cache_set(self._path_cache, segment_cache_key, node)
            return node

        segments = [part for part in normalized.split("/") if part]
        attempts: list[list[str]] = [segments]
        if len(segments) > 1:
            attempts.append(segments[1:])

        for candidate in attempts:
            resolved = walk(candidate)
            if resolved is not None:
                self._cache_set(self._path_cache, path_cache_key, resolved)
                return resolved
        return None

    def copy_node(self, ticket: str, node_id: str, target_parent_id: str, name: str | None = None) -> dict:
        payload: dict[str, str] = {"targetParentId": target_parent_id}
        if name:
            payload["name"] = name
        response = self._request_json("POST", self.node_copy_url(node_id), headers=self.auth_headers(ticket), payload=payload)
        self._invalidate_structure_cache(ticket)
        return response

    def move_node(self, ticket: str, node_id: str, target_parent_id: str, name: str | None = None) -> dict:
        payload: dict[str, str] = {"targetParentId": target_parent_id}
        if name:
            payload["name"] = name
        response = self._request_json("POST", self.node_move_url(node_id), headers=self.auth_headers(ticket), payload=payload)
        self._invalidate_structure_cache(ticket)
        return response

    def create_child_node(
        self,
        ticket: str,
        parent_id: str,
        name: str,
        is_folder: bool = False,
        content_base64: str | None = None,
    ) -> dict:
        folder_type = self._configured_node_type("folder", "cm:folder")
        file_type = self._configured_node_type("file", "cm:content")
        if not is_folder and content_base64 is not None:
            try:
                content_bytes = base64.b64decode(content_base64, validate=True)
            except Exception as exc:
                raise ValueError("Invalid base64 payload for Alfresco upload.") from exc

            boundary = f"----edocatbridge{hashlib.sha1(name.encode('utf-8')).hexdigest()[:16]}"
            safe_name = name.replace('"', "_")

            body = bytearray()

            def append_field(field_name: str, field_value: str) -> None:
                body.extend(f"--{boundary}\r\n".encode("utf-8"))
                body.extend(f"Content-Disposition: form-data; name=\"{field_name}\"\r\n\r\n".encode("utf-8"))
                body.extend(field_value.encode("utf-8"))
                body.extend(b"\r\n")

            append_field("name", name)
            append_field("nodeType", file_type)
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f"Content-Disposition: form-data; name=\"filedata\"; filename=\"{safe_name}\"\r\n".encode("utf-8"))
            body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
            body.extend(content_bytes)
            body.extend(b"\r\n")
            body.extend(f"--{boundary}--\r\n".encode("utf-8"))

            request_headers = self.auth_headers(ticket)
            request_headers["Accept"] = "application/json"
            request_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            req = request.Request(
                url=self.node_create_child_url(parent_id),
                data=bytes(body),
                headers=request_headers,
                method="POST",
            )
            with request.urlopen(req, timeout=30) as response:
                content = response.read().decode("utf-8")
                result = json.loads(content) if content else {}
            self._invalidate_structure_cache(ticket)
            return result

        payload: dict[str, object] = {
            "name": name,
            "nodeType": folder_type if is_folder else file_type,
        }
        response = self._request_json(
            "POST",
            self.node_create_child_url(parent_id),
            headers=self.auth_headers(ticket),
            payload=payload,
        )
        self._invalidate_structure_cache(ticket)
        return response

    def delete_node(self, ticket: str, node_id: str) -> dict:
        response = self._request_json("DELETE", self.node_delete_url(node_id), headers=self.auth_headers(ticket))
        self._invalidate_structure_cache(ticket)
        return response

    def download_node_content(self, ticket: str, node_id: str, max_bytes: int | None = None) -> tuple[bytes, str | None]:
        return self._request_bytes("GET", self.node_content_url(node_id), headers=self.auth_headers(ticket), max_bytes=max_bytes)
