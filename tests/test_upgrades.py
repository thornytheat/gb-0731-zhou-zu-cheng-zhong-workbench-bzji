import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

from fastapi.testclient import TestClient

from app.main import create_app


def run(client, sample="dirty"):
    return client.post("/api/batches", json={"sample": sample})


def upgrade(client, run_id, rules="axle-1.1.0", parameters=None):
    return client.post("/api/upgrades", json={"run_id": run_id, "rules": rules, "parameters": parameters or {}})


def archived(client, sample="dirty"):
    return run(client, sample).json()["manifest"]["run_id"]


def entry(order, pass_id):
    return next(item for item in order["entries"] if item["pass_id"] == pass_id)


def test_upgrade_flags_only_impacted_trips_with_old_new_and_basis(client):
    run_id = archived(client)
    reply = upgrade(client, run_id, parameters={"ticket_tolerance_kg": "49.99"})
    assert reply.status_code == 201
    order = reply.json()["order"]
    assert reply.json()["reused"] is False
    assert order["summary"] == {"passes": 7, "changed": 1, "unchanged": 6}
    assert order["from"]["rules"] == "axle-1.0.0"
    assert order["to"]["rules"] == "axle-1.1.0"
    assert order["parameter_changes"] == [{"name": "ticket_tolerance_kg", "old": "50.00", "new": "49.99"}]
    changed = entry(order, "0007")
    assert changed["origin"] == "reconcile"
    assert changed["old"]["status"] == "matched" and changed["old"]["codes"] == []
    assert changed["new"]["status"] == "review" and changed["new"]["codes"] == ["WEIGHT_DIFFERENCE"]
    assert changed["old"]["difference_kg"] == changed["new"]["difference_kg"] == "50.00"
    assert changed["basis"]["wheels"] == [] and changed["basis"]["issues"] == []
    assert changed["basis"]["reconcile"]["new_codes"] == ["WEIGHT_DIFFERENCE"]
    for other in order["entries"]:
        if other["pass_id"] != "0007":
            assert other["impact"] == "unchanged"
            assert other["old"] == other["new"] and other["basis"] is None
    assert client.get("/api/batches").json()["batches"][0]["rules"] == "axle-1.0.0"


def test_same_upgrade_repost_reuses_order_without_duplicates(client):
    run_id = archived(client)
    first = upgrade(client, run_id, parameters={"severe_ratio": "0.25"}).json()["order"]
    second = upgrade(client, run_id, parameters={"severe_ratio": "0.25"})
    assert second.status_code == 200
    assert second.json() == {"order": first, "reused": True}
    orders = client.get("/api/upgrades").json()["orders"]
    assert [item["order_id"] for item in orders] == [first["order_id"]]
    codes = [event["code"] for event in client.get("/api/batches/events").json()["events"]]
    assert (codes.count("UPGRADE_ISSUED"), codes.count("UPGRADE_REUSED")) == (1, 1)


def test_issued_order_is_retrievable_as_issued_and_survives_restart(client, settings):
    run_id = archived(client)
    order = upgrade(client, run_id).json()["order"]
    assert client.get(f"/api/upgrades/{order['order_id']}").json()["order"] == order
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f"/api/upgrades/{order['order_id']}").json()["order"] == order
        assert restarted.get("/api/upgrades").json()["orders"][0]["order_id"] == order["order_id"]


def test_failed_upgrade_keeps_previous_order_and_sources_untouched(client, settings):
    run_id = archived(client)
    order = upgrade(client, run_id, "axle-1.1.0").json()["order"]
    source = settings.source_dir / "dirty-triggers.csv"
    source.write_bytes(source.read_bytes() + b"\r\n")
    reply = upgrade(client, run_id, "axle-2.0.0", {"ticket_tolerance_kg": "49.99"})
    assert (reply.status_code, reply.json()["error"]["code"]) == (409, "SOURCE_CHANGED")
    assert client.get(f"/api/upgrades/{order['order_id']}").json()["order"] == order
    assert len(client.get("/api/upgrades").json()["orders"]) == 1
    assert upgrade(client, run_id, "axle-1.1.0").status_code == 200


def test_failed_first_attempt_issues_no_order(client, settings):
    run_id = archived(client)
    (settings.source_dir / "dirty-tickets.csv").unlink()
    reply = upgrade(client, run_id)
    assert (reply.status_code, reply.json()["error"]["code"]) == (422, "SOURCE_MISSING")
    assert client.get("/api/upgrades").json()["orders"] == []


def test_noop_upgrade_is_rejected(client):
    run_id = archived(client)
    for parameters in ({}, {"ticket_tolerance_kg": "50.00", "debounce_ms": 12}):
        reply = upgrade(client, run_id, "axle-1.0.0", parameters)
        assert (reply.status_code, reply.json()["error"]["code"]) == (422, "UPGRADE_NOOP")
    assert client.get("/api/upgrades").json()["orders"] == []


