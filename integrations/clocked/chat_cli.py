#!/usr/bin/env python3
"""Independent CLOCKED chat CLI.

This is a participant tool, not the service. It talks to the scoped CLOCKED
gateway, keeps a revisioned local scratch, and uses an OpenAI-compatible model
for the conversational loop. Raw API responses can be pasted into the scratch
and then referenced from later prompts or task plans.

It never reads or prints the upstream CLOCKED_API_KEY. The participant token is
read from CLOCKED_GATEWAY_TOKEN or --token.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ENDPOINTS = (
    "decide", "extract", "fill", "pii", "injection", "script",
    "grounding", "compare", "rerank", "pipeline",
)
MAX_TEXT = 64 * 1024
MAX_RESPONSE = 4 * 1024 * 1024
SCRATCH_LANES = {
    "user", "assistant", "prompt_buffer", "source", "api_request",
    "api_result", "plan", "approval", "final",
}
ZERO = "0" * 64


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class GatewayError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Scratch:
    """Durable, hash-chained local CLI scratch."""

    def __init__(self, root: str | Path, scratch_id: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", scratch_id or ""):
            raise ValueError("invalid scratch id")
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / (scratch_id + ".jsonl")
        self.lock = self.root / (scratch_id + ".lock")

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        result, previous = [], ZERO
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("corrupt scratch at line %d" % number) from exc
            claimed = row.pop("revision", None)
            if row.get("parent_revision") != previous or digest(row) != claimed:
                raise ValueError("scratch hash chain mismatch at line %d" % number)
            row["revision"] = claimed
            result.append(row)
            previous = claimed
        return result

    def snapshot(self) -> dict:
        rows = self.rows()
        return {"scratch_id": self.path.stem,
                "revision": rows[-1]["revision"] if rows else ZERO,
                "entries": rows, "entry_count": len(rows)}

    def append(self, lane: str, writer: str, payload) -> dict:
        if lane not in SCRATCH_LANES:
            raise ValueError("unknown scratch lane")
        raw = canonical(payload)
        if len(raw) > 1_048_576:
            raise ValueError("scratch payload exceeds 1 MiB")
        lock_fd = os.open(self.lock, os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(lock_fd, "a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            rows = self.rows()
            parent = rows[-1]["revision"] if rows else ZERO
            row = {
                "schema": "nanlm.clocked-chat-entry/1",
                "scratch_id": self.path.stem,
                "entry_id": uuid.uuid4().hex,
                "sequence": len(rows) + 1,
                "lane": lane, "writer": writer,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "parent_revision": parent, "payload": payload,
            }
            row["revision"] = digest(row)
            fd = os.open(self.path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                stream.write(canonical(row).decode("utf-8") + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return row


class Gateway:
    """Small participant client for all CLOCKED gateway routes."""

    def __init__(self, base_url: str, token: str, timeout: int = 90,
                 runner_token: str = "", admin_token: str = ""):
        parsed = urlparse(base_url)
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ValueError("CLOCKED_GATEWAY_URL must be an HTTP(S) URL")
        if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("HTTPS is required except on localhost")
        if not token or len(token) > 512:
            raise ValueError("CLOCKED_GATEWAY_TOKEN is missing or invalid")
        if not 1 <= timeout <= 300:
            raise ValueError("timeout out of range")
        self.base = base_url.rstrip("/")
        self.token = token
        self.runner_token = runner_token
        self.admin_token = admin_token
        self.timeout = timeout

    def _request(self, method: str, path: str, body=None, headers=None,
                 credential: str | None = None) -> dict:
        data = None if body is None else json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        request_headers = {
            "Authorization": "Bearer " + (credential or self.token),
            "Accept": "application/json",
        }
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        request = Request(self.base + path, data=data, headers=request_headers,
                          method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise GatewayError("CLOCKED response exceeds 4 MiB")
                return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            raise GatewayError("CLOCKED gateway returned HTTP %d" % exc.code, exc.code) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise GatewayError("CLOCKED gateway transport failure") from exc
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise GatewayError("CLOCKED gateway returned invalid JSON") from exc

    def health(self):
        return self._request("GET", "/healthz")

    def experience(self, text: str):
        return self._request("POST", "/v1/experience",
                             {"protocol": "nanlm.clocked-experience", "text": text})

    def tasks(self, plan: dict, idempotency_key: str | None = None):
        key = idempotency_key or plan.get("plan_id") or uuid.uuid4().hex
        return self._request("POST", "/v1/tasks",
                             {"protocol": "nanlm.clocked-task-plan",
                              "version": 1, "plan": plan},
                             {"Idempotency-Key": key})

    def observations(self, payload: dict):
        return self._request("POST", "/v1/observations", payload)

    def poll_observations(self):
        return self._request("GET", "/internal/observations",
                             credential=self.runner_token or self.token)

    def ack_observations(self, payload: dict):
        return self._request("POST", "/internal/observations/ack", payload,
                             credential=self.runner_token or self.token)

    def issue_token(self, payload: dict):
        return self._request("POST", "/admin/tokens", payload,
                             credential=self.admin_token)


class ChatModel:
    def __init__(self, base_url: str = "", model: str = "", token: str = ""):
        self.base = base_url.rstrip("/")
        self.model = model
        self.token = token

    @property
    def configured(self) -> bool:
        return bool(self.base and self.model)

    def complete(self, messages: list[dict], max_tokens: int = 1024) -> str:
        if not self.configured:
            return ("No chat model is configured. Set NANLM_MODEL_URL and "
                    "NANLM_MODEL, or use /health, /experience, /plan and /run.")
        body = json.dumps({"model": self.model, "messages": messages,
                           "temperature": 0.2, "max_tokens": max_tokens}).encode()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = Request(self.base + "/chat/completions", data=body,
                          headers=headers, method="POST")
        try:
            with urlopen(request, timeout=180) as response:
                payload = json.load(response)
            return payload["choices"][0]["message"]["content"]
        except (HTTPError, URLError, OSError, KeyError, IndexError,
                TypeError, json.JSONDecodeError) as exc:
            return "Chat provider unavailable (%s)." % type(exc).__name__


class Session:
    def __init__(self, gateway: Gateway | None, model: ChatModel, scratch: Scratch,
                 admin_token: str = ""):
        self.gateway = gateway
        self.model = model
        self.scratch = scratch
        self.admin_token = admin_token
        self.sources: dict[str, str] = {}
        self.pending_plan: dict | None = None
        self.pending_digest = ""

    # ----- shared helpers -------------------------------------------------
    def _require_gateway(self) -> Gateway:
        if self.gateway is None:
            raise GatewayError("CLOCKED gateway is not configured")
        return self.gateway

    def _buffer(self, label: str, text: str) -> dict:
        if not text.strip():
            raise ValueError("buffer is empty")
        entry = self.scratch.append("prompt_buffer", "user",
                                    {"label": label, "text": text})
        print("buffer %s -> %s" % (label, entry["revision"][:16]))
        return entry

    def _resolve(self, value: str) -> str:
        """Resolve @buffer, @source, or a literal string."""
        if not value.startswith("@"):
            return value
        name = value[1:]
        if name in self.sources:
            return self.sources[name]
        rows = [row for row in self.scratch.rows()
                if row["lane"] == "prompt_buffer"
                and row["payload"].get("label") == name]
        if not rows:
            raise ValueError("unknown buffer or source: " + name)
        return rows[-1]["payload"]["text"]

    def _record(self, lane: str, writer: str, payload) -> dict:
        return self.scratch.append(lane, writer, payload)

    # ----- commands ------------------------------------------------------
    def chat(self, text: str) -> str:
        if not text.strip():
            return ""
        self._record("user", "user", {"text": text})
        context = [
            {"lane": row["lane"], "payload": row["payload"]}
            for row in self.scratch.rows()
            if row["lane"] in {"user", "assistant", "source", "api_result",
                               "plan", "final", "prompt_buffer"}
        ][-24:]
        messages = [
            {"role": "system", "content": (
                "You are the CLOCKED chat interface. Use the supplied scratch as "
                "evidence. CLOCKED observations are not ground truth. Preserve "
                "uncertainty and ask before executing a plan that transmits sources."
            )},
            {"role": "user", "content": json.dumps(
                {"message": text, "scratch": context},
                ensure_ascii=False, sort_keys=True)},
        ]
        answer = self.model.complete(messages, 1200)
        self._record("assistant", "assistant", {"text": answer})
        return answer

    def paste(self, label: str, lines: list[str]) -> dict:
        return self._buffer(label, "\n".join(lines))

    def use(self, value: str) -> dict:
        text = self._resolve(value)
        entry = self._record("prompt_buffer", "user",
                             {"label": "active-prompt", "text": text})
        print("active prompt set (%d bytes) %s" % (len(text), entry["revision"][:16]))
        return entry

    def source(self, label: str, value: str) -> dict:
        text = self._resolve(value)
        if not text.strip():
            raise ValueError("source is empty")
        if len(text.encode("utf-8")) > MAX_TEXT:
            raise ValueError("source exceeds 64 KiB")
        self.sources[label] = text
        entry = self._record("source", "user",
                             {"label": label, "text": text,
                              "sha256": hashlib.sha256(text.encode()).hexdigest()})
        print("source %s stored (%d bytes)" % (label, len(text)))
        return entry

    def plan(self, question: str, endpoints: list[str] | None = None) -> dict:
        if not self.sources:
            raise ValueError("add at least one /source before planning")
        selected = endpoints or ["extract", "grounding", "decide"]
        if any(endpoint not in ENDPOINTS for endpoint in selected):
            raise ValueError("plan contains an unsupported endpoint")
        tasks, previous = [], []
        for source_id, text in self.sources.items():
            for endpoint in selected:
                if endpoint == "decide":
                    continue
                task_id = endpoint + "-" + source_id
                options = {}
                if endpoint == "grounding":
                    extract_id = "extract-" + source_id
                    if extract_id in previous:
                        options = {"claims_from": extract_id}
                tasks.append({"id": task_id, "source_id": source_id,
                              "endpoint": endpoint, "text": text,
                              "options": options, "depends_on": previous[:]})
                previous.append(task_id)
        tasks.append({"id": "decide", "endpoint": "decide",
                      "text": question + "\n\n" + "\n\n".join(self.sources.values()),
                      "depends_on": previous[:]})
        plan = {"schema": "nanlm.clocked-task-plan/1", "version": 1,
                "plan_id": uuid.uuid4().hex, "tasks": tasks}
        self.pending_plan = plan
        self.pending_digest = digest(plan)
        self._record("plan", "user", {
            "question": question, "plan": plan, "plan_sha256": self.pending_digest,
            "requires_approval": True,
        })
        print(json.dumps({"plan": plan, "plan_sha256": self.pending_digest},
                         indent=2, ensure_ascii=False))
        return plan

    def endpoint(self, endpoint: str, text: str, options: dict | None = None) -> dict:
        if endpoint not in ENDPOINTS:
            raise ValueError("unsupported endpoint; choose: " + ", ".join(ENDPOINTS))
        plan = {"schema": "nanlm.clocked-task-plan/1", "version": 1,
                "plan_id": uuid.uuid4().hex,
                "tasks": [{"id": "task-1", "endpoint": endpoint,
                           "text": text, "depends_on": [],
                           "options": options or {}}]}
        self._record("plan", "user", {"plan": plan,
                                      "plan_sha256": digest(plan),
                                      "requires_approval": False})
        result = self._require_gateway().tasks(plan)
        self._record("api_result", "clocked",
                     {"route": "/v1/tasks", "plan_sha256": digest(plan),
                      "response": result})
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return result

    def approve(self, digest_value: str) -> dict:
        if self.pending_plan is None:
            raise ValueError("no pending plan")
        if digest_value != self.pending_digest:
            raise ValueError("approval digest does not match the pending plan")
        self._record("approval", "user",
                     {"plan_sha256": digest_value, "approved": True})
        print("approved", digest_value)
        return {"approved": True, "plan_sha256": digest_value}

    def run(self) -> dict:
        if self.pending_plan is None:
            raise ValueError("no pending plan; run /plan first")
        approvals = [row for row in self.scratch.rows()
                     if row["lane"] == "approval"
                     and row["payload"].get("plan_sha256") == self.pending_digest
                     and row["payload"].get("approved") is True]
        if not approvals:
            raise PermissionError("run /approve %s first" % self.pending_digest)
        result = self._require_gateway().tasks(
            self.pending_plan, self.pending_plan["plan_id"])
        self._record("api_result", "clocked", {
            "route": "/v1/tasks", "plan_sha256": self.pending_digest,
            "response": result,
        })
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return result

    def experience(self, value: str) -> dict:
        text = self._resolve(value)
        result = self._require_gateway().experience(text)
        self._record("api_request", "user", {"route": "/v1/experience",
                                             "text_sha256": hashlib.sha256(text.encode()).hexdigest()})
        self._record("api_result", "clocked", {"route": "/v1/experience",
                                               "response": result})
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return result

    def issue_token(self, payload: dict) -> dict:
        result = self._require_gateway().issue_token(payload)
        self._record("api_result", "clocked", {"route": "/admin/tokens",
                                               "response": result})
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return result

    def observations(self, payload: dict) -> dict:
        result = self._require_gateway().observations(payload)
        self._record("api_result", "clocked", {"route": "/v1/observations",
                                               "response": result})
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return result

    def poll(self) -> dict:
        result = self._require_gateway().poll_observations()
        self._record("api_result", "clocked", {"route": "/internal/observations",
                                               "response": result})
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return result

    def ack(self, payload: dict) -> dict:
        result = self._require_gateway().ack_observations(payload)
        self._record("api_result", "clocked", {"route": "/internal/observations/ack",
                                               "response": result})
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        return result

    def show(self, lane: str | None = None) -> dict:
        snapshot = self.scratch.snapshot()
        if lane is None:
            return snapshot
        return {"lane": lane, "entries": self.scratch.rows()
                and [r for r in self.scratch.rows() if r["lane"] == lane] or []}

    def copy(self, lane: str | None = None) -> str:
        value = json.dumps(self.show(lane), indent=2, ensure_ascii=False,
                           sort_keys=True)
        print(value)
        return value


HELP = """\
Commands:
  /health                     GET /healthz
  /paste LABEL                read a multiline paste ending with ::end
  /source LABEL @BUFFER       save a paste as a named source
  /use @BUFFER                set the active prompt buffer
  /plan QUESTION [endpoints]  build a reviewable task plan from named sources
  /approve DIGEST             approve the exact pending plan
  /run                        execute the approved plan
  /endpoint NAME TEXT         execute one endpoint: decide, extract, fill, pii,
                              injection, script, grounding, compare, rerank, pipeline
  /experience TEXT|@BUFFER    legacy /v1/experience endpoint
  /tasks JSON                 execute a raw task plan (JSON or @paste)
  /observations JSON          POST /v1/observations
  /poll                       GET /internal/observations (runner token required)
  /ack JSON                   POST /internal/observations/ack
  /token JSON                 POST /admin/tokens (admin token required)
  /show [LANE]                print scratch
  /copy [LANE]                print scratch for copy/paste
  /quit
