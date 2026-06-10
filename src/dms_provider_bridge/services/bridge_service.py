from __future__ import annotations

import time
from urllib.parse import unquote, urlparse

from dms_provider_bridge.adapters.commander_api import WfxErrorCode, build_wfx_path, parse_wfx_path
from dms_provider_bridge.core.logging import get_logger
from dms_provider_bridge.core.errors import AuthenticationError, ProviderNotFoundError, VersionRequiredError
from dms_provider_bridge.models.bridge import BridgeAuthContext, WfxResponse
from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.services.auth_service import validate_bridge_auth
from dms_provider_bridge.services.provider_service import get_default_provider_name, get_provider, list_registered_providers
from dms_provider_bridge.services.bridge_transfer_ops import TransferNotFoundError, TransferPrecheckError, copy_fso_to_edocat, upload_with_preflight


_LOGGER = get_logger(__name__)


def _success(data: object = None, message: str | None = None, metadata: dict | None = None) -> WfxResponse:
    return WfxResponse(ok=True, error_code=WfxErrorCode.OK, message=message, data=data, metadata=metadata)


def _failure(code: int, message: str, metadata: dict | None = None) -> WfxResponse:
    return WfxResponse(ok=False, error_code=code, message=message, data=None, metadata=metadata)


def _resolve(path: str):
    parsed = parse_wfx_path(path)
    provider = get_provider(parsed.provider)
    return provider, parsed


def _metadata(provider, operation: str) -> dict[str, str | None]:
    return {
        "provider": provider.name,
        "upstream_auth_scheme": provider.upstream_auth_scheme,
        "upstream_endpoint": provider.bridge_endpoint_for(operation),
    }


def _deduplicate_repeated_leaf(path: str) -> str | None:
    normalized = (path or "").strip()
    if not normalized:
        return None

    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    parts = [segment for segment in normalized.split("/") if segment]
    if len(parts) < 2:
        return None
    if parts[-1] != parts[-2]:
        return None

    return "/" + "/".join(parts[:-1])


def _is_provider_root_path(path: str | None) -> bool:
    normalized = (path or "").strip().replace("\\", "/")
    return normalized in {"", "/"}


def _provider_root_listing() -> ListingResult:
    providers = list_registered_providers()
    items = [
        DmsItem(
            id=provider_name,
            name=provider_name,
            path=build_wfx_path(provider_name, "/"),
            is_folder=True,
            mime_type="application/x-dms-provider",
        )
        for provider_name in providers
    ]
    return ListingResult(provider="bridge", path="/", total=len(items), items=items)


def _provider_capabilities(provider) -> dict[str, bool]:
    method_by_operation = {
        "list": "list_items",
        "stat": "stat_item",
        "download": "download_item",
        "upload": "upload_item",
        "mkdir": "make_dir",
        "delete": "delete_item",
        "rename": "rename_item",
        "copy": "copy_item",
    }
    return {
        operation: callable(getattr(provider, method_name, None))
        for operation, method_name in method_by_operation.items()
    }


def _versioning_payload(versioning: object) -> dict | None:
    if versioning is None:
        return None
    if hasattr(versioning, "model_dump"):
        dumped = versioning.model_dump(exclude_none=True)
        return dumped if isinstance(dumped, dict) else None
    return versioning if isinstance(versioning, dict) else None


def _provider_versioning(provider) -> dict[str, object]:
    if getattr(provider, "name", "") == "alfresco":
        return {
            "supported": True,
            "existing_upload": "version_required",
            "modes": ["version"],
            "version_types": ["minor", "major"],
            "default_major": False,
            "comment_supported": True,
        }
    return {"supported": False}


