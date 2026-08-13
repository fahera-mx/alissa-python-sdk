"""Typed structures for the Local Bridge queue-mode wire (``/v1/bridge``).

Every model here mirrors a zod schema in ``api/src/schemas/bridge.ts`` of
fahera-mx/studio.alissa.app (design: ``docs/design/local-bridge-queue-mode.md``
§5). Nothing is invented and nothing is inferred: a field exists here only
because the server sends it, optionality matches the schema's, and the names are
the wire's names in snake_case.

Two conventions worth knowing before reading:

* **Plain stdlib dataclasses, frozen.** The SDK core carries zero third-party
  dependencies, so there is no pydantic to validate against — ``from_wire`` maps
  and coerces, it does not enforce. Responses are server-shaped data, and a
  binding that rejected a field the server legitimately added would be a
  liability, not a safety net.
* **Unknown keys are dropped, absent keys become ``None``.** That is what makes
  these forward-compatible: a new optional field on the server does not break a
  deployed reader.

.. note::

   The **feed carries the full spec, prompt included** — ``summarizeJobForFeed``
   in ``convex/apiBridgeOps.ts`` projects ``spec`` whole. What the feed omits is
   the *result* side (``result``, ``error``, timing, ``cancelRequested``); those
   are :class:`JobDetail`, i.e. ``GET /v1/bridge/jobs/{jobId}``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

__all__ = [
    "ExecutorCapabilities",
    "ExecutorSummary",
    "ExecutorRegistration",
    "ExecutorHeartbeat",
    "ExecutorStopResult",
    "ResumedJob",
    "JobDeliverable",
    "JobAcceptanceCriterion",
    "JobReference",
    "JobSpec",
    "JobFeedItem",
    "JobFeed",
    "JobDetail",
    "JobClaim",
    "JobStartAck",
    "JobProgressAck",
    "JobResultLink",
    "JobResultAcceptance",
    "JobResult",
    "JobFulfillAck",
    "JobFailAck",
]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _str_tuple(value: Any) -> tuple[str, ...] | None:
    """Optional list-of-strings field: ``None`` when absent, never a silent ``()``.

    The distinction is load-bearing on this wire — an absent
    ``capabilities.workspaceRoots`` means "accepts any workspace", while an
    empty one would mean "accepts none".
    """
    if value is None:
        return None
    return tuple(str(item) for item in _sequence(value))


# ── Executor lifecycle (§5.1) ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ExecutorCapabilities:
    """What an executor will accept. Every field optional, and absence means something.

    ``workspace_roots`` absent ⇒ any workspace. ``max_concurrent_jobs`` is
    clamped server-side to [1, 16]. ``handoffs`` absent ⇒ the daemon's default.
    ``tags`` is reserved for v2 pool routing and unread today.
    """

    workspace_roots: tuple[str, ...] | None = None
    max_concurrent_jobs: int | None = None
    handoffs: tuple[str, ...] | None = None
    tags: tuple[str, ...] | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "ExecutorCapabilities":
        return cls(
            workspace_roots=_str_tuple(payload.get("workspaceRoots")),
            max_concurrent_jobs=payload.get("maxConcurrentJobs"),
            handoffs=_str_tuple(payload.get("handoffs")),
            tags=_str_tuple(payload.get("tags")),
        )

    def to_wire(self) -> dict[str, Any]:
        """The registration payload. Unset fields are omitted, never sent as null."""
        payload: dict[str, Any] = {}
        if self.workspace_roots is not None:
            payload["workspaceRoots"] = list(self.workspace_roots)
        if self.max_concurrent_jobs is not None:
            payload["maxConcurrentJobs"] = self.max_concurrent_jobs
        if self.handoffs is not None:
            payload["handoffs"] = list(self.handoffs)
        if self.tags is not None:
            payload["tags"] = list(self.tags)
        return payload


@dataclass(frozen=True, slots=True)
class ResumedJob:
    """A non-terminal job the executor already held, returned by registration."""

    job_id: str
    status: str
    attempt: int
    #: Absent on a ``pending`` row — nothing holds it yet.
    consumer_id: str | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "ResumedJob":
        return cls(
            job_id=payload["jobId"],
            status=payload["status"],
            attempt=payload["attempt"],
            consumer_id=payload.get("consumerId"),
        )


@dataclass(frozen=True, slots=True)
class ExecutorRegistration:
    """``POST /v1/bridge/executors`` — the upsert, plus anything already in flight."""

    executor_id: str
    #: The row was still open: another daemon may be running under this id.
    took_over: bool
    #: This id arrived from a different machine. Benign after a re-image; a flap
    #: means two machines are fighting over one executor id.
    fingerprint_changed: bool
    #: This executor's own non-terminal jobs, so a restart reconciles in one round trip.
    resumed: tuple[ResumedJob, ...] = ()

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "ExecutorRegistration":
        return cls(
            executor_id=payload["executorId"],
            took_over=bool(payload.get("tookOver")),
            fingerprint_changed=bool(payload.get("fingerprintChanged")),
            resumed=tuple(ResumedJob.from_wire(_mapping(row)) for row in _sequence(payload.get("resumed"))),
        )


@dataclass(frozen=True, slots=True)
class ExecutorHeartbeat:
    """``POST /v1/bridge/executors/{id}/heartbeat`` — what the beat did.

    ``beat`` is one of ``missing`` (re-register), ``closed`` (the row was stopped
    deliberately), ``resumed`` (a stale close was undone), ``touched``, or
    ``coalesced`` (counted, not written). A ``missing`` row comes back as a
    *value*, not a 404.
    """

    executor_id: str
    beat: str

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "ExecutorHeartbeat":
        return cls(executor_id=payload["executorId"], beat=payload["beat"])


@dataclass(frozen=True, slots=True)
class ExecutorStopResult:
    """``POST /v1/bridge/executors/{id}/stop`` — whether it closed, and what went with it."""

    executor_id: str
    found: bool
    already_ended: bool
    #: Non-terminal jobs terminated as ``executor_stopped``. A repeat call
    #: releases nothing — the endpoint is idempotent.
    released_jobs: int

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "ExecutorStopResult":
        return cls(
            executor_id=payload["executorId"],
            found=bool(payload.get("found")),
            already_ended=bool(payload.get("alreadyEnded")),
            released_jobs=payload.get("releasedJobs", 0),
        )


@dataclass(frozen=True, slots=True)
class ExecutorSummary:
    """One row of ``GET /v1/bridge/executors``.

    No ``fingerprint``: machine identifiers stay server-side. ``status`` is
    derived from the heartbeat and never stored — ``"active"`` or the end reason.
    All timestamps are epoch milliseconds, as the wire sends them.
    """

    executor_id: str
    kind: str
    label: str
    hostname: str
    started_at: int
    last_heartbeat_at: int
    status: str
    cli_version: str | None = None
    poll_seconds: int | None = None
    worker_name: str | None = None
    capabilities: ExecutorCapabilities | None = None
    ended_at: int | None = None
    end_reason: str | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "ExecutorSummary":
        capabilities = payload.get("capabilities")
        return cls(
            executor_id=payload["executorId"],
            kind=payload["kind"],
            label=payload["label"],
            hostname=payload["hostname"],
            started_at=payload["startedAt"],
            last_heartbeat_at=payload["lastHeartbeatAt"],
            status=payload["status"],
            cli_version=payload.get("cliVersion"),
            poll_seconds=payload.get("pollSeconds"),
            worker_name=payload.get("workerName"),
            capabilities=(
                ExecutorCapabilities.from_wire(_mapping(capabilities)) if capabilities is not None else None
            ),
            ended_at=payload.get("endedAt"),
            end_reason=payload.get("endReason"),
        )


# ── Job spec (§5.2) ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class JobDeliverable:
    """What the job is expected to produce: ``pull_request``/``patch``/``artifact``/``report``."""

    kind: str
    description: str

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobDeliverable":
        return cls(kind=payload["kind"], description=payload["description"])


@dataclass(frozen=True, slots=True)
class JobAcceptanceCriterion:
    """One acceptance criterion on the spec: ``type`` is ``manual`` or ``automated``."""

    id: str
    description: str
    type: str

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobAcceptanceCriterion":
        return cls(id=payload["id"], description=payload["description"], type=payload["type"])


@dataclass(frozen=True, slots=True)
class JobReference:
    """A pointer carried with the spec: ``task``, ``url``, ``repo`` or ``evidence``."""

    kind: str
    ref: str
    label: str | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobReference":
        return cls(kind=payload["kind"], ref=payload["ref"], label=payload.get("label"))


@dataclass(frozen=True, slots=True)
class JobSpec:
    """The contract the executor was handed. **Never a credential channel.**

    ``env`` carries variable *names* only — the daemon resolves values from its
    own environment, and nothing here ever holds a secret.
    """

    title: str
    prompt: str
    deliverable: JobDeliverable
    acceptance: tuple[JobAcceptanceCriterion, ...] = ()
    references: tuple[JobReference, ...] | None = None
    workspace_root: str | None = None
    handoff: str | None = None
    env: tuple[str, ...] | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobSpec":
        references = payload.get("references")
        return cls(
            title=payload["title"],
            prompt=payload["prompt"],
            deliverable=JobDeliverable.from_wire(_mapping(payload.get("deliverable"))),
            acceptance=tuple(
                JobAcceptanceCriterion.from_wire(_mapping(row)) for row in _sequence(payload.get("acceptance"))
            ),
            references=(
                tuple(JobReference.from_wire(_mapping(row)) for row in _sequence(references))
                if references is not None
                else None
            ),
            workspace_root=payload.get("workspaceRoot"),
            handoff=payload.get("handoff"),
            env=_str_tuple(payload.get("env")),
        )


# ── Job feed and detail (§5.2) ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class JobFeedItem:
    """One claimable row from ``GET /v1/bridge/jobs``.

    ``claim_seq`` is the CAS generation — send it back verbatim when you claim,
    or the server answers ``CAS_CONFLICT``. ``status`` is one of ``pending``,
    ``claimed``, ``running``: the feed is the claimable slice, never a history.
    """

    job_id: str
    claim_seq: int
    attempt: int
    max_attempts: int
    status: str
    spec: JobSpec
    created_at: int
    pending_expires_at: int
    consumer_id: str | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobFeedItem":
        return cls(
            job_id=payload["jobId"],
            claim_seq=payload["claimSeq"],
            attempt=payload["attempt"],
            max_attempts=payload["maxAttempts"],
            status=payload["status"],
            spec=JobSpec.from_wire(_mapping(payload.get("spec"))),
            created_at=payload["createdAt"],
            pending_expires_at=payload["pendingExpiresAt"],
            consumer_id=payload.get("consumerId"),
        )


@dataclass(frozen=True, slots=True)
class JobFeed:
    """``GET /v1/bridge/jobs`` — the claimable slice plus the folded-in heartbeat.

    The poll *is* the liveness signal, which is why ``beat`` rides back on it;
    ``beat == "missing"`` means re-register before doing anything else.
    """

    jobs: tuple[JobFeedItem, ...]
    beat: str

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobFeed":
        return cls(
            jobs=tuple(JobFeedItem.from_wire(_mapping(row)) for row in _sequence(payload.get("jobs"))),
            beat=payload["beat"],
        )


@dataclass(frozen=True, slots=True)
class JobResultLink:
    """A labelled link on a job result (at most 25 per result)."""

    label: str
    url: str

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobResultLink":
        return cls(label=payload["label"], url=payload["url"])

    def to_wire(self) -> dict[str, Any]:
        return {"label": self.label, "url": self.url}


@dataclass(frozen=True, slots=True)
class JobResultAcceptance:
    """The executor's self-report for one acceptance criterion — a claim, not a decision."""

    id: str
    met: bool
    note: str | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobResultAcceptance":
        return cls(id=payload["id"], met=bool(payload["met"]), note=payload.get("note"))

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "met": self.met}
        if self.note is not None:
            payload["note"] = self.note
        return payload