Plain text is a chat turn. API output is retained in scratch and can be reused
with @buffer/@source references. Nothing is transmitted until an explicit command.
"""


def _json_arg(value: str, session: Session):
    text = session._resolve(value)
    return json.loads(text)


def repl(session: Session) -> int:
    print(HELP)
    while True:
        try:
            line = input("clocked> ")
        except EOFError:
            print()
            return 0
        line = line.strip()
        if not line:
            continue
        if line in ("/quit", "/exit"):
            return 0
        try:
            if not line.startswith("/"):
                print(session.chat(line))
                continue
            command, _, rest = line.partition(" ")
            if command == "/help":
                print(HELP)
            elif command == "/health":
                print(json.dumps(session._require_gateway().health(),
                                 indent=2, sort_keys=True))
            elif command == "/paste":
                label = rest.strip() or "paste"
                print("paste multiline text; finish with ::end")
                lines = []
                while True:
                    row = input()
                    if row == "::end":
                        break
                    lines.append(row)
                session.paste(label, lines)
            elif command == "/source":
                label, _, value = rest.partition(" ")
                if not label or not value:
                    raise ValueError("usage: /source LABEL @BUFFER")
                session.source(label, value.strip())
            elif command == "/use":
                session.use(rest.strip())
            elif command == "/plan":
                question, separator, tail = rest.partition("|")
                endpoints = ([item.strip() for item in tail.split(",") if item.strip()]
                             if separator else None)
                session.plan(question.strip() or "Summarize the sources",
                             endpoints)
            elif command == "/approve":
                session.approve(rest.strip())
            elif command == "/run":
                session.run()
            elif command == "/endpoint":
                endpoint, _, text = rest.partition(" ")
                if not endpoint or not text:
                    raise ValueError("usage: /endpoint NAME TEXT")
                session.endpoint(endpoint, session._resolve(text))
            elif command == "/experience":
                session.experience(rest.strip())
            elif command == "/tasks":
                plan = _json_arg(rest.strip(), session)
                result = session._require_gateway().tasks(plan)
                session._record("api_result", "clocked",
                                {"route": "/v1/tasks", "response": result})
                print(json.dumps(result, indent=2, sort_keys=True))
            elif command == "/observations":
                session.observations(_json_arg(rest.strip(), session))
            elif command == "/poll":
                session.poll()
            elif command == "/ack":
                session.ack(_json_arg(rest.strip(), session))
            elif command == "/token":
                session.issue_token(_json_arg(rest.strip(), session))
            elif command == "/show":
                print(json.dumps(session.show(rest.strip() or None),
                                 indent=2, ensure_ascii=False, sort_keys=True))
            elif command == "/copy":
                session.copy(rest.strip() or None)
            else:
                print("unknown command; /help")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        except Exception as exc:
            print("error: %s" % str(exc)[:500], file=sys.stderr)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-url", default=os.environ.get("CLOCKED_GATEWAY_URL", ""))
    parser.add_argument("--token", default=os.environ.get("CLOCKED_GATEWAY_TOKEN", ""))
    parser.add_argument("--model-url", default=os.environ.get("NANLM_MODEL_URL", ""))
    parser.add_argument("--model", default=os.environ.get("NANLM_MODEL", ""))
    parser.add_argument("--model-token", default=os.environ.get("NANLM_MODEL_TOKEN", ""))
    parser.add_argument("--scratch-dir", default=os.environ.get(
        "CLOCKED_CHAT_SCRATCH", "~/.local/share/nanlmind-clocked/scratch"))
    parser.add_argument("--scratch-id", default="default")
    parser.add_argument("--runner-token", default=os.environ.get(
        "NANLM_RUNNER_INGEST_TOKEN", ""))
    parser.add_argument("--admin-token", default=os.environ.get(
        "CLOCKED_GATEWAY_ADMIN_TOKEN", ""))
    args = parser.parse_args(argv)
    gateway = None
    if args.gateway_url and args.token:
        gateway = Gateway(args.gateway_url, args.token,
                          runner_token=args.runner_token,
                          admin_token=args.admin_token)
    elif args.gateway_url or args.token:
        parser.error("--gateway-url and --token must be provided together")
    session = Session(gateway, ChatModel(args.model_url, args.model, args.model_token),
                      Scratch(args.scratch_dir, args.scratch_id), args.admin_token)
    return repl(session)


if __name__ == "__main__":
    raise SystemExit(main())
