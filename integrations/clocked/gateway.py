#!/usr/bin/env python3
"""Hardware-neutral Clocked and endpoint intake gateway.

The privileged Clocked credential stays server-side. Endpoint tokens are
scoped by a trusted endpoint identity assigned at issuance, never by request
body fields. Public endpoint observations are evidence-only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from typing import Any, Dict
from wsgiref.simple_server import make_server

from clocked_experience import build_pipeline, make_event

MAX_BODY = 64 * 1024
SCHEMA_VERSION = 1
SOURCE_ENDPOINT = "clocked_demo"
ENDPOINTS = {"my_android", "hermes_demo", "clocked_demo"}
EVENT_ID = re.compile(r"^[a-f0-9]{64}$")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def token_hash(token: str, pepper: str) -> str:
    return hashlib.sha256((pepper + token).encode("utf-8")).hexdigest()


def connect_db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS demo_tokens (
            token_hash TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            endpoint_id TEXT NOT NULL DEFAULT 'clocked_demo',
            expires_at INTEGER NOT NULL,
            max_requests INTEGER NOT NULL,
            used_requests INTEGER NOT NULL DEFAULT 0,
            revoked INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        )
    """)
    # Upgrade databases created by the first Clocked-only gateway.
    columns = {row["name"] for row in db.execute("PRAGMA table_info(demo_tokens)")}
    if "endpoint_id" not in columns:
        db.execute("ALTER TABLE demo_tokens ADD COLUMN endpoint_id TEXT NOT NULL DEFAULT 'clocked_demo'")
    db.execute("""
        CREATE TABLE IF NOT EXISTS experience_requests (
            token_hash TEXT NOT NULL,
            request_key TEXT NOT NULL,
            body_sha256 TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            response_status TEXT,
            response_json TEXT,
            created_at INTEGER NOT NULL,
            PRIMARY KEY(token_hash, request_key)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS endpoint_inbox (
            event_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            source_endpoint TEXT NOT NULL,
            base_generation INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            received_at INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            lease_id TEXT,
            lease_until INTEGER
        )
    """)
    inbox_columns = {row["name"] for row in db.execute("PRAGMA table_info(endpoint_inbox)")}
    if "lease_id" not in inbox_columns:
        db.execute("ALTER TABLE endpoint_inbox ADD COLUMN lease_id TEXT")
    if "lease_until" not in inbox_columns:
        db.execute("ALTER TABLE endpoint_inbox ADD COLUMN lease_until INTEGER")
    db.commit()
    return db


def json_response(start_response, status: str, payload: Dict[str, Any]):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    start_response(status, [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
    ])
    return [body]


