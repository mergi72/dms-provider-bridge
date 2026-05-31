from __future__ import annotations

import hashlib
from dataclasses import dataclass


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
        normalized = path.replace("\\", "/")
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
