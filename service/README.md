# Clocked experience adapter

This adapter makes Clocked a **supervisory observation source** for NaNLMind. It does not train Clocked, replace the 256-head universe, or write directly into the NaN16 guest.

**Topology:** the NaNLMind six-runner ring is the primary training universe and owns the canonical 256-head state. Overbootstrap aggregates verified evidence from four environments: the bootstrap ring, MY Android, Hermes demo, and Clocked demo. Clocked is only endpoint 4; it is not the model owner or coordinator. See [the canonical training topology](../../docs/72_CANONICAL_TRAINING_UNIVERSE.md) and [the endpoint registry](training_endpoints.json).

## Hardware-neutral boundary

All clients use the same versioned HTTP/JSON contract:

- `GET /healthz` reports the protocol and version.
- `POST /v1/experience` accepts `{"protocol":"nanlm.clocked-experience","text":"..."}`.
- The response contains a content-minimized `nanlm.clocked-experience` event and a remaining request quota.
- The normative event shape is `protocol.schema.json`.

The gateway is a host-side service. Android, Termux, ARM, x86, and other runners do not need the Clocked SDK or any Clocked credential. Each platform only needs an HTTP client and a small adapter from the common event envelope to its local NaNLMind/NaN16 intake. Hardware capability negotiation belongs to the runner; it must not change event meaning.

Protocol version 1 is architecture-neutral JSONL/JSON. Integers, hashes, labels, provenance and lifecycle fields have the same meaning on every device. A future binary transport can carry the same logical fields without changing the protocol semantics.

## Credential and participant-token boundary

- Set `CLOCKED_API_KEY` only in the gateway server's secret environment.
- Set `CLOCKED_GATEWAY_ADMIN_TOKEN` to a separate high-entropy administrator secret.
- Set `CLOCKED_TOKEN_PEPPER` to a separate random secret used to hash participant tokens at rest.
- Never put the upstream Clocked key in source, GitHub variables, Android resources, CLI arguments, corpus files, JSONL events, logs, or screenshots.
- Participants receive a short-lived `CLOCKED_USER_API` token from the gateway. It is a gateway-only credential, not a wrapped or encrypted Clocked key.
- The gateway stores only a peppered SHA-256 digest of each participant token, enforces expiry and request quotas, and returns the token only once.
- Clocked demo clients call this gateway; Android and Hermes use their own endpoint adapters and scoped credentials. No endpoint receives the privileged Clocked key.

The key shared during setup should be rotated. Add the replacement to the actual server's secret store as `CLOCKED_API_KEY`. The GitHub integration used for this change cannot create repository Actions secrets.

## Install

Python 3.9+:

```sh
python -m pip install -r integrations/clocked/requirements.txt
```

## Run the gateway

Configure `CLOCKED_GATEWAY_ADMIN_TOKEN` and `CLOCKED_TOKEN_PEPPER` in the server secret manager. `CLOCKED_API_KEY` is optional for the generic Android/Hermes intake and is required only to enable the Clocked `/v1/experience` route. Also configure `CLOCKED_GATEWAY_DB`, `CLOCKED_GATEWAY_HOST`, and `CLOCKED_GATEWAY_PORT` as needed.

```sh
python integrations/clocked/gateway.py
```

Put it behind HTTPS before exposing it publicly. Keep the admin token out of participant devices. Issue a participant token from a trusted admin workstation:

```sh
curl --fail-with-body https://YOUR_GATEWAY/admin/tokens \
  -H "Authorization: Bearer $CLOCKED_GATEWAY_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"hackathon-demo","max_requests":25,"ttl_seconds":21600}'
```

The response's `token` is the participant's `CLOCKED_USER_API`. Give each participant their own token, not the admin token. A Termux/desktop participant can use the standard-library client:

```sh
export CLOCKED_INTAKE_URL="https://YOUR_GATEWAY/v1/experience"
export CLOCKED_USER_API="(participant token)"
python integrations/clocked/client.py input.txt
```

Native Android and NaN16 runners implement the same HTTP contract without needing Python. A raw HTTP example is:

```sh
curl --fail-with-body https://YOUR_GATEWAY/v1/experience \
  -H "Authorization: Bearer $CLOCKED_USER_API" \
  -H "Content-Type: application/json" \
  -d '{"protocol":"nanlm.clocked-experience","text":"A small demo input"}'
```

The gateway defaults to 25 requests per token, six hours' lifetime, a 64 KiB request limit, and a maximum issuance policy of 500 requests/24 hours. It consumes quota before upstream processing to prevent retries from bypassing limits. Use a production WSGI server, HTTPS termination, persistent protected storage, and monitoring for a public deployment; the built-in server is for local/demo use.

## Native hackathon demo: Clocked labels to NaNLMind routing replay

The demo is intentionally two-mode:

- **Fixture mode** is offline and deterministic. It does not call Clocked or consume credits. It is used by CI to prove the complete local native-learning path.
- **Live mode** sends the labelled synthetic curriculum through the authenticated gateway and uses the actual Clocked response. Only training examples whose Clocked `task_family` matches the independent gold label are admitted to native training. Mismatches are skipped.