def _provider_auth_requirements(provider) -> dict[str, object]:
    config = getattr(provider, "config", {})
    credentials = config.get("credentials") if isinstance(config, dict) else None
    auth: dict[str, object] = {}
    if isinstance(credentials, dict):
        mode = str(credentials.get("mode") or "").strip() or "credentials"
        auth["mode"] = mode
        for key in ("target", "targetBase"):
            value = credentials.get(key)
            if isinstance(value, str) and value.strip():
                auth[key] = value
        required = credentials.get("required")
        auth["required"] = bool(required) if isinstance(required, bool) else mode.lower() != "none"
        return auth

    if getattr(provider, "upstream_auth_scheme", "unknown") == "none":
        return {"mode": "none", "required": False}
    return {"mode": "credentials", "required": True}


def _log_and_return(
    operation: str,
    provider: str | None,
    path: str,
    started_at: float,
    response: WfxResponse,
    error: str | None = None,
) -> WfxResponse:
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    provider_value = provider or "-"
    error_value = error or response.message or ""
    level_method = _LOGGER.info if response.ok else _LOGGER.warning
    level_method(
        "bridge_operation operation=%s provider=%s path=%s error=%s duration_ms=%d",
        operation,
        provider_value,
        path,
        error_value,
        duration_ms,
    )
    return response


def providers_path() -> WfxResponse:
    started_at = time.perf_counter()
    providers = list_registered_providers()
    default_provider = get_default_provider_name()
    response = _success(
        data={
            "providers": providers,
            "default_provider": default_provider,
        },
        metadata={"operation": "providers"},
    )
    return _log_and_return("providers", None, "/", started_at, response)


def provider_detail_path(provider_name: str) -> WfxResponse:
    started_at = time.perf_counter()
    try:
        provider = get_provider(provider_name)
        response = _success(
            data={
                "name": provider.name,
                "enabled": provider.name in list_registered_providers(),
                "auth": _provider_auth_requirements(provider),
                "capabilities": _provider_capabilities(provider),
                "versioning": _provider_versioning(provider),
            },
            metadata={"operation": "provider_detail", "provider": provider.name},
        )
        return _log_and_return("provider_detail", provider.name, "/", started_at, response)
    except ProviderNotFoundError as exc:
        response = _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
        return _log_and_return("provider_detail", provider_name, "/", started_at, response, str(exc))


def list_path(path: str, auth: BridgeAuthContext | None) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        if _is_provider_root_path(path):
            response = _success(
                data=_provider_root_listing().model_dump(),
                metadata={
                    "operation": "list",
                    "provider_root": True,
                    "providers": list_registered_providers(),
                    "default_provider": get_default_provider_name(),
                },
            )
            return _log_and_return("list", "bridge", "/", started_at, response)
        if auth is None:
            response = _failure(WfxErrorCode.ACCESS_DENIED, "Authentication is required for provider paths.")
            return _log_and_return("list", provider_name, resolved_path, started_at, response, response.message)
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        listing = provider.list_items(parsed.path, auth)
        response = _success(data=listing.model_dump(), metadata=_metadata(provider, "list"))
        return _log_and_return("list", provider_name, resolved_path, started_at, response)
    except AuthenticationError as exc:
        response = _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
        return _log_and_return("list", provider_name, resolved_path, started_at, response, str(exc))
    except ValueError as exc:
        response = _failure(WfxErrorCode.BAD_PATH, str(exc))
        return _log_and_return("list", provider_name, resolved_path, started_at, response, str(exc))
    except ProviderNotFoundError as exc:
        response = _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
        return _log_and_return("list", provider_name, resolved_path, started_at, response, str(exc))
    except Exception as exc:
        response = _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
        return _log_and_return("list", provider_name, resolved_path, started_at, response, str(exc))