def test_invalid_upgrade_inputs_are_rejected(client):
    run_id = archived(client)
    bad = [
        ("", {}), ("axle 1.1", {}), ("axle-1.1.0", {"unknown": 1}),
        ("axle-1.1.0", {"debounce_ms": "12"}), ("axle-1.1.0", {"debounce_ms": True}),
        ("axle-1.1.0", {"pair_ms": 0}), ("axle-1.1.0", {"notice_ratio": "abc"}),
        ("axle-1.1.0", {"notice_ratio": "NaN"}), ("axle-1.1.0", {"severe_ratio": [0.2]}),
        ("axle-1.1.0", {"notice_ratio": "0.30", "severe_ratio": "0.20"}),
        ("axle-1.1.0", {"min_spacing_m": "2.0", "tandem_spacing_m": "1.80"}),
    ]
    for rules, parameters in bad:
        reply = upgrade(client, run_id, rules, parameters)
        assert (reply.status_code, reply.json()["error"]["code"]) == (422, "UPGRADE_INVALID"), (rules, parameters)
    assert client.get("/api/upgrades").json()["orders"] == []


def test_wheel_correction_cascade_marks_calibration_origin(client):
    run_id = archived(client)
    order = upgrade(client, run_id, "axle-2.0.0", {"max_wheel_kg": "2900"}).json()["order"]
    changed = entry(order, "0007")
    assert changed["origin"] == "calibration"
    assert changed["basis"]["wheels"] == [{
        "trigger": "0007-3L", "side": "L", "ref": "dirty-triggers.csv:14",
        "old_kg": "3000.00", "new_kg": None, "old_cert": "L-1120", "new_cert": None,
    }]
    assert {issue["code"] for issue in changed["basis"]["issues"]} == {"WHEEL_RANGE", "PAIR_MISSING"}
    assert changed["old"]["axles"] == 4 and changed["new"]["axles"] == 3
    assert changed["old"]["wheel_kg"] == "20000.01" and changed["new"]["wheel_kg"] == "15000.01"
    assert changed["new"]["codes"] == ["WHEELS_INCOMPLETE", "WEIGHT_DIFFERENCE"]
    assert order["summary"]["changed"] == 1


def test_threshold_only_change_marks_balance_origin_without_wheel_changes(client):
    run_id = archived(client)
    order = upgrade(client, run_id, "axle-2.2.0", {"severe_ratio": "0.25"}).json()["order"]
    changed = entry(order, "0007")
    assert changed["origin"] == "balance"
    assert changed["basis"]["wheels"] == [] and changed["basis"]["issues"] == []
    assert changed["basis"]["balance"] == [{"axle": "0007/A03", "old": "severe", "new": "warn"}]
    assert changed["old"]["balance"] == {"pass": 2, "warn": 1, "severe": 1}
    assert changed["new"]["balance"] == {"pass": 2, "warn": 2, "severe": 0}
    assert changed["new"]["status"] == "matched"


def test_debounce_window_change_marks_debounce_origin(client):
    run_id = archived(client)
    order = upgrade(client, run_id, "axle-2.1.0", {"debounce_ms": 11}).json()["order"]
    changed = entry(order, "0007")
    assert changed["origin"] == "debounce"
    removed = {issue["code"] for issue in changed["basis"]["issues"] if issue["change"] == "removed"}
    added = {issue["code"] for issue in changed["basis"]["issues"] if issue["change"] == "added"}
    assert removed == {"BOUNCE"} and added == {"PAIR_AMBIGUOUS"}
    assert changed["old"]["axles"] == 4 and changed["new"]["axles"] == 3
    assert changed["new"]["status"] == "review"


def test_version_only_upgrade_keeps_clean_sample_unchanged(client):
    run_id = archived(client, "clean")
    order = upgrade(client, run_id, "axle-1.1.0").json()["order"]
    assert order["parameter_changes"] == []
    assert order["summary"] == {"passes": 7, "changed": 0, "unchanged": 7}
    assert all(item["impact"] == "unchanged" and item["basis"] is None for item in order["entries"])


def test_concurrent_upgrade_posts_issue_one_order(client):
    run_id = archived(client)
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _: upgrade(client, run_id), range(4)))
    assert sorted(result.status_code for result in results) == [200, 200, 200, 201]
    ids = {result.json()["order"]["order_id"] for result in results}
    assert len(ids) == 1
    assert len(client.get("/api/upgrades").json()["orders"]) == 1
    codes = [event["code"] for event in client.get("/api/batches/events").json()["events"]]
    assert (codes.count("UPGRADE_ISSUED"), codes.count("UPGRADE_REUSED")) == (1, 3)


def test_unknown_batch_or_order_fail_explicitly(client):
    reply = upgrade(client, "absent")
    assert (reply.status_code, reply.json()["error"]["code"]) == (404, "RUN_UNKNOWN")
    reply = client.get("/api/upgrades/absent")
    assert (reply.status_code, reply.json()["error"]["code"]) == (404, "ORDER_UNKNOWN")


def test_database_error_during_issue_rolls_back_order_and_event(client, settings):
    run_id = archived(client)
    with closing(sqlite3.connect(settings.db_file)) as db:
        db.executescript("""
            CREATE TRIGGER deny_order BEFORE INSERT ON upgrade_orders
            BEGIN SELECT RAISE(ABORT, 'order write failed'); END;
        """)
    with TestClient(client.app, raise_server_exceptions=False) as tolerant:
        assert upgrade(tolerant, run_id).status_code == 500
    assert client.get("/api/upgrades").json()["orders"] == []
    codes = [event["code"] for event in client.get("/api/batches/events").json()["events"]]
    assert "UPGRADE_ISSUED" not in codes
