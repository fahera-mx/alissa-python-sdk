"""``alissa.sdk.api.bridge`` — typed bindings for the Local Bridge queue mode.

The ``/v1/bridge`` executor and job surface of the Alissa API, mirroring
``api/src/schemas/bridge.ts`` (design: ``docs/design/local-bridge-queue-mode.md``
§5). :mod:`~alissa.sdk.api.bridge.client` holds the eleven endpoint methods;
:mod:`~alissa.sdk.api.bridge.models` holds the response structures.

Request/response plumbing only — the executor daemon itself is the Node `alissa`
CLI's, and lives nowhere in this package.
"""
from .client import BRIDGE_PREFIX, EXECUTOR_KIND, BridgeClient
from .models import (
    ExecutorCapabilities,
    ExecutorHeartbeat,
    ExecutorRegistration,
    ExecutorStopResult,
    ExecutorSummary,
    JobAcceptanceCriterion,
    JobClaim,
    JobDeliverable,
    JobDetail,
    JobFailAck,
    JobFeed,
    JobFeedItem,
    JobFulfillAck,
    JobProgressAck,
    JobReference,
    JobResult,
    JobResultAcceptance,
    JobResultLink,
    JobSpec,
    JobStartAck,
    ResumedJob,
)

__all__ = [
    "BRIDGE_PREFIX",
    "EXECUTOR_KIND",
    "BridgeClient",
    "ExecutorCapabilities",
    "ExecutorHeartbeat",
    "ExecutorRegistration",
    "ExecutorStopResult",
    "ExecutorSummary",
    "JobAcceptanceCriterion",
    "JobClaim",
    "JobDeliverable",
    "JobDetail",
    "JobFailAck",
    "JobFeed",
    "JobFeedItem",
    "JobFulfillAck",
    "JobProgressAck",
    "JobReference",
    "JobResult",
    "JobResultAcceptance",
    "JobResultLink",
    "JobSpec",
    "JobStartAck",
    "ResumedJob",
]
