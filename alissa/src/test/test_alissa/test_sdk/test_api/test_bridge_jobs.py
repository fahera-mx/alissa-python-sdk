"""The seven job endpoints of ``/v1/bridge`` (§5.2), against recorded responses.

Feed, detail, claim, start, progress, fulfill, fail — request shape and typed
response for each, plus the noop/absorb and cancel paths that a reader of this
surface has to be able to see.
"""
from __future__ import annotations

from alissa.sdk.api.bridge import JobResult, JobResultAcceptance, JobResultLink

from conftest import TEST_BASE_URL


# ── Feed ─────────────────────────────────────────────────────────────────────


def test_feed_requires_an_executor_and_folds_in_the_heartbeat(bridge, transport):
    transport.reply("jobs_feed.json")

    feed = bridge.list_jobs(executor_id="macbook-pro-work")

    assert transport.last.method == "GET"
    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/jobs?executorId=macbook-pro-work"
    # The poll IS the liveness signal, so the beat rides back on it.
    assert feed.beat == "touched"
    assert [job.job_id for job in feed.jobs] == ["j57bridge0002", "j57bridge0001"]


def test_feed_statuses_are_comma_joined_and_limit_passes_through(bridge, transport):
    transport.reply("jobs_feed.json")

    bridge.list_jobs(executor_id="mbp", status=["pending", "running"], limit=10)

    assert transport.last.url == (
        f"{TEST_BASE_URL}/v1/bridge/jobs?executorId=mbp&status=pending%2Crunning&limit=10"
    )


def test_a_single_status_may_be_passed_as_a_bare_string(bridge, transport):
    transport.reply("jobs_feed.json")

    bridge.list_jobs(executor_id="mbp", status="claimed")

    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/jobs?executorId=mbp&status=claimed"


def test_feed_rows_project_the_cas_generation_and_the_attempt_budget(bridge, transport):
    transport.reply("jobs_feed.json")

    pending, running = bridge.list_jobs(executor_id="mbp").jobs

    assert (pending.claim_seq, pending.attempt, pending.max_attempts) == (4, 1, 3)
    assert pending.status == "pending"
    assert pending.created_at == 1786500000000
    assert pending.pending_expires_at == 1786503600000
    # Nothing holds a pending row yet.
    assert pending.consumer_id is None
    assert running.consumer_id == "consumer-a1"


def test_feed_carries_the_whole_spec_including_the_prompt(bridge, transport):
    # summarizeJobForFeed projects `spec` whole — the feed omits the RESULT side
    # (result/error/timing), not the prompt. Modelling a promptless feed spec
    # would be inventing a projection the server does not perform.
    transport.reply("jobs_feed.json")

    spec = bridge.list_jobs(executor_id="mbp").jobs[0].spec

    assert spec.title == "Wire the queue-mode bindings"
    assert spec.prompt.startswith("Implement the typed bindings")
    assert spec.deliverable.kind == "pull_request"
    assert [criterion.id for criterion in spec.acceptance] == ["surface", "tests"]
    assert spec.acceptance[1].type == "automated"
    assert spec.references is not None
    assert spec.references[0].ref == "TASK-1115046778"
    assert spec.references[1].label is None
    assert spec.workspace_root == "/workspace"
    assert spec.handoff == "claude"
    # env is variable NAMES only — never a credential channel.
    assert spec.env == ("ALISSA_API_TOKEN",)


def test_a_spec_without_optional_blocks_keeps_them_absent(bridge, transport):
    transport.reply("jobs_feed.json")

    spec = bridge.list_jobs(executor_id="mbp").jobs[1].spec

    assert spec.acceptance == ()
    assert spec.references is None
    assert spec.env is None
    assert spec.workspace_root is None


# ── Detail ───────────────────────────────────────────────────────────────────