Build and run the offline demo:

```sh
make -j2 build/clocked-demo
make clocked-demo-test
```

The native C++ program uses transparent lexical anchor features for six task families. It reports the untrained baseline, verified sample count, Overbootstrap Clocked evidence, bounded routing feedback and held-out replay. This is a small routing-memory demonstration, not a general language-model benchmark and not a canonical six-runner generation commit.

For a live Clocked run, first deploy the gateway with these secrets configured server-side:

- `CLOCKED_API_KEY` — upstream Clocked key; never give this to participants.
- `CLOCKED_GATEWAY_ADMIN_TOKEN` — separate gateway administrator secret.
- `CLOCKED_TOKEN_PEPPER` — separate high-entropy token-hashing pepper.

Start the gateway behind HTTPS, issue a scoped token using the admin route shown above, then run:

```sh
export CLOCKED_INTAKE_URL="https://YOUR_GATEWAY/v1/experience"
export CLOCKED_USER_API="(scoped participant token)"
make -j2 build/clocked-demo
python integrations/clocked/demo.py --native-binary build/clocked-demo
```

The demo sends an `Idempotency-Key` for each training sample only. The held-out split is never sent to Clocked, including in live mode, so the teacher cannot see evaluation examples. The gateway stores the request-body digest and minimized response under the participant token scope. A retry with the same key and body replays the response without another Clocked call or quota charge; reusing a key with a different body returns conflict. The short-lived native TSV is deleted after the learner exits. The durable event log contains sample IDs, labels, digests and outcome status, not source text.

The labelled curriculum is synthetic and intended for demonstration. For a real training chain, use independently reviewed labels, provenance/license metadata and source-separated held-out evaluation. See [the chainable training architecture](../../specs/CLOCKED_CHAINABLE_TRAINING.md).

## Shared endpoint observation intake

Android and Hermes submit observations to the same gateway without invoking
Clocked. The server assigns endpoint identity from each scoped token:

- `my_android` → `NANLM_DEVICE_TOKEN`
- `hermes_demo` → `HERMES_DEMO_API`
- `clocked_demo` → `CLOCKED_USER_API`

Issue a token with an admin-authenticated `POST /admin/tokens` body such as
`{"tenant_id":"android-demo","endpoint_id":"my_android","max_requests":100,"ttl_seconds":21600}`.
The gateway returns the corresponding scoped token once and stores only its
peppered digest.

The common `POST /v1/observations` contract is documented in
[endpoint-observation.schema.json](endpoint-observation.schema.json). It is
hardware-neutral version-1 JSON: event digest, base generation, active-head
indices, and an explicit unverified outcome. The caller cannot provide a
trusted source identity or assert correctness.

Accepted events enter a durable SQLite inbox. Admin-only
`GET /internal/observations` retrieves pending events and
`POST /internal/observations/ack` acknowledges them after the runner service
has durably accepted them. This queue is not yet wired to the live runner's
canonical commit; queued observations remain
`awaiting_runner_ring_ingest`.

The standard-library publisher is `endpoint_client.py`. It reads
`NANLM_INTAKE_URL` and a scoped token from `NANLM_DEVICE_TOKEN`,
`HERMES_DEMO_API`, or `CLOCKED_USER_API`; it never reads
`CLOCKED_API_KEY`. Provide a JSON event file and run:

```sh
python integrations/clocked/endpoint_client.py observation.json
```

## Direct adapter (server-side only)

For a single trusted runner, the direct adapter remains available:

```sh
python integrations/clocked/clocked_experience.py input.txt --output experiences.jsonl
```

The default pipeline performs PII detection, prompt-injection detection (which can stop later steps), task classification, and structured extraction. Pipeline steps see the original input; the PII anonymization result is not a sanitization stage for later pipeline steps. Do not treat the pipeline as a guarantee that downstream steps receive redacted text.

## Event contract

Each JSONL event is a credential-free, content-minimized external observation:

- schema/version and deterministic event id
- input and response digests
- endpoint status/timing summaries
- allowlisted task labels and verdict flags, never arbitrary extracted values
- credit/cost metadata when supplied by the SDK
- trusted source endpoint identity (`clocked_demo`) and tenant attribution at the gateway boundary
- explicit `learning_state: awaiting_nanlmind_ingest`

It deliberately does **not** invent active heads, head deltas, correctness labels, or a committed NaNLMind generation. Those are produced only after the native learner evaluates the observation against its own baseline and a verified outcome.

## Idempotency and billing

The Clocked SDK sends an idempotency key and reuses it for retries. The direct adapter uses one pipeline request per input document. Review endpoint results and the Clocked account's credit usage before processing large corpora.

## Current integration boundary

This adds the server-side gateway, participant-token issuance, quota enforcement, an architecture-neutral protocol envelope, a standard-library participant client, a normative JSON schema, and offline tests. Native ingestion into the runner ring's Overbootstrap evidence fold, the durable inbox is implemented, but a live runner queue consumer and canonical ledger commit, native Android/Hermes app wiring, and held-out cross-endpoint learning benchmarks remain subsequent integration steps. No claim of end-to-end training is made by this adapter.