class Gateway:
    def __init__(self, db_path: str, clocked_client=None):
        self.db_path = db_path
        self.clocked_client = clocked_client

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        if method == "GET" and path == "/healthz":
            return json_response(start_response, "200 OK", {
                "status": "ok", "protocol": "nanlm.endpoint-observation",
                "protocol_version": SCHEMA_VERSION, "source_endpoints": sorted(ENDPOINTS),
            })
        if method == "POST" and path == "/admin/tokens":
            return self.issue_token(environ, start_response)
        if method == "POST" and path == "/v1/experience":
            return self.run_experience(environ, start_response)
        if method == "POST" and path == "/v1/observations":
            return self.accept_observation(environ, start_response)
        if method == "GET" and path == "/internal/observations":
            return self.poll_observations(environ, start_response)
        if method == "POST" and path == "/internal/observations/ack":
            return self.ack_observations(environ, start_response)
        return json_response(start_response, "404 Not Found", {"error": "not_found"})

    def read_body(self, environ):
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            raise ValueError("invalid_content_length")
        if length <= 0 or length > MAX_BODY:
            raise ValueError("body_size_out_of_range")
        raw = environ["wsgi.input"].read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("invalid_json")
        if not isinstance(value, dict):
            raise ValueError("json_object_required")
        return value

    def admin_ok(self, environ):
        admin = os.environ.get("CLOCKED_GATEWAY_ADMIN_TOKEN", "")
        supplied = environ.get("HTTP_AUTHORIZATION", "")
        return bool(admin) and secrets.compare_digest(supplied, "Bearer " + admin)

    def runner_ok(self, environ):
        runner = os.environ.get("NANLM_RUNNER_INGEST_TOKEN", "")
        supplied = environ.get("HTTP_AUTHORIZATION", "")
        return bool(runner) and secrets.compare_digest(supplied, "Bearer " + runner)

    def issue_token(self, environ, start_response):
        pepper = os.environ.get("CLOCKED_TOKEN_PEPPER", "")
        if not pepper or not self.admin_ok(environ):
            return json_response(start_response, "401 Unauthorized", {"error": "unauthorized"})
        try:
            data = self.read_body(environ)
            tenant_id = str(data.get("tenant_id", "demo"))[:64]
            endpoint_id = str(data.get("endpoint_id", "clocked_demo"))
            max_requests = int(data.get("max_requests", 25))
            ttl_seconds = int(data.get("ttl_seconds", 21600))
            if not tenant_id or endpoint_id not in ENDPOINTS:
                raise ValueError("invalid_endpoint_policy")
            if not (1 <= max_requests <= 500) or not (60 <= ttl_seconds <= 86400):
                raise ValueError("token_policy_out_of_range")
        except (ValueError, TypeError) as exc:
            return json_response(start_response, "400 Bad Request", {"error": str(exc)[:64]})
        token = "clu_" + secrets.token_urlsafe(32)
        now = int(time.time())
        db = connect_db(self.db_path)
        try:
            db.execute(
                "INSERT INTO demo_tokens(token_hash,tenant_id,endpoint_id,expires_at,max_requests,created_at) VALUES(?,?,?,?,?,?)",
                (token_hash(token, pepper), tenant_id, endpoint_id, now + ttl_seconds, max_requests, now),
            )
            db.commit()
        finally:
            db.close()
        token_type = {"clocked_demo": "CLOCKED_USER_API",
                      "my_android": "NANLM_DEVICE_TOKEN",
                      "hermes_demo": "HERMES_DEMO_API"}[endpoint_id]
        return json_response(start_response, "201 Created", {
            "token_type": token_type, "token": token, "tenant_id": tenant_id,
            "source_endpoint": endpoint_id, "expires_at": now + ttl_seconds,
            "max_requests": max_requests,
        })

    def reserve_request(self, token: str):
        pepper = os.environ.get("CLOCKED_TOKEN_PEPPER", "")
        if not pepper:
            return None, "gateway_misconfigured"
        db = connect_db(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM demo_tokens WHERE token_hash=?",
                (token_hash(token, pepper),),
            ).fetchone()
            now = int(time.time())
            if row is None or row["revoked"] or row["expires_at"] <= now:
                db.rollback()
                return None, "unauthorized"
            if row["used_requests"] >= row["max_requests"]:
                db.rollback()
                return None, "quota_exceeded"
            db.execute("UPDATE demo_tokens SET used_requests=used_requests+1 WHERE token_hash=?",
                       (row["token_hash"],))
            db.commit()
            return {"tenant_id": row["tenant_id"], "endpoint_id": row["endpoint_id"],
                    "remaining": row["max_requests"] - row["used_requests"] - 1}, None
        finally:
            db.close()

    def authenticate(self, environ, start_response):
        auth = environ.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith("Bearer ") or len(auth) > 512:
            return json_response(start_response, "401 Unauthorized", {"error": "unauthorized"})
        identity, error = self.reserve_request(auth[7:])
        if error:
            status = "429 Too Many Requests" if error == "quota_exceeded" else (
                "503 Service Unavailable" if error == "gateway_misconfigured" else "401 Unauthorized")
            return json_response(start_response, status, {"error": error})
        return identity

    def reserve_experience(self, token: str, request_key: str, body_sha256: str):
        pepper = os.environ.get("CLOCKED_TOKEN_PEPPER", "")
        if not pepper:
            return None, None, "gateway_misconfigured", "503 Service Unavailable"
        if not token or len(token) > 512:
            return None, None, "unauthorized", "401 Unauthorized"
        digest = token_hash(token, pepper)
        db = connect_db(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM demo_tokens WHERE token_hash=?", (digest,)).fetchone()
            now = int(time.time())
            if row is None or row["revoked"] or row["expires_at"] <= now:
                db.rollback()
                return None, None, "unauthorized", "401 Unauthorized"
            if row["endpoint_id"] != "clocked_demo":
                db.rollback()
                return None, None, "endpoint_scope_mismatch", "403 Forbidden"
            if request_key:
                prior = db.execute(
                    "SELECT * FROM experience_requests WHERE token_hash=? AND request_key=?",
                    (digest, request_key),
                ).fetchone()
                if prior is not None:
                    if prior["body_sha256"] != body_sha256:
                        db.rollback()
                        return None, None, "idempotency_key_conflict", "409 Conflict"
                    if prior["state"] == "complete" and prior["response_json"]:
                        cached = json.loads(prior["response_json"])
                        status = prior["response_status"] or "200 OK"
                        db.rollback()
                        return None, (status, cached), None, None
                    db.rollback()
                    return None, None, "request_in_progress", "409 Conflict"
            if row["used_requests"] >= row["max_requests"]:
                db.rollback()
                return None, None, "quota_exceeded", "429 Too Many Requests"
            if request_key:
                db.execute(
                    "INSERT INTO experience_requests(token_hash,request_key,body_sha256,created_at) VALUES(?,?,?,?)",
                    (digest, request_key, body_sha256, now),
                )
            db.execute("UPDATE demo_tokens SET used_requests=used_requests+1 WHERE token_hash=?", (digest,))
            db.commit()
            return {
                "tenant_id": row["tenant_id"],
                "endpoint_id": row["endpoint_id"],
                "remaining": row["max_requests"] - row["used_requests"] - 1,
                "token_hash": digest,
            }, None, None, None
        finally:
            db.close()

    def complete_experience(self, token_digest: str, request_key: str,
                            status: str, payload: Dict[str, Any]) -> None:
        if not request_key:
            return
        db = connect_db(self.db_path)
        try:
            db.execute(
                "UPDATE experience_requests SET state='complete',response_status=?,response_json=? "
                "WHERE token_hash=? AND request_key=?",
                (status, json.dumps(payload, sort_keys=True, separators=(",", ":")),
                 token_digest, request_key),
            )
            db.commit()
        finally:
            db.close()

    def run_experience(self, environ, start_response):
        try:
            data = self.read_body(environ)
            if data.get("protocol") not in (None, "nanlm.clocked-experience"):
                raise ValueError("unsupported_protocol")
            source_text = data.get("text")
            if not isinstance(source_text, str) or not source_text.strip():
                raise ValueError("text_required")
            if len(source_text.encode("utf-8")) > MAX_BODY:
                raise ValueError("text_too_large")
        except (ValueError, TypeError) as exc:
            return json_response(start_response, "400 Bad Request", {"error": str(exc)[:64]})

        authorization = environ.get("HTTP_AUTHORIZATION", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        request_key = environ.get("HTTP_IDEMPOTENCY_KEY", "")
        if request_key and not IDEMPOTENCY_KEY.fullmatch(request_key):
            return json_response(start_response, "400 Bad Request", {"error": "invalid_idempotency_key"})
        body_sha256 = hashlib.sha256(json.dumps(
            data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")).hexdigest()
        identity, cached, error, error_status = self.reserve_experience(
            token, request_key, body_sha256
        )
        if error:
            return json_response(start_response, error_status, {"error": error})
        if cached is not None:
            return json_response(start_response, cached[0], cached[1])

        try:
            if self.clocked_client is None:
                if not os.environ.get("CLOCKED_API_KEY"):
                    payload = {"error": "clocked_upstream_not_configured"}
                    self.complete_experience(identity["token_hash"], request_key,
                                              "503 Service Unavailable", payload)
                    return json_response(start_response, "503 Service Unavailable", payload)
                from clocked_sdk import Clocked
                with Clocked() as client:
                    response = client.pipeline(text=source_text, steps=build_pipeline(source_text),
                                                on_error="continue")
                    event = make_event(source_text, dict(response), response)
            else:
                response = self.clocked_client.pipeline(text=source_text,
                    steps=build_pipeline(source_text), on_error="continue")
                event = make_event(source_text, dict(response), response)
            event["source_endpoint"] = "clocked_demo"
            event["tenant_id"] = identity["tenant_id"]
            event["protocol_version"] = SCHEMA_VERSION
            event["learning_state"] = "awaiting_nanlmind_ingest"
            payload = {
                "protocol": "nanlm.clocked-experience", "protocol_version": SCHEMA_VERSION,
                "event": event, "quota_remaining": identity["remaining"],
            }
            self.complete_experience(identity["token_hash"], request_key, "200 OK", payload)
            return json_response(start_response, "200 OK", payload)
        except Exception:
            payload = {"error": "upstream_unavailable"}
            self.complete_experience(identity["token_hash"], request_key,
                                      "502 Bad Gateway", payload)
            return json_response(start_response, "502 Bad Gateway", payload)

    def accept_observation(self, environ, start_response):
        identity = self.authenticate(environ, start_response)
        if not isinstance(identity, dict):
            return identity
        try:
            data = self.read_body(environ)
            allowed_fields = {
                "protocol", "version", "event_id", "base_generation",
                "active_heads", "outcome_verified",
            }
            if data.get("outcome_verified", False) is not False or "correct" in data:
                raise ValueError("endpoint_cannot_assert_correctness")
            if set(data) - allowed_fields:
                raise ValueError("unknown_observation_fields")
            if data.get("protocol") != "nanlm.endpoint-observation" or data.get("version") != 1:
                raise ValueError("unsupported_protocol")
            event_id = data.get("event_id")
            generation = data.get("base_generation")
            heads = data.get("active_heads", [])
            if not isinstance(event_id, str) or not EVENT_ID.fullmatch(event_id):
                raise ValueError("invalid_event_id")
            if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
                raise ValueError("invalid_base_generation")
            if not isinstance(heads, list) or len(heads) > 256 or any(
                isinstance(h, bool) or not isinstance(h, int) or h < 0 or h > 255 for h in heads
            ):
                raise ValueError("invalid_active_heads")
            payload = {
                "protocol": "nanlm.endpoint-observation", "version": 1,
                "event_id": event_id, "base_generation": generation,
                "active_heads": sorted(set(heads)), "outcome_verified": False,
            }
        except (ValueError, TypeError) as exc:
            return json_response(start_response, "400 Bad Request", {"error": str(exc)[:64]})
        db = connect_db(self.db_path)
        try:
            try:
                db.execute(
                    "INSERT INTO endpoint_inbox(event_id,tenant_id,source_endpoint,base_generation,payload_json,received_at) VALUES(?,?,?,?,?,?)",
                    (event_id, identity["tenant_id"], identity["endpoint_id"], generation,
                     json.dumps(payload, sort_keys=True, separators=(",", ":")), int(time.time())),
                )
                db.commit()
                accepted = True
            except sqlite3.IntegrityError:
                accepted = False
        finally:
            db.close()
        return json_response(start_response, "202 Accepted" if accepted else "200 OK", {
            "event_id": event_id, "source_endpoint": identity["endpoint_id"],
            "learning_state": "awaiting_runner_ring_ingest" if accepted else "duplicate_noop",
            "outcome_verified": False, "quota_remaining": identity["remaining"],
        })

    def poll_observations(self, environ, start_response):
        if not self.runner_ok(environ):
            return json_response(start_response, "401 Unauthorized", {"error": "runner_unauthorized"})
        now = int(time.time())
        lease_id = secrets.token_hex(16)
        db = connect_db(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT event_id,tenant_id,source_endpoint,base_generation,payload_json,received_at "
                "FROM endpoint_inbox WHERE status='pending' OR "
                "(status='leased' AND lease_until<=?) ORDER BY received_at,event_id LIMIT 100",
                (now,),
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE endpoint_inbox SET status='leased',lease_id=?,lease_until=? "
                    "WHERE event_id=?",
                    (lease_id, now + 120, row["event_id"]),
                )
            db.commit()
            events = [{
                "tenant_id": row["tenant_id"], "source_endpoint": row["source_endpoint"],
                "received_at": row["received_at"], **json.loads(row["payload_json"]),
            } for row in rows]
        finally:
            db.close()
        return json_response(start_response, "200 OK", {
            "events": events, "count": len(events), "lease_id": lease_id,
            "lease_seconds": 120,
        })

    def ack_observations(self, environ, start_response):
        if not self.runner_ok(environ):
            return json_response(start_response, "401 Unauthorized", {"error": "runner_unauthorized"})
        try:
            data = self.read_body(environ)
            ids = data.get("event_ids")
            lease_id = data.get("lease_id")
            if (not isinstance(lease_id, str) or not re.fullmatch(r"[a-f0-9]{32}", lease_id)
                    or not isinstance(ids, list) or len(ids) > 100 or any(
                        not isinstance(value, str) or not EVENT_ID.fullmatch(value) for value in ids
                    )):
                raise ValueError("invalid_lease_or_event_ids")
        except (ValueError, TypeError) as exc:
            return json_response(start_response, "400 Bad Request", {"error": str(exc)[:64]})
        db = connect_db(self.db_path)
        try:
            changed = 0
            for event_id in ids:
                changed += db.execute(
                    "UPDATE endpoint_inbox SET status='accepted',lease_id=NULL,lease_until=NULL "
                    "WHERE event_id=? AND status='leased' AND lease_id=?",
                    (event_id, lease_id),
                ).rowcount
            db.commit()
        finally:
            db.close()
        complete = changed == len(ids)
        return json_response(start_response, "200 OK", {
            "acknowledged": changed, "complete": complete,
        })

def main():
    for name in ("CLOCKED_GATEWAY_ADMIN_TOKEN", "CLOCKED_TOKEN_PEPPER"):
        if not os.environ.get(name):
            raise SystemExit(name + " must be configured in the server secret manager")
    host = os.environ.get("CLOCKED_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("CLOCKED_GATEWAY_PORT", "8787"))
    db_path = os.environ.get("CLOCKED_GATEWAY_DB", "clocked_gateway.sqlite3")
    app = Gateway(db_path)
    with make_server(host, port, app) as server:
        print("Clocked and endpoint intake gateway listening on %s:%d" % (host, port), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
