# CLOCKED demo gateway on Koyeb

This deploys the CLOCKED gateway and scoped demo-token issuer as one persistent
service. The upstream provider key remains server-side. Demo clients receive
short-lived `clu_` tokens; they never receive `CLOCKED_API_KEY`.

## Koyeb service settings

- Build: Dockerfile at repository root
- Service type: Web
- Port: `8080`
- Health check: HTTP `GET /healthz`
- Persistent volume: mount at `/data`
- Replicas: **1** while using the local SQLite volume allocator
- Container runs as UID/GID `10001:10001`
- Set `CLOCKED_GATEWAY_DB=/data/clocked_gateway.sqlite3`

One service replica is intentional: SQLite serializes point allocation safely
inside the single persistent volume. The gateway can serve many concurrent
demo participants through 12 worker threads. Do not scale this container to
multiple replicas unless the allocator and token store are moved to a shared,
transactional database.

## Required Koyeb secrets

Set these as Koyeb environment secrets; never put their values in Git:

| Secret | Purpose |
|---|---|
| `CLOCKED_API_KEY` | Privileged upstream CLOCKED API credential; server only |
| `CLOCKED_GATEWAY_ADMIN_TOKEN` | Admin-only token issuance/revocation |
| `CLOCKED_DEMO_ENROLLMENT_TOKEN` | Demo enrollment credential for the token-mint endpoint |
| `CLOCKED_TOKEN_PEPPER` | Server-side pepper for one-way participant-token hashes |
| `CLOCKED_RESULT_ENCRYPTION_KEY` | Fernet key for encrypted idempotent task-result cache |

Generate independent random secrets. For example:

```sh
python -c 'import secrets; print(secrets.token_urlsafe(48))'
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Use separate random values for the admin token, enrollment token, and pepper.
Do not reuse the provider API key as any of these values.

## Multiple demo instances and node points

`POST /auth/demo-token` accepts the enrollment bearer token and a bounded
JSON body:

```json
{"instance_label":"demo-participant-01","max_requests":50,"ttl_seconds":21600}
```

The service transactionally reserves the **lowest currently available node
point in 9..255**, then issues a unique, expiring, request-limited token. The
caller cannot select or override a point. Concurrent issuance is serialized
with SQLite `BEGIN IMMEDIATE`, so two participants cannot receive the same
active point. Expired and revoked reservations are reclaimed.

The response includes `token`, `instance_id`, `node_point`, and
`registration_state`. The point is a reserved overbootstrap **node point**,
not a local head index and not a BSR runner slot. Points 0..8 remain reserved
by the canonical NaNROUTER point map.

The state is deliberately reported as
`reserved_pending_nannet_registration`: this gateway reserves the demo
identity but does not claim to have completed a signed NANNET registration or
committed a route. The route authority must still confirm that step before the
instance is treated as a routable network endpoint.

Revoke a participant and release its point using the admin token:

```sh
curl -X POST "$CLOCKED_GATEWAY_URL/admin/instances/revoke" \
  -H "Authorization: Bearer $CLOCKED_GATEWAY_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"instance_id":"demo-..."}'
```

## Participant flow

1. Obtain a scoped token from `POST /auth/demo-token`.
2. Send that token to `/v1/experience` or `/v1/tasks`.
3. The gateway calls CLOCKED with its server-side `CLOCKED_API_KEY`.
4. Returned events carry the assigned `node_point` and `instance_id`.
5. NaNLMind still treats results as evidence awaiting its own validation and
   ingest; CLOCKED does not write canonical heads or route tables.

## Local verification

```sh
python -m pip install -r integrations/clocked/requirements.txt
python -m unittest discover -s integrations/clocked -p 'test_*.py' -v
docker build -t nanlmind-clocked-gateway .
```

The live API key is never required for offline tests.
