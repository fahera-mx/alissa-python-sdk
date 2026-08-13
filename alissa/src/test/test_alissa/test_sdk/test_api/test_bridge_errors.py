"""§5.3's error codes, raised through the bindings that answer with them.

The point of this file is the promise in the issue: a caller branches on a
**code** (or its class), never on the prose of ``message``. One test per code
family, each driven by the envelope the API actually sends — including the
structured detail two of them are documented to carry.
"""
from __future__ import annotations

import pytest

from alissa.sdk.api import (
    ApiError,
    CapacityExceededError,
    CasConflictError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PreconditionFailedError,
    RetryAfterReadError,
    StaleConsumerError,
    StickyViolationError,
    UnauthorizedError,
    ValidationError,
)
from alissa.sdk.api.bridge import JobResult


def test_stale_consumer_is_typed_branchable_and_carries_the_observed_status(bridge, transport):
    # The nonce being echoed belongs to a superseded attempt: this caller must
    # stop, not retry. That is why it is its own class.
    transport.fail("error_stale_consumer.json", status=409)

    with pytest.raises(StaleConsumerError) as caught:
        bridge.progress_job("j57bridge0001", consumer_id="stale-nonce", note="still here")

    error = caught.value
    assert error.code == "STALE_CONSUMER"
    assert error.http_status == 409
    assert error.observed_status == "running"
    assert isinstance(error, RetryAfterReadError)
    assert str(error).startswith("STALE_CONSUMER: ")


def test_cas_conflict_reports_the_generation_to_re_read(bridge, transport):
    transport.fail("error_cas_conflict.json", status=409)

    with pytest.raises(CasConflictError) as caught:
        bridge.claim_job("j", executor_id="mbp", consumer_id="c", claim_seq=4)

    assert caught.value.code == "CAS_CONFLICT"
    assert caught.value.current_claim_seq == 7
    assert caught.value.observed_status == "pending"


def test_conflict_reports_the_status_actually_observed(bridge, transport):
    transport.fail("error_conflict.json", status=409)

    with pytest.raises(ConflictError) as caught:
        bridge.claim_job("j", executor_id="mbp", consumer_id="c", claim_seq=4)

    assert caught.value.code == "CONFLICT"
    assert caught.value.observed_status == "running"


def test_sticky_violation_names_the_executor_the_job_is_pinned_to(bridge, transport):
    transport.fail("error_sticky_violation.json", status=409)

    with pytest.raises(StickyViolationError) as caught:
        bridge.claim_job("j", executor_id="mbp", consumer_id="c", claim_seq=4)

    assert caught.value.sticky_executor_id == "mac-mini"


def test_every_409_shares_one_retry_after_read_base(bridge, transport):
    # The whole family means "re-read the row and retry", not "give up" — a
    # caller must be able to say that once.
    for fixture in (
        "error_conflict.json",
        "error_cas_conflict.json",
        "error_sticky_violation.json",
        "error_stale_consumer.json",
    ):
        transport.fail(fixture, status=409)
        with pytest.raises(RetryAfterReadError):
            bridge.start_job("j", consumer_id="c")


def test_capacity_exceeded_reports_held_and_cap(bridge, transport):
    transport.fail("error_capacity_exceeded.json", status=429)

    with pytest.raises(CapacityExceededError) as caught:
        bridge.claim_job("j", executor_id="mbp", consumer_id="c", claim_seq=4)

    assert caught.value.http_status == 429
    assert (caught.value.held, caught.value.cap) == (2, 2)
    # Not a re-read: this executor is full, and re-polling changes nothing.
    assert not isinstance(caught.value, RetryAfterReadError)


def test_precondition_failed_is_412_on_this_surface(bridge, transport):
    # §5.3 pins it at 412 where the rest of the Alissa API answers 409 — which
    # is exactly why callers must branch on the code, not the status.
    transport.fail("error_precondition_failed.json", status=412)

    with pytest.raises(PreconditionFailedError) as caught:
        bridge.claim_job("j", executor_id="mbp", consumer_id="c", claim_seq=4)

    assert caught.value.code == "PRECONDITION_FAILED"
    assert caught.value.http_status == 412


def test_forbidden_is_the_ultra_plan_gate(bridge, transport):
    transport.fail("error_forbidden.json", status=403)

    with pytest.raises(ForbiddenError):
        bridge.register_executor("mbp", label="L", hostname="h", fingerprint="f")


def test_unauthorized_covers_a_bad_or_revoked_token(bridge, transport):
    transport.fail("error_unauthorized.json", status=401)

    with pytest.raises(UnauthorizedError):
        bridge.list_executors()


def test_not_found_is_also_the_answer_for_another_users_row(bridge, transport):
    transport.fail("error_not_found.json", status=404)

    with pytest.raises(NotFoundError):
        bridge.get_job("someone-elses-job")


def test_validation_error_is_raised_for_a_malformed_query(bridge, transport):
    transport.fail("error_validation.json", status=400)

    with pytest.raises(ValidationError) as caught:
        bridge.list_jobs(executor_id="mbp", limit=999)

    assert caught.value.code == "VALIDATION_ERROR"


def test_fulfill_and_fail_raise_the_same_typed_errors(bridge, transport):
    transport.fail("error_stale_consumer.json", status=409)
    with pytest.raises(StaleConsumerError):
        bridge.fulfill_job("j", consumer_id="stale", result=JobResult(summary="Done."))

    transport.fail("error_stale_consumer.json", status=409)
    with pytest.raises(StaleConsumerError):
        bridge.fail_job("j", consumer_id="stale", error="boom", retryable=True)


def test_an_unmodelled_code_survives_as_a_plain_api_error(bridge, transport):
    # A code this SDK has never heard of must stay branchable by string rather
    # than crash or be swallowed.
    transport.fail("error_unknown_code.json", status=409)

    with pytest.raises(ApiError) as caught:
        bridge.stop_executor("mbp")

    assert type(caught.value) is ApiError
    assert caught.value.code == "SOME_FUTURE_CODE"
    assert caught.value.detail == {"hint": "re-read"}
