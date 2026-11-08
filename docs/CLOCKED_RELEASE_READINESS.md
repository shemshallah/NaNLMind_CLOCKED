# CLOCKED release readiness and HW3:0 architecture update

**Verdict:** not ready to submit against the stated acceptance criteria.

The current system is ready for a live integration demo, not for a claim that
CLOCKED trains and improves a 255-head, 8 MiB universe behind `HW3:0`.

## What is actually verified

- `nannet.apps.mistral.run` is healthy.
- CLOCKED `/v1/experience` and `/v1/tasks` execute against the live upstream
  CLOCKED key.
- HERMES can plan, approve, execute, and retain typed CLOCKED observations.
- Live smoke: 11/11 repository checks pass.
- The six-runner NaNROUTER ring reports 6/6 slots in sync.
- The live head-cortex service answers read-only relation requests and creates
  isolated candidate states.
- Candidate evaluation is non-promoting and records baseline/candidate metrics.

## What is not verified

- No `HW3:0` service identity, registration, lease, or Route binding exists in
  the live service. `HW3` is reserved in `devices.py`, but the registry accepts
  only `android` and `hermes`; the live smoke device received `HW2`.
- No per-HW3 8 MiB universe is instantiated. The head-cortex service loads the
  existing serialized topology; it does not allocate or own an HW3 universe.
- No 255-head external port interface exists. Native candidate requests currently
  accept internal head indices `0..255`; there is no `HW3:1..255` port mapping.
- The six-runner ring is used for synchronization, but there is no completed
  canonical promotion through a generation barrier.
- The live smoke candidate evaluation is a one-row smoke test and returned
  `retain_baseline`; no training improvement has been demonstrated.
- The standalone CLOCKED CLI is a participant chat client. It does not boot an
  HW3 universe, orchestrate 255 head ports, or submit a candidate for canonical
  promotion.
- Head count terminology is inconsistent across repositories: some code still
  says 256 physical heads, while the newest HERMES work reserves head 0 and
  refers to 255 usable heads. The public contract must choose one vocabulary.

The 256/255 distinction must be explicit:

- **256 physical palindromic heads** exist in the chart.
- **Head 0** is the NaNNet/polarity anchor if that reservation is retained.
- **255 learned or externally addressable heads** are available to CLOCKED.
- `HW3:0` is the NANNET service interface, not one of the 255 learned heads.

## Target architecture

```text
CLI chat / API paste / scratch
          |
          v
CLOCKED participant gateway
  /v1/experience, /v1/tasks
          |
          v
HW3:0 NANNET service identity
  auth, session, route, receipt
          |
          v
CLOCKED runner (internal repository)
  boot 8 MiB universe
  bind head 0 anchor + 255 usable head ports
  load/save per-HW3 state
          |
          v
NaNLMind 8 MiB universe
  256 physical heads
  255 usable ports (HW3:1..255)
  native relation train/eval
          |
          v
candidate -> held-out evaluation -> six-runner barrier -> promotion
          |
          v
CLI review: metrics, head trace, diff, approve/reject
```

## Point-by-point TODO

### P0: contracts and identity

1. **Freeze head vocabulary.**
   - Define `physical_heads=256`, `anchor_head=0`, `usable_heads=255`.
   - Update all schemas, APIs, CLI help, docs, and tests that still assume
     every head is learnable.
   - Acceptance: schema test rejects `head_index=0` for learned-port requests
     when the anchor is reserved; accepts `1..255`.

2. **Define `HW3:0` contract.**
   - Add a versioned `nanlm.clocked-hw3/1` envelope for:
     session, auth reference, universe generation/digest, head-port request,
     input payload digest, output receipt, and error class.
   - State explicitly that `HW3:0` is transport/control and cannot mutate a
     learned head by itself.
   - Acceptance: schema examples and negative tests for role confusion.

3. **Add CLOCKED hardware identity.**
   - Extend `DeviceRegistry` with `hardware_kind=clocked`.
   - Reserve HW3 as a service identity, not a competing Hermes/Android lease.
   - Add registration/rotation/release tests; ensure HW2/HW4+ behavior is
     unchanged.
   - Acceptance: exactly one active HW3 CLOCKED identity; no duplicate lease.

4. **Bind HW3:0 through NaNROUTER.**
   - Add an explicit Router registry record: point 3 ↔ HW3 ↔ HW3:0 ↔ selected
     universe generation/digest.
   - Do not infer point 3 from head 3 or BSR wire 3.
   - Acceptance: signed route lookup resolves the service; stale generation is
     rejected.

### P0: 8 MiB universe and 255 ports

5. **Per-HW3 universe allocation.**
   - Add a CLOCKED runner that creates or restores exactly one 8,388,608-byte
     universe under a protected state path.
   - Persist seed, generation, digest, head-0 anchor, candidate directory, and
     restore receipt.
   - Acceptance: fresh boot and restart produce the same digest; memory proof
     shows one 8 MiB chart, not a second hidden universe.

