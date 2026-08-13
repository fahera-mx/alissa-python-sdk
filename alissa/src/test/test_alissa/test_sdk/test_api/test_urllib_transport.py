"""The default transport, driven with a stubbed ``urlopen`` — still no network.

The one rule this file exists to lock: **a 4xx/5xx is a response, not an
exception**. ``urllib`` raises ``HTTPError`` for error statuses, and the API's
whole error contract lives in the *body* of those responses — a transport that
let the exception through would throw the contract away, and every typed error
in this SDK would degrade to "something went wrong".

The second rule, locked at the bottom: **the transport does not follow
redirects**, because ``urllib`` would carry the bearer token across origins.
"""
from __future__ import annotations

import io
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from alissa.sdk.api import HttpRequest, TransportError, UrllibTransport
from alissa.sdk.api.client import _NoRedirectHandler


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


def _transport(open_impl, **kwargs) -> UrllibTransport:
    """A transport whose opener is stubbed — the one seam, still no socket."""
    transport = UrllibTransport(**kwargs)
    transport.opener = SimpleNamespace(open=open_impl)
    return transport


def test_a_success_is_passed_through_with_its_body_and_headers():
    response = _transport(lambda req, timeout: _FakeResponse(200, b'{"ok":true}')).send(_request())

    assert response.status == 200
    assert response.body == b'{"ok":true}'
    assert response.headers["Content-Type"] == "application/json"


def test_an_http_error_comes_back_as_a_response_so_the_envelope_survives():
    body = b'{"error":"STALE_CONSUMER","message":"nope","status":"running"}'

    def raise_http_error(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 409, "Conflict", {}, io.BytesIO(body))

    response = _transport(raise_http_error).send(_request())

    assert response.status == 409
    assert response.body == body


def test_a_connection_failure_is_a_transport_error():
    def raise_url_error(req, timeout):
        raise urllib.error.URLError("name or service not known")

    with pytest.raises(TransportError):
        _transport(raise_url_error).send(_request())


def test_a_timeout_is_a_transport_error():
    def raise_timeout(req, timeout):
        raise TimeoutError("timed out")

    with pytest.raises(TransportError):
        _transport(raise_timeout, timeout=0.001).send(_request())


def test_the_timeout_is_finite_by_default():
    # An observer loop must fail rather than hang forever on a dead connection.
    assert 0 < UrllibTransport().timeout < 120


def test_redirects_are_not_followed_so_the_bearer_token_stays_on_one_origin():
    # urllib's redirect handler copies every header onto the new request,
    # Authorization included, and does it across hosts. The transport must not
    # give it the chance.
    assert not any(
        type(handler) is urllib.request.HTTPRedirectHandler for handler in UrllibTransport().opener.handlers
    )
    assert any(isinstance(handler, _NoRedirectHandler) for handler in UrllibTransport().opener.handlers)


def test_the_redirect_handler_refuses_rather_than_rewriting_the_request():
    # Returning None is what leaves the 3xx as an HTTPError, which send() hands
    # back as a plain response — so an unexpected redirect stays visible.
    assert _NoRedirectHandler().redirect_request(None, None, 302, "Found", {}, "https://evil.invalid/") is None


def test_a_redirect_surfaces_as_a_response_carrying_its_status():
    def raise_redirect(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 302, "Found", {}, io.BytesIO(b""))

    response = _transport(raise_redirect).send(_request())

    assert response.status == 302
    assert response.body == b""
