"""Bindings for the Local Bridge queue-mode surface (``/v1/bridge``).

Eleven endpoints, one method each: the executor lifecycle (§5.1) and the job
lifecycle (§5.2) of ``docs/design/local-bridge-queue-mode.md``, as implemented by
``api/src/routes/bridge.ts`` in fahera-mx/studio.alissa.app.

**Bindings only.** There is no polling loop, no claim state machine, no nonce
minting and no tmux here, on purpose: the executor *daemon* is the Node `alissa`
CLI's, and a second implementation of those rules in another language is a
divergence waiting to happen. What this module is for is observers and tooling —
reading the queue, tailing a job, and operating a row by hand.

    from alissa.sdk.api import BridgeClient

    bridge = BridgeClient()                       # token from $ALISSA_API_TOKEN
    for executor in bridge.list_executors():
        print(executor.executor_id, executor.status)

    job = bridge.get_job("j57…")
    print(job.status, job.attempt, "/", job.max_attempts, job.progress_note)
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence, TypeVar

from ..client import ApiClient, encode_path
from ..errors import TransportError
from .models import (
    ExecutorCapabilities,
    ExecutorHeartbeat,
    ExecutorRegistration,
    ExecutorStopResult,
    ExecutorSummary,
    JobClaim,
    JobDetail,
    JobFailAck,
    JobFeed,
    JobFulfillAck,
    JobProgressAck,
    JobResult,
    JobStartAck,
)

#: Path prefix for the whole surface.
BRIDGE_PREFIX = "/v1/bridge"

#: The only executor kind this contract accepts (``z.literal("alissa-code")``).
EXECUTOR_KIND = "alissa-code"

_Model = TypeVar("_Model")


def _decoded(build: Callable[[Mapping[str, Any]], _Model], payload: Any, endpoint: str) -> _Model:
    """Build a model from a decoded body, keeping every failure an ``AlissaError``.

    The models index their required fields directly (``payload["jobId"]``), so a
    drift between the server's shape and the schemas these were written from
    would escape as a ``KeyError`` or ``TypeError`` from inside ``from_wire`` —
    neither of which is an :class:`~alissa.sdk.api.errors.AlissaError`, so the
    ``except AlissaError`` pattern this package documents would not catch it.
    Shape drift is the one residual risk on this surface; funnel it into
    :class:`~alissa.sdk.api.errors.TransportError`, which already means "the
    response was not what the contract says".
    """
    if not isinstance(payload, Mapping):
        raise TransportError(f"{endpoint}: expected a JSON object, got {type(payload).__name__}.")
    try:
        return build(payload)
    except KeyError as exc:
        raise TransportError(f"{endpoint}: the response is missing {exc}.") from exc
    except (TypeError, ValueError) as exc:
        raise TransportError(f"{endpoint}: the response did not match the expected shape: {exc}") from exc


def _unwrapped(payload: Any, key: str, endpoint: str) -> Mapping[str, Any]:
    """Pull the single-object envelope key some responses wrap their row in."""
    inner = payload.get(key) if isinstance(payload, Mapping) else None
    if not isinstance(inner, Mapping):
        raise TransportError(f"{endpoint}: the response carries no {key!r} object.")
    return inner


class BridgeClient:
    """Typed access to ``/v1/bridge``'s executor and job endpoints.

    :param client: an :class:`~alissa.sdk.api.client.ApiClient` to send through.
        Pass one to share a transport (or to inject a fake); omit it and the
        remaining keyword arguments build one.
    :param token: forwarded to :class:`ApiClient` when ``client`` is omitted.
    :param base_url: forwarded to :class:`ApiClient` when ``client`` is omitted.

    Every method raises the typed errors in :mod:`alissa.sdk.api.errors` — in
    particular :class:`~alissa.sdk.api.errors.RetryAfterReadError` and its four
    subclasses for §5.3's 409s, which mean *re-read the row and retry*, not
    *give up*.
    """

    def __init__(
        self,
        client: ApiClient | None = None,
        *,
        token: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.client = client or ApiClient(token=token, base_url=base_url)

    # ── Executor lifecycle (§5.1) ────────────────────────────────────────────

    def register_executor(
        self,
        executor_id: str,
        *,
        label: str,
        hostname: str,
        fingerprint: str,
        kind: str = EXECUTOR_KIND,
        cli_version: str | None = None,
        poll_seconds: int | None = None,
        worker_name: str | None = None,
        capabilities: ExecutorCapabilities | None = None,
    ) -> ExecutorRegistration:
        """``POST /v1/bridge/executors`` — register or take over this machine's executor.

        Upsert by (user, executorId) with takeover semantics: an existing row is
        refreshed and any close cleared. ``fingerprint`` is a stable machine id
        kept server-side — renaming a laptop must not create a second executor.

        The response's ``resumed`` list is this executor's own non-terminal jobs,
        so a restarting caller reconciles in one round trip.
        """
        payload: dict[str, Any] = {
            "executorId": executor_id,
            "kind": kind,
            "label": label,
            "hostname": hostname,
            "fingerprint": fingerprint,
            "cliVersion": cli_version,
            "pollSeconds": poll_seconds,
            "workerName": worker_name,
            "capabilities": capabilities.to_wire() if capabilities is not None else None,
        }
        return _decoded(
            ExecutorRegistration.from_wire,
            self.client.post(f"{BRIDGE_PREFIX}/executors", body=payload),
            "POST /v1/bridge/executors",
        )

    def list_executors(self) -> tuple[ExecutorSummary, ...]:
        """``GET /v1/bridge/executors`` — this user's executors.

        ``status`` is derived from the heartbeat and never stored; machine
        fingerprints are not returned.
        """
        payload = self.client.get(f"{BRIDGE_PREFIX}/executors")
        rows = payload.get("executors") if isinstance(payload, Mapping) else None
        endpoint = "GET /v1/bridge/executors"
        return tuple(_decoded(ExecutorSummary.from_wire, row, endpoint) for row in (rows or ()))

    def heartbeat_executor(self, executor_id: str) -> ExecutorHeartbeat:
        """``POST /v1/bridge/executors/{id}/heartbeat`` — report this executor alive.

        For a caller that is not polling, and as the fallback when a poll fails —
        a polling daemon's beat rides :meth:`list_jobs` instead. Writes coalesce
        to one a minute. ``beat == "missing"`` means re-register.
        """
        path = f"{BRIDGE_PREFIX}/executors/{encode_path(executor_id)}/heartbeat"
        # An empty JSON object rather than no body at all: the route reads
        # nothing from it, but a bodyless POST is the kind of request proxies
        # and body parsers disagree about.
        return _decoded(
            ExecutorHeartbeat.from_wire,
            self.client.post(path, body={}),
            "POST /v1/bridge/executors/{id}/heartbeat",
        )

    def stop_executor(self, executor_id: str, *, reason: str | None = None) -> ExecutorStopResult:
        """``POST /v1/bridge/executors/{id}/stop`` — close it and release its jobs.

        Non-terminal jobs terminate immediately as ``executor_stopped`` — a
        deliberate stop is proof of death, so there is no reason to wait for the
        sweep, and it fires no escalation the way ``executor_lost`` does.
        Idempotent: a repeat call releases nothing.
        """
        path = f"{BRIDGE_PREFIX}/executors/{encode_path(executor_id)}/stop"
        return _decoded(
            ExecutorStopResult.from_wire,
            self.client.post(path, body={"reason": reason}),
            "POST /v1/bridge/executors/{id}/stop",
        )

    # ── Jobs (§5.2) ──────────────────────────────────────────────────────────

    def list_jobs(
        self,
        *,
        executor_id: str,
        status: str | Sequence[str] | None = None,
        limit: int | None = None,
    ) -> JobFeed:
        """``GET /v1/bridge/jobs`` — the claimable slice for one executor.

        :param executor_id: required. Jobs are pinned to one executor and never
            migrated, so there is no "all executors" feed.
        :param status: ``pending`` (the server's default), ``claimed`` or
            ``running`` — one, or a sequence. A misspelled status is a 400, never
            a silently empty page.
        :param limit: 1–50, default 25 server-side.

        The heartbeat rides this call, which is why the response carries ``beat``.
        """
        statuses = [status] if isinstance(status, str) else (list(status) if status is not None else None)
        query: dict[str, Any] = {
            "executorId": executor_id,
            "status": ",".join(statuses) if statuses else None,
            "limit": limit,
        }
        return _decoded(
            JobFeed.from_wire,
            self.client.get(f"{BRIDGE_PREFIX}/jobs", query=query),
            "GET /v1/bridge/jobs",
        )

    def get_job(self, job_id: str) -> JobDetail:
        """``GET /v1/bridge/jobs/{jobId}`` — one job, with lifecycle timing.

        For reconciling a row you already hold — an id from a registration's
        ``resumed``, or a job you lost track of mid-run. Carries
        ``cancel_requested`` and the full timing the feed omits.
        """
        endpoint = "GET /v1/bridge/jobs/{jobId}"
        payload = self.client.get(f"{BRIDGE_PREFIX}/jobs/{encode_path(job_id)}")
        return _decoded(JobDetail.from_wire, _unwrapped(payload, "job", endpoint), endpoint)

    def claim_job(self, job_id: str, *, executor_id: str, consumer_id: str, claim_seq: int) -> JobClaim:
        """``POST /v1/bridge/jobs/{id}/claim`` — compare-and-swap on ``claimSeq``.

        Send back the ``claim_seq`` read from the feed and a per-attempt
        ``consumer_id`` you have persisted: that nonce is what every later write
        is checked against, so a caller that hung and woke up cannot overwrite
        the attempt that replaced it.

        :raises CasConflictError: the generation moved — re-poll.
        :raises StickyViolationError: the job is pinned to another executor.
        :raises ConflictError: the row is not ``pending``.
        :raises CapacityExceededError: this executor is at ``maxConcurrentJobs``.
        :raises PreconditionFailedError: the executor is closed; re-register first.
        """
        path = f"{BRIDGE_PREFIX}/jobs/{encode_path(job_id)}/claim"
        body = {"executorId": executor_id, "consumerId": consumer_id, "claimSeq": claim_seq}
        return _decoded(JobClaim.from_wire, self.client.post(path, body=body), "POST /v1/bridge/jobs/{id}/claim")

    def start_job(
        self,
        job_id: str,
        *,
        consumer_id: str,
        executor_session_id: str | None = None,
        tmux_session: str | None = None,
    ) -> JobStartAck:
        """``POST /v1/bridge/jobs/{id}/start`` — a session now exists for this job.

        Also the first place a cancel becomes observable: check
        ``cancel_requested`` on the response before spawning, or you start a
        session you are about to tear down.
        """
        path = f"{BRIDGE_PREFIX}/jobs/{encode_path(job_id)}/start"
        body = {
            "consumerId": consumer_id,
            "executorSessionId": executor_session_id,
            "tmuxSession": tmux_session,
        }
        return _decoded(JobStartAck.from_wire, self.client.post(path, body=body), "POST /v1/bridge/jobs/{id}/start")

    def progress_job(self, job_id: str, *, consumer_id: str, note: str | None = None) -> JobProgressAck:
        """``POST /v1/bridge/jobs/{id}/progress`` — beat a running job, observe a cancel.

        Required every five minutes or the stall deadline collects the row.
        ``note`` is a one-line UI status of at most 500 characters, last write
        wins; a note posted inside the one-a-minute coalescing window is dropped
        (``coalesced``). It is not a log stream.
        """
        path = f"{BRIDGE_PREFIX}/jobs/{encode_path(job_id)}/progress"
        return _decoded(
            JobProgressAck.from_wire,
            self.client.post(path, body={"consumerId": consumer_id, "note": note}),
            "POST /v1/bridge/jobs/{id}/progress",
        )

    def fulfill_job(self, job_id: str, *, consumer_id: str, result: JobResult) -> JobFulfillAck:
        """``POST /v1/bridge/jobs/{id}/fulfill`` — deliver the result.

        A result arriving after a deadline swept the row is absorbed rather than
        errored: ``noop`` with the ``current_status`` that absorbed it.
        """
        path = f"{BRIDGE_PREFIX}/jobs/{encode_path(job_id)}/fulfill"
        body = {"consumerId": consumer_id, "result": result.to_wire()}
        return _decoded(
            JobFulfillAck.from_wire,
            self.client.post(path, body=body),
            "POST /v1/bridge/jobs/{id}/fulfill",
        )

    def fail_job(
        self,
        job_id: str,
        *,
        consumer_id: str,
        error: str,
        retryable: bool,
        failure_kind: str | None = None,
    ) -> JobFailAck:
        """``POST /v1/bridge/jobs/{id}/fail`` — report a failed run.

        :param retryable: ``True`` hands the row back to **this** executor with a
            fresh generation (jobs are never migrated to another machine) until
            the attempt budget is spent, at which point it goes terminal instead.
        :param failure_kind: only ``executor_error``, ``spec_rejected`` or
            ``cancelled``. The server-only kinds (``executor_lost``,
            ``executor_stopped``, ``no_executor``, ``stalled``, ``deadline``) are
            refused here so a caller cannot forge them.
        """
        path = f"{BRIDGE_PREFIX}/jobs/{encode_path(job_id)}/fail"
        body = {
            "consumerId": consumer_id,
            "error": error,
            "retryable": retryable,
            "failureKind": failure_kind,
        }
        return _decoded(JobFailAck.from_wire, self.client.post(path, body=body), "POST /v1/bridge/jobs/{id}/fail")