@dataclass(frozen=True, slots=True)
class JobResult:
    """What ``fulfill`` delivers, and what ``GET /jobs/{id}`` returns once it has.

    Server-side caps: ``summary`` ≤ 2 000 UTF-8 bytes, ``markdown`` ≤ 200 000,
    ``links`` ≤ 25. They are the server's to enforce — this binding does not
    pre-reject, so a cap change does not need an SDK release.
    """

    summary: str
    markdown: str | None = None
    links: tuple[JobResultLink, ...] | None = None
    acceptance: tuple[JobResultAcceptance, ...] | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobResult":
        links = payload.get("links")
        acceptance = payload.get("acceptance")
        return cls(
            summary=payload["summary"],
            markdown=payload.get("markdown"),
            links=(
                tuple(JobResultLink.from_wire(_mapping(row)) for row in _sequence(links))
                if links is not None
                else None
            ),
            acceptance=(
                tuple(JobResultAcceptance.from_wire(_mapping(row)) for row in _sequence(acceptance))
                if acceptance is not None
                else None
            ),
        )

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"summary": self.summary}
        if self.markdown is not None:
            payload["markdown"] = self.markdown
        if self.links is not None:
            payload["links"] = [link.to_wire() for link in self.links]
        if self.acceptance is not None:
            payload["acceptance"] = [row.to_wire() for row in self.acceptance]
        return payload


