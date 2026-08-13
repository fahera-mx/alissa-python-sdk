"""The SDK's HTTP/auth core: base URL, bearer token, JSON, error envelope.

One transport for every ``alissa.sdk.api.*`` binding. A binding module (see
:mod:`alissa.sdk.api.bridge`) owns *paths and shapes*; it never opens a socket,
never reads the environment, and never decodes an error — those live here, once.

Zero third-party dependencies, matching the rest of the SDK core: the transport
is :mod:`urllib.request` from the standard library. The one seam is
:class:`Transport` — inject your own to test bindings against recorded
responses without a network, which is exactly how this repo's unit tests run.

    from alissa.sdk.api import ApiClient

    client = ApiClient()                       # token from $ALISSA_API_TOKEN
    client = ApiClient(token="alissa_…", base_url="https://api.alissa.app")
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ..version import version as _sdk_version
from .errors import ApiError, MissingTokenError, TransportError, error_from_envelope

#: Where the Alissa REST API lives. Every path is versioned under ``/v1``.
DEFAULT_BASE_URL = "https://api.alissa.app"

#: Environment variables the client falls back to, matching the `alissa` CLI.
ENV_TOKEN = "ALISSA_API_TOKEN"
ENV_BASE_URL = "ALISSA_BASE"

USER_AGENT = f"alissa-python-sdk/{_sdk_version.value}"

#: Seconds before a request is abandoned. Deliberately finite: a binding used
#: inside an observer loop must fail rather than hang.
DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True, slots=True)
class HttpRequest:
    """One outbound request, fully resolved — URL, headers and encoded body."""

    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes | None = None


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """One inbound response: the status and the raw body, nothing interpreted."""

    status: int
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)


class Transport(Protocol):
    """How :class:`ApiClient` reaches the network.

    An error status is a **response**, not an exception: the API's failure
    envelope only exists in the body of a 4xx/5xx, so a transport that raised
    would throw the contract away. Raise :class:`~alissa.sdk.api.errors.TransportError`
    only when there is no response at all.
    """

    def send(self, request: HttpRequest) -> HttpResponse:  # pragma: no cover - protocol
        ...


class UrllibTransport:
    """The default transport — :mod:`urllib.request`, no third-party dependency."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def send(self, request: HttpRequest) -> HttpResponse:
        req = urllib.request.Request(
            request.url,
            data=request.body,
            headers=dict(request.headers),
            method=request.method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return HttpResponse(
                    status=response.status,
                    body=response.read(),
                    headers=dict(response.headers.items()),
                )
        except urllib.error.HTTPError as exc:
            # A 4xx/5xx carries the API's error envelope in its body — hand it
            # back as a response so the client can decode it into a typed error.
            return HttpResponse(
                status=exc.code,
                body=exc.read(),
                headers=dict(exc.headers.items()) if exc.headers else {},
            )
        except urllib.error.URLError as exc:
            raise TransportError(f"{request.method} {request.url} failed: {exc.reason}") from exc
        except OSError as exc:  # socket timeouts and friends
            raise TransportError(f"{request.method} {request.url} failed: {exc}") from exc


class ApiClient:
    """Authenticated JSON access to the Alissa REST API.

    :param token: personal access token; falls back to ``$ALISSA_API_TOKEN``.
    :param base_url: API root; falls back to ``$ALISSA_BASE``, then
        :data:`DEFAULT_BASE_URL`.
    :param timeout: seconds, applied by the default transport.
    :param transport: inject to bypass the network (tests, recorded fixtures).

    The token is resolved lazily, at the first request rather than at
    construction, so building a client in a module that is imported before the
    environment is configured is not itself an error.
    """

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Transport | None = None,
    ) -> None:
        self._token = token
        self.base_url = (base_url or os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")
        self.transport: Transport = transport or UrllibTransport(timeout=timeout)

    @property
    def token(self) -> str:
        """The bearer token, resolved from the constructor or the environment."""
        token = self._token or os.environ.get(ENV_TOKEN)
        if not token:
            raise MissingTokenError(
                f"No Alissa API token. Pass token=… or set ${ENV_TOKEN}."
            )
        return token

    def url_for(self, path: str, query: Mapping[str, Any] | None = None) -> str:
        """Absolute URL for ``path``, with ``None``-valued query keys dropped."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        pairs = _query_pairs(query)
        return f"{url}?{urllib.parse.urlencode(pairs)}" if pairs else url

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        """Send one request and return its decoded JSON body.

        ``body`` keys whose value is ``None`` are dropped rather than sent as
        ``null`` — the API's zod schemas treat an absent optional and an
        explicit ``null`` differently, and only the former means "not supplied".

        :raises ApiError: the API answered with its error envelope.
        :raises TransportError: no response, or a response that is not JSON.
        """
        encoded = None
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if body is not None:
            encoded = json.dumps(_without_none(body)).encode("utf-8")
            headers["Content-Type"] = "application/json"
        headers["Authorization"] = f"Bearer {self.token}"

        response = self.transport.send(
            HttpRequest(method=method.upper(), url=self.url_for(path, query), headers=headers, body=encoded)
        )
        return self._decode(method, path, response)

    def get(self, path: str, *, query: Mapping[str, Any] | None = None) -> Any:
        return self.request("GET", path, query=query)

    def post(self, path: str, *, body: Mapping[str, Any] | None = None) -> Any:
        return self.request("POST", path, body=body)

    def _decode(self, method: str, path: str, response: HttpResponse) -> Any:
        try:
            payload = json.loads(response.body) if response.body else None
        except ValueError:
            payload = None

        if 200 <= response.status < 300:
            if payload is None:
                raise TransportError(
                    f"{method.upper()} {path} returned {response.status} with a non-JSON body."
                )
            return payload

        if isinstance(payload, dict):
            raise error_from_envelope(response.status, payload)
        raise ApiError(
            f"{method.upper()} {path} failed with HTTP {response.status}.",
            code=f"HTTP_{response.status}",
            http_status=response.status,
        )


def _query_pairs(query: Mapping[str, Any] | None) -> list[tuple[str, str]]:
    """Flatten a query mapping, dropping ``None`` and repeating list values."""
    pairs: list[tuple[str, str]] = []
    for key, value in (query or {}).items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            pairs.extend((key, str(item)) for item in value)
        else:
            pairs.append((key, str(value)))
    return pairs


def _without_none(body: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if value is not None}


def encode_path(*segments: str) -> str:
    """Percent-encode path segments so an id can never inject a path."""
    return "/".join(urllib.parse.quote(str(segment), safe="") for segment in segments)
