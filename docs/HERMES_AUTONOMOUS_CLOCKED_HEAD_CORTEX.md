# HERMES Autonomous CLOCKED Cognition and NaN Head Cortex

**Status:** design specification; runtime implementation remains to be built  
**Service owner:** `shemshallah/NaNLMind_CLOCKED`  
**Conversational coordinator:** `shemshallah/NaNLMind_HERMES`  
**Canonical mathematical substrate:** `shemshallah/NaNLMind`  
**Rule:** CLOCKED owns the external API integration; NaNLMind owns the NaN-language contract, native heads and canonical learning state.

## 1. The integration boundary

The repository boundary is deliberate:

### CLOCKED repository owns
- Rezolve.ai CLOCKED SDK dependency and upstream API client.
- Upstream CLOCKED authentication, key custody and gateway.
- Endpoint planning/execution service, endpoint-specific request schemas and SDK-version pinning.
- CLOCKED request idempotency, retry semantics, credit/cost accounting and rate limits.
- Multi-endpoint orchestration helpers and the HERMES-facing CLOCKED API.
- CLOCKED-specific fixtures, synthetic demo corpora and service tests.
- Translation from upstream CLOCKED response types into a versioned, content-addressed evidence package.

### NaNLMind owns
- The canonical NaN16/NaN language protocol and evidence intake schema.
- The NANNET/NaNROUTER route, HW3:0 interface contract and authorization policy.
- The runner-side evidence consumer, durable receipt, generation compatibility and canonical commit path.
- The existing 256 Boolean-derived heads, HeadGate, LogicSessionTrainer, N16REL relation learner and M0-M9 transformations.
- The six-runner ring and all canonical model-state mutation.
- Independent evaluation and training promotion gates.

### HERMES owns
- User-facing chat and explicit CLOCKED mode.
- Autonomous mode selection and bounded planning.
- Scratch lifecycle, multi-source evidence reconciliation and source-aware synthesis.
- The local head-cortex client that submits a typed request to NaNLMind and receives a relation/evidence response.
- Natural-language rendering from the head response, followed by a final validation pass.

**Do not move NaNLMind head, Boolean, relation-training, runner-ring, or NANNET consumer code into this repository.** CLOCKED does not own NaNLMind's cognition or weights. The service returns evidence; NaNLMind transforms it.

## 2. Current code relocation decision

The service-side Python SDK adapter, upstream gateway, participant client, demo harness, synthetic sample set, SDK requirements and their service tests belong in this repository under `integrations/clocked/`.

The following remain in NaNLMind because they are the receiving-language contract or native learner side:
- `integrations/clocked/protocol.schema.json` and `endpoint-observation.schema.json` — canonical schemas consumed by NaNLMind.
- `integrations/clocked/endpoint_client.py` and its test — generic scoped publisher for the NaNLMind observation contract.
- `integrations/clocked/native_demo.cpp` — deliberately native NaNLMind head/routing demonstration, compiled against NaNLMind APIs.
- `integrations/clocked/training_endpoints.json` — registry of canonical training topology and endpoint roles.
- `runner/clocked_observation_consumer.py` and tests — NaNLMind-side durable evidence fold before queue acknowledgement.
- `docs/73_CLOCKED_NANNET_BRIDGE.md` and `specs/CLOCKED_CHAINABLE_TRAINING.md` — receiving-side trust and generation contracts.

The service repo may carry test fixtures and client-side mirrors of the schemas, but NaNLMind's checked-in schemas remain authoritative. A schema change requires a coordinated version bump and compatibility test in both repositories.

## 3. System shape

