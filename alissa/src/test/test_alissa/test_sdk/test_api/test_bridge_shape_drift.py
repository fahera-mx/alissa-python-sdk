"""What happens when the server's shape is not the shape these models expect.

The fixtures in this directory are written from ``api/src/schemas/bridge.ts``,
not captured from a live response, so a drift between schema and runtime is the
one residual risk on this surface. These tests do not claim the drift cannot
happen — they lock what it *looks like* when it does: always an
:class:`AlissaError`, never a raw ``KeyError`` escaping ``from_wire``.

That matters because the module docstrings and ``alissa/README.md`` teach
``except AlissaError`` as the way to wrap a binding call. An exception outside
that hierarchy would walk straight past the handler the docs told callers to
write.
"""
from __future__ import annotations

import pytest

from alissa.sdk.api import AlissaError, TransportError
from alissa.sdk.api.bridge.client import _decoded


def test_a_detail_response_without_its_job_envelope_is_a_transport_error(bridge, transport):
    transport.respond(200, {"ok": True})

    with pytest.raises(TransportError):
        bridge.get_job("j57bridge0001")


def test_a_detail_whose_job_is_not_an_object_is_a_transport_error(bridge, transport):
    transport.respond(200, {"job": "j57bridge0001"})

    with pytest.raises(TransportError):
        bridge.get_job("j57bridge0001")


def test_a_missing_required_field_is_a_transport_error_not_a_key_error(bridge, transport):
    # `jobId` is required by BridgeJobDetailSchema; dropping it is the drift.
    transport.respond(200, {"job": {"status": "running"}})

    with pytest.raises(TransportError) as caught:
        bridge.get_job("j57bridge0001")

    assert "jobId" in str(caught.value)


def test_the_drift_error_is_catchable_as_the_documented_base_class(bridge, transport):
    transport.respond(200, {"job": {"status": "running"}})

    with pytest.raises(AlissaError):
        bridge.get_job("j57bridge0001")


def test_a_feed_row_missing_its_id_is_a_transport_error(bridge, transport):
    transport.respond(200, {"jobs": [{"status": "pending"}], "beat": "ok"})

    with pytest.raises(TransportError):
        bridge.list_jobs(executor_id="exec-1")


def test_an_executor_row_missing_its_id_is_a_transport_error(bridge, transport):
    transport.respond(200, {"executors": [{"kind": "alissa-code"}]})

    with pytest.raises(TransportError):
        bridge.list_executors()


def test_a_stop_response_without_released_jobs_is_a_transport_error(bridge, transport):
    # `releasedJobs` is required (z.number()). Defaulting it to 0 would report
    # "nothing was released" — a meaningful, wrong answer — instead of failing.
    transport.respond(200, {"executorId": "exec-1", "found": True, "alreadyEnded": False})

    with pytest.raises(TransportError):
        bridge.stop_executor("exec-1")


def test_a_response_that_is_not_an_object_at_all_is_a_transport_error(bridge, transport):
    transport.respond(200, ["not", "an", "object"])

    with pytest.raises(TransportError):
        bridge.claim_job("j57bridge0001", executor_id="exec-1", consumer_id="c1", claim_seq=1)


def test_a_model_raising_a_type_error_is_converted_too():
    # No model here coerces in a way that can raise this today — the guard is
    # for the ones that will, so it is driven directly rather than through a
    # payload that pretends otherwise.
    def explode(_payload):
        raise TypeError("'NoneType' object is not subscriptable")

    with pytest.raises(TransportError) as caught:
        _decoded(explode, {"jobId": "j57bridge0001"}, "GET /v1/bridge/jobs/{jobId}")

    assert "GET /v1/bridge/jobs/{jobId}" in str(caught.value)