def test_detail_unwraps_the_job_envelope_and_carries_lifecycle_state(bridge, transport):
    transport.reply("job_detail.json")

    job = bridge.get_job("j57bridge0001")

    assert transport.last.method == "GET"
    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/jobs/j57bridge0001"
    assert job.job_id == "j57bridge0001"
    assert job.status == "fulfilled"
    assert job.sticky_executor_id == "macbook-pro-work"
    assert job.claimed_by_executor_id == "macbook-pro-work"
    assert job.cancel_requested is False
    assert job.progress_note == "running the test suite"
    assert job.executor_session_id == "cs57session01"
    assert job.tmux_session == "ali-bridge-j57bridge0001"
    assert (job.claimed_at, job.started_at) == (1786499100000, 1786499200000)
    assert (job.last_progress_at, job.deadline_at) == (1786500100000, 1786506800000)
    assert job.completed_at == 1786500200000


def test_detail_models_the_result_body_the_feed_omits(bridge, transport):
    transport.reply("job_detail.json")

    result = bridge.get_job("j57bridge0001").result

    assert result is not None
    assert result.summary == "Opened the draft PR."
    assert result.markdown is not None and result.markdown.startswith("## What changed")
    assert result.links is not None and result.links[0].label == "PR"
    assert result.acceptance is not None
    assert [(row.id, row.met) for row in result.acceptance] == [("surface", True), ("tests", True)]
    assert result.acceptance[0].note == "eleven endpoints"
    assert result.acceptance[1].note is None


def test_detail_accepts_a_server_only_failure_kind(bridge, transport):
    # A daemon may only claim executor_error/spec_rejected/cancelled, but the
    # server writes kinds of its own. A reader that enumerated the daemon's
    # three would choke on every swept row.
    transport.reply("job_detail_failed.json")

    job = bridge.get_job("j57bridge0003")

    assert job.status == "failed"
    assert job.failure_kind == "executor_lost"
    assert job.error == "the executor stopped answering"
    assert job.cancel_requested is True
    assert job.result is None


def test_job_ids_are_percent_encoded_into_the_path(bridge, transport):
    transport.reply("job_detail.json")

    bridge.get_job("weird/id")

    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/jobs/weird%2Fid"


# ── Claim ────────────────────────────────────────────────────────────────────


def test_claim_echoes_the_generation_and_returns_the_wall_clock_deadline(bridge, transport):
    transport.reply("job_claim.json")

    claim = bridge.claim_job(
        "j57bridge0002", executor_id="macbook-pro-work", consumer_id="consumer-b2", claim_seq=4
    )

    assert transport.last.method == "POST"
    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/jobs/j57bridge0002/claim"
    assert transport.last_body == {
        "executorId": "macbook-pro-work",
        "consumerId": "consumer-b2",
        "claimSeq": 4,
    }
    assert claim.ok is True
    assert claim.job_id == "j57bridge0002"
    assert claim.claim_seq == 5
    assert claim.deadline_at == 1786507200000
    assert claim.spec.title == "Wire the queue-mode bindings"


# ── Start ────────────────────────────────────────────────────────────────────


def test_start_reports_the_session_and_any_pending_cancel(bridge, transport):
    transport.reply("job_start.json")

    ack = bridge.start_job(
        "j57bridge0002",
        consumer_id="consumer-b2",
        executor_session_id="cs57session02",
        tmux_session="ali-bridge-j57bridge0002",
    )

    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/jobs/j57bridge0002/start"
    assert transport.last_body == {
        "consumerId": "consumer-b2",
        "executorSessionId": "cs57session02",
        "tmuxSession": "ali-bridge-j57bridge0002",
    }
    assert ack.ok is True
    assert ack.status == "running"
    assert ack.cancel_requested is False


def test_start_surfaces_a_cancel_before_a_session_is_spawned(bridge, transport):
    # §5.4: a job cancelled while merely `claimed` must be observable here, or
    # the caller starts a session it is about to tear down.
    transport.reply("job_start_cancelled.json")

    assert bridge.start_job("j", consumer_id="c").cancel_requested is True


def test_start_at_a_terminal_row_is_a_noop_carrying_the_absorbing_status(bridge, transport):
    transport.reply("job_start_noop.json")

    ack = bridge.start_job("j", consumer_id="c")

    assert ack.noop is True
    assert ack.current_status == "timeout"
    assert ack.status is None


