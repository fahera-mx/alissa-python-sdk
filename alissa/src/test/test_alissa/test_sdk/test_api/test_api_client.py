"""The shared client/auth core: token resolution, URL building, JSON, decoding.

These lock the behaviours every binding inherits, so a binding's own tests do
not have to re-assert them: bearer auth on every call, ``None``-valued fields
dropped rather than sent as ``null``, and a non-JSON response failing as a
transport problem rather than as an API error.
"""
from __future__ import annotations

import pytest

from alissa.sdk.api import ApiClient, DEFAULT_BASE_URL, MissingTokenError, TransportError
from alissa.sdk.api.client import ENV_BASE_URL, ENV_TOKEN, USER_AGENT, encode_path
from alissa.sdk.api.errors import ApiError

from conftest import TEST_BASE_URL, TEST_TOKEN, RecordedTransport


def test_defaults_to_the_public_api(monkeypatch):
    monkeypatch.delenv(ENV_BASE_URL, raising=False)
    assert ApiClient(token="t").base_url == DEFAULT_BASE_URL
    assert DEFAULT_BASE_URL == "https://api.alissa.app"


def test_base_url_comes_from_the_environment_and_loses_its_trailing_slash(monkeypatch):
    monkeypatch.setenv(ENV_BASE_URL, "https://api.staging.invalid/")
    assert ApiClient(token="t").base_url == "https://api.staging.invalid"


def test_token_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setenv(ENV_TOKEN, "alissa_from_env")
    assert ApiClient().token == "alissa_from_env"


def test_explicit_token_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv(ENV_TOKEN, "alissa_from_env")
    assert ApiClient(token="alissa_explicit").token == "alissa_explicit"


def test_missing_token_is_typed_and_raised_lazily(monkeypatch):
    monkeypatch.delenv(ENV_TOKEN, raising=False)
    client = ApiClient()  # constructing is fine — only using it is not
    with pytest.raises(MissingTokenError):
        _ = client.token


def test_url_building_drops_none_and_repeats_lists():
    client = ApiClient(token=TEST_TOKEN, base_url=TEST_BASE_URL)

    assert client.url_for("/v1/ping") == f"{TEST_BASE_URL}/v1/ping"
    assert client.url_for("v1/ping") == f"{TEST_BASE_URL}/v1/ping"
    assert client.url_for("/v1/x", {"a": 1, "b": None}) == f"{TEST_BASE_URL}/v1/x?a=1"
    assert client.url_for("/v1/x", {"s": ["a", "b"]}) == f"{TEST_BASE_URL}/v1/x?s=a&s=b"


def test_path_segments_are_percent_encoded():
    # An id is user-controlled data; it must never be able to inject a path.
    assert encode_path("a/b") == "a%2Fb"
    assert encode_path("a", "b c") == "a/b%20c"


def test_every_request_carries_bearer_auth_and_the_sdk_user_agent(client, transport):
    transport.respond(200, {"ok": True})

    client.get("/v1/ping")

    assert transport.last.headers["Authorization"] == f"Bearer {TEST_TOKEN}"
    assert transport.last.headers["Accept"] == "application/json"
    assert transport.last.headers["User-Agent"] == USER_AGENT
    assert USER_AGENT.startswith("alissa-python-sdk/")
    # A GET carries no body, so it must not claim a content type.
    assert "Content-Type" not in transport.last.headers
    assert transport.last.body is None


def test_none_valued_body_fields_are_omitted_not_sent_as_null(client, transport):
    transport.respond(200, {"ok": True})

    client.post("/v1/x", body={"kept": "yes", "dropped": None})

    assert transport.last_body == {"kept": "yes"}
    assert transport.last.headers["Content-Type"] == "application/json"


def test_error_envelope_becomes_a_typed_error(client, transport):
    transport.fail("error_not_found.json", status=404)

    with pytest.raises(ApiError) as caught:
        client.get("/v1/bridge/jobs/nope")

    assert caught.value.code == "NOT_FOUND"
    assert caught.value.http_status == 404


def test_non_json_error_body_still_raises_a_coded_api_error(client, transport):
    transport.respond_raw(502, b"<html>bad gateway</html>")

    with pytest.raises(ApiError) as caught:
        client.get("/v1/ping")

    assert caught.value.code == "HTTP_502"
    assert caught.value.http_status == 502


def test_non_json_success_body_is_a_transport_error(client, transport):
    transport.respond_raw(200, b"not json at all")

    with pytest.raises(TransportError):
        client.get("/v1/ping")


def test_transport_is_the_only_seam_the_tests_need():
    # The default client builds its own transport; ours is injected. This is the
    # property that keeps every test in this directory offline.
    assert isinstance(ApiClient(token="t", transport=RecordedTransport()).transport, RecordedTransport)