```text
                          USER / CLI
                              |
                              v
                      HERMES conversation
                              |
                    autonomous mode planner
                              |
                   bounded CLOCKED task graph
                              |
                    CLOCKED service gateway
                              |
                 +------------+-------------+
                 |            |             |
              DECIDE        EXTRACT       GROUND
              COMPARE       RERANK        PII/GUARD
                 |            |             |
                 +------------+-------------+
                              |
                    typed source observations
                              |
                    revisioned shared scratch
                              |
                    NaN16 evidence package
                              |
                HW3:0 / NANNET / NaNROUTER
                              |
                    NaNLMind M0-M9 pipeline
                              |
                     Boolean head cortex
                              |
                  relation graph + head trace
                              |
                    HERMES synthesis draft
                              |
                 final draft -> head validation
                              |
                       final response
                              |
                  optional learning proposal
                              |
            native evaluator / six-runner barrier
```

CLOCKED never writes directly to the heads. HERMES never commits native weights. The CLOCKED service never receives authority to alter routes, volumes, runner membership or canonical generations.

## 4. Autonomous mode selection

Modes are execution policies, not separate personalities or model instances. The conversation, memory, scratch and head topology remain shared.

| Mode | Selection signal | Operation |
|---|---|---|
| `LOCAL_CHAT` | Conversation, explanation, creative work; no external structured evidence needed | Local HERMES + optional local head check |
| `CLOCKED_CLASSIFY` | Task family, intent or decision criteria are unclear | Decide |
| `CLOCKED_EXTRACT` | Exact values, dates, fields or source spans are required | Extract / Fill |
| `CLOCKED_VERIFY` | Claims need checking against named source documents | Grounding |
| `CLOCKED_COMPARE` | Multiple sources or versions may disagree | Compare + claim-level reconciliation |
| `CLOCKED_RETRIEVE` | Many documents/passages need selection | Rerank, then targeted Extract/Ground |
| `CLOCKED_GUARDED` | Untrusted text, code, scripts, injection or sensitive data | PII / Injection / Script |
| `CLOCKED_MULTI_SOURCE` | The task needs independent API observations or source branches | Bounded fan-out task graph |
| `CLOCKED_PIPELINE` | A linear sequence over one text input is sufficient | CLOCKED Pipeline |
| `NAN_HEAD_REASON` | Boolean relations, implications, exceptions, consistency or symbolic structure dominate | NaNLMind head cortex |
| `HYBRID` | External evidence plus logical synthesis is useful | CLOCKED -> scratch -> NaN heads -> HERMES |

### 4.1 Planner design

Use a two-stage planner. The language model proposes a structured plan; deterministic policy validates it. Never let free-form model text call arbitrary endpoints.

The plan schema should include:
- intent class and desired answer contract;
- source references and source ACLs;
- candidate mode and concise rationale labels;
- endpoint operations, inputs, output schema IDs and dependencies;
- maximum calls, bytes, concurrency, wall time and credit budget;
- sensitivity classification and guard requirements;
- whether approval is required;
- idempotency scope and retry policy;
- required NaNLMind transformation profile and final head-validation profile.

Policy rejects cycles, unsupported endpoint fields, unapproved sources, budget overruns, missing credentials, stale capabilities and attempts to mutate canonical model state.

### 4.2 Autonomous call policy

Three explicit policies:
- `offline`: no upstream CLOCKED call;
- `approval`: propose the exact plan and wait for the user;
- `budgeted_auto`: execute within a user-configured per-turn/day credit and request budget.

Default should be approval until the user explicitly configures budgeted automatic use. HERMES may autonomously decide that CLOCKED would help, but this does not grant permission to spend credits or transmit sensitive data.

### 4.3 Mode-selection pseudocode

```text
intent = HERMES.analyze(user_turn, current_scratch_summary)
proposal = HERMES.propose_mode_and_task_graph(intent, capability_manifest)
plan = POLICY.validate(proposal, scopes, ACLs, budgets, schemas)

if plan.requires_approval and not approval_grant:
    scratch.append("plan", plan.preview)
    return ask_user_to_approve(plan.preview)

observations = CLOCKED_SERVICE.execute(plan)
scratch.append_each("clocked_result", observations)
```

Record the chosen mode, policy version, plan digest and reason codes. Do not expose private chain-of-thought; expose a short actionable explanation such as “Using Extract + Compare + Grounding because three source documents contain overlapping requirements.”