def test_start_omits_the_optional_session_fields(bridge, transport):
    transport.reply("job_start.json")

    bridge.start_job("j", consumer_id="c")

    assert transport.last_body == {"consumerId": "c"}


# ── Progress ─────────────────────────────────────────────────────────────────


def test_progress_posts_the_note_and_reports_the_beat(bridge, transport):
    transport.reply("job_progress.json")

    ack = bridge.progress_job("j57bridge0002", consumer_id="consumer-b2", note="running tests")

    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/jobs/j57bridge0002/progress"
    assert transport.last_body == {"consumerId": "consumer-b2", "note": "running tests"}
    assert ack.ok is True
    assert ack.coalesced is False
    assert ack.cancel_requested is False


def test_a_coalesced_progress_write_is_visible_to_the_caller(bridge, transport):
    # Writes coalesce to one a minute: the beat counted, the note was dropped.
    transport.reply("job_progress_coalesced.json")

    ack = bridge.progress_job("j", consumer_id="c", note="dropped")

    assert ack.coalesced is True
    assert ack.cancel_requested is True


def test_progress_without_a_note_is_a_bare_beat(bridge, transport):
    transport.reply("job_progress.json")

    bridge.progress_job("j", consumer_id="c")

    assert transport.last_body == {"consumerId": "c"}


# ── Fulfill ──────────────────────────────────────────────────────────────────


def test_fulfill_serializes_the_full_result(bridge, transport):
    transport.reply("job_fulfill.json")

    ack = bridge.fulfill_job(
        "j57bridge0002",
        consumer_id="consumer-b2",
        result=JobResult(
            summary="Done.",
            markdown="## Notes",
            links=(JobResultLink(label="PR", url="https://example.invalid/pr/1"),),
            acceptance=(
                JobResultAcceptance(id="surface", met=True, note="all eleven"),
                JobResultAcceptance(id="tests", met=False),
            ),
        ),
    )

    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/jobs/j57bridge0002/fulfill"
    assert transport.last_body == {
        "consumerId": "consumer-b2",
        "result": {
            "summary": "Done.",
            "markdown": "## Notes",
            "links": [{"label": "PR", "url": "https://example.invalid/pr/1"}],
            "acceptance": [
                {"id": "surface", "met": True, "note": "all eleven"},
                {"id": "tests", "met": False},
            ],
        },
    }
    assert ack.ok is True
    assert ack.noop is None


def test_a_minimal_result_sends_only_its_summary(bridge, transport):
    transport.reply("job_fulfill.json")

    bridge.fulfill_job("j", consumer_id="c", result=JobResult(summary="Done."))

    assert transport.last_body == {"consumerId": "c", "result": {"summary": "Done."}}


def test_a_late_fulfill_is_absorbed_rather_than_errored(bridge, transport):
    transport.reply("job_fulfill_noop.json")

    ack = bridge.fulfill_job("j", consumer_id="c", result=JobResult(summary="Done."))

    assert ack.noop is True
    assert ack.current_status == "timeout"


# ── Fail ─────────────────────────────────────────────────────────────────────


def test_a_retryable_failure_hands_the_row_back_as_pending(bridge, transport):
    transport.reply("job_fail_retry.json")

    ack = bridge.fail_job(
        "j57bridge0002",
        consumer_id="consumer-b2",
        error="the agent crashed",
        retryable=True,
        failure_kind="executor_error",
    )

    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/jobs/j57bridge0002/fail"
    assert transport.last_body == {
        "consumerId": "consumer-b2",
        "error": "the agent crashed",
        "retryable": True,
        "failureKind": "executor_error",
    }
    assert ack.status == "pending"
    assert ack.attempt == 3


def test_a_terminal_failure_reports_the_spent_budget(bridge, transport):
    transport.reply("job_fail_terminal.json")

    ack = bridge.fail_job("j", consumer_id="c", error="gave up", retryable=False)

    # retryable is a real False, not an omitted optional — it must survive.
    assert transport.last_body == {"consumerId": "c", "error": "gave up", "retryable": False}
    assert ack.status == "failed"
    assert ack.attempt == 3