6. **Head-port mapping.**
   - Implement `HW3:1..255` → internal learned head indices.
   - Provide a mapping table and a stable external port number independent of
     internal page placement.
   - Acceptance: round-trip route for all 255 ports; unmapped/0 ports fail
     closed.

7. **Input/output orchestration.**
   - Add a bounded head-port request:
     question, source digest, typed evidence, requested resolution, budget.
   - Return: per-port votes/relations, truth state, head trace, output digest,
     and a reviewable candidate record.
   - Acceptance: CLI can submit one source and receive 255-port results; no
     source text persists in telemetry.

8. **CLI boot handshake.**
   - The CLI must show:
     HW3 identity, universe generation/digest, 8 MiB state status, 255-port
     availability, and CLOCKED quota before accepting a chat turn.
   - Add `clocked boot`, `clocked status`, `clocked ports`, `clocked scratch`,
     and `clocked review`.
   - Acceptance: startup fails closed when HW3:0/universe/ports are unavailable.

### P0: training improvement

9. **Frozen training benchmark.**
   - Define a reproducible dataset with train/validation/test splits and
     independent labels.
   - Record dataset SHA-256 and prevent test rows from reaching CLOCKED or
     native training.
   - Acceptance: leakage test proves held-out rows never occur in training.

10. **Before/after metric.**
    - Train a candidate on the train split against the 255-head universe.
    - Evaluate baseline and candidate on the same frozen test split.
    - Report accuracy, balanced accuracy, coverage, utility, confusion, and
      per-resolution metrics.
    - Acceptance: candidate improvement is reproducible across at least three
      seeds; otherwise the gate says `retain_baseline`.

11. **Meaningful candidate promotion gate.**
    - Promotion requires:
      - a valid base generation/digest;
      - a candidate digest;
      - no canonical mutation during evaluation;
      - a positive, pre-registered utility delta over baseline;
      - six-runner generation-barrier agreement;
      - a signed promotion receipt.
    - Acceptance: a candidate that improves only on smoke data cannot promote.

### P1: CLI and API completeness

12. **Standalone CLI package.**
    - Ship `clocked` as an installable command with a stable entry point.
    - Add `--transport` selection for x86_64, aarch64, ARMv7 and RISC-V C
      bridge builds.
    - Keep the Python CLI portable; use the C bridge only for native
      NaN16/HW3 login and transport.
    - Acceptance: install-and-run test on each supported architecture.

13. **Chat/scratch workflow.**
    - Support:
      - `/paste`, `/source`, `/use`, `/copy`, `/review`;
      - `/experience`, `/tasks`, all ten endpoint names;
      - `/plan`, `/approve`, `/run`;
      - `/head`, `/ports`, `/candidate`, `/evaluate`, `/promote`;
      - `/health`, `/observations`, `/poll`, `/ack`.
    - Acceptance: one CLI transcript demonstrates paste → plan → API → scratch
      → 255-head review → candidate evaluation.

14. **Output review.**
    - Show CLOCKED raw results, typed evidence atoms, head trace, candidate
      diff, baseline/candidate metrics, and promotion refusal reasons.
    - Never collapse unlike CLOCKED scores into a single confidence value.
    - Acceptance: a rejection is as reviewable as a promotion.

### P1: operations and submission

15. **Live service wiring.**
    - Add HW3:0 route registration and an operator-visible readiness page.
    - Add health fields: HW3 identity, universe digest, 255-port count,
      generation, Clocked quota, and barrier state.
    - Acceptance: live smoke includes HW3:0 boot, 255-port request, candidate
      improvement or retain, and barrier receipt.

16. **Persistence and recovery.**
    - Store the 8 MiB universe and candidate manifests on protected `/data`.
    - Test restart, volume reattach, stale candidate, and corrupted digest.
    - Acceptance: restart resumes the exact universe; corruption fails closed.

17. **Submission evidence.**
    - Update plugin manifest/version, catalog admission, secret declarations,
      install instructions, demo transcript, live smoke, and changelog.
    - Include an explicit “not yet proven” section for any remaining limit.
    - Acceptance: no claim of general improvement, AGI, or full M0–M9
      autonomy without the measured gate.

## Definition of done

The submission gate is satisfied only when all of these are true:

```text
HW3:0 authenticated and routed
8 MiB universe created/restored at HW3
256 physical heads: head 0 anchor + 255 usable ports
CLI boots, chats, pastes, plans, executes, reviews
CLOCKED live results retained in scratch
255-port head request returns typed output
candidate trains on train split only
held-out baseline vs candidate metrics recorded
positive improvement reproducible, or honest retain_baseline
six-runner barrier promotion receipt verified
no canonical mutation outside promotion
restart preserves universe generation and digest
```

Until the training and HW3:0 rows pass, this is a successful **integration
demo**, not a complete CLOCKED plugin submission.
