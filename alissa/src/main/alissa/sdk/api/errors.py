"""Typed errors for the Alissa REST API.

The API answers every failure with the same JSON envelope — a machine-readable
``error`` code, a human ``message``, and (for a handful of codes) extra
structured detail::

    { "error": "STALE_CONSUMER", "message": "…", "status": "running" }

This module turns that envelope into an exception *class per code*, so callers
branch on a type or on :attr:`ApiError.code` and never on the prose of
``message`` — the message is free text the server may reword at any time, the
code is the contract.

The Local Bridge queue-mode codes (``docs/design/local-bridge-queue-mode.md``
§5.3) are the reason this exists. Its four 409s are all *retryable after a
re-read* rather than terminal, which is a materially different instruction than
"this failed" — they share :class:`RetryAfterReadError` so a caller can say
"re-poll and try again" in one ``except`` clause::

    try:
        claim = bridge.claim_job(job_id, executor_id=…, consumer_id=…, claim_seq=…)
    except StaleConsumerError:
        return                       # another attempt owns this row now
    except RetryAfterReadError:
        jobs = bridge.list_jobs(executor_id=…)   # re-read, do not spin

An unmapped code is **not** an error to this layer: it becomes a plain
:class:`ApiError` carrying the code verbatim, so a server that grows a new code
degrades to "branchable by string" rather than to a crash.
"""
from __future__ import annotations

from typing import Any, Mapping


class AlissaError(Exception):
    """Base class for every error this SDK raises."""


class MissingTokenError(AlissaError):
    """No API token was passed and none was found in the environment."""


class TransportError(AlissaError):
    """The request never produced a usable JSON response.

    Raised for connection failures, timeouts, and bodies that are not JSON —
    i.e. everything that is *not* the API telling us something in its envelope.
    """


class ApiError(AlissaError):
    """An error the API reported in its ``{ "error", "message" }`` envelope.

    :attr:`code` is the branchable value. :attr:`http_status` is the transport
    status that carried it, and :attr:`detail` holds any extra fields the code
    is documented to carry (kept in the wire's own spelling, so nothing is lost
    for a code this SDK does not model yet).
    """

    #: The envelope ``error`` code this subclass is registered for.
    code: str = "UNKNOWN"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        http_status: int = 0,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.http_status = http_status
        self.detail: dict[str, Any] = dict(detail or {})

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ValidationError(ApiError):
    """``VALIDATION_ERROR`` (400) — body shape, slug shape or a length cap."""

    code = "VALIDATION_ERROR"


class UnauthorizedError(ApiError):
    """``UNAUTHORIZED`` (401) — missing, expired or revoked token."""

    code = "UNAUTHORIZED"


class ForbiddenError(ApiError):
    """``FORBIDDEN`` (403) — plan entitlement; queue mode is Ultra-gated."""

    code = "FORBIDDEN"


class NotFoundError(ApiError):
    """``NOT_FOUND`` (404) — no such row *for this user*.

    Also the answer for another user's row: absence and inaccessibility are
    deliberately indistinguishable.
    """

    code = "NOT_FOUND"


class PreconditionFailedError(ApiError):
    """``PRECONDITION_FAILED`` (412) — executor closed, or the executor cap is reached.

    Note the status: §5.3 pins this code at **412** on the bridge surface, where
    the rest of the Alissa API answers 409. Branch on the code, not the status.
    """

    code = "PRECONDITION_FAILED"


class CapacityExceededError(ApiError):
    """``CAPACITY_EXCEEDED`` (429) — the executor is at ``maxConcurrentJobs``."""

    code = "CAPACITY_EXCEEDED"

    @property
    def held(self) -> int | None:
        """Jobs this executor currently holds, when the server reported it."""
        value = self.detail.get("held")
        return value if isinstance(value, int) else None

    @property
    def cap(self) -> int | None:
        """The executor's concurrency cap, when the server reported it."""
        value = self.detail.get("cap")
        return value if isinstance(value, int) else None


class RetryAfterReadError(ApiError):
    """Base of §5.3's four 409s: re-read the row and retry, do not spin.

    Every one of them carries the ``status`` actually observed on the row, which
    is what makes the re-read cheap — see :attr:`observed_status`.
    """

    @property
    def observed_status(self) -> str | None:
        """The row status the server observed, when it reported one."""
        value = self.detail.get("status")
        return value if isinstance(value, str) else None


class ConflictError(RetryAfterReadError):
    """``CONFLICT`` (409) — the job is not in the state this call requires."""

    code = "CONFLICT"


class CasConflictError(RetryAfterReadError):
    """``CAS_CONFLICT`` (409) — the ``claimSeq`` sent did not match the row."""

    code = "CAS_CONFLICT"

    @property
    def current_claim_seq(self) -> int | None:
        """The generation the row is actually on — claim against this, or re-poll."""
        value = self.detail.get("currentClaimSeq")
        return value if isinstance(value, int) else None


class StickyViolationError(RetryAfterReadError):
    """``STICKY_VIOLATION`` (409) — this job is sticky to a different executor."""

    code = "STICKY_VIOLATION"

    @property
    def sticky_executor_id(self) -> str | None:
        """The executor the job is pinned to."""
        value = self.detail.get("stickyExecutorId")
        return value if isinstance(value, str) else None


class StaleConsumerError(RetryAfterReadError):
    """``STALE_CONSUMER`` (409) — the ``consumerId`` is not the row's current attempt.

    The nonce you are echoing belongs to an attempt that has been superseded:
    a daemon that hung and woke up must **not** write over the attempt that
    replaced it. Stop working this job — do not retry with the same nonce.
    """

    code = "STALE_CONSUMER"


#: Envelope code → exception class. Codes absent here become a plain
#: :class:`ApiError` carrying the code, so a new server-side code is degraded
#: to "branchable by string" rather than swallowed or crashed on.
ERROR_CLASSES: dict[str, type[ApiError]] = {
    cls.code: cls
    for cls in (
        ValidationError,
        UnauthorizedError,
        ForbiddenError,
        NotFoundError,
        PreconditionFailedError,
        CapacityExceededError,
        ConflictError,
        CasConflictError,
        StickyViolationError,
        StaleConsumerError,
    )
}


def error_from_envelope(http_status: int, payload: Mapping[str, Any]) -> ApiError:
    """Build the typed error for one ``{ "error", "message", … }`` envelope.

    Every key other than ``error`` and ``message`` is kept in :attr:`ApiError.detail`
    under its wire spelling — the server whitelists detail per code, and this
    layer must not decide which of those keys matter.
    """
    code = payload.get("error")
    code = code if isinstance(code, str) and code else f"HTTP_{http_status}"
    message = payload.get("message")
    message = message if isinstance(message, str) else "Request failed."
    detail = {key: value for key, value in payload.items() if key not in ("error", "message")}

    cls = ERROR_CLASSES.get(code, ApiError)
    return cls(message, code=code, http_status=http_status, detail=detail)
