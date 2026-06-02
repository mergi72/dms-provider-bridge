from __future__ import annotations

import base64
from pathlib import Path

import pytest

from edocat_bridge.core.errors import ProviderOperationError
from edocat_bridge.providers.fso import FsoProvider


pytestmark = pytest.mark.unit


def _fso_path(path: Path) -> str:
    value = path.resolve().as_posix()
    return f"/{value}" if not value.startswith("/") else value


def test_fso_download_and_upload_roundtrip(tmp_path: Path) -> None:
    provider = FsoProvider()

    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")

    download_result = provider.download_item(_fso_path(source))
    assert download_result.success is True
    assert download_result.content_base64 == base64.b64encode(b"hello").decode("ascii")

    destination_dir = tmp_path / "dst"
    upload_result = provider.upload_item(_fso_path(destination_dir), "copied.txt", content_base64=download_result.content_base64, overwrite=False)
    assert upload_result.success is True

    copied = destination_dir / "copied.txt"
    assert copied.read_text(encoding="utf-8") == "hello"


def test_fso_list_and_stat(tmp_path: Path) -> None:
    provider = FsoProvider()
    folder = tmp_path / "folder"
    folder.mkdir()
    file_path = folder / "a.txt"
    file_path.write_text("x", encoding="utf-8")

    stat_folder = provider.stat_item(_fso_path(folder))
    assert stat_folder is not None
    assert stat_folder.is_folder is True

    listing = provider.list_items(_fso_path(folder))
    assert listing.total == 1
    assert listing.items[0].name == "a.txt"
    assert listing.items[0].is_folder is False


def test_fso_copy_folder(tmp_path: Path) -> None:
    provider = FsoProvider()
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("abc", encoding="utf-8")

    dst = tmp_path / "dst"
    result = provider.copy_item(_fso_path(src), _fso_path(dst))

    assert result.success is True
    assert (dst / "a.txt").read_text(encoding="utf-8") == "abc"


def test_fso_delete_rejects_path_outside_allowed_roots(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    target = outside_root / "danger.txt"
    target.write_text("x", encoding="utf-8")

    provider = FsoProvider(config={"allowedRoots": [str(allowed_root)]})

    with pytest.raises(ProviderOperationError, match="outside allowed roots"):
        provider.delete_item(_fso_path(target))


def test_fso_upload_allows_path_inside_allowed_roots(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    provider = FsoProvider(config={"allowedRoots": [str(allowed_root)]})

    result = provider.upload_item(
        _fso_path(allowed_root),
        "inside.txt",
        content_base64="aGVsbG8=",
        overwrite=False,
    )

    assert result.success is True
    assert (allowed_root / "inside.txt").read_text(encoding="utf-8") == "hello"