## 5. Multi-source CLOCKED task graph

CLOCKED Pipeline is a sequential 1–16 step operation over one text input. It is not a general multi-source DAG. HERMES should use separate endpoint calls for independent source branches and merge them only after preserving their native result types.

Example: compare four sources, extract requirements, resolve conflicts and produce a recommendation.

```text
                         QUESTION
                            |
                      HERMES PLAN
                            |
                      GUARD / PII
                            |
             +--------------+--------------+
             |              |              |
           SOURCE A       SOURCE B       SOURCE C/D
             |              |              |
          EXTRACT         EXTRACT         EXTRACT
             |              |              |
          GROUND          GROUND          GROUND
             +--------------+--------------+
                            |
                      COMPARE SOURCES
                            |
                     CLAIM NORMALIZATION
                            |
                      CLAIM CONFLICT MAP
                            |
                  QUERY-CONDITIONED RERANK
                            |
                  DECIDE USING EXPLICIT CRITERIA
                            |
                   GROUND EACH ANSWER CLAIM
                            |
                    SHARED SCRATCH REVISION
                            |
                     NaN HEAD CORTEX
```

Each branch has its own request ID, source digest, endpoint, schema version, idempotency key, status, timing, cost, retry count and output reference. Fan-out concurrency is bounded. A partial failure remains visible; it must not silently disappear from the synthesis.

### 5.1 Preserve type semantics

- Decide distributions are candidate decisions, not truth probabilities.
- Extract fields and spans are source evidence, not verified claims.
- Grounding verdicts are external support signals, not infallible truth.
- Compare results are candidate conflicts/duplicates, not proof of contradiction.
- Rerank scores express relevance under a query, not confidence in truth.
- PII/Injection/Script outputs are risk signals, not universal safety certificates.

Never average unlike scores into one “confidence” value. Keep endpoint-native confidence, calibration and score semantics separately typed.

### 5.2 Claim-level reconciliation

Convert each extracted/grounded item into a claim atom:
`claim_id, normalized_subject, predicate, object, polarity, qualifiers, source_ref, span, endpoint_ref, status`.

Build explicit edges:
- `supports`
- `contradicts`
- `qualifies`
- `duplicates`
- `derived_from`
- `temporally_supersedes`
- `missing_from`

A contradiction is not resolved by majority vote. Prefer authoritative, newer, directly applicable sources; retain unresolved conflict and abstain when the source hierarchy does not settle it.

## 6. Shared scratch: one coherent intermediate record

The scratch is the durable working object shared by user, HERMES, CLOCKED service and NaNLMind. It is revisioned, append-only and lane-separated.

| Lane | Writer | Contents |
|---|---|---|
| `user` | User | Question, corrections, supplied source references |
| `hermes_plan` | HERMES | Mode, plan, budget, endpoint graph |
| `clocked_request` | CLOCKED adapter | Immutable request snapshot and digest |
| `clocked_result` | CLOCKED service | Native typed outputs, receipt, status, cost and timing |
| `evidence_atoms` | Normalizer | Claims, fields, spans, source refs, provenance |
| `conflict_map` | Reconciler | Support, contradiction, qualification and missing edges |
| `nan16_package` | HERMES bridge | Canonical serialized package sent to NaNLMind |
| `head_response` | NaNLMind | M0-M9 outputs, active-head trace, relation graph, abstentions |
| `hermes_synthesis` | HERMES | Answer draft, source-linked reasoning summary, unresolved issues |
| `head_validation` | NaNLMind | Draft validation, contradiction/coverage flags, suggested corrections |
| `final` | HERMES | Final user-facing response |
| `learning_proposal` | HERMES / learner | Candidate training item, provenance and review status |

Every append carries scratch ID, expected revision, parent revision, lane, writer identity, schema, content digest, idempotency key and signature. Stale revision is a conflict, not permission to overwrite. Raw source text is stored only under an explicit retention/ACL policy; compact evidence refs and hashes go into the NaN16 package.