@dataclass(frozen=True, slots=True)
class JobDetail:
    """``GET /v1/bridge/jobs/{jobId}`` — the feed row plus the state it cannot infer.

    ``status`` widens past the feed's three to include ``fulfilled``, ``failed``
    and ``timeout``. ``failure_kind`` is a plain string, not an enum: a daemon
    may only *claim* ``executor_error``/``spec_rejected``/``cancelled``, but the
    server writes kinds of its own (``executor_lost``, ``executor_stopped``,
    ``no_executor``, ``stalled``, ``deadline``) that a reader must not choke on.

    ``discardedResult`` — the late-fulfil stash — is deliberately not on this
    wire, so there is deliberately no field for it here.
    """

    job_id: str
    claim_seq: int
    attempt: int
    max_attempts: int
    status: str
    spec: JobSpec
    created_at: int
    pending_expires_at: int
    cancel_requested: bool
    consumer_id: str | None = None
    sticky_executor_id: str | None = None
    claimed_by_executor_id: str | None = None
    progress_note: str | None = None
    executor_session_id: str | None = None
    tmux_session: str | None = None
    result: JobResult | None = None
    error: str | None = None
    failure_kind: str | None = None
    claimed_at: int | None = None
    started_at: int | None = None
    last_progress_at: int | None = None
    deadline_at: int | None = None
    completed_at: int | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobDetail":
        result = payload.get("result")
        return cls(
            job_id=payload["jobId"],
            claim_seq=payload["claimSeq"],
            attempt=payload["attempt"],
            max_attempts=payload["maxAttempts"],
            status=payload["status"],
            spec=JobSpec.from_wire(_mapping(payload.get("spec"))),
            created_at=payload["createdAt"],
            pending_expires_at=payload["pendingExpiresAt"],
            cancel_requested=bool(payload.get("cancelRequested")),
            consumer_id=payload.get("consumerId"),
            sticky_executor_id=payload.get("stickyExecutorId"),
            claimed_by_executor_id=payload.get("claimedByExecutorId"),
            progress_note=payload.get("progressNote"),
            executor_session_id=payload.get("executorSessionId"),
            tmux_session=payload.get("tmuxSession"),
            result=JobResult.from_wire(_mapping(result)) if result is not None else None,
            error=payload.get("error"),
            failure_kind=payload.get("failureKind"),
            claimed_at=payload.get("claimedAt"),
            started_at=payload.get("startedAt"),
            last_progress_at=payload.get("lastProgressAt"),
            deadline_at=payload.get("deadlineAt"),
            completed_at=payload.get("completedAt"),
        )