def stat_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        item = provider.stat_item(parsed.path, auth)
        if item is None:
            deduplicated_path = _deduplicate_repeated_leaf(parsed.path)
            if deduplicated_path and deduplicated_path != parsed.path:
                item = provider.stat_item(deduplicated_path, auth)
                if item is not None:
                    resolved_path = deduplicated_path
                    response = _success(data=item.model_dump(), metadata=_metadata(provider, "stat"))
                    return _log_and_return("stat", provider_name, resolved_path, started_at, response)

            response = _failure(WfxErrorCode.NOT_FOUND, f"Path not found: {path}")
            return _log_and_return("stat", provider_name, resolved_path, started_at, response, response.message)
        response = _success(data=item.model_dump(), metadata=_metadata(provider, "stat"))
        return _log_and_return("stat", provider_name, resolved_path, started_at, response)
    except AuthenticationError as exc:
        response = _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
        return _log_and_return("stat", provider_name, resolved_path, started_at, response, str(exc))
    except ValueError as exc:
        response = _failure(WfxErrorCode.BAD_PATH, str(exc))
        return _log_and_return("stat", provider_name, resolved_path, started_at, response, str(exc))
    except ProviderNotFoundError as exc:
        response = _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
        return _log_and_return("stat", provider_name, resolved_path, started_at, response, str(exc))
    except Exception as exc:
        response = _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
        return _log_and_return("stat", provider_name, resolved_path, started_at, response, str(exc))


def mkdir_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        result = provider.make_dir(parsed.path, auth)
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "mkdir"))
        return _log_and_return("mkdir", provider_name, resolved_path, started_at, response)
    except AuthenticationError as exc:
        response = _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
        return _log_and_return("mkdir", provider_name, resolved_path, started_at, response, str(exc))
    except ValueError as exc:
        response = _failure(WfxErrorCode.BAD_PATH, str(exc))
        return _log_and_return("mkdir", provider_name, resolved_path, started_at, response, str(exc))
    except ProviderNotFoundError as exc:
        response = _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
        return _log_and_return("mkdir", provider_name, resolved_path, started_at, response, str(exc))
    except Exception as exc:
        response = _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
        return _log_and_return("mkdir", provider_name, resolved_path, started_at, response, str(exc))


def delete_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        result = provider.delete_item(parsed.path, auth)
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "delete"))
        return _log_and_return("delete", provider_name, resolved_path, started_at, response)
    except AuthenticationError as exc:
        response = _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
        return _log_and_return("delete", provider_name, resolved_path, started_at, response, str(exc))
    except ValueError as exc:
        response = _failure(WfxErrorCode.BAD_PATH, str(exc))
        return _log_and_return("delete", provider_name, resolved_path, started_at, response, str(exc))
    except ProviderNotFoundError as exc:
        response = _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
        return _log_and_return("delete", provider_name, resolved_path, started_at, response, str(exc))
    except Exception as exc:
        response = _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
        return _log_and_return("delete", provider_name, resolved_path, started_at, response, str(exc))