### 6.1 Typed scratch evidence object

```text
EvidenceAtom {
  atom_id
  source_id
  source_digest
  endpoint
  operation
  schema_version
  native_type
  exact_value_ref
  exact_span_start
  exact_span_end
  coordinate_system
  polarity
  qualifiers[]
  endpoint_score?
  endpoint_score_semantics?
  validation_state
  provenance_ref
  response_digest
  created_revision
}
```

Do not hash away the only copy of evidence needed to answer. The protected scratch stores permitted evidence values/spans; the NaNLMind endpoint telemetry remains content-minimized and contains only digests/allowlisted metadata. These are different storage products with different ACLs.

## 7. HERMES Head Cortex: reuse the NaN heads, not the runners

The request to “clone the runners and remove the runner code” should be implemented as a **head-cortex extraction**, not a fork of the six-runner system.

### 7.1 Reuse these NaNLMind primitives

- `HeadArray` / `HeadView` and `HeadRunner` from `head.hpp` / `head.cpp`.
- Boolean truth-table learner in each head.
- `HeadGate` relation gates and learned Boolean composition.
- `LogicSessionTrainer` as the prerequisite Boolean curriculum.
- `N16REL/1` and `relation_train.cpp` as the canonical relation-record format and native learner.
- Existing M0-M9 mapping and evidence/provenance rules.

Do not copy the head state or create a competing head implementation in HERMES. HERMES gets a lightweight **HeadCortexClient** and a local orchestration facade. The native NaNLMind service remains the sole owner of head objects and authoritative state.

### 7.2 What is removed from the runner pattern

The HERMES head cortex does not contain:
- six-runner membership or leader election;
- runner-to-runner synchronization;
- ring heartbeat, lease or shard ownership;
- distributed training barriers or generation commits;
- Koyeb volume administration;
- canonical checkpoint ownership;
- global route mutation or BSR control logic.

Those remain in NaNLMind/NaNROUTER/Koyeb. The head cortex only schedules bounded work against head IDs, gathers their relation outputs and returns a signed/digested result.

### 7.3 Cortex layout

```text
HermesHeadCortex
  |
  +-- IntentProjector
  +-- EvidenceAtomizer
  +-- M0TruthGate
  +-- M1ByteAndSpanMapper
  +-- M2TypeAndHeadRouter
  +-- M3FeatureProjector
  +-- M4TemporalMapper
  +-- M5RelationHypergraphBuilder
  +-- M6BooleanInference
  +-- M7ProvenanceAndRouteValidator
  +-- M8CrossSourceConsensus
  +-- M9MetacontrolAndCalibration
  |
  +-- HeadScheduler (256 logical IDs, no runner ownership)
  +-- RelationAssembler
  +-- MutationSandbox
  +-- ResponseSerializer
```

The 256 IDs remain the existing logical head namespace. Do not infer a head ID from HW3 selector, Router point 3, BSR wire ID or transport port. Explicit mapping tables only.

### 7.4 Per-head work contract

Each scheduled head receives a bounded typed packet:
`task_id, scratch_revision, input_digest, source_atom_refs, M-layer, relation_family, Boolean inputs, prior_generation, mutation_budget`.

It returns:
`head_id, input_digest, active_rule_id, Boolean outputs, relation_candidates, evidence_refs, confidence_type, abstention_reason, mutation_proposal_ref`.

A head cannot claim it verified a source or mutate another head's state directly. The scheduler verifies the packet/result digest and the native service records the actual active-head trace.

## 8. Ten transformation layers

The M0-M9 names below are a CLOCKED/HERMES task profile, not a replacement for the canonical NaNLMind layer definitions. Before implementation, bind each profile to the existing layer IDs and tests.

