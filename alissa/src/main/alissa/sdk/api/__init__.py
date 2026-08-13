"""``alissa.sdk.api`` — typed bindings for the Alissa REST API.

Two layers, deliberately separated:

* **The core** — :class:`~alissa.sdk.api.client.ApiClient` (base URL, bearer
  token, JSON, timeouts) and :mod:`alissa.sdk.api.errors` (the failure envelope
  as a class per code). Every binding shares these; there is no second HTTP
  stack anywhere in this SDK.
* **The bindings** — one subpackage per API surface, owning paths and shapes and
  nothing else. Today: :mod:`alissa.sdk.api.bridge`, the Local Bridge queue-mode
  executor and job endpoints.

Both are stdlib-only, matching the SDK core's zero-dependency contract.

    from alissa.sdk.api import ApiClient, BridgeClient, StaleConsumerError

    bridge = BridgeClient(ApiClient(token="alissa_…"))
    for executor in bridge.list_executors():
        print(executor.executor_id, executor.status)
"""
from .bridge import BridgeClient
from .client import DEFAULT_BASE_URL, ApiClient, HttpRequest, HttpResponse, Transport, UrllibTransport
from .errors import (
    AlissaError,
    ApiError,
    CapacityExceededError,
    CasConflictError,
    ConflictError,
    ForbiddenError,
    MissingTokenError,
    NotFoundError,
    PreconditionFailedError,
    RetryAfterReadError,
    StaleConsumerError,
    StickyViolationError,
    TransportError,
    UnauthorizedError,
    ValidationError,
)

__all__ = [
    "ApiClient",
    "BridgeClient",
    "DEFAULT_BASE_URL",
    "HttpRequest",
    "HttpResponse",
    "Transport",
    "UrllibTransport",
    "AlissaError",
    "ApiError",
    "CapacityExceededError",
    "CasConflictError",
    "ConflictError",
    "ForbiddenError",
    "MissingTokenError",
    "NotFoundError",
    "PreconditionFailedError",
    "RetryAfterReadError",
    "StaleConsumerError",
    "StickyViolationError",
    "TransportError",
    "UnauthorizedError",
    "ValidationError",
]
