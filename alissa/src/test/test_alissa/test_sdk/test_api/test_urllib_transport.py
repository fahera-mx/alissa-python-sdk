"""The default transport, driven with a stubbed ``urlopen`` — still no network.

The one rule this file exists to lock: **a 4xx/5xx is a response, not an
exception**. ``urllib`` raises ``HTTPError`` for error statuses, and the API's
whole error contract lives in the *body* of those responses — a transport that
let the exception through would throw the contract away, and every typed error
in this SDK would degrade to "something went wrong".
"""
from __future__ import annotations

import io
import urllib.error
import urllib.request

import pytest

from alissa.sdk.api import HttpRequest, TransportError, UrllibTransport


class _FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body
        self.headers = {"Content-Type": "application/json"}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _request() -> HttpRequest:
    return HttpRequest(method="POST", url="https://api.test.invalid/v1/x", headers={}, body=b"{}")


def test_a_success_is_passed_through_with_its_body_and_headers(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _FakeResponse(200, b'{"ok":true}'))

    response = UrllibTransport().send(_request())

    assert response.status == 200
    assert response.body == b'{"ok":true}'
    assert response.headers["Content-Type"] == "application/json"


def test_an_http_error_comes_back_as_a_response_so_the_envelope_survives(monkeypatch):
    body = b'{"error":"STALE_CONSUMER","message":"nope","status":"running"}'

    def raise_http_error(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 409, "Conflict", {}, io.BytesIO(body))

    monkeypatch.setattr(urllib.request, "urlopen", raise_http_error)

    response = UrllibTransport().send(_request())

    assert response.status == 409
    assert response.body == body


def test_a_connection_failure_is_a_transport_error(monkeypatch):
    def raise_url_error(req, timeout):
        raise urllib.error.URLError("name or service not known")

    monkeypatch.setattr(urllib.request, "urlopen", raise_url_error)

    with pytest.raises(TransportError):
        UrllibTransport().send(_request())


def test_a_timeout_is_a_transport_error(monkeypatch):
    def raise_timeout(req, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", raise_timeout)

    with pytest.raises(TransportError):
        UrllibTransport(timeout=0.001).send(_request())


def test_the_timeout_is_finite_by_default():
    # An observer loop must fail rather than hang forever on a dead connection.
    assert 0 < UrllibTransport().timeout < 120