| Layer | Input transformation | Output |
|---|---|---|
| M0 | Boolean validity, truth-table checks, null/unknown distinction, contradiction detection | Truth/status atoms |
| M1 | UTF-8/byte boundaries, exact spans, offsets, token and source framing | Addressable evidence units |
| M2 | Typed endpoint schema and logical head-family routing | Typed head work packets |
| M3 | Deterministic feature/coordinate projection | Comparable feature vectors |
| M4 | Temporal ordering, versioning, event sequence and supersession | Temporal relation edges |
| M5 | Subject-predicate-object and hyperedge assembly | Evidence hypergraph |
| M6 | Boolean gates, implication, conjunction/disjunction, negation and bounded inference | Derived relation candidates |
| M7 | Source identity, ACL, signature, route generation and provenance checks | Trusted/untrusted partitions |
| M8 | Cross-source support, conflict and consensus analysis | Coherent relation graph with unresolved conflicts |
| M9 | Calibration, abstention, policy, mutation admission and learning metadata | Response/mutation decision |

The pipeline must preserve the distinction between:
- directly observed evidence;
- CLOCKED-derived candidate interpretations;
- NaNLMind-derived logical relations;
- independently verified outcomes;
- HERMES-generated natural-language synthesis.

No layer may silently upgrade an unverified observation into verified truth.

## 9. Boolean-derived mathematical relation mapping

The core cognitive mechanism should begin with Boolean truth tables, then compose learned gates into relations over evidence atoms. Do not ask the model to invent a relation and immediately believe it.

### 9.1 Primitive relation predicates

Examples:
- `A supports B`
- `A contradicts B`
- `A implies B`
- `A requires B`
- `A excludes B`
- `A temporally precedes B`
- `A is a qualified instance of B`
- `A is missing from source S`

Each relation has typed inputs and a truth state: `TRUE`, `FALSE`, `UNKNOWN`, or `CONFLICT`. Unknown is not false. Conflict is not averaged away.

### 9.2 Boolean relation composition

A candidate inference is represented as a small proof graph:
`premise atoms -> Boolean gate IDs -> intermediate relations -> conclusion atom`.

Every conclusion carries:
- premise atom IDs;
- gate/rule IDs and version;
- layer path M0-M9;
- source provenance refs;
- independent verification status;
- confidence semantics or explicit unknown;
- counterexample search status.

The Boolean gate can establish that a conclusion follows from premises under a rule. It cannot establish that the premises themselves are true. This is the key epistemic boundary.

### 9.3 Meta-mapping

The cortex maps *relations between relations*:
- same relation pattern across different source domains;
- contradiction pattern caused by time/version differences;
- shared prerequisites across multiple claims;
- a source that supports one premise but contradicts a dependent premise;
- a missing premise that prevents a conclusion;
- a Boolean proof shape that recurs in different tasks.

Store these as higher-order hyperedges with links to original proof graphs. Do not collapse distinct sources or domains into one unlabeled embedding.

## 10. Self-modifying heads with controlled evolution

“Self-modifying” should mean that heads can propose and test changes to their own Boolean rules, routing preferences and relation weights—not that they can rewrite arbitrary executable code or overwrite the canonical model during a user turn.

### 10.1 Mutation hierarchy

1. **Ephemeral adaptation:** per-turn scratch activations and task-specific temporary weights; discarded after the turn unless explicitly saved.
2. **Local candidate mutation:** a head proposes a change to its Boolean truth table, gate selection, relation-feature mapping or routing bias in an isolated candidate state.
3. **Cortex experiment:** multiple candidate heads are tested against the same train/validation/negative-control suite.
4. **Accepted local profile:** a candidate may be saved as a versioned noncanonical HERMES profile after passing local tests.
5. **Canonical promotion:** only NaNLMind's evaluator and six-runner generation barrier may promote changes into the shared canonical head state.

### 10.2 Mutation proposal contract

```text
HeadMutationProposal {
  proposal_id
  head_id
  base_head_digest
  base_generation
  target_rule_or_gate
  before_truth_table
  proposed_truth_table
  relation_feature_delta
  routing_bias_delta
  training_evidence_refs[]
  counterexamples[]
  expected_effect
  mutation_budget
  proposer_version
}
```

