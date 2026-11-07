"""Offline tests for the CLOCKED -> native NaNLMind demo harness."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "integrations" / "clocked" / "demo.py"
SPEC = importlib.util.spec_from_file_location("clocked_demo", MODULE_PATH)
demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo)


class ClockedDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.samples = [
            {"id": "train-1", "split": "train",
             "expected_task_family": "technical_document",
             "text": "technical architecture specification"},
            {"id": "train-2", "split": "train",
             "expected_task_family": "code_or_script",
             "text": "python code compiler"},
            {"id": "test-1", "split": "test",
             "expected_task_family": "support_request",
             "text": "support account password reset"},
        ]
        self.sample_path = self.root / "samples.jsonl"
        self.sample_path.write_text(
            "".join(json.dumps(row) + "\n" for row in self.samples),
            encoding="utf-8",
        )
        self.binary = self.root / "fake-native-demo"
        self.binary.write_text(
            "#!/usr/bin/env python3\nimport sys\n"
            "import json, pathlib, sys\n"
            "rows = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').splitlines()\n"
            "print(json.dumps({'seen_rows': len(rows), 'native_ok': True}))\n",
            encoding="utf-8",
        )
        self.binary.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fixture_demo_keeps_test_rows_out_of_clocked_and_logs_no_source_text(self):
        samples = demo.load_samples(self.sample_path)
        result = demo.run_demo(samples, "fixture", self.binary, self.root / "out")
        self.assertEqual(result["verified_training_examples"], 2)
        self.assertEqual(result["heldout_examples"], 1)
        self.assertEqual(result["native"]["seen_rows"], 3)
        self.assertFalse(result["source_text_persisted_in_event_log"])
        event_log = Path(result["event_log"]).read_text(encoding="utf-8")
        self.assertNotIn("technical architecture specification", event_log)
        self.assertNotIn("support account password reset", event_log)
        heldout = [row for row in map(json.loads, event_log.splitlines())
                   if row["split"] == "test"]
        self.assertEqual(len(heldout), 1)
        self.assertEqual(heldout[0]["learning_state"], "heldout_never_sent_to_clocked")

    @patch.dict(os.environ, {
        "CLOCKED_INTAKE_URL": "https://clocked.example/v1/experience",
        "CLOCKED_USER_API": "scoped-test-token",
    })
    @patch.object(demo, "live_classify")
    def test_live_mode_calls_clocked_for_train_only(self, live_classify):
        live_classify.side_effect = [
            ("technical_document", {"event_id": "a" * 64,
                                    "schema": "nanlm.clocked-experience"}),
            ("code_or_script", {"event_id": "b" * 64,
                                "schema": "nanlm.clocked-experience"}),
        ]
        result = demo.run_demo(
            demo.load_samples(self.sample_path), "live", self.binary, self.root / "live-out"
        )
        self.assertEqual(live_classify.call_count, 2)
        self.assertEqual(result["heldout_examples"], 1)
        self.assertEqual(result["verified_training_examples"], 2)

    def test_rejects_duplicate_ids_and_missing_test_split(self):
        duplicate = [dict(self.samples[0]), dict(self.samples[1]), dict(self.samples[2])]
        duplicate[1]["id"] = duplicate[0]["id"]
        self.sample_path.write_text(
            "".join(json.dumps(row) + "\n" for row in duplicate), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "unique"):
            demo.load_samples(self.sample_path)
        no_test = [row for row in self.samples if row["split"] == "train"]
        self.sample_path.write_text(
            "".join(json.dumps(row) + "\n" for row in no_test), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "both train and held-out test"):
            demo.load_samples(self.sample_path)

    @patch.dict(os.environ, {
        "CLOCKED_INTAKE_URL": "https://clocked.example/v1/experience",
        "CLOCKED_USER_API": "scoped-test-token",
    })
    @patch.object(demo, "live_classify")
    def test_unmatched_teacher_labels_never_enter_native_training(self, live_classify):
        live_classify.return_value = (
            "unknown",
            {"event_id": "f" * 64, "schema": "nanlm.clocked-experience"},
        )
        with self.assertRaisesRegex(RuntimeError, "no independently verified"):
            demo.run_demo(
                demo.load_samples(self.sample_path), "live",
                self.binary, self.root / "mismatch-out",
            )
        self.assertEqual(live_classify.call_count, 2)
        self.assertFalse((self.root / "mismatch-out" / "samples.tsv").exists())

    def test_native_failure_cleans_up_temporary_source_tsv(self):
        self.binary.write_text(
            "#!/usr/bin/env python3\nimport sys\n"
            "print('native failure', file=sys.stderr)\nsys.exit(2)\n",
            encoding="utf-8",
        )
        self.binary.chmod(0o755)
        output = self.root / "native-failure"
        with self.assertRaisesRegex(RuntimeError, "native demo failed"):
            demo.run_demo(
                demo.load_samples(self.sample_path), "fixture", self.binary, output
            )
        leftovers = list(output.glob("*.tsv"))
        self.assertEqual(leftovers, [])
        self.assertTrue((output / "clocked-events.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
