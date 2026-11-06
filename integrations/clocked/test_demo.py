import json
import os
import unittest
from unittest.mock import patch
from pathlib import Path

from demo import fixture_classify, load_samples, run_demo


class ClockedDemoTests(unittest.TestCase):
    def test_fixture_labels_cover_all_six_task_families(self):
        examples = {
            "technical_document": "technical architecture specification protocol",
            "code_or_script": "python code script compiler function",
            "support_request": "customer support login password reset",
            "general_prose": "meeting notes prose story report",
            "structured_record": "invoice receipt amount total due",
            "unknown": "weather forecast garden trail music",
        }
        for expected, text in examples.items():
            with self.subTest(expected=expected):
                self.assertEqual(fixture_classify(text), expected)

    def test_sample_curriculum_has_train_and_heldout_splits(self):
        path = Path(__file__).with_name("demo_samples.jsonl")
        samples = load_samples(path)
        self.assertEqual(len(samples), 60)
        self.assertEqual(sum(x["split"] == "train" for x in samples), 48)
        self.assertEqual(sum(x["split"] == "test" for x in samples), 12)


    def test_live_demo_calls_teacher_only_for_training_split(self):
        root = Path(__file__).resolve().parents[2]
        binary = root / "build" / "clocked-demo"
        if not binary.exists():
            self.skipTest("native demo binary is built by the CI workflow")
        samples = load_samples(Path(__file__).with_name("demo_samples.jsonl"))
        calls = []
        def fake_live(sample, endpoint, token):
            calls.append(sample["id"])
            label = sample["expected_task_family"]
            return label, {
                "schema": "nanlm.clocked-experience",
                "event_id": sample["id"] * 64,
            }
        with patch.dict(os.environ, {
            "CLOCKED_INTAKE_URL": "https://gateway.example.test/v1/experience",
            "CLOCKED_USER_API": "scoped-test-token",
        }), patch("demo.live_classify", side_effect=fake_live):
            result = run_demo(samples, "live", binary, root / "build" / "clocked-demo-live-unit")
        self.assertEqual(len(calls), 48)
        self.assertEqual(result["clocked_samples"], 48)
        self.assertEqual(result["heldout_examples"], 12)
        self.assertEqual(result["verified_training_examples"], 48)

    def test_fixture_demo_runs_native_learning_and_heldout_replay(self):
        root = Path(__file__).resolve().parents[2]
        binary = root / "build" / "clocked-demo"
        if not binary.exists():
            self.skipTest("native demo binary is built by the CI workflow")
        samples = load_samples(Path(__file__).with_name("demo_samples.jsonl"))
        output = root / "build" / "clocked-demo-unit"
        result = run_demo(samples, "fixture", binary, output)
        self.assertEqual(result["clocked_label_accuracy"], 1.0)
        self.assertEqual(result["verified_training_examples"], 48)
        self.assertEqual(result["native"]["baseline_accuracy"], 0.0)
        self.assertEqual(result["native"]["heldout_accuracy"], 1.0)
        self.assertEqual(result["native"]["clocked_verified_events"], 48)
        self.assertGreater(result["native"]["nonzero_routing_biases"], 0)
        self.assertFalse(result["source_text_persisted_in_event_log"])
        encoded = (output / "clocked-events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("technical architecture specification protocol", encoded)
        event_rows = [json.loads(line) for line in encoded.splitlines()]
        heldout = [row for row in event_rows if row["split"] == "test"]
        self.assertEqual(len(heldout), 12)
        self.assertTrue(all(row["event_id"] is None for row in heldout))
        self.assertTrue(all(row["learning_state"] == "heldout_never_sent_to_clocked"
                            for row in heldout))
        self.assertEqual(result["clocked_samples"], 48)


if __name__ == "__main__":
    unittest.main()