Mutation is rejected if the base digest is stale, the proposal changes a protected invariant, it uses unverified labels as correctness targets, or it exceeds its bounded budget.

### 10.3 Evaluation and promotion

Every mutation must pass:
- full Boolean truth-table regression;
- existing deep-logic circuit suite;
- positive examples and adversarial counterexamples;
- source-separated held-out examples;
- shuffled-label and random negative controls;
- no-CLOCKED baseline comparison;
- replay stability and deterministic digest checks;
- calibration/abstention checks where meaningful;
- regression tests for every previously passing relation family.

Keep the prior head state and a rollback pointer. Mutation is append-only and reversible. Never self-modify the canonical generation directly from the live chat path.

### 10.4 Anti-reward-hacking rule

CLOCKED agreement is not an independent reward signal when the outputs share the same upstream model. The head cannot optimize only for matching CLOCKED. Score candidates against independent gold, deterministic tests, authoritative source evidence and human review where required.

## 11. Two-pass head processing for the answer

This is the recommended response cycle because it ensures both the gathered evidence and the proposed answer are processed by the heads.

### Pass A — evidence cognition

1. HERMES completes the validated CLOCKED task graph.
2. HERMES appends all raw permitted outputs, source refs and typed metadata to the shared scratch.
3. The scratch revision is frozen as an immutable input snapshot.
4. HERMES serializes a NaN16 evidence package containing the user question, claim atoms, source spans/refs, result types, conflicts, endpoint provenance and policy metadata.
5. NaNLMind processes the package through M0-M9 and the Boolean head cortex.
6. NaNLMind returns a relation graph, proof references, head trace, confidence semantics, unresolved conflicts and abstentions.
7. HERMES synthesizes an answer draft from the evidence scratch plus the head result.

### Pass B — answer validation

1. HERMES appends the draft to `hermes_synthesis`.
2. It sends the draft and its claim-to-source map through the same NaNLMind interface as a new typed input, with task profile `ANSWER_VALIDATION`.
3. M0-M9 checks the answer's claims, source coverage, contradictions, unsupported leaps and uncertainty statements.
4. The heads return corrections/abstentions, not arbitrary prose.
5. HERMES applies only supported corrections, then appends the final answer to `final`.
6. The user receives the answer with citations/source references and unresolved issues clearly identified.

Do not loop indefinitely. Permit at most one automatic correction pass; further disagreement returns to the user or a bounded replan.

## 12. Learning pipeline

The interactive response path and the learning path must be distinct:

- Every interaction may produce a **candidate learning record** with source digests, prompt/plan version, CLOCKED output refs, head traces, HERMES draft/final digests and evaluation status.
- It does not automatically become a training example.
- Training admission requires provenance/license/consent checks and an independent target or review.
- A replay set is source-separated and never sent to CLOCKED during prompt tuning.
- Native NaNLMind training APIs transform accepted records; the six-runner ring validates and commits a candidate generation.
- CLOCKED output is a teacher observation, not a correctness label or gradient.

Recommended phases:
A. Boolean foundation and existing logic tests.
B. Freeze baseline head generation and fixed evaluation.
C. Generate CLOCKED observations on training split only.
D. Normalize observations into evidence atoms and N16REL records.
E. Train candidate relation profiles with the native learner.
F. Run held-out, negative-control and ablation evaluation.
G. Human review for ambiguous/high-impact examples.
H. Submit accepted candidate to the six-runner barrier; promote only on measured improvement.

## 13. HERMES CLI and controls

Keep current HERMES command parser and add a small command group that calls the same domain service as the GUI:

```text
/nanlm mode auto
/nanlm mode local
/nanlm mode clocked
/nanlm clocked status
/nanlm clocked capabilities
/nanlm clocked budget
/nanlm clocked scratch new
/nanlm clocked scratch show
/nanlm clocked plan
/nanlm clocked run
/nanlm clocked sources
/nanlm clocked synthesize
/nanlm heads inspect
/nanlm heads trace
/nanlm heads validate
/nanlm heads mutations
/nanlm heads mutation inspect <id>
/nanlm heads mutation test <id>
/nanlm heads mutation accept <id>
/nanlm heads mutation discard <id>
```

