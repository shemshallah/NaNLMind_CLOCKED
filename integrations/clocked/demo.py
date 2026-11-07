#!/usr/bin/env python3
"""Run the Clocked-to-NaNLMind hackathon demo.

Live mode calls the authenticated Clocked gateway. Fixture mode is explicitly
simulated and exists only for offline/CI verification. Only Clocked labels that
match the sample's independent gold label are admitted to native training.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

LABELS = {
    "technical_document", "code_or_script", "support_request",
    "general_prose", "structured_record", "unknown",
}
ANCHORS = {
    "technical_document": {"technical", "architecture", "specification", "protocol", "design", "documentation"},
    "code_or_script": {"python", "code", "script", "compiler", "function", "debug"},
    "support_request": {"support", "customer", "login", "password", "account", "reset"},
    "general_prose": {"meeting", "notes", "prose", "story", "report", "paragraph"},
    "structured_record": {"invoice", "receipt", "amount", "total", "payment", "due"},
}


def load_samples(path: Path) -> list[dict]:
    samples = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError("sample line %d must be an object" % number)
        if item.get("split") not in ("train", "test"):
            raise ValueError("sample line %d has invalid split" % number)
        if item.get("expected_task_family") not in LABELS:
            raise ValueError("sample line %d has invalid expected_task_family" % number)
        text = item.get("text")
        if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 4096:
            raise ValueError("sample line %d has invalid text" % number)
        if any(ch in text for ch in "\t\r\n"):
            raise ValueError("sample line %d must be a single TSV-safe line" % number)
        samples.append(item)
    if not samples or not any(x["split"] == "train" for x in samples) or not any(x["split"] == "test" for x in samples):
        raise ValueError("demo requires both train and held-out test samples")
    ids = [x.get("id") for x in samples]
    if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("sample IDs must be unique non-empty strings")
    return samples


def fixture_classify(text: str) -> str:
    """Deterministic stand-in for Clocked; never presented as a live result."""
    tokens = set("".join(c.lower() if c.isalnum() else " " for c in text).split())
    scores = {label: len(tokens & words) for label, words in ANCHORS.items()}
    best = max(scores, key=lambda label: (scores[label], -list(ANCHORS).index(label)))
    return best if scores[best] else "unknown"


def live_classify(sample: dict, endpoint: str, token: str) -> tuple[str, dict]:
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("CLOCKED_INTAKE_URL must be an HTTPS URL")
    payload = json.dumps({
        "protocol": "nanlm.clocked-experience",
        "text": sample["text"],
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request_id = hashlib.sha256(
        (sample["id"] + "\\0" + hashlib.sha256(payload).hexdigest()).encode()
    ).hexdigest()
    request = Request(endpoint, data=payload, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Idempotency-Key": request_id,
    }, method="POST")
    with urlopen(request, timeout=90) as response:
        raw = response.read(1_048_577)
    if len(raw) > 1_048_576:
        raise RuntimeError("CLOCKED gateway response exceeds 1 MiB")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("CLOCKED gateway returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("CLOCKED gateway response must be a JSON object")
    event = result.get("event")
    if not isinstance(event, dict) or event.get("schema") != "nanlm.clocked-experience":
        raise RuntimeError("gateway returned an invalid Clocked event")
    event_id = event.get("event_id")
    if (not isinstance(event_id, str) or len(event_id) != 64
            or any(ch not in "0123456789abcdef" for ch in event_id)):
        raise RuntimeError("gateway returned an invalid Clocked event ID")
    labels = event.get("task_labels")
    label = labels.get("task_family") if isinstance(labels, dict) else None
    if label not in LABELS:
        raise RuntimeError("Clocked did not return an allowed task_family label")
    return label, event


def run_demo(samples: list[dict], mode: str, native_binary: Path,
             output_dir: Path) -> dict:
    if mode == "live":
        endpoint = os.environ.get("CLOCKED_INTAKE_URL", "").strip()
        token = os.environ.get("CLOCKED_USER_API", "").strip()
        if not endpoint or not token:
            raise ValueError("live mode requires CLOCKED_INTAKE_URL and CLOCKED_USER_API")
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "clocked-events.jsonl"
    train_rows = []
    test_rows = []
    records = []
    verified_train = 0
    skipped_train = 0
    clocked_correct = 0

    with events_path.open("w", encoding="utf-8") as events_file:
        for sample in samples:
            if sample["split"] == "test":
                # Keep held-out data isolated: it is never sent to Clocked.
                test_rows.append("test\t%s\t%s" % (
                    sample["expected_task_family"], sample["text"]
                ))
                records.append({
                    "sample_id": sample["id"], "split": "test",
                    "expected": sample["expected_task_family"],
                    "clocked": None, "matched": None,
                })
                events_file.write(json.dumps({
                    "sample_id": sample["id"], "split": "test",
                    "expected_task_family": sample["expected_task_family"],
                    "clocked_task_family": None, "matched_gold": None,
                    "event_id": None, "source_schema": None,
                    "learning_state": "heldout_never_sent_to_clocked",
                }, sort_keys=True) + "\n")
                continue

            if mode == "fixture":
                label = fixture_classify(sample["text"])
                event = {
                    "schema": "nanlm.clocked-experience-fixture",
                    "event_id": hashlib.sha256((sample["id"] + "\0" + label).encode()).hexdigest(),
                    "task_labels": {"task_family": label},
                    "raw_text_persisted": False,
                }
            else:
                label, event = live_classify(sample, endpoint, token)
            matched = label == sample["expected_task_family"]
            clocked_correct += int(matched)
            records.append({
                "sample_id": sample["id"], "split": "train",
                "expected": sample["expected_task_family"], "clocked": label,
                "matched": matched,
            })
            events_file.write(json.dumps({
                "sample_id": sample["id"], "split": "train",
                "expected_task_family": sample["expected_task_family"],
                "clocked_task_family": label, "matched_gold": matched,
                "event_id": event.get("event_id"),
                "source_schema": event.get("schema"),
                "learning_state": "verified_for_demo" if matched
                                  else "evidence_only_mismatch",
            }, sort_keys=True) + "\n")
            if matched:
                train_rows.append("train\t%s\t%s" % (label, sample["text"]))
                verified_train += 1
            else:
                skipped_train += 1

    if not train_rows:
        raise RuntimeError("Clocked produced no independently verified training samples")
    if not test_rows:
        raise RuntimeError("no held-out samples")

    # The raw sample text is written only to a short-lived file for the native
    # process, then removed. The durable event artifact contains no source text.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                     dir=output_dir, suffix=".tsv", delete=False) as tmp:
        sample_path = Path(tmp.name)
        tmp.write("\n".join(train_rows + test_rows) + "\n")
    try:
        completed = subprocess.run(
            [str(native_binary), str(sample_path)],
            check=False, capture_output=True, text=True, timeout=60,
        )
        if completed.returncode != 0:
            raise RuntimeError("native demo failed (exit %d): %s" % (
                completed.returncode, completed.stderr[-500:]
            ))
        native_metrics = json.loads(completed.stdout)
    finally:
        sample_path.unlink(missing_ok=True)

    return {
        "demo": "clocked-to-nanlmind-native-routing",
        "mode": mode,
        "clocked_samples": len(train_rows) + skipped_train,
        "clocked_label_accuracy": clocked_correct / (len(train_rows) + skipped_train),
        "verified_training_examples": verified_train,
        "skipped_training_examples": skipped_train,
        "heldout_examples": len(test_rows),
        "native": native_metrics,
        "event_log": str(events_path),
        "source_text_persisted_in_event_log": False,
        "sample_results": records,
        "interpretation": (
            "fixture mode uses a deterministic local stand-in and makes no live Clocked API calls"
            if mode == "fixture" else
            "live mode used Clocked through the authenticated gateway; only gold-matched training labels entered the native learner"
        ),
    }


def main(argv=None) -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path,
                        default=Path(__file__).with_name("demo_samples.jsonl"))
    configured_binary = os.environ.get("NANLM_CLOCKED_NATIVE_DEMO", "").strip()
    parser.add_argument("--native-binary", type=Path,
                        default=Path(configured_binary) if configured_binary else None,
                        help="NaNLMind native demo binary built in the NaNLMind repository")
    parser.add_argument("--output-dir", type=Path, default=root / "build" / "clocked-demo-run")
    parser.add_argument("--fixture", action="store_true",
                        help="run offline with a clearly labelled deterministic Clocked stand-in")
    args = parser.parse_args(argv)
    try:
        samples = load_samples(args.samples)
        if args.native_binary is None:
            raise ValueError("provide --native-binary or NANLM_CLOCKED_NATIVE_DEMO; build it in NaNLMind with make build/clocked-demo")
        if not args.native_binary.is_file():
            raise ValueError("NaNLMind native demo binary does not exist: %s" % args.native_binary)
        mode = "fixture" if args.fixture else "live"
        result = run_demo(samples, mode, args.native_binary, args.output_dir)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, HTTPError, URLError,
            json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print("Clocked demo failed: %s" % str(exc)[:500], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