# ── Job lifecycle acknowledgements (§5.2) ────────────────────────────────────


@dataclass(frozen=True, slots=True)
class JobClaim:
    """``POST /v1/bridge/jobs/{id}/claim`` — the claim, the spec and the wall clock.

    Past ``deadline_at`` the sweep collects the row as ``deadline``; it is wall
    clock (epoch ms), not a duration.
    """

    ok: bool
    job_id: str
    claim_seq: int
    deadline_at: int
    spec: JobSpec

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobClaim":
        return cls(
            ok=bool(payload.get("ok")),
            job_id=payload["jobId"],
            claim_seq=payload["claimSeq"],
            deadline_at=payload["deadlineAt"],
            spec=JobSpec.from_wire(_mapping(payload.get("spec"))),
        )


@dataclass(frozen=True, slots=True)
class JobStartAck:
    """``POST /v1/bridge/jobs/{id}/start`` — running, or absorbed.

    ``cancel_requested`` is surfaced here as well as on progress, so a job
    cancelled while merely *claimed* is observable **before** a session is
    spawned. ``noop`` means the row was already terminal and nothing was
    written; ``current_status`` is the status that absorbed the call.
    """

    ok: bool
    status: str | None = None
    cancel_requested: bool | None = None
    noop: bool | None = None
    current_status: str | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobStartAck":
        return cls(
            ok=bool(payload.get("ok")),
            status=payload.get("status"),
            cancel_requested=payload.get("cancelRequested"),
            noop=payload.get("noop"),
            current_status=payload.get("currentStatus"),
        )


