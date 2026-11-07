# NaNLMind_CLOCKED

CLOCKED by Rezolve.ai integration service, multi-endpoint orchestration, evidence packaging and the HERMES autonomous cognition bridge.

## Canonical design documents

- [CLOCKED × NaNLMind × HERMES architecture brainstorm](docs/CLOCKED_HERMES_BRAINSTORM.md)
- [HERMES Autonomous CLOCKED Cognition and NaN Head Cortex](docs/HERMES_AUTONOMOUS_CLOCKED_HEAD_CORTEX.md)

## Repository boundary

- **This repository:** upstream CLOCKED SDK/API client, gateway, credentials, task graph, endpoint orchestration, request idempotency, quotas, credit accounting, fixtures and service tests.
- **NaNLMind:** NaN16 protocol and schemas, native Boolean heads, relation learner, M0-M9 transformation pipeline, evidence consumer, six-runner ring and canonical learning commits.
- **HERMES:** autonomous mode planner, user-facing scratch, cross-source synthesis, head-cortex client and final answer rendering.
- **NaNNet / NaNROUTER / Koyeb:** authenticated transport, HW3:0 route, policy and persistent gateway infrastructure.

The CLOCKED service returns typed observations. It does not own or modify NaNLMind heads, weights, route tables, runner membership or canonical generations.

## Service code

The upstream SDK and gateway implementation lives under `integrations/clocked/`. NaNLMind-side receiving schemas and native learner code remain in the NaNLMind repository. See the architecture document for the exact file ownership split.

## Independent CLOCKED chat CLI

`integrations/clocked/chat_cli.py` is a participant tool for the scoped gateway:

```sh
export CLOCKED_GATEWAY_URL=https://<gateway>
export CLOCKED_GATEWAY_TOKEN=clu_...
python integrations/clocked/chat_cli.py \
  --model-url http://127.0.0.1:11434/v1 --model gemma4:31b-cloud
```

The CLI keeps a revisioned, hash-chained scratch. Use `/paste NAME` to open a
multiline copy/paste section, `/source NAME @BUFFER` to turn it into a named
source, `/use @BUFFER` to put text into the active prompt, and `/copy` to print
scratch for reuse. `/plan`, `/approve`, `/run`, `/endpoint`, `/experience`,
`/tasks`, `/observations`, `/poll` and `/ack` cover the participant API routes;
`/token` is available only when the separate admin token is explicitly supplied.
API output is retained in scratch and can be fed back into later prompts or task
plans. Nothing is transmitted until an explicit command is entered.

The CLI does not read `CLOCKED_API_KEY`; the privileged Clocked credential stays
server-side.

## Portable C / NaN16 boundary

`native/clocked_nan.h` and `native/clocked_nan.c` provide the dependency-free C99
boundary for x86, x86_64, aarch64, ARM, RISC-V, ppc64 and wasm builds. They
encode/decode raw NaN16 in canonical byte order, produce five-part NANNET route
bytes/text, build `/v1/bootstrap/oidc` login bodies and Bearer headers, and
implement the 32-lane Boolean table. Network I/O remains the caller's transport.
See `native/README.md` and run `make -C native test`.

## Security

Never commit CLOCKED API keys, gateway admin tokens, participant tokens, private source corpora or raw customer responses. Use server-side secrets and scoped, expiring participant credentials. Raw evidence belongs in an ACL-protected scratch store under explicit retention rules, not in Git or minimized telemetry.

## Koyeb demo gateway and multi-instance auth

The root Dockerfile deploys the CLOCKED gateway as a persistent Koyeb web
service. The upstream `CLOCKED_API_KEY` remains in Koyeb secrets and is never
returned to participants. Demo clients obtain short-lived scoped tokens from
`POST /auth/demo-token` using the separate `CLOCKED_DEMO_ENROLLMENT_TOKEN`.

The token issuer atomically assigns the lowest free overbootstrap node point
in `9..255` to each active demo instance. Points `0..8` stay reserved. The
response explicitly reports `reserved_pending_nannet_registration`; a token
reservation is not represented as a completed NANNET registration or route
commit. Revoke an instance with the admin-only
`POST /admin/instances/revoke` route. See [Koyeb deployment and secret setup](deploy/koyeb/README.md).