No CLI command should expose the upstream CLOCKED key or accept a user-supplied head delta.

## 14. Proposed service contracts

### HERMES -> CLOCKED service
`POST /v1/tasks/plan` and `POST /v1/tasks/execute` accept a schema-bound plan, scratch ID/revision, scoped HERMES identity, budget grant and idempotency key. CLOCKED service validates and runs only allowed operations.

### CLOCKED service -> HERMES
Returns typed operation receipts and content-addressed result refs. Full permitted values/spans are available only to the authorized scratch tenant; global telemetry remains minimized.

### HERMES -> NaNLMind
`POST /v1/cognition/transform` accepts a signed NaN16 package, scratch revision, input digest, transformation profile, requested M0-M9 stages and response budget. It does not accept model-state mutation commands.

### NaNLMind -> HERMES
Returns a signed/digested `NaNHeadResponse`:
`input_digest, base_generation, layer_receipts[], relation_graph_ref, proof_refs[], active_head_trace[], mutation_proposal_refs[], abstentions[], unresolved_conflicts[], response_digest`.

The exact route path is illustrative. It must be reconciled with existing NANNET API/versioning and HW3:0 routing; do not create a parallel route namespace.

## 15. Implementation sequence

1. **Repository ownership cleanup:** move CLOCKED SDK/gateway/demo service code into this repository; keep NaNLMind protocol, native heads, consumer and canonical trainer in NaNLMind.
2. **Contract freeze:** publish one versioned NaN16 evidence package and one NaN head response schema. Add compatibility fixtures.
3. **HERMES scratch:** implement revisioned lanes and content-addressed result references.
4. **CLOCKED task graph:** add bounded fan-out, dependency validation, typed endpoint outputs, idempotency and per-call cost receipts.
5. **Autonomous planner:** add schema-bound plan proposal and deterministic policy gate.
6. **NaN head-cortex API:** expose existing head/Boolean/relation learner through an inference-only interface; no runner code copied.
7. **Two-pass response:** evidence cognition then final-answer validation.
8. **Mutation sandbox:** candidate-only head mutations with complete Boolean and relation regressions.
9. **Learning admission:** separate interaction scratch from accepted training corpus.
10. **Six-runner promotion:** canonical generation barrier only after independent held-out evaluation.

## 16. Acceptance tests

- Local chat does not call CLOCKED.
- Auto mode selects CLOCKED only when a documented trigger applies.
- Approval and budgeted-auto policies enforce credit and byte limits.
- Multiple independent CLOCKED branches preserve individual source/endpoint identity.
- Pipeline is never misused as a parallel DAG.
- Partial failures and conflicts remain visible in scratch.
- Replaying an idempotency key cannot cause a second paid request.
- Scratch revision conflicts never overwrite another writer's lane.
- NaN16 package digest and source offsets round-trip exactly.
- M0-M9 emits typed receipts and preserves unknown/conflict distinctions.
- Boolean inference includes premise and gate proof references.
- HERMES sends both evidence package and final draft through NaNLMind.
- A head cannot claim source truth based only on its own Boolean consistency.
- Candidate self-modification is isolated, reversible and tested against negative controls.
- No CLOCKED service or HERMES client can commit canonical model state.
- Only the six-runner generation barrier can promote canonical head changes.
- Secrets never enter scratch, logs, prompts, fixtures or Git.

## 17. Non-goals

- No duplicate head universe in HERMES.
- No forked runner ring or six-runner orchestration in HERMES.
- No direct CLOCKED-to-head mutation.
- No self-editing executable code in production.
- No automatic promotion from unverified API output.
- No blending endpoint scores into an uncalibrated confidence number.
- No claim that a successful API response means the NaNLMind learner improved.
