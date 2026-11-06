import unittest

from clocked_experience import digest, make_event, summarize_step


class ClockedExperienceTests(unittest.TestCase):
    def test_digest_is_deterministic(self):
        self.assertEqual(digest({"b": 2, "a": 1}), digest({"a": 1, "b": 2}))

    def test_step_summary_does_not_persist_extracted_values(self):
        summary = summarize_step({
            "endpoint": "extract",
            "status": 200,
            "result": {"fields": {"email": "secret@example.test", "amount": "$42"}},
        })
        self.assertEqual(summary["extracted_field_names"], ["amount", "email"])
        self.assertNotIn("secret@example.test", repr(summary))
        self.assertNotIn("$42", repr(summary))

    def test_decision_output_is_allowlisted(self):
        summary = summarize_step({
            "endpoint": "decide",
            "result": {"answers": {
                "task_family": "technical_document",
                "contains_claims": True,
                "freeform_echo": "private text must not persist",
                "unexpected": "untrusted model output",
            }},
        })
        self.assertEqual(summary["decisions"], {
            "task_family": "technical_document", "contains_claims": True
        })
        self.assertNotIn("private text", repr(summary))
        self.assertNotIn("untrusted model output", repr(summary))

    def test_event_is_explicitly_not_native_training_commit(self):
        event = make_event("hello", {"steps": []}, object())
        self.assertEqual(event["learning_state"], "awaiting_nanlmind_ingest")
        self.assertFalse(event["raw_text_persisted"])
        self.assertFalse(event["raw_response_persisted"])
        self.assertNotIn("hello", repr(event))


if __name__ == "__main__":
    unittest.main()
