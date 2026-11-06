# CLOCKED service adapter

This directory contains the upstream Rezolve.ai CLOCKED SDK integration and the service-side gateway. It is owned by `shemshallah/NaNLMind_CLOCKED`.

The service translates authorized HERMES task plans into CLOCKED API calls and returns typed, provenance-bearing observations. It does not write to NaNLMind heads or commit training generations.

## Install

Python 3.9+:

```sh
python -m pip install -r integrations/clocked/requirements.txt
```

## Server-side secrets

- `CLOCKED_API_KEY`: upstream CLOCKED key, server-side only.
- `CLOCKED_GATEWAY_ADMIN_TOKEN`: separate gateway administrator credential.
- `CLOCKED_TOKEN_PEPPER`: random secret for participant-token hashing.
- `CLOCKED_GATEWAY_DB`: protected persistent database path.
- `CLOCKED_GATEWAY_HOST` and `CLOCKED_GATEWAY_PORT`: bind configuration.

Never expose the upstream key or admin token to HERMES, NaNNet, Android, user scratch, prompts, CLI arguments, logs or Git.

## Run locally

```sh
python integrations/clocked/gateway.py
```

Use HTTPS termination, persistent protected storage, monitoring and per-tenant quotas before exposing the service publicly. The built-in development server is not a production deployment configuration.

## Participant access

Issue short-lived scoped participant tokens through the admin interface. A participant token is a gateway credential only; it is not a wrapped CLOCKED key. The upstream CLOCKED key remains in the server secret environment.

The service enforces request limits, byte limits, idempotency and endpoint scope. Reuse the same idempotency key for retries of the same logical request. A key reused with a different body must fail with conflict.

## HERMES integration

HERMES should call the service through the versioned typed task-plan/execute contract described in [the autonomous cognition design](../../docs/HERMES_AUTONOMOUS_CLOCKED_HEAD_CORTEX.md). HERMES does not import the CLOCKED SDK or hold the upstream API key.

CLOCKED Pipeline is sequential and operates on one text input. HERMES multi-source orchestration uses separate typed calls and merges their results in a revisioned scratch; it must not pretend Pipeline is a parallel DAG.

## NaNLMind receiving side

The canonical NaNLMind event schemas, endpoint observation publisher, durable evidence consumer, native head demo and six-runner training topology remain in `shemshallah/NaNLMind`. See [the NaNLMind CLOCKED/NANNET bridge](https://github.com/shemshallah/NaNLMind/blob/main/docs/73_CLOCKED_NANNET_BRIDGE.md) and [chainable training contract](https://github.com/shemshallah/NaNLMind/blob/main/specs/CLOCKED_CHAINABLE_TRAINING.md).

The current native demo is a bounded task-family routing experiment, not a general language model or proof of production model improvement. Fixture results are simulated; live results must retain the actual CLOCKED receipt and cost metadata.

## Native NaNLMind routing demonstration

The native learner executable is intentionally built and owned by NaNLMind.
From a NaNLMind checkout, build it with:

```sh
make build/clocked-demo
```

Then run this repository's Python harness with the resulting binary path:

```sh
python integrations/clocked/demo.py --fixture \
  --native-binary /absolute/path/to/NaNLMind/build/clocked-demo
```

For a live run, omit `--fixture` and configure `CLOCKED_INTAKE_URL` plus a
scoped `CLOCKED_USER_API`. The harness never sends held-out examples to
CLOCKED. Only labels matching an independent gold label enter the native demo.
The C++ learner remains in NaNLMind because it directly exercises NaNLMind's
native routing/head implementation; this repository owns the service harness.
