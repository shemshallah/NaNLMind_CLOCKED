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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from wsgiref.simple_server import make_server

from clocked_experience import build_pipeline, make_event

MAX_BODY = 64 * 1024
MAX_TASK_RESULT_BYTES = 262_144
MAX_TASK_RESPONSE_BYTES = 4 * 1024 * 1024
SCHEMA_VERSION = 1
SOURCE_ENDPOINT = "clocked_demo"
ENDPOINTS = {"my_android", "hermes_demo", "clocked_demo"}
EVENT_ID = re.compile(r"^[a-f0-9]{64}$")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def token_hash(token: str, pepper: str) -> str:
    return hashlib.sha256((pepper + token).encode("utf-8")).hexdigest()


def _result_fernet():
    key = os.environ.get("CLOCKED_RESULT_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("CLOCKED_RESULT_ENCRYPTION_KEY is required for encrypted result caching")
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError("cryptography is required for encrypted result caching") from exc
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise RuntimeError("CLOCKED_RESULT_ENCRYPTION_KEY must be a valid Fernet key") from exc


def ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Apply a SQLite column migration safely when requests initialize concurrently."""
    columns = {row["name"] for row in db.execute("PRAGMA table_info(" + table + ")")}
    if column in columns:
        return
    try:
        db.execute("ALTER TABLE " + table + " ADD COLUMN " + column + " " + definition)
    except sqlite3.OperationalError as exc:
        # A second worker may have observed the old schema before the first
        # worker committed the same ALTER TABLE.
        if "duplicate column name" not in str(exc).lower():
            raise


def connect_db(path: str) -> sqlite3.Connection:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, mode=0o700, exist_ok=True)
        try:
            os.chmod(parent, 0o700)
        except OSError:
            pass
    db = sqlite3.connect(path, timeout=10)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
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
    ensure_column(db, "demo_tokens", "endpoint_id", "TEXT NOT NULL DEFAULT 'clocked_demo'")
    db.execute("""
        CREATE TABLE IF NOT EXISTS demo_instances (
            node_point INTEGER PRIMARY KEY CHECK(node_point BETWEEN 9 AND 255),
            instance_id TEXT NOT NULL UNIQUE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at INTEGER NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            nannet_address TEXT,
            nannet_token_ciphertext TEXT,
            nannet_lease_id TEXT
        )
    """)
    ensure_column(db, "demo_instances", "nannet_address", "TEXT")
    ensure_column(db, "demo_instances", "nannet_token_ciphertext", "TEXT")
    ensure_column(db, "demo_instances", "nannet_lease_id", "TEXT")
    ensure_column(db, "demo_tokens", "node_point", "INTEGER")
    ensure_column(db, "demo_tokens", "instance_id", "TEXT")
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
    ensure_column(db, "endpoint_inbox", "node_point", "INTEGER")
    ensure_column(db, "endpoint_inbox", "lease_id", "TEXT")
    ensure_column(db, "endpoint_inbox", "lease_until", "INTEGER")
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
        if method == "POST" and path == "/auth/demo-token":
            return self.issue_demo_instance_token(environ, start_response)
        if method == "POST" and path == "/admin/instances/revoke":
            return self.revoke_demo_instance(environ, start_response)
        if method == "GET" and path == "/admin/instances":
            return self.list_demo_instances(environ, start_response)
        if method == "POST" and path == "/v1/experience":
            return self.run_experience(environ, start_response)
        if method == "POST" and path == "/v1/tasks":
            return self.run_tasks(environ, start_response)
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

    def nannet_post(self, path: str, payload: Dict[str, Any], bearer: str = ""):
        """Call the existing NANNET Koyeb authority without exposing its token."""
        base = os.environ.get("NANNET_URL", "").rstrip("/")
        if not base.startswith("https://"):
            raise RuntimeError("nannet_https_url_not_configured")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if bearer:
            headers["Authorization"] = "Bearer " + bearer
        request = Request(
            base + path,
            data=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read(65536)
                status_value = getattr(response, "status", None)
                status = int(status_value if status_value is not None else response.getcode())
        except HTTPError as exc:
            raw = exc.read(65536)
            status = int(exc.code)
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("nannet_service_unavailable") from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            result = {"error": "invalid_nannet_response"}
        if not isinstance(result, dict):
            result = {"error": "invalid_nannet_response"}
        return status, result

    def enrollment_ok(self, environ):
        enrollment = os.environ.get("CLOCKED_DEMO_ENROLLMENT_TOKEN", "")
        supplied = environ.get("HTTP_AUTHORIZATION", "")
        return bool(enrollment) and secrets.compare_digest(
            supplied, "Bearer " + enrollment
        )

    def issue_demo_instance_token(self, environ, start_response):
        """Issue a CLOCKED token bound to a point leased by the NANNET authority."""
        if not self.enrollment_ok(environ):
            return json_response(start_response, "401 Unauthorized", {"error": "unauthorized"})
        if not os.environ.get("CLOCKED_API_KEY"):
            return json_response(start_response, "503 Service Unavailable",
                                 {"error": "clocked_upstream_not_configured"})
        pepper = os.environ.get("CLOCKED_TOKEN_PEPPER", "")
        if len(pepper) < 32:
            return json_response(start_response, "503 Service Unavailable",
                                 {"error": "token_service_misconfigured"})
        try:
            _result_fernet()
            data = self.read_body(environ)
            if set(data) - {"instance_label", "max_requests", "ttl_seconds", "consent"}:
                raise ValueError("unknown_fields")
            if data.get("consent") is not True:
                raise ValueError("explicit_nannet_registration_consent_required")
            label = data.get("instance_label", "demo-instance")
            if not isinstance(label, str) or not label.strip() or len(label) > 64:
                raise ValueError("invalid_instance_label")
            max_requests = data.get("max_requests", 50)
            ttl_seconds = data.get("ttl_seconds", 21600)
            if (isinstance(max_requests, bool) or not isinstance(max_requests, int)
                    or not 1 <= max_requests <= 500):
                raise ValueError("max_requests_out_of_range")
            if (isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int)
                    or not 60 <= ttl_seconds <= 21600):
                raise ValueError("ttl_seconds_out_of_range")
        except RuntimeError:
            return json_response(start_response, "503 Service Unavailable",
                                 {"error": "result_encryption_unavailable"})
        except (ValueError, TypeError) as exc:
            return json_response(start_response, "400 Bad Request", {"error": str(exc)[:64]})

        try:
            nannet_status, registration = self.nannet_post("/v1/devices/register", {
                "device_secret": secrets.token_urlsafe(32),
                "consent": True,
                "terms_version": "nannet-device-registration-v1",
                "system_report": {
                    "platform": "CLOCKED demo instance",
                    "os_version": "Koyeb",
                    "app_version": "1",
                    "abi": "server-managed",
                    "device_model": label.strip(),
                    "capabilities": ["clocked-demo", "nannet-observation"],
                },
            })
        except RuntimeError:
            return json_response(start_response, "503 Service Unavailable",
                                 {"error": "nannet_service_unavailable"})
        if nannet_status != 201:
            return json_response(start_response, "503 Service Unavailable", {
                "error": "nannet_registration_failed",
                "nannet_status": nannet_status,
                "nannet_error": str(registration.get("error", "unknown"))[:96],
            })

        nannet_token = registration.get("token")
        address = registration.get("address")
        node_point = registration.get("node_point")
        lease_id = registration.get("lease_id")
        lease_expires_at = registration.get("lease_expires_at")
        address_match = re.fullmatch(
            r"nan://GM0:SC0:MC0:BS0:HW([0-9]{1,3})", address
        ) if isinstance(address, str) else None
        valid_registration = (
            isinstance(nannet_token, str) and nannet_token.startswith("nnt_")
            and len(nannet_token) <= 512
            and isinstance(lease_id, str) and bool(lease_id)
            and isinstance(node_point, int) and not isinstance(node_point, bool)
            and 9 <= node_point <= 255
            and address_match is not None
            and int(address_match.group(1)) + 1 == node_point
            and isinstance(lease_expires_at, int) and not isinstance(lease_expires_at, bool)
            and lease_expires_at > int(time.time())
        )
        if not valid_registration:
            if isinstance(nannet_token, str) and nannet_token.startswith("nnt_"):
                try:
                    self.nannet_post("/v1/devices/release", {}, nannet_token)
                except RuntimeError:
                    pass
            return json_response(start_response, "502 Bad Gateway",
                                 {"error": "nannet_returned_invalid_node_lease"})

        now = int(time.time())
        token_expires_at = min(now + ttl_seconds, lease_expires_at)
        token = "clu_" + secrets.token_urlsafe(32)
        instance_id = "demo-" + secrets.token_urlsafe(12)
        digest = token_hash(token, pepper)
        encrypted_nannet_token = _result_fernet().encrypt(
            nannet_token.encode("utf-8")
        ).decode("ascii")
        db = connect_db(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            # NANNET owns allocation. This local row is only a binding/audit mirror.
            # If NANNET has reassigned a previously mirrored point, its old lease
            # must have been released/expired by the authoritative allocator.
            existing = db.execute(
                "SELECT token_hash,expires_at,revoked FROM demo_instances WHERE node_point=?",
                (node_point,),
            ).fetchone()
            if existing:
                if not existing["revoked"] and existing["expires_at"] > now:
                    db.rollback()
                    try:
                        self.nannet_post("/v1/devices/release", {}, nannet_token)
                    except RuntimeError:
                        pass
                    return json_response(start_response, "409 Conflict",
                                         {"error": "nannet_point_conflicts_with_active_local_lease"})
                db.execute("UPDATE demo_tokens SET revoked=1 WHERE token_hash=?",
                           (existing["token_hash"],))
                db.execute("DELETE FROM demo_instances WHERE node_point=?", (node_point,))
            db.execute(
                "INSERT INTO demo_tokens(token_hash,tenant_id,endpoint_id,expires_at,max_requests,created_at,node_point,instance_id) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (digest, "demo", "clocked_demo", token_expires_at, max_requests, now,
                 node_point, instance_id),
            )
            db.execute(
                "INSERT INTO demo_instances(node_point,instance_id,token_hash,expires_at,created_at,nannet_address,nannet_token_ciphertext,nannet_lease_id) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (node_point, instance_id, digest, lease_expires_at, now, address,
                 encrypted_nannet_token, lease_id),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            try:
                self.nannet_post("/v1/devices/release", {}, nannet_token)
            except RuntimeError:
                pass
            return json_response(start_response, "409 Conflict",
                                 {"error": "nannet_point_already_mirrored"})
        except Exception:
            db.rollback()
            try:
                self.nannet_post("/v1/devices/release", {}, nannet_token)
            except RuntimeError:
                pass
            return json_response(start_response, "503 Service Unavailable",
                                 {"error": "demo_instance_store_unavailable"})
        finally:
            db.close()
        return json_response(start_response, "201 Created", {
            "token_type": "CLOCKED_DEMO_INSTANCE",
            "token": token,
            "nannet_token": nannet_token,
            "nannet_address": address,
            "instance_id": instance_id,
            "instance_label": label.strip(),
            "node_point": node_point,
            "registration_state": "nannet_lease_active",
            "tenant_id": "demo",
            "source_endpoint": "clocked_demo",
            "expires_at": token_expires_at,
            "lease_expires_at": lease_expires_at,
            "max_requests": max_requests,
            "nannet_scopes": registration.get("scopes", []),
        })

    def revoke_demo_instance(self, environ, start_response):
        if not self.admin_ok(environ):
            return json_response(start_response, "401 Unauthorized", {"error": "unauthorized"})
        try:
            data = self.read_body(environ)
            if set(data) == {"instance_id"} and isinstance(data["instance_id"], str):
                where, value = "instance_id=?", data["instance_id"]
            elif set(data) == {"node_point"} and isinstance(data["node_point"], int) and not isinstance(data["node_point"], bool):
                where, value = "node_point=?", data["node_point"]
            else:
                raise ValueError("provide exactly one instance_id or node_point")
        except (ValueError, TypeError) as exc:
            return json_response(start_response, "400 Bad Request", {"error": str(exc)[:64]})

        db = connect_db(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT token_hash,node_point,nannet_token_ciphertext FROM demo_instances WHERE " + where,
                (value,),
            ).fetchone()
            if row is None:
                db.rollback()
                return json_response(start_response, "404 Not Found", {"error": "instance_not_found"})
            if not row["nannet_token_ciphertext"]:
                db.rollback()
                return json_response(start_response, "409 Conflict",
                                     {"error": "nannet_registration_missing_manual_review_required"})
            # Disable CLOCKED access before asking NANNET to release its lease.
            db.execute("UPDATE demo_tokens SET revoked=1 WHERE token_hash=?", (row["token_hash"],))
            db.commit()
        finally:
            db.close()

        try:
            nannet_token = _result_fernet().decrypt(
                row["nannet_token_ciphertext"].encode("ascii")
            ).decode("utf-8")
            release_status, release_result = self.nannet_post(
                "/v1/devices/release", {}, nannet_token
            )
        except (RuntimeError, ValueError):
            return json_response(start_response, "502 Bad Gateway",
                                 {"error": "nannet_release_unavailable",
                                  "clocked_token_revoked": True})
        if release_status == 409:
            return json_response(start_response, "409 Conflict", {
                "error": "nannet_instance_has_pending_work",
                "node_point": int(row["node_point"]),
                "clocked_token_revoked": True,
            })
        if release_status != 200:
            return json_response(start_response, "502 Bad Gateway", {
                "error": "nannet_release_failed",
                "nannet_status": release_status,
                "clocked_token_revoked": True,
            })
        db = connect_db(self.db_path)
        try:
            db.execute("UPDATE demo_instances SET revoked=1 WHERE " + where, (value,))
            db.commit()
        finally:
            db.close()
        return json_response(start_response, "200 OK", {
            "revoked": True, "node_point": int(row["node_point"]),
            "nannet_node_released": True,
        })

    def list_demo_instances(self, environ, start_response):
        if not self.admin_ok(environ):
            return json_response(start_response, "401 Unauthorized", {"error": "unauthorized"})
        db = connect_db(self.db_path)
        try:
            now = int(time.time())
            rows = db.execute(
                "SELECT node_point,instance_id,expires_at,revoked,nannet_address,nannet_lease_id "
                "FROM demo_instances WHERE revoked=0 ORDER BY node_point"
            ).fetchall()
            instances = [{
                "node_point": int(row["node_point"]),
                "instance_id": row["instance_id"],
                "nannet_address": row["nannet_address"],
                "nannet_lease_id": row["nannet_lease_id"],
                "lease_expires_at": int(row["expires_at"]),
                "registration_state": (
                    "nannet_lease_active" if row["expires_at"] > now
                    else "nannet_lease_expired_pending_reconcile"
                ),
            } for row in rows]
        finally:
            db.close()
        return json_response(start_response, "200 OK", {
            "instances": instances,
            "active_count": len(instances),
            "authoritative_allocator": "NANNET",
            "available_range": "9..255",
        })

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
                    "node_point": row["node_point"], "instance_id": row["instance_id"],
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
                        stored = prior["response_json"]
                        if stored.startswith("fernet:"):
                            cached = json.loads(_result_fernet().decrypt(stored[7:].encode("ascii")).decode("utf-8"))
                        else:
                            cached = json.loads(stored)
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
                "node_point": row["node_point"],
                "instance_id": row["instance_id"],
            }, None, None, None
        finally:
            db.close()

    def complete_experience(self, token_digest: str, request_key: str,
                            status: str, payload: Dict[str, Any],
                            encrypt: bool = False) -> None:
        if not request_key:
            return
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if encrypt:
            encoded = "fernet:" + _result_fernet().encrypt(encoded.encode("utf-8")).decode("ascii")
        db = connect_db(self.db_path)
        try:
            db.execute(
                "UPDATE experience_requests SET state='complete',response_status=?,response_json=? "
                "WHERE token_hash=? AND request_key=?",
                (status, encoded, token_digest, request_key),
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
            if identity.get("node_point") is not None:
                event["node_point"] = identity["node_point"]
                event["instance_id"] = identity["instance_id"]
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


    def run_tasks(self, environ, start_response):
        """Execute a bounded list of independent typed CLOCKED endpoint calls."""
        try:
            _result_fernet()  # Fail closed before billing if result encryption is unavailable.
            length = int(environ.get("CONTENT_LENGTH") or "0")
            if length <= 0 or length > 1_048_576:
                raise ValueError("task_body_size_out_of_range")
            raw = environ["wsgi.input"].read(length)
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict) or data.get("protocol") != "nanlm.clocked-task-plan" or data.get("version") != 1:
                raise ValueError("unsupported_task_protocol")
            plan = data.get("plan")
            if not isinstance(plan, dict) or plan.get("schema") != "nanlm.clocked-task-plan/1":
                raise ValueError("invalid_task_plan")
            tasks = plan.get("tasks")
            if not isinstance(tasks, list) or not 1 <= len(tasks) <= 16:
                raise ValueError("task_count_out_of_range")
            seen = set()
            total_bytes = 0
            allowed = {"decide", "extract", "fill", "pii", "injection",
                       "script", "grounding", "compare", "rerank", "pipeline"}
            for task in tasks:
                if not isinstance(task, dict):
                    raise ValueError("invalid_task")
                task_id = task.get("id")
                endpoint = task.get("endpoint")
                text = task.get("text")
                if not isinstance(task_id, str) or not task_id or task_id in seen:
                    raise ValueError("invalid_or_duplicate_task_id")
                if endpoint not in allowed:
                    raise ValueError("unsupported_endpoint")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("task_text_required")
                deps = task.get("depends_on", [])
                if not isinstance(deps, list) or any(dep not in seen for dep in deps):
                    raise ValueError("dependencies_must_reference_prior_tasks")
                options = task.get("options", {})
                if not isinstance(options, dict) or len(json.dumps(options)) > 8192:
                    raise ValueError("invalid_task_options")
                total_bytes += len(text.encode("utf-8"))
                seen.add(task_id)
            if total_bytes > 1_048_576:
                raise ValueError("task_input_limit_exceeded")
        except RuntimeError:
            return json_response(start_response, "503 Service Unavailable",
                                  {"error": "result_cache_encryption_unavailable"})
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return json_response(start_response, "400 Bad Request", {"error": str(exc)[:96]})

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
            client = self.clocked_client
            if client is None:
                if not os.environ.get("CLOCKED_API_KEY"):
                    raise RuntimeError("clocked_upstream_not_configured")
                from clocked_sdk import Clocked
                client_context = Clocked()
            else:
                client_context = None

            def execute_with(active_client):
                results = []
                results_by_id = {}
                for task in tasks:
                    endpoint = task["endpoint"]
                    source_text = task["text"]
                    options = dict(task.get("options", {}))
                    claims_from = options.pop("claims_from", None)
                    if claims_from is not None:
                        prior = results_by_id.get(claims_from)
                        if prior is None or not isinstance(prior.get("result"), dict):
                            raise RuntimeError("task_dependency_result_missing")
                        fields = prior["result"].get("fields", {})
                        claims = fields.get("claims", []) if isinstance(fields, dict) else []
                        if isinstance(claims, str):
                            claims = [claims]
                        if not isinstance(claims, list):
                            raise RuntimeError("extracted_claims_invalid")
                        options["claims"] = [str(value)[:2048] for value in claims[:64]]
                    if endpoint == "pipeline":
                        response = active_client.pipeline(
                            text=source_text, steps=build_pipeline(source_text),
                            on_error="continue")
                    else:
                        operation = getattr(active_client, endpoint, None)
                        if not callable(operation):
                            raise RuntimeError("clocked_endpoint_not_available:" + endpoint)
                        # The SDK methods do not share a universal `text`
                        # parameter. Adapt the typed source text to each
                        # endpoint instead of sending an invalid keyword.
                        if endpoint == "decide":
                            options.setdefault("state", source_text)
                            options.setdefault("questions", {
                                "answer": {
                                    "type": "noul",
                                    "instructions": "Does the source support a useful answer?",
                                }
                            })
                            options.pop("text", None)
                        elif endpoint == "grounding":
                            options.setdefault("documents", [source_text])
                            options.setdefault("answer", source_text)
                            options.setdefault("claims", [source_text])
                            options.pop("text", None)
                        elif endpoint == "compare":
                            options.setdefault("documents", [source_text])
                            options.pop("text", None)
                        elif endpoint == "rerank":
                            options.setdefault("documents", [source_text])
                            options.setdefault("query", source_text)
                            options.pop("text", None)
                        elif endpoint == "script":
                            options.setdefault("script", source_text)
                            options.pop("text", None)
                        else:
                            options.setdefault("text", source_text)
                        response = operation(**options)
                    try:
                        result_data = dict(response)
                    except (TypeError, ValueError):
                        result_data = {"result": str(response)[:4096]}
                    if len(json.dumps(result_data, ensure_ascii=False).encode("utf-8")) > MAX_TASK_RESULT_BYTES:
                        raise RuntimeError("clocked_result_exceeds_size_limit")
                    event = make_event(source_text, {
                        "steps": [{"endpoint": endpoint, "status": 200,
                                   "result": result_data}],
                    }, response)
                    item = {
                        "task_id": task["id"], "endpoint": endpoint,
                        "source_id": task.get("source_id"),
                        "result_type": endpoint, "status": "ok",
                        "result": result_data, "provenance": {
                            "event_id": event["event_id"],
                            "input_sha256": event["input_sha256"],
                            "response_sha256": event["response_sha256"],
                            "observed_at": event["observed_at"],
                            "credits": event.get("credits"),
                            "cost_usd": event.get("cost_usd"),
                            "cost_basis": event.get("cost_basis"),
                            "model_ms": event.get("timing"),
                        },
                    }
                    results.append(item)
                    results_by_id[task["id"]] = item
                return results

            if client_context is None:
                results = execute_with(client)
            else:
                with client_context as active_client:
                    results = execute_with(active_client)
            payload = {
                "protocol": "nanlm.clocked-task-results", "version": 1,
                "plan_id": plan.get("plan_id"), "results": results,
                "instance_id": identity.get("instance_id"),
                "node_point": identity.get("node_point"),
                "learning_state": "awaiting_nanlmind_ingest",
                "quota_remaining": identity["remaining"],
            }
            if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_TASK_RESPONSE_BYTES:
                raise RuntimeError("clocked_task_response_exceeds_size_limit")
            self.complete_experience(identity["token_hash"], request_key, "200 OK", payload, encrypt=True)
            return json_response(start_response, "200 OK", payload)
        except Exception as exc:
            print("clocked task execution failed: " + type(exc).__name__ +
                  " " + str(exc)[:240], flush=True)
            payload = {"error": "clocked_task_execution_failed"}
            self.complete_experience(identity["token_hash"], request_key,
                                      "502 Bad Gateway", payload, encrypt=True)
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
                    "INSERT INTO endpoint_inbox(event_id,tenant_id,source_endpoint,base_generation,payload_json,received_at,node_point) VALUES(?,?,?,?,?,?,?)",
                    (event_id, identity["tenant_id"], identity["endpoint_id"], generation,
                     json.dumps(payload, sort_keys=True, separators=(",", ":")), int(time.time()),
                     identity.get("node_point")),
                )
                db.commit()
                accepted = True
            except sqlite3.IntegrityError:
                accepted = False
        finally:
            db.close()
        return json_response(start_response, "202 Accepted" if accepted else "200 OK", {
            "event_id": event_id, "source_endpoint": identity["endpoint_id"],
            "node_point": identity.get("node_point"),
            "instance_id": identity.get("instance_id"),
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
                "SELECT event_id,tenant_id,source_endpoint,base_generation,payload_json,received_at,node_point "
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
                "node_point": row["node_point"],
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
    port = int(os.environ.get("PORT", os.environ.get("CLOCKED_GATEWAY_PORT", "8787")))
    db_path = os.environ.get("CLOCKED_GATEWAY_DB", "/data/clocked_gateway.sqlite3")
    app = Gateway(db_path)
    with make_server(host, port, app) as server:
        print("Clocked and endpoint intake gateway listening on %s:%d" % (host, port), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()


# Gunicorn/Koyeb application entry point. Keep a single worker with threaded
# requests while the SQLite allocator owns the shared persistent /data volume.
application = Gateway(os.environ.get("CLOCKED_GATEWAY_DB", "/data/clocked_gateway.sqlite3"))