def rename_path(source: str, destination: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    operation_path = f"{source} -> {destination}"
    try:
        src_provider, src = _resolve(source)
        dst_provider, dst = _resolve(destination)
        provider_name = src_provider.name
        operation_path = f"{src.path} -> {dst.path}"
        validate_bridge_auth(auth)
        if src_provider.name != dst_provider.name:
            response = _failure(WfxErrorCode.NOT_SUPPORTED, "Cross-provider rename is not supported.")
            return _log_and_return("rename", provider_name, operation_path, started_at, response, response.message)
        result = src_provider.rename_item(src.path, dst.path, auth)
        response = _success(data=result.model_dump(), metadata=_metadata(src_provider, "rename"))
        return _log_and_return("rename", provider_name, operation_path, started_at, response)
    except AuthenticationError as exc:
        response = _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
        return _log_and_return("rename", provider_name, operation_path, started_at, response, str(exc))
    except ValueError as exc:
        response = _failure(WfxErrorCode.BAD_PATH, str(exc))
        return _log_and_return("rename", provider_name, operation_path, started_at, response, str(exc))
    except ProviderNotFoundError as exc:
        response = _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
        return _log_and_return("rename", provider_name, operation_path, started_at, response, str(exc))
    except Exception as exc:
        response = _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
        return _log_and_return("rename", provider_name, operation_path, started_at, response, str(exc))


def copy_path(source: str, destination: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    operation_path = f"{source} -> {destination}"
    try:
        src_provider, src = _resolve(source)
        dst_provider, dst = _resolve(destination)
        provider_name = f"{src_provider.name}->{dst_provider.name}"
        operation_path = f"{src.path} -> {dst.path}"
        validate_bridge_auth(auth)
        if src_provider.name == dst_provider.name:
            result = src_provider.copy_item(src.path, dst.path, auth)
            response = _success(data=result.model_dump(), metadata=_metadata(src_provider, "copy"))
            return _log_and_return("copy", provider_name, operation_path, started_at, response)

        # Cross-provider upload flow: local file system provider -> any DMS provider.
        if src_provider.name != "fso" or dst_provider.name == "fso":
            response = _failure(WfxErrorCode.NOT_SUPPORTED, "Cross-provider copy is supported only for fso -> dms providers.")
            return _log_and_return("copy", provider_name, operation_path, started_at, response, response.message)

        try:
            result = copy_fso_to_edocat(src_provider, dst_provider, src.path, dst.path, auth)
        except TransferNotFoundError:
            response = _failure(WfxErrorCode.NOT_FOUND, f"Path not found: {source}")
            return _log_and_return("copy", provider_name, operation_path, started_at, response, response.message)
        except TransferPrecheckError as exc:
            response = _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
            return _log_and_return("copy", provider_name, operation_path, started_at, response, str(exc))
        response = _success(data=result.model_dump(), metadata=_metadata(dst_provider, "upload"))
        return _log_and_return("copy", provider_name, operation_path, started_at, response)
    except AuthenticationError as exc:
        response = _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
        return _log_and_return("copy", provider_name, operation_path, started_at, response, str(exc))
    except ValueError as exc:
        response = _failure(WfxErrorCode.BAD_PATH, str(exc))
        return _log_and_return("copy", provider_name, operation_path, started_at, response, str(exc))
    except ProviderNotFoundError as exc:
        response = _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
        return _log_and_return("copy", provider_name, operation_path, started_at, response, str(exc))
    except Exception as exc:
        response = _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
        return _log_and_return("copy", provider_name, operation_path, started_at, response, str(exc))


def download_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        result = provider.download_item(parsed.path, auth)
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "download"))
        return _log_and_return("download", provider_name, resolved_path, started_at, response)
    except AuthenticationError as exc:
        response = _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
        return _log_and_return("download", provider_name, resolved_path, started_at, response, str(exc))
    except ValueError as exc:
        response = _failure(WfxErrorCode.BAD_PATH, str(exc))
        return _log_and_return("download", provider_name, resolved_path, started_at, response, str(exc))
    except ProviderNotFoundError as exc:
        response = _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
        return _log_and_return("download", provider_name, resolved_path, started_at, response, str(exc))
    except Exception as exc:
        response = _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
        return _log_and_return("download", provider_name, resolved_path, started_at, response, str(exc))


def open_download_stream(path: str, auth: BridgeAuthContext) -> WfxResponse | None:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        stream_item = getattr(provider, "stream_item", None)
        if not callable(stream_item):
            return None
        validate_bridge_auth(auth)
        result = stream_item(parsed.path, auth)
        response = _success(data=result, metadata=_metadata(provider, "download"))
        return _log_and_return("download_raw_stream", provider_name, resolved_path, started_at, response)
    except AuthenticationError as exc:
        response = _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
        return _log_and_return("download_raw_stream", provider_name, resolved_path, started_at, response, str(exc))
    except ValueError as exc:
        response = _failure(WfxErrorCode.BAD_PATH, str(exc))
        return _log_and_return("download_raw_stream", provider_name, resolved_path, started_at, response, str(exc))
    except ProviderNotFoundError as exc:
        response = _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
        return _log_and_return("download_raw_stream", provider_name, resolved_path, started_at, response, str(exc))
    except Exception as exc:
        response = _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
        return _log_and_return("download_raw_stream", provider_name, resolved_path, started_at, response, str(exc))


