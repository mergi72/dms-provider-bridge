from fastapi.testclient import TestClient

from dms_provider_bridge.app.server import create_app
from dms_provider_bridge.tracing import CORRELATION_HEADER


def test_bridge_preserves_valid_correlation_header() -> None:
    value = "123e4567-e89b-12d3-a456-426614174000"
    response = TestClient(create_app()).get("/health", headers={CORRELATION_HEADER: value})
    assert response.headers[CORRELATION_HEADER] == value


def test_bridge_replaces_invalid_correlation_header() -> None:
    response = TestClient(create_app()).get("/health", headers={CORRELATION_HEADER: "invalid"})
    assert response.headers[CORRELATION_HEADER] != "invalid"