@dataclass(frozen=True, slots=True)
class JobProgressAck:
    """``POST /v1/bridge/jobs/{id}/progress`` — the beat, and any pending cancel.

    ``coalesced`` means the beat counted but the note was dropped: writes
    coalesce to one a minute. It is a status line, not a log stream.
    """

    ok: bool
    coalesced: bool | None = None
    cancel_requested: bool | None = None
    noop: bool | None = None
    current_status: str | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobProgressAck":
        return cls(
            ok=bool(payload.get("ok")),
            coalesced=payload.get("coalesced"),
            cancel_requested=payload.get("cancelRequested"),
            noop=payload.get("noop"),
            current_status=payload.get("currentStatus"),
        )


@dataclass(frozen=True, slots=True)
class JobFulfillAck:
    """``POST /v1/bridge/jobs/{id}/fulfill`` — fulfilled, or absorbed.

    A result arriving after a deadline already swept the row is absorbed rather
    than errored (``noop`` with ``current_status``), and the payload is stashed
    server-side so hours of real work stay recoverable.
    """

    ok: bool
    noop: bool | None = None
    current_status: str | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobFulfillAck":
        return cls(
            ok=bool(payload.get("ok")),
            noop=payload.get("noop"),
            current_status=payload.get("currentStatus"),
        )


@dataclass(frozen=True, slots=True)
class JobFailAck:
    """``POST /v1/bridge/jobs/{id}/fail`` — where the row landed.

    ``status`` is ``pending`` when a retryable failure handed the row back to
    **this** executor with a fresh generation (jobs are never migrated), or
    ``failed`` once the attempt budget is spent.
    """

    ok: bool
    status: str | None = None
    attempt: int | None = None
    noop: bool | None = None
    current_status: str | None = None

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "JobFailAck":
        return cls(
            ok=bool(payload.get("ok")),
            status=payload.get("status"),
            attempt=payload.get("attempt"),
            noop=payload.get("noop"),
            current_status=payload.get("currentStatus"),
        )