def upload_path(destination: str, file_name: str, auth: BridgeAuthContext, content_base64: str | None = None, source_path: str | None = None, overwrite: bool = False, versioning: dict | None = None) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = destination
    try:
        provider, parsed = _resolve(destination)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        try:
            result = upload_with_preflight(provider, parsed.path, file_name, auth, content_base64=content_base64, source_path=source_path, overwrite=overwrite, versioning=_versioning_payload(versioning))
        except TransferPrecheckError as exc:
            response = _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
            return _log_and_return("upload", provider_name, resolved_path, started_at, response, str(exc))
        except VersionRequiredError as exc:
            response = _failure(WfxErrorCode.ACCESS_DENIED, str(exc), metadata=exc.metadata)
            return _log_and_return("upload", provider_name, resolved_path, started_at, response, str(exc))
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "upload"))
        return _log_and_return("upload", provider_name, resolved_path, started_at, response)
    except AuthenticationError as exc:
        response = _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
        return _log_and_return("upload", provider_name, resolved_path, started_at, response, str(exc))
    except ValueError as exc:
        response = _failure(WfxErrorCode.BAD_PATH, str(exc))
        return _log_and_return("upload", provider_name, resolved_path, started_at, response, str(exc))
    except ProviderNotFoundError as exc:
        response = _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
        return _log_and_return("upload", provider_name, resolved_path, started_at, response, str(exc))
    except Exception as exc:
        response = _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
        return _log_and_return("upload", provider_name, resolved_path, started_at, response, str(exc))


def resolve_share_url(share_url: str, provider: str = "alfresco") -> WfxResponse:
    try:
        if provider != "alfresco":
            return _failure(WfxErrorCode.NOT_SUPPORTED, f"Unsupported provider for share URL: {provider}")

        parsed = urlparse(share_url)
        fragment = parsed.fragment or ""
        if not fragment:
            return _failure(WfxErrorCode.BAD_PATH, "Share URL must contain a hash path (fragment).")

        fragment_path = fragment.split("?", 1)[0].strip()
        if not fragment_path:
            return _failure(WfxErrorCode.BAD_PATH, "Share URL fragment path is empty.")

        normalized = unquote(fragment_path)
        normalized = normalized.replace("\\", "/")
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"

        wfx_path = build_wfx_path(provider, normalized)
        return _success(
            data={
                "provider": provider,
                "path": wfx_path,
                "share_path": normalized,
                "source_url": share_url,
            },
            metadata={"provider": provider, "operation": "resolve-share-url"},
        )
    except Exception as exc:
        return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))


