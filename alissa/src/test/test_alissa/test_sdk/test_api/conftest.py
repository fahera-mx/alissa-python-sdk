"""Offline plumbing for the API-binding tests.

Every test in this directory runs against **recorded response bodies** in
``fixtures/`` — the JSON these endpoints actually answer with — replayed through
an injected transport. Nothing here opens a socket, and nothing reads a real
token: a binding whose tests needed the network could only be run by someone
holding an Ultra plan and a live executor.

:class:`RecordedTransport` is also the assertion surface for the *request* half
of each binding. It records what was sent, so a test can check the method, the
URL, the query string and the JSON body — which is where "no invented fields"
is actually enforced.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from alissa.sdk.api import ApiClient, BridgeClient, HttpRequest, HttpResponse

FIXTURES = Path(__file__).parent / "fixtures"

TEST_TOKEN = "alissa_test_token"
TEST_BASE_URL = "https://api.test.invalid"


def load_fixture(name: str) -> Any:
    """Read one recorded response body by file name (``jobs_feed.json``)."""
    with open(FIXTURES / name, "r") as handle:
        return json.load(handle)


class RecordedTransport:
    """A transport that replays queued responses and records what was sent.

    Queue responses with :meth:`reply` (a 2xx fixture) or :meth:`fail` (an error
    envelope with its documented status). Responses are served in FIFO order;
    running out is a test bug, not a runtime condition, so it raises.
    """

    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []
        self._responses: list[HttpResponse] = []

    def reply(self, fixture: str, status: int = 200) -> "RecordedTransport":
        return self.respond(status, load_fixture(fixture))

    def fail(self, fixture: str, status: int) -> "RecordedTransport":
        return self.respond(status, load_fixture(fixture))

    def respond(self, status: int, payload: Any) -> "RecordedTransport":
        self._responses.append(HttpResponse(status=status, body=json.dumps(payload).encode("utf-8")))
        return self

    def respond_raw(self, status: int, body: bytes) -> "RecordedTransport":
        self._responses.append(HttpResponse(status=status, body=body))
        return self

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError(f"No queued response for {request.method} {request.url}")
        return self._responses.pop(0)

    # ── assertion helpers ────────────────────────────────────────────────────

    @property
    def last(self) -> HttpRequest:
        assert self.requests, "no request was sent"
        return self.requests[-1]

    @property
    def last_body(self) -> Any:
        """The JSON body of the last request, or ``None`` when it carried none."""
        body = self.last.body
        return json.loads(body) if body else None


@pytest.fixture
def transport() -> RecordedTransport:
    return RecordedTransport()


@pytest.fixture
def client(transport: RecordedTransport) -> ApiClient:
    return ApiClient(token=TEST_TOKEN, base_url=TEST_BASE_URL, transport=transport)


@pytest.fixture
def bridge(client: ApiClient) -> BridgeClient:
    return BridgeClient(client)
