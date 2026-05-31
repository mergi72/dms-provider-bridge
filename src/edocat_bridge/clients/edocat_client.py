from __future__ import annotations

from dataclasses import dataclass


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

    @classmethod
    def from_config(cls, config: dict) -> "EdocatClient":
        return cls(
            base_url=str(config.get("base_url", "")),
            api_root=str(config.get("api", "")),
            endpoints=dict(config.get("endpoints", {})),
        )

    def ping(self) -> bool:
        return bool(self.base_url)

    def endpoint_url(self, endpoint_key: str) -> str:
        suffix = self.endpoints.get(endpoint_key, "")
        return _join_url(self.base_url, self.api_root, suffix)
