# NaNLMind_CLOCKED

CLOCKED by Rezolve.ai SDK integration, multi-endpoint orchestration, evidence packaging and the HERMES autonomous cognition bridge. The service adapter is hosted inside the existing NaNLMind Koyeb deployment.

## Canonical design documents

- [CLOCKED × NaNLMind × HERMES architecture brainstorm](docs/CLOCKED_HERMES_BRAINSTORM.md)
- [HERMES Autonomous CLOCKED Cognition and NaN Head Cortex](docs/HERMES_AUTONOMOUS_CLOCKED_HEAD_CORTEX.md)

## Repository boundary

- **This repository:** upstream CLOCKED SDK/API client, task graph, endpoint orchestration, request idempotency, quotas, credit accounting, fixtures and service tests; gateway source is maintained in NaNLMind's existing Koyeb service.
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

The Clocked gateway is embedded in the existing NaNLMind Koyeb NANNET service.
Do not deploy this repository as a separate Koyeb service. The existing
NaNLMind root Dockerfile installs the adapter from
`integrations/nannet/clocked_gateway.py` and mounts its routes in the existing
`integrations/nannet/server.py` process.

The upstream `CLOCKED_API_KEY` belongs in the existing NaNLMind Koyeb service's
secret environment and is never returned to participants. Demo clients obtain
a scoped CLOCKED token from `POST /auth/demo-token`; that same process calls
its own NANNET registration routes to allocate the lowest-free HW8–HW254 slot
(node points `9..255`). It returns scoped `clu_` and `nnt_` participant
credentials while keeping the upstream API key server-side. Revocation
disables CLOCKED access and asks the same NANNET allocator to release the lease.

Configure `NANNET_URL` as the public HTTPS origin of the existing NaNLMind
service itself. Configure the Clocked secrets listed in
[`integrations/nannet/README.md`](https://github.com/shemshallah/NaNLMind/blob/main/integrations/nannet/README.md).
There is one Koyeb service, one process and one persistent volume.

## Manually gated live demo workflow

After the existing NaNLMind Koyeb service has the Clocked secrets configured, run the
`CLOCKED live demo` GitHub Actions workflow with `confirm_live_calls=true`.
It uses the Actions-side `CLOCKED_API_KEY` for a one-request credential smoke
test, asks Koyeb for one scoped demo-instance token, builds the native learner
from the canonical NaNLMind repository, and runs the 48-training / 12-held-out
sample demo against Koyeb. The live job is disabled by default and requires an explicit manual confirmation because it makes billable upstream calls. The existing NaNLMind Koyeb service must have `NANNET_URL` set to its own public HTTPS origin and `NANLM_DEVICE_LEASE_SECONDS=21600` for the six-hour demo lease.

Add these GitHub Actions repository secrets:

- `CLOCKED_API_KEY` — upstream credential for the one-request Actions smoke test.
- `CLOCKED_GATEWAY_URL` — existing NaNLMind Koyeb service base URL (HTTPS).
- `CLOCKED_DEMO_ENROLLMENT_TOKEN` — same enrollment secret configured on Koyeb.
