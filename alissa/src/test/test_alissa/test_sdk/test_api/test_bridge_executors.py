"""The four executor endpoints of ``/v1/bridge`` (§5.1), against recorded responses.

Each test asserts both halves of the binding: the request it puts on the wire
(method, path, body — where "no invented fields" is enforced) and the typed
structure it hands back.
"""
from __future__ import annotations

from alissa.sdk.api.bridge import EXECUTOR_KIND, ExecutorCapabilities

from conftest import TEST_BASE_URL


def test_register_sends_the_declared_fields_and_returns_resumed_jobs(bridge, transport):
    transport.reply("executors_register.json")

    registration = bridge.register_executor(
        "macbook-pro-work",
        label="MacBook Pro (work)",
        hostname="mbp-work.local",
        fingerprint="fp-2f9c",
        cli_version="1.4.2",
        poll_seconds=15,
        worker_name="worker-mbp",
        capabilities=ExecutorCapabilities(
            workspace_roots=("/workspace",),
            max_concurrent_jobs=2,
            handoffs=("claude",),
        ),
    )

    assert transport.last.method == "POST"
    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/executors"
    assert transport.last_body == {
        "executorId": "macbook-pro-work",
        "kind": "alissa-code",
        "label": "MacBook Pro (work)",
        "hostname": "mbp-work.local",
        "fingerprint": "fp-2f9c",
        "cliVersion": "1.4.2",
        "pollSeconds": 15,
        "workerName": "worker-mbp",
        "capabilities": {
            "workspaceRoots": ["/workspace"],
            "maxConcurrentJobs": 2,
            "handoffs": ["claude"],
        },
    }

    assert registration.executor_id == "macbook-pro-work"
    assert registration.took_over is True
    assert registration.fingerprint_changed is False
    assert [job.job_id for job in registration.resumed] == ["j57bridge0001", "j57bridge0002"]
    # A pending resumed row has nothing holding it — the field is absent, not empty.
    assert registration.resumed[0].consumer_id == "consumer-a1"
    assert registration.resumed[1].consumer_id is None
    assert registration.resumed[1].attempt == 1


def test_register_omits_every_unset_optional(bridge, transport):
    transport.reply("executors_register.json")

    bridge.register_executor(
        "macbook-pro-work",
        label="MacBook Pro (work)",
        hostname="mbp-work.local",
        fingerprint="fp-2f9c",
    )

    assert transport.last_body == {
        "executorId": "macbook-pro-work",
        "kind": EXECUTOR_KIND,
        "label": "MacBook Pro (work)",
        "hostname": "mbp-work.local",
        "fingerprint": "fp-2f9c",
    }


def test_capabilities_absence_and_emptiness_stay_distinguishable(bridge, transport):
    # Absent workspaceRoots means "accepts any workspace"; an empty list would
    # mean "accepts none". The binding must not collapse the two.
    assert ExecutorCapabilities().to_wire() == {}
    assert ExecutorCapabilities(workspace_roots=()).to_wire() == {"workspaceRoots": []}
    # `tags` is reserved for v2 pool routing and unread today, but it is on the
    # wire — a binding that dropped it would be lossy, not tidy.
    assert ExecutorCapabilities(tags=("gpu",)).to_wire() == {"tags": ["gpu"]}

    transport.reply("executors_list.json")
    executors = bridge.list_executors()
    assert executors[0].capabilities is not None
    assert executors[0].capabilities.workspace_roots == ("/workspace",)
    assert executors[1].capabilities is None


def test_list_executors_projects_every_row(bridge, transport):
    transport.reply("executors_list.json")

    executors = bridge.list_executors()

    assert transport.last.method == "GET"
    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/executors"

    active, retired = executors
    assert active.executor_id == "macbook-pro-work"
    assert active.kind == "alissa-code"
    assert active.label == "MacBook Pro (work)"
    assert active.hostname == "mbp-work.local"
    assert active.cli_version == "1.4.2"
    assert active.poll_seconds == 15
    assert active.worker_name == "worker-mbp"
    assert active.started_at == 1786500000000
    assert active.last_heartbeat_at == 1786500600000
    assert active.status == "active"
    assert active.ended_at is None and active.end_reason is None

    assert retired.status == "executor_stopped"
    assert retired.ended_at == 1786401000000
    assert retired.end_reason == "executor_stopped"
    assert retired.cli_version is None


def test_executor_summary_never_carries_a_fingerprint(bridge, transport):
    # Machine identifiers stay server-side; modelling one would invent a field.
    transport.reply("executors_list.json")

    summary = bridge.list_executors()[0]

    assert not hasattr(summary, "fingerprint")


def test_heartbeat_posts_to_the_executor_and_reports_what_the_beat_did(bridge, transport):
    transport.reply("executor_heartbeat.json")

    beat = bridge.heartbeat_executor("macbook-pro-work")

    assert transport.last.method == "POST"
    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/executors/macbook-pro-work/heartbeat"
    assert beat.executor_id == "macbook-pro-work"
    assert beat.beat == "coalesced"


def test_a_missing_executor_comes_back_as_a_value_not_an_error(bridge, transport):
    # §5.1: "missing" means re-register. It is deliberately not a 404.
    transport.reply("executor_heartbeat_missing.json")

    assert bridge.heartbeat_executor("macbook-pro-work").beat == "missing"


def test_stop_reports_how_many_jobs_went_with_it(bridge, transport):
    transport.reply("executor_stop.json")

    stopped = bridge.stop_executor("macbook-pro-work", reason="signal")

    assert transport.last.method == "POST"
    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/executors/macbook-pro-work/stop"
    assert transport.last_body == {"reason": "signal"}
    assert stopped.executor_id == "macbook-pro-work"
    assert stopped.found is True
    assert stopped.already_ended is False
    assert stopped.released_jobs == 3


def test_stop_without_a_reason_sends_an_empty_body(bridge, transport):
    transport.reply("executor_stop.json")

    bridge.stop_executor("macbook-pro-work")

    assert transport.last_body == {}


def test_executor_ids_are_percent_encoded_into_the_path(bridge, transport):
    transport.reply("executor_heartbeat.json")

    bridge.heartbeat_executor("weird/id")

    assert transport.last.url == f"{TEST_BASE_URL}/v1/bridge/executors/weird%2Fid/heartbeat"