def browse_share_url(
    share_url: str,
    auth: BridgeAuthContext | None,
    provider: str = "alfresco",
    operation: str = "list",
    execute: bool = True,
    provider_path_override: str | None = None,
    destination_share_url: str | None = None,
    destination_path_override: str | None = None,
    file_name: str | None = None,
    content_base64: str | None = None,
    overwrite: bool = False,
    versioning: dict | None = None,
) -> WfxResponse:
    if not execute:
        validated = validate_browse_share_url(
            share_url,
            provider,
            operation,
            provider_path_override,
            destination_share_url,
            destination_path_override,
            file_name,
        )
        if not validated.ok:
            return validated
        metadata = dict(validated.metadata or {})
        metadata["operation"] = f"browse-share-url:dry-run:{operation}"
        payload = dict(validated.data) if isinstance(validated.data, dict) else {"validated": validated.data}
        payload["executed"] = False
        return _success(data=payload, metadata=metadata)

    resolved = resolve_share_url(share_url, provider)
    if not resolved.ok:
        return resolved

    if not isinstance(resolved.data, dict):
        return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved share URL payload has invalid format.")

    resolved_payload = dict(resolved.data)

    path = str(resolved_payload.get("path", ""))
    path_source = "share_url"
    if provider_path_override:
        normalized_override = unquote(provider_path_override).replace("\\", "/").strip()
        if not normalized_override:
            return _failure(WfxErrorCode.BAD_PATH, "provider_path_override is empty.")
        if not normalized_override.startswith("/"):
            normalized_override = f"/{normalized_override}"
        path = build_wfx_path(provider, normalized_override)
        resolved_payload["path"] = path
        resolved_payload["share_path"] = normalized_override
        path_source = "provider_path_override"

    if not path:
        return _failure(WfxErrorCode.BAD_PATH, "Resolved share URL does not contain a target path.")

    if execute and auth is None:
        return _failure(WfxErrorCode.ACCESS_DENIED, "Auth is required when execute=true.")

    destination_path: str | None = None
    destination_source: str | None = None

    if operation == "list":
        response = list_path(path, auth)
    elif operation == "stat":
        response = stat_path(path, auth)
    elif operation == "download":
        response = download_path(path, auth)
    elif operation == "mkdir":
        response = mkdir_path(path, auth)
    elif operation == "delete":
        response = delete_path(path, auth)
    elif operation in {"copy", "move"}:
        if destination_path_override:
            normalized_destination = unquote(destination_path_override).replace("\\", "/").strip()
            if not normalized_destination:
                return _failure(WfxErrorCode.BAD_PATH, "destination_path_override is empty.")
            if not normalized_destination.startswith("/"):
                normalized_destination = f"/{normalized_destination}"
            destination_path = build_wfx_path(provider, normalized_destination)
            destination_source = "destination_path_override"
        elif destination_share_url:
            destination_resolved = resolve_share_url(destination_share_url, provider)
            if not destination_resolved.ok:
                return destination_resolved
            if not isinstance(destination_resolved.data, dict):
                return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved destination share URL payload has invalid format.")
            destination_path = str(destination_resolved.data.get("path", ""))
            destination_source = "destination_share_url"
        else:
            return _failure(
                WfxErrorCode.BAD_PATH,
                "copy/move requires destination_path_override or destination_share_url.",
            )

        if not destination_path:
            return _failure(WfxErrorCode.BAD_PATH, "Destination path is empty.")

        response = copy_path(path, destination_path, auth) if operation == "copy" else rename_path(path, destination_path, auth)
    elif operation == "upload":
        if not file_name:
            return _failure(WfxErrorCode.BAD_PATH, "upload requires file_name.")

        upload_destination_path = path
        upload_destination_source = path_source
        if destination_path_override:
            normalized_destination = unquote(destination_path_override).replace("\\", "/").strip()
            if not normalized_destination:
                return _failure(WfxErrorCode.BAD_PATH, "destination_path_override is empty.")
            if not normalized_destination.startswith("/"):
                normalized_destination = f"/{normalized_destination}"
            upload_destination_path = build_wfx_path(provider, normalized_destination)
            upload_destination_source = "destination_path_override"
        elif destination_share_url:
            destination_resolved = resolve_share_url(destination_share_url, provider)
            if not destination_resolved.ok:
                return destination_resolved
            if not isinstance(destination_resolved.data, dict):
                return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved destination share URL payload has invalid format.")
            upload_destination_path = str(destination_resolved.data.get("path", ""))
            upload_destination_source = "destination_share_url"

        if not upload_destination_path:
            return _failure(WfxErrorCode.BAD_PATH, "Upload destination path is empty.")

        response = upload_path(
            upload_destination_path,
            file_name,
            auth,
            content_base64=content_base64,
            overwrite=overwrite,
            versioning=_versioning_payload(versioning),
        )
        destination_path = upload_destination_path
        destination_source = upload_destination_source
    else:
        return _failure(WfxErrorCode.NOT_SUPPORTED, f"Unsupported operation for share URL browse: {operation}")

    if not response.ok:
        return response

    merged_data = {
        "resolved": resolved_payload,
        "path_source": path_source,
        "result": response.data,
    }
    if operation in {"copy", "move", "upload"} and destination_path and destination_source:
        merged_data["destination"] = {
            "path": destination_path,
            "path_source": destination_source,
        }
    merged_meta = dict(response.metadata or {})
    merged_meta["operation"] = f"browse-share-url:{operation}"
    return _success(data=merged_data, metadata=merged_meta)


