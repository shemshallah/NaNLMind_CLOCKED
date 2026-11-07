import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

try:
    from cryptography.fernet import Fernet
except ImportError:  # optional on minimal hosts; CI installs service requirements
    Fernet = None

from clocked_experience import digest, make_event, summarize_step
from gateway import Gateway, connect_db


class FakeClocked:
    def __init__(self):
        self.calls = 0

    def pipeline(self, text, steps, on_error):
        self.calls += 1
        return {
            "steps": [
                {"endpoint": "decide", "name": "task_classification", "status": 200,
                 "result": {"answers": {"task_family": "technical_document", "contains_claims": True}}},
                {"endpoint": "extract", "name": "evidence_extraction", "status": 200,
                 "result": {"fields": {"claims": ["private claim"], "dates": ["2026-11-05"]}}},
            ],
            "stopped": False,
            "timing": {"total_ms": 12},
        }

    def extract(self, text, **options):
        self.calls += 1
        return {"fields": {"claims": [text]}, "timing": {"model_ms": 3}}

    def grounding(self, text, **options):
        self.calls += 1
        return {"verdict": "unknown", "timing": {"model_ms": 2}}


def invoke(app, path, method="GET", payload=None, bearer=None, headers=None):
    raw = b"" if payload is None else json.dumps(payload).encode("utf-8")
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw)}
    if bearer:
        environ["HTTP_AUTHORIZATION"] = "Bearer " + bearer
    for key, value in (headers or {}).items():
        environ["HTTP_" + key.upper().replace("-", "_")] = value
    captured = {}
    def start_response(status, headers):
        captured["status"] = status
    body = b"".join(app(environ, start_response))
    return captured["status"], json.loads(body.decode("utf-8"))


class ClockedExperienceTests(unittest.TestCase):
    def test_digest_is_deterministic(self):
        self.assertEqual(digest({"b": 2, "a": 1}), digest({"a": 1, "b": 2}))

    def test_step_summary_does_not_persist_extracted_values(self):
        summary = summarize_step({"endpoint": "extract", "status": 200,
            "result": {"fields": {"email": "secret@example.test", "amount": "$42"}}})
        self.assertEqual(summary["extracted_field_names"], ["amount", "email"])
        self.assertNotIn("secret@example.test", repr(summary))
        self.assertNotIn("$42", repr(summary))

    def test_event_is_explicitly_not_native_training_commit(self):
        event = make_event("hello", {"steps": []}, object())
        self.assertEqual(event["learning_state"], "awaiting_nanlmind_ingest")
        self.assertFalse(event["raw_text_persisted"])
        self.assertFalse(event["raw_response_persisted"])
        self.assertNotIn("hello", repr(event))


