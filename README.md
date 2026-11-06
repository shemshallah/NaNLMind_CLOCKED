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

## Security

Never commit CLOCKED API keys, gateway admin tokens, participant tokens, private source corpora or raw customer responses. Use server-side secrets and scoped, expiring participant credentials. Raw evidence belongs in an ACL-protected scratch store under explicit retention rules, not in Git or minimized telemetry.