def validate_browse_share_url(
    share_url: str,
    provider: str = "alfresco",
    operation: str = "list",
    provider_path_override: str | None = None,
    destination_share_url: str | None = None,
    destination_path_override: str | None = None,
    file_name: str | None = None,
) -> WfxResponse:
    resolved = resolve_share_url(share_url, provider)
    if not resolved.ok:
        return resolved

    if not isinstance(resolved.data, dict):
        return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved share URL payload has invalid format.")

    resolved_payload = dict(resolved.data)
    source_path = str(resolved_payload.get("path", ""))
    source_path_source = "share_url"
    if provider_path_override:
        normalized_override = unquote(provider_path_override).replace("\\", "/").strip()
        if not normalized_override:
            return _failure(WfxErrorCode.BAD_PATH, "provider_path_override is empty.")
        if not normalized_override.startswith("/"):
            normalized_override = f"/{normalized_override}"
        source_path = build_wfx_path(provider, normalized_override)
        source_path_source = "provider_path_override"
        resolved_payload["path"] = source_path
        resolved_payload["share_path"] = normalized_override

    if not source_path:
        return _failure(WfxErrorCode.BAD_PATH, "Resolved share URL does not contain a source path.")

    supported = {"list", "stat", "download", "copy", "move", "mkdir", "delete", "upload"}
    if operation not in supported:
        return _failure(WfxErrorCode.NOT_SUPPORTED, f"Unsupported operation for share URL validation: {operation}")

    destination_path = None
    destination_path_source = None
    if operation in {"copy", "move", "upload"}:
        if destination_path_override:
            normalized_destination = unquote(destination_path_override).replace("\\", "/").strip()
            if not normalized_destination:
                return _failure(WfxErrorCode.BAD_PATH, "destination_path_override is empty.")
            if not normalized_destination.startswith("/"):
                normalized_destination = f"/{normalized_destination}"
            destination_path = build_wfx_path(provider, normalized_destination)
            destination_path_source = "destination_path_override"
        elif destination_share_url:
            destination_resolved = resolve_share_url(destination_share_url, provider)
            if not destination_resolved.ok:
                return destination_resolved
            if not isinstance(destination_resolved.data, dict):
                return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved destination share URL payload has invalid format.")
            destination_path = str(destination_resolved.data.get("path", ""))
            destination_path_source = "destination_share_url"
        elif operation == "upload":
            destination_path = source_path
            destination_path_source = source_path_source
        else:
            return _failure(
                WfxErrorCode.BAD_PATH,
                "copy/move requires destination_path_override or destination_share_url.",
            )

        if not destination_path:
            return _failure(WfxErrorCode.BAD_PATH, "Destination path is empty.")

    if operation == "upload" and not file_name:
        return _failure(WfxErrorCode.BAD_PATH, "upload requires file_name.")

    payload: dict[str, object] = {
        "resolved": resolved_payload,
        "operation": operation,
        "source": {
            "path": source_path,
            "path_source": source_path_source,
        },
        "can_execute": True,
    }
    if destination_path and destination_path_source:
        payload["destination"] = {
            "path": destination_path,
            "path_source": destination_path_source,
        }
    if operation == "upload":
        payload["upload"] = {
            "file_name": file_name,
            "requires_content_base64": False,
        }

    return _success(
        data=payload,
        metadata={
            "provider": provider,
            "operation": f"browse-share-url-validate:{operation}",
        },
    )