@unittest.skipUnless(Fernet is not None, "cryptography is required for gateway result-cache tests")
class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "gateway.sqlite3")
        self.app = Gateway(self.db_path, FakeClocked())
        self.result_key = Fernet.generate_key().decode("ascii")
        self.env = patch.dict(os.environ, {
            "CLOCKED_RESULT_ENCRYPTION_KEY": self.result_key,
            "CLOCKED_TOKEN_PEPPER": "test-only-pepper",
            "CLOCKED_GATEWAY_ADMIN_TOKEN": "admin-test-token",
            "NANLM_RUNNER_INGEST_TOKEN": "runner-test-token",
            "CLOCKED_DEMO_ENROLLMENT_TOKEN": "enroll-test-token",
            "CLOCKED_API_KEY": "test-upstream-key",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)

    def issue(self, max_requests=2, endpoint_id="clocked_demo"):
        status, result = invoke(self.app, "/admin/tokens", "POST",
            {"tenant_id": "test-tenant", "endpoint_id": endpoint_id, "max_requests": max_requests, "ttl_seconds": 600},
            "admin-test-token")
        self.assertEqual(status, "201 Created")
        expected_type = {"clocked_demo": "CLOCKED_USER_API", "my_android": "NANLM_DEVICE_TOKEN", "hermes_demo": "HERMES_DEMO_API"}[endpoint_id]
        self.assertEqual(result["token_type"], expected_type)
        self.assertEqual(result["source_endpoint"], endpoint_id)
        return result["token"]

    def test_health_does_not_require_credentials(self):
        status, result = invoke(self.app, "/healthz")
        self.assertEqual(status, "200 OK")
        self.assertEqual(result["protocol"], "nanlm.endpoint-observation")
        self.assertEqual(result["source_endpoints"], ["clocked_demo", "hermes_demo", "my_android"])

    def test_admin_issues_scoped_token_and_demo_returns_content_minimized_event(self):
        token = self.issue()
        status, result = invoke(self.app, "/v1/experience", "POST",
            {"protocol": "nanlm.clocked-experience", "text": "private source text"}, token)
        self.assertEqual(status, "200 OK")
        self.assertEqual(result["event"]["tenant_id"], "test-tenant")
        self.assertEqual(result["event"]["source_endpoint"], "clocked_demo")
        self.assertEqual(result["event"]["learning_state"], "awaiting_nanlmind_ingest")
        encoded = json.dumps(result)
        self.assertNotIn("private source text", encoded)
        self.assertNotIn("private claim", encoded)
        self.assertNotIn("2026-11-05", encoded)


    def test_experience_idempotency_replays_without_second_clocked_call(self):
        token = self.issue(max_requests=1)
        payload = {"protocol": "nanlm.clocked-experience", "text": "same request"}
        headers = {"Idempotency-Key": "demo-request-0001"}
        status, first = invoke(self.app, "/v1/experience", "POST", payload, token, headers)
        self.assertEqual(status, "200 OK")
        calls_after_first = self.app.clocked_client.calls
        status, replay = invoke(self.app, "/v1/experience", "POST", payload, token, headers)
        self.assertEqual(status, "200 OK")
        self.assertEqual(first, replay)
        self.assertEqual(self.app.clocked_client.calls, calls_after_first)
        status, quota = invoke(self.app, "/v1/experience", "POST",
            {"text": "different request"}, token, {"Idempotency-Key": "demo-request-0002"})
        self.assertEqual(status, "429 Too Many Requests")
        self.assertEqual(quota["error"], "quota_exceeded")

    def test_idempotency_key_cannot_be_reused_for_different_body(self):
        token = self.issue()
        headers = {"Idempotency-Key": "same-key"}
        status, _ = invoke(self.app, "/v1/experience", "POST", {"text": "one"}, token, headers)
        self.assertEqual(status, "200 OK")
        status, result = invoke(self.app, "/v1/experience", "POST", {"text": "two"}, token, headers)
        self.assertEqual(status, "409 Conflict")
        self.assertEqual(result["error"], "idempotency_key_conflict")

    def test_quota_is_enforced(self):
        token = self.issue(max_requests=1)
        status, _ = invoke(self.app, "/v1/experience", "POST", {"text": "one"}, token)
        self.assertEqual(status, "200 OK")
        status, result = invoke(self.app, "/v1/experience", "POST", {"text": "two"}, token)
        self.assertEqual(status, "429 Too Many Requests")
        self.assertEqual(result["error"], "quota_exceeded")

    def test_multi_endpoint_task_plan_returns_typed_source_results(self):
        token = self.issue(max_requests=2)
        plan = {
            "schema": "nanlm.clocked-task-plan/1", "version": 1,
            "plan_id": "task-plan-0001",
            "tasks": [
                {"id": "extract-a", "endpoint": "extract", "text": "source A", "depends_on": []},
                {"id": "ground-a", "endpoint": "grounding", "text": "source A", "depends_on": ["extract-a"]},
            ],
        }
        status, result = invoke(self.app, "/v1/tasks", "POST",
            {"protocol": "nanlm.clocked-task-plan", "version": 1, "plan": plan},
            token, {"Idempotency-Key": "task-plan-0001"})
        self.assertEqual(status, "200 OK")
        self.assertEqual(result["protocol"], "nanlm.clocked-task-results")
        self.assertEqual([item["endpoint"] for item in result["results"]], ["extract", "grounding"])
        self.assertEqual([item["result_type"] for item in result["results"]], ["extract", "grounding"])
        self.assertEqual(result["results"][0]["result"]["fields"]["claims"], ["source A"])
        self.assertEqual(result["learning_state"], "awaiting_nanlmind_ingest")
        db = connect_db(self.db_path)
        stored = db.execute("SELECT response_json FROM experience_requests").fetchone()[0]
        db.close()
        self.assertTrue(stored.startswith("fernet:"))
        calls = self.app.clocked_client.calls
        status, replay = invoke(self.app, "/v1/tasks", "POST",
            {"protocol": "nanlm.clocked-task-plan", "version": 1, "plan": plan},
            token, {"Idempotency-Key": "task-plan-0001"})
        self.assertEqual(status, "200 OK")
        self.assertEqual(replay, result)
        self.assertEqual(self.app.clocked_client.calls, calls)

    def test_multi_endpoint_fails_closed_without_result_encryption_key(self):
        token = self.issue()
        plan = {"schema": "nanlm.clocked-task-plan/1", "version": 1,
                "plan_id": "task-plan-no-encryption",
                "tasks": [{"id": "extract-a", "endpoint": "extract",
                           "text": "private source", "depends_on": []}]}
        with patch.dict(os.environ, {"CLOCKED_RESULT_ENCRYPTION_KEY": ""}):
            status, result = invoke(self.app, "/v1/tasks", "POST",
                {"protocol": "nanlm.clocked-task-plan", "version": 1, "plan": plan}, token)
        self.assertEqual(status, "503 Service Unavailable")
        self.assertEqual(result["error"], "result_cache_encryption_unavailable")
        self.assertEqual(self.app.clocked_client.calls, 0)

    def test_multi_endpoint_plan_rejects_forward_dependency_and_unknown_endpoint(self):
        token = self.issue()
        plan = {"schema": "nanlm.clocked-task-plan/1", "version": 1,
                "plan_id": "task-plan-0002",
                "tasks": [{"id": "a", "endpoint": "extract", "text": "x",
                           "depends_on": ["b"]}]}
        status, result = invoke(self.app, "/v1/tasks", "POST",
            {"protocol": "nanlm.clocked-task-plan", "version": 1, "plan": plan}, token)
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(result["error"], "dependencies_must_reference_prior_tasks")
        plan["tasks"][0]["depends_on"] = []
        plan["tasks"][0]["endpoint"] = "arbitrary_method"
        status, result = invoke(self.app, "/v1/tasks", "POST",
            {"protocol": "nanlm.clocked-task-plan", "version": 1, "plan": plan}, token)
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(result["error"], "unsupported_endpoint")

    def test_unknown_token_is_rejected(self):
        status, result = invoke(self.app, "/v1/experience", "POST", {"text": "hello"}, "not-a-token")
        self.assertEqual(status, "401 Unauthorized")
        self.assertEqual(result["error"], "unauthorized")


    def test_android_token_cannot_claim_correctness_and_event_is_durable(self):
        token = self.issue(endpoint_id="my_android")
        payload = {
            "protocol": "nanlm.endpoint-observation", "version": 1,
            "event_id": "a" * 64, "base_generation": 7,
            "active_heads": [3, 3, 255], "outcome_verified": False,
        }
        status, result = invoke(self.app, "/v1/observations", "POST", payload, token)
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(result["source_endpoint"], "my_android")
        self.assertEqual(result["learning_state"], "awaiting_runner_ring_ingest")
        status, duplicate = invoke(self.app, "/v1/observations", "POST", payload, token)
        self.assertEqual(status, "200 OK")
        self.assertEqual(duplicate["learning_state"], "duplicate_noop")
        status, denied = invoke(self.app, "/internal/observations", bearer="admin-test-token")
        self.assertEqual(status, "401 Unauthorized")
        status, queued = invoke(self.app, "/internal/observations", bearer="runner-test-token")
        self.assertEqual(status, "200 OK")
        self.assertEqual(queued["count"], 1)
        event = queued["events"][0]
        self.assertEqual(event["source_endpoint"], "my_android")
        self.assertEqual(event["active_heads"], [3, 255])
        self.assertFalse(event["outcome_verified"])
        self.assertEqual(queued["lease_seconds"], 120)
        status, ack = invoke(self.app, "/internal/observations/ack", "POST",
            {"lease_id": queued["lease_id"], "event_ids": [event["event_id"]]}, "runner-test-token")
        self.assertEqual(status, "200 OK")
        self.assertTrue(ack["complete"])

    def test_expired_lease_is_reclaimed_and_stale_ack_is_rejected(self):
        token = self.issue(endpoint_id="my_android")
        payload = {"protocol":"nanlm.endpoint-observation","version":1,"event_id":"e"*64,
                   "base_generation":0,"active_heads":[],"outcome_verified":False}
        status, _ = invoke(self.app, "/v1/observations", "POST", payload, token)
        self.assertEqual(status, "202 Accepted")
        _, first = invoke(self.app, "/internal/observations", bearer="runner-test-token")
        db = connect_db(self.db_path)
        db.execute("UPDATE endpoint_inbox SET lease_until=0 WHERE event_id=?", ("e"*64,))
        db.commit()
        db.close()
        _, second = invoke(self.app, "/internal/observations", bearer="runner-test-token")
        self.assertEqual(second["count"], 1)
        _, stale = invoke(self.app, "/internal/observations/ack", "POST",
            {"lease_id":first["lease_id"],"event_ids":["e"*64]},"runner-test-token")
        self.assertFalse(stale["complete"])
        _, fresh = invoke(self.app, "/internal/observations/ack", "POST",
            {"lease_id":second["lease_id"],"event_ids":["e"*64]},"runner-test-token")
        self.assertTrue(fresh["complete"])

    def test_observation_rejects_fields_outside_the_published_schema(self):
        token = self.issue(endpoint_id="hermes_demo")
        payload = {
            "protocol": "nanlm.endpoint-observation", "version": 1,
            "event_id": "d" * 64, "base_generation": 0, "active_heads": [],
            "outcome_verified": False, "source_endpoint": "clocked_demo",
        }
        status, result = invoke(self.app, "/v1/observations", "POST", payload, token)
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(result["error"], "unknown_observation_fields")

    def test_endpoint_cannot_submit_its_own_correctness_label(self):
        token = self.issue(endpoint_id="hermes_demo")
        payload = {
            "protocol": "nanlm.endpoint-observation", "version": 1,
            "event_id": "b" * 64, "base_generation": 0,
            "active_heads": [1], "outcome_verified": True, "correct": True,
        }
        status, result = invoke(self.app, "/v1/observations", "POST", payload, token)
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(result["error"], "endpoint_cannot_assert_correctness")

    def test_clocked_identity_is_server_assigned_for_generic_events(self):
        token = self.issue()
        payload = {
            "protocol": "nanlm.endpoint-observation", "version": 1,
            "event_id": "c" * 64, "base_generation": 0, "active_heads": [],
            "outcome_verified": False,
        }
        status, result = invoke(self.app, "/v1/observations", "POST", payload, token)
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(result["source_endpoint"], "clocked_demo")

    def test_internal_poll_requires_runner_token_not_admin(self):
        status, result = invoke(self.app, "/internal/observations")
        self.assertEqual(status, "401 Unauthorized")
        self.assertEqual(result["error"], "runner_unauthorized")
        status, result = invoke(self.app, "/internal/observations", bearer="admin-test-token")
        self.assertEqual(status, "401 Unauthorized")
        self.assertEqual(result["error"], "runner_unauthorized")


    def issue_demo_instance(self, label="instance"):
        status, result = invoke(
            self.app, "/auth/demo-token", "POST",
            {"instance_label": label, "max_requests": 20, "ttl_seconds": 600},
            "enroll-test-token",
        )
        self.assertEqual(status, "201 Created", result)
        self.assertEqual(result["registration_state"], "reserved_pending_nannet_registration")
        return result

    def test_demo_auth_mints_scoped_tokens_and_allocates_lowest_free_points(self):
        denied, _ = invoke(self.app, "/auth/demo-token", "POST", {"instance_label": "x"},
                           "wrong-enrollment-token")
        self.assertEqual(denied, "401 Unauthorized")
        first = self.issue_demo_instance("first")
        second = self.issue_demo_instance("second")
        self.assertEqual(first["node_point"], 9)
        self.assertEqual(second["node_point"], 10)
        self.assertNotEqual(first["token"], second["token"])
        db = connect_db(self.db_path)
        rows = db.execute("SELECT token_hash,node_point FROM demo_tokens ORDER BY node_point").fetchall()
        db.close()
        self.assertTrue(all(row["token_hash"] != first["token"] for row in rows))

    def test_demo_instance_identity_flows_into_clocked_event_and_observation(self):
        instance = self.issue_demo_instance()
        status, result = invoke(
            self.app, "/v1/experience", "POST",
            {"protocol": "nanlm.clocked-experience", "text": "instance-bound demo"},
            instance["token"], {"Idempotency-Key": "point-bound-demo"},
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(result["event"]["node_point"], 9)
        self.assertEqual(result["event"]["instance_id"], instance["instance_id"])

        payload = {
            "protocol": "nanlm.endpoint-observation", "version": 1,
            "event_id": "f" * 64, "base_generation": 0,
            "active_heads": [2, 4], "outcome_verified": False,
        }
        status, accepted = invoke(self.app, "/v1/observations", "POST", payload, instance["token"])
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(accepted["node_point"], 9)
        status, queued = invoke(self.app, "/internal/observations", bearer="runner-test-token")
        self.assertEqual(status, "200 OK")
        self.assertEqual(queued["events"][0]["node_point"], 9)

    def test_revocation_releases_lowest_point_for_reuse(self):
        first = self.issue_demo_instance()
        second = self.issue_demo_instance()
        status, result = invoke(
            self.app, "/admin/instances/revoke", "POST",
            {"instance_id": first["instance_id"]}, "admin-test-token",
        )
        self.assertEqual(status, "200 OK")
        self.assertTrue(result["revoked"])
        third = self.issue_demo_instance()
        self.assertEqual(second["node_point"], 10)
        self.assertEqual(third["node_point"], 9)

    def test_expired_instance_releases_point(self):
        first = self.issue_demo_instance()
        db = connect_db(self.db_path)
        db.execute("UPDATE demo_instances SET expires_at=0 WHERE instance_id=?",
                   (first["instance_id"],))
        db.commit()
        db.close()
        replacement = self.issue_demo_instance()
        self.assertEqual(replacement["node_point"], 9)

    def test_demo_instance_allocator_enforces_247_point_capacity(self):
        db = connect_db(self.db_path)
        now = int(time.time())
        for point in range(9, 256):
            db.execute(
                "INSERT INTO demo_instances(node_point,instance_id,token_hash,expires_at,created_at) "
                "VALUES(?,?,?,?,?)",
                (point, "occupied-%d" % point, "hash-%d" % point, now + 600, now),
            )
        db.commit()
        db.close()
        status, result = invoke(
            self.app, "/auth/demo-token", "POST", {"instance_label": "overflow"},
            "enroll-test-token",
        )
        self.assertEqual(status, "429 Too Many Requests")
        self.assertEqual(result["available_range"], "9..255")

    def test_demo_token_request_rejects_caller_selected_point_and_oversized_policy(self):
        status, result = invoke(
            self.app, "/auth/demo-token", "POST",
            {"instance_label": "bad", "node_point": 200}, "enroll-test-token",
        )
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(result["error"], "unknown_fields")
        status, result = invoke(
            self.app, "/auth/demo-token", "POST",
            {"instance_label": "bad", "ttl_seconds": 86400}, "enroll-test-token",
        )
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(result["error"], "ttl_seconds_out_of_range")



    def test_concurrent_instance_issuance_never_duplicates_node_points(self):
        from concurrent.futures import ThreadPoolExecutor
        def issue(index):
            status, result = invoke(
                self.app, "/auth/demo-token", "POST",
                {"instance_label": "parallel-%d" % index, "ttl_seconds": 600},
                "enroll-test-token",
            )
            self.assertEqual(status, "201 Created", result)
            return result
        with ThreadPoolExecutor(max_workers=12) as pool:
            issued = list(pool.map(issue, range(12)))
        points = [item["node_point"] for item in issued]
        self.assertEqual(sorted(points), list(range(9, 21)))
        self.assertEqual(len({item["instance_id"] for item in issued}), 12)

    def test_admin_inventory_reports_active_instances_without_tokens(self):
        first = self.issue_demo_instance()
        status, result = invoke(self.app, "/admin/instances", bearer="admin-test-token")
        self.assertEqual(status, "200 OK")
        self.assertEqual(result["active_count"], 1)
        self.assertEqual(result["available_count"], 246)
        self.assertEqual(result["instances"][0]["node_point"], first["node_point"])
        self.assertNotIn("token", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
