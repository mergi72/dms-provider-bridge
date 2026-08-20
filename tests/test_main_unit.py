from __future__ import annotations

import pytest

from dms_provider_bridge.app.server import _request_is_local
from dms_provider_bridge.main import _validate_local_host


pytestmark = pytest.mark.unit


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "LOCALHOST"])
def test_validate_local_host_accepts_loopback(host: str) -> None:
    assert _validate_local_host(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "bridge.example"])
def test_validate_local_host_rejects_remote_bind(host: str) -> None:
    with pytest.raises(ValueError, match="only on localhost"):
        _validate_local_host(host)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "testclient"])
def test_request_is_local_accepts_loopback(host: str) -> None:
    request = type("Request", (), {"client": type("Client", (), {"host": host})()})()
    assert _request_is_local(request) is True


@pytest.mark.parametrize("host", ["192.168.1.10", "bridge.example", ""])
def test_request_is_local_rejects_remote_client(host: str) -> None:
    request = type("Request", (), {"client": type("Client", (), {"host": host})()})()
    assert _request_is_local(request) is False
