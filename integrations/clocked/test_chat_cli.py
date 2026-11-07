import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chat_cli import ChatModel, Gateway, Session, Scratch, digest


class FakeGateway:
    def __init__(self):
        self.calls = []

    def health(self):
        self.calls.append(("health", None))
        return {"status": "ok"}

    def experience(self, text):
        self.calls.append(("experience", text))
        return {"event": {"event_id": "a" * 64, "learning_state": "awaiting_nanlmind_ingest"}}

    def tasks(self, plan, idempotency_key=None):
        self.calls.append(("tasks", plan, idempotency_key))
        return {"protocol": "nanlm.clocked-task-results",
                "results": [{"endpoint": "extract", "status": 200,
                             "result": {"fields": {"claims": ["x"]}}}]}

    def observations(self, payload):
        self.calls.append(("observations", payload))
        return {"accepted": True}

    def poll_observations(self):
        self.calls.append(("poll", None))
        return {"events": []}

    def ack_observations(self, payload):
        self.calls.append(("ack", payload))
        return {"complete": True}


class FakeModel:
    def complete(self, messages, max_tokens=1024):
        return "answer:" + str(len(messages))


class ChatCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.scratch = Scratch(self.tmp.name, "test")
        self.gateway = FakeGateway()
        self.session = Session(self.gateway, FakeModel(), self.scratch)
        self.addCleanup(self.tmp.cleanup)

    def test_chat_and_scratch_are_append_only(self):
        self.assertEqual(self.session.chat("hello"), "answer:2")
        snapshot = self.session.show()
        self.assertEqual(snapshot["entry_count"], 2)
        self.assertEqual(snapshot["entries"][0]["lane"], "user")
        self.assertTrue(snapshot["revision"])

    def test_source_plan_approval_and_run(self):
        self.session.source("doc", "source text")
        plan = self.session.plan("Summarize this")
        self.assertEqual(self.session.pending_digest, digest(plan))
        self.session.approve(self.session.pending_digest)
        result = self.session.run()
        self.assertEqual(result["protocol"], "nanlm.clocked-task-results")
        self.assertEqual(self.gateway.calls[-1][0], "tasks")
        self.assertEqual(self.gateway.calls[-1][2], plan["plan_id"])
        self.assertTrue(any(row["lane"] == "approval" for row in self.session.show()["entries"]))

    def test_run_requires_exact_approval(self):
        self.session.source("doc", "source text")
        self.session.plan("Summarize this")
        with self.assertRaises(PermissionError):
            self.session.run()
        with self.assertRaises(ValueError):
            self.session.approve("0" * 64)

    def test_endpoint_covers_arbitrary_supported_endpoint(self):
        self.session.endpoint("rerank", "select the best passage")
        self.assertEqual(self.gateway.calls[-1][0], "tasks")
        self.assertEqual(self.gateway.calls[-1][1]["tasks"][0]["endpoint"], "rerank")

    def test_experience_records_api_output(self):
        result = self.session.experience("hello")
        self.assertEqual(result["event"]["learning_state"], "awaiting_nanlmind_ingest")
        self.assertTrue(any(row["lane"] == "api_result" for row in self.session.show()["entries"]))

    def test_paste_buffer_can_be_reused_as_source(self):
        self.session.paste("raw", ["line one", "line two"])
        self.session.source("doc", "@raw")
        self.assertIn("line one", self.session.sources["doc"])
        self.session.experience("@doc")
        self.assertEqual(self.gateway.calls[-1][1], "line one\nline two")

    def test_invalid_source_reference_is_rejected(self):
        with self.assertRaises(ValueError):
            self.session.source("doc", "@missing")

    def test_gateway_requires_https_except_localhost(self):
        with self.assertRaises(ValueError):
            Gateway("http://example.test", "x" * 32)
        Gateway("http://127.0.0.1:8787", "x" * 32)


if __name__ == "__main__":
    unittest.main()
