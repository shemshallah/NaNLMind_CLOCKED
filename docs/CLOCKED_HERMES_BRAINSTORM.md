# CLOCKED × NaNLMind × HERMES — Deep Integration Brainstorm

**Design status:** architecture / pseudocode only; no runtime implementation in this round  
**Intended project:** `NaNLMind_CLOCKED`  
**Canonical location:** `shemshallah/NaNLMind_CLOCKED/docs/CLOCKED_HERMES_BRAINSTORM.md`  
**HERMES consumer:** `shemshallah/NaNLMind_HERMES`  
**Service:** [CLOCKED by Rezolve.ai](https://clocked.rezolve.ai/)  
**API origin documented by the official SDK:** `https://clocked.rezolve.ai/clocked`

## 0. Executive position

Build a CLOCKED-specialized learning and evidence universe as a **coherent extension of the one NaNLMind topology**, with a separately addressable HW3 service identity and a dedicated CLOCKED NANNET ingress at **HW3:0**. Give HERMES a first-class CLOCKED mode, but keep the CLOCKED adapter and mathematical learning substrate reusable outside HERMES.

The project is not to clone or fine-tune CLOCKED's model. CLOCKED is a hosted structured-reasoning API. Its value is that it returns typed judgments and evidence: decisions and probability distributions, verbatim extractions with source spans, completed records, privacy findings, injection/script safety assessments, grounding checks, document comparisons, and relevance rankings. NaNLMind should learn the *structure, relationships, transformations, retrieval patterns, calibration behavior, and task-specific logic* of those interactions. It must preserve the distinction between an API observation, an independently verified fact, and a learned prediction.

The design has six central ideas:

1. **HW3 is the CLOCKED service address/identity. HW3:0 is its NANNET interface.** HW3:1–255 are externally addressable logical head ports, mapped by explicit Router registry records into the existing 256-head mathematical topology. The port namespace must not be confused with Router node points, BSR wire IDs, or internal head indices.
2. **Use the existing 8 MiB NaN register chart and its exact mirror-pair algebra.** Map tokens, evidence spans, field/value relations, decisions, probabilities, provenance and transformations down to bit-addressable registers. Use the existing extension/scratch regions for compact metadata and references; store large raw content and durable artifacts on the appropriate registered data volume.
3. **Keep the existing ten mathematical layers M0–M9.** Do not invent a competing ten-layer stack. Add CLOCKED-specific projections, codecs and learning objectives within those layers. A CLOCKED observation should be traceable from raw byte and token positions through heads, pair cells, vector bins, temporal rails, hyperedges, logic, route, merge and meta-policy.
4. **Logic-first pretraining, then CLOCKED interaction training.** First pass the deterministic Boolean/formal-logic foundation gates and existing reasoning controls. Then ingest CLOCKED examples and outputs as typed teacher observations, train task-specific local representations, and evaluate against CLOCKED, non-CLOCKED baselines and frozen held-out cases.
5. **A persistent scratch is the interaction workbench.** The user writes into it; HERMES reads and extends it; CLOCKED is called against selected snapshots; multiple CLOCKED results are normalized and synthesized; NaNLMind reads the same immutable evidence revisions and appends its response into a separate lane; HERMES presents and continues the loop.
6. **NaN16/NaNnet-first semantics.** The CLOCKED project may use a thin Python SDK adapter where that is the most practical boundary, but NaN16 owns guest-side protocol state, address transformations, deterministic mapping, scratch transitions, validation and learning semantics. C/C++ or Python must not become a second semantic implementation.

The expected result is not “a chatbot that calls CLOCKED.” It is a CLOCKED-specialized, auditable, addressable evidence-and-reasoning memory system, operated by HERMES and routed through NaNNet/NaNROUTER/Koyeb/Runner Ring.

---

## 1. What CLOCKED actually supplies

### 1.1 Service contract and SDK facts

The public CLOCKED developer surface is at `https://clocked.rezolve.ai/docs`; the challenge page is `https://clocked.rezolve.ai/challenge#submit`. The public docs page was not directly readable by the web fetcher in this research session, so the official `clocked-sdk` package README is used as the accessible API reference. Pin and re-check the official docs and SDK version before implementation.

The official Python package is named **`clocked-sdk`**, imported as `clocked_sdk`; do not confuse it with the unrelated PyPI package named `clocked`. The current package documentation identifies version 0.7.0 and ten client methods: nine task endpoints plus Pipeline.

| SDK method | CLOCKED capability | Structured result to preserve | NaNLMind learning use |
|---|---|---|---|
| `decide` | Decide | typed yes/no, choice, multiselect or score answers; probability/confidence fields | decision boundary, criteria, uncertainty and alternative outcomes |
| `extract` | Extract | verbatim field values, list items, source offsets/spans | source-grounded token/byte alignment and field-value binding |
| `fill` | Fill | completed structured record, typed field outcomes | schema completion, field dependency and missingness patterns |
| `pii` | Protect | entity types, detected spans, anonymized/transformed text | sensitive-span recognition and reversible/irreversible transform metadata |
| `injection` | Guard | verdict and injection evidence | adversarial instruction boundary, source trust and threat features |
| `script` | Inspect | script verdict, risk/evidence | code-operation classification and safety logic |
| `grounding` | Verify | claim-level support/evidence and answer support verdict | claim-source graph, entailment/support/refutation and evidence alignment |
| `compare` | Compare | duplicates, conflicts and document relationships | contradiction, equivalence, version drift and source reconciliation |
| `rerank` | Rerank | ordered documents, use/expand/skip, relevance/document scores, probability levels | query-conditioned retrieval and ranking calibration |
| `pipeline` | Pipeline | ordered named endpoint steps, per-step status/timing/result, stop behavior | multi-stage observation graph and causal task sequencing |

The developer material also describes image support for most endpoints, PDF input for most endpoints, optional marked PDFs, and source offsets for extraction/evidence. The SDK's Pipeline can execute 1–16 sequential steps over one text input as one request/admission; steps can stop on guard verdicts. It is not a general arbitrary graph executor: only the documented sequential pipeline semantics should be assumed.

### 1.2 What this means for NaNLMind

CLOCKED's outputs are not ordinary free-form assistant paragraphs. They are **typed observations**. Treat each response as a bundle of typed evidence atoms, not as one string to tokenize and throw into a language learner.

Examples:

- A Decide response is a set of named questions, answer types, criteria, alternatives and probability mass. Store the complete distribution when provided, not just the winning label.
- An Extract response is a set of exact source substrings plus source positions. The span is a first-class reference to the input bytes, not merely a string copied into a corpus.
- A PII result contains detection and transformation semantics. The redacted/anonymized output must not overwrite the raw source evidence.
- Injection and Script results are security judgments. Keep the source class, evidence, threshold and verdict together.
- Grounding returns evidence per claim. A supported claim is not a general truth certificate; it is supported by the supplied documents under that request.
- Compare returns relationships among documents, including duplicates and conflicts. Preserve document identity and passage alignment.
- Rerank gives query-dependent relevance and skip/expand/use actions. Do not turn a relevance score into a universal semantic similarity.
- Pipeline results are a causal sequence of steps. Store each step separately and preserve the stop/error/skipped states.

### 1.3 CLOCKED is a teacher/assessor, not NaNLMind's memory

Keep four states distinct:

1. **Observed:** exact input and raw CLOCKED response, identified by request key and digest.
2. **Normalized:** parsed, schema-validated evidence atoms with offsets and provenance.
3. **Learned:** local NaNLMind representation or predictor updated from the observation.
4. **Verified:** an outcome independently confirmed by a source, human decision, deterministic rule, or downstream event.

A CLOCKED response can be a high-quality teacher label, but it is not automatically an independently verified fact. Store teacher agreement and external correctness separately. For a decision with no external outcome, the local model may learn to imitate the CLOCKED decision distribution; it may not claim calibrated real-world correctness from agreement alone.

---

## 1.4 Existing CLOCKED-named pipeline work — important distinction

NaNLMind already has `docs/80_TRAINING_CORPUS_PIPELINE.md` and
`docs/81_CONVERSATIONAL_TRAINING_LOOP.md`. The corpus pipeline describes a
`ClockedAdapter` in `runner/hermes_pipeline.py` that attaches a training
session to an epoch/clock value and reuses the existing `training` runner
operation. The conversation trainer already loops model intent → staged
pipeline → metrics → reflection.

That is useful groundwork for the temporal/session side of this proposal, but
it is **not the Rezolve.ai CLOCKED API adapter**. Do not conflate the existing
logical-clock/session adapter with the hosted service. The new service adapter
must have a distinct name (for example `RezolveClockedClient` or
`ClockedApiAdapter`) and preserve the existing logical clock as a separate
NaNLMind subsystem. Reuse the current HERMES corpus pipeline and conversation
trainer where their contracts fit; do not replace them with a second corpus
generator or a duplicate conversation loop.

The current HERMES `MemoryStore`, native relation learner, mandatory Boolean
foundation, frozen L0–L9 challenges and native mutation receipts are also
existing integration points. CLOCKED-specific observations should extend
these same stores/topology through a typed evidence codec, not create a
parallel student or a parallel evidence ledger.

---

## 2. System boundaries and repository responsibilities

### 2.1 Proposed repository: NaNLMind_CLOCKED

Create a dedicated repository named **`NaNLMind_CLOCKED`** as the domain-specific adapter, experiment, schema and learning design home. It should not fork the NaNLMind engine or duplicate the HERMES plugin.

Proposed ownership:

| Repository/system | Owns |
|---|---|
| `NaNLMind_CLOCKED` | CLOCKED API adapter contract, typed response codec, CLOCKED-specific NaN16 mappings, scratch protocol extensions, learning objectives, CLI, evaluation corpus, experiment manifests and service integration |
| `NaNLMind` | one canonical topology, 8 MiB register chart, 256 internal heads, mirror algebra, temporal clock, hypergraph, training primitives, global ledger and native runner |
| `NaNLMind_HERMES` | user interaction, chat/CLOCKED modes, prompt construction, scratch authoring UX, orchestration, user consent and plugin-facing tools |
| `NaNROUTER` | point/HW binding, route compilation, ACLs, generation-chained cache, head/object associations, Koyeb volume registry and health |
| `NaN0S` | NaN16 guest protocol, codecs, CLI state machines and NaN-native guest implementation |
| `NaNLMind_android` | phone-side NANNET endpoint/client and future CLOCKED scratch viewing or authoring, subject to actual N16T feature support |
| Koyeb | persistent ingress/egress gateway and registered volume mounts; not the model runner and not the canonical semantic learner |
| MC0:0 / six-runner ring | head computation, phase barriers, packet handoff, merge validation and checkpoint coordination |

### 2.2 No parallel semantic topology

NaNLMind_CLOCKED is a *domain projection and training profile* over the one NaNLMind topology. It may have its own namespace, dataset manifests, task queues, scratch IDs, calibration tables and experimental checkpoints. It must not create a separate competing 256-head brain, private ledger or second global semantic store.

The demo can be isolated at the service/tenant/ACL/data layer while still using the canonical NaNLMind substrate. If the product owner requires a physically separate demo topology, that is a separate deployment decision with explicit identity and synchronization rules; it must not be inferred from a demo route or a folder name.

---

## 3. HW3 addressing: service endpoint and head ports

### 3.1 Namespace model

The target convention is:

- **HW3** — the registered hardware/service identity for the CLOCKED integration.
- **HW3:0** — the CLOCKED NANNET interface/control endpoint.
- **HW3:1–HW3:255** — logical head ports for CLOCKED-specific work and memory access.

This is an explicit *HW selector namespace*. It is not interchangeable with:

- NaNROUTER node point 3 (the already documented Clocked demo point);
- BSR0–BSR5 (six runner wire identities);
- the one-based BSR display labels;
- internal NaNLMind head indices 0–255;
- Koyeb volume logical addresses such as BS0/MC0/SC0/GM0;
- physical mount paths or provider volume IDs.

The current Router point map already assigns node point 3 to the Clocked demo, and the HERMES README reserves HW3 for the Clocked demo identity. Those two facts are compatible but are not the same address field. The Router must hold an explicit binding record connecting the Clocked service identity, node point 3, HW3, the NANNET endpoint and the selected demo universe.

### 3.2 HW3:0 must be transport/control, not a learned head

HW3:0 is the NANNET ingress/egress interface. It handles:

- authenticated HELLO/CAPABILITIES and service discovery;
- request/response framing;
- route resolution and signed micro-route packets;
- bounded mailbox/queue operations;
- scratch references and append requests;
- task submission, lease/status, ACK and receipt delivery;
- CLOCKED API adapter dispatch or proxy routing;
- service health, quota metadata and capability manifest;
- version negotiation and protocol errors.

HW3:0 should not be treated as one of the 256 semantic heads. It is an interface selector in the HW3 service namespace. It must not mutate head state merely because a packet arrived.

### 3.3 HW3:1–255 are logical head ports, not assumed physical cores

The 255 ports should be stable external selectors that Router resolves to one or more internal head IDs, mirror-pair ranges, scratch windows or task roles. They are not 255 new heads and they do not replace the existing 256-head table.

Do not implement the mapping as `port == internal_head` by numerical coincidence. The current topology reserves BSR/control heads 0, 4, 5, 6, 7 and 8, and distributes all 256 internal heads across six runners with `owner(head) = head mod 6`. The port registry must preserve those constraints.

Recommended record:

```text
HW3HeadPort {
  hw_identity: HW3
  port: 1..255
  target_universe_ref
  internal_head_refs[]        // explicit, can be one-to-many
  pair_range_refs[]
  layer_mask                  // M0..M9 permissions
  task_roles[]                // e.g. extract, decide, grounding, synthesis
  runner_placement_policy     // scheduler-selected, not hard-coded by HERMES
  read_capability
  write_capability
  lease_policy
  generation
  route_digest
  acl_digest
}
```

A port can select a task role while the scheduler fans the work across several heads. One head may participate in more than one task role. All 256 internal heads remain addressable through their canonical internal references, even though the external HW3 service-port range is 1–255.

### 3.4 Proposed logical grouping

Start with role *hints*, not permanent partitions. A reasonable first mapping is:

| Role group | Work |
|---|---|
| ingress/guard | byte framing, source typing, injection and script risk evidence |
| extract/align | tokenization, exact spans, offsets, field-value anchors |
| decide/calibrate | question schema, alternatives, probability vectors, confidence |
| fill/schema | record completion, required/optional fields, missing values |
| ground/compare | claims, support/refutation, duplicate/conflict links |
| rerank/retrieve | query-document relations, use/expand/skip and score profiles |
| temporal/sequence | interaction order, revisions, pipeline step dependencies |
| hypergraph/synthesis | multi-result evidence composition and contradiction retention |
| meta/validation | schema, digest, calibration, provenance and cross-layer consistency |

The exact 255-port allocation should be derived from measured task load and the existing runner map. Do not reserve hundreds of heads to named API methods before measuring their overlap and concurrency.

---

## 4. Bit-addressable CLOCKED memory using mirror pairs

### 4.1 Preserve the existing address algebra

NaNLMind already defines a 16-bit local address space:

```text
A = {0,1}^16
R(x) = reverse16(x)
C(x) = min(x, R(x))
```

Bit reversal and byte swap are involutions and commute. The mirror quotient has 32,896 canonical classes per chart: 32,640 off-diagonal mirror pairs and 256 fixed-point heads. The mapping

```text
addr(a,b) = (a << 8) | reverse8(b)
R(addr(a,b)) = addr(b,a)
```

makes mirror reversal exactly matrix transposition on the 256×256 head grid. For a pair `(a,b)`, the forward and reverse rails are independent; the fixed diagonal `(a,a)` anchors a head.

Use this exact existing algebra. Do not invent a second CLOCKED-specific mirror transform.

### 4.2 Four NaN words carry direction and validation

The canonical pair/head register already contains four NaN16 words:

- `s+`: forward rail;
- `s-`: reverse rail;
- `q+`: forward shadow/validation;
- `q-`: reverse shadow/validation.

The four legal NaN classes and the 16 Boolean functions are already defined in the mathematical structure. The pair register also contains the operator mask, selected rule, epoch, generation, owner and metadata.

CLOCKED-specific design should assign *typed meanings* to those existing fields and side tables. It must not overload the IEEE sign/payload bits with undocumented application semantics. Keep a versioned codec from CLOCKED evidence atoms to NaN16 word patterns, and keep the canonical structured record in the ledger for audit/replay.

### 4.3 Exact source offsets must survive tokenization

CLOCKED Extract and Grounding can return source offsets. Tokenization must therefore be offset-preserving:

```text
source bytes
  -> UTF-8 validation (reject malformed input; never silently repair)
  -> codepoint boundary table
  -> byte-preserving lexical tokens
  -> token/subtoken/nibble/bit views
  -> source-span map: token_ref -> [byte_start, byte_end)
```

Never normalize, lowercase, strip whitespace, normalize Unicode, or reflow the source before recording its canonical byte digest and source-offset coordinate system. A separate normalized view may be created for search, but every normalized token must point back to the exact raw source span. When CLOCKED returns offsets, validate them against the exact submitted representation and record whether the offset unit is bytes, code points or another documented unit. Never assume without checking.

### 4.4 Token-to-pair address mapping

Use deterministic, reversible *indexing* rather than a lossy hash-only address assignment:

1. Compute a stable source/object identity digest.
2. Assign each source, request, document, field, token, span, decision and claim a typed object reference.
3. Derive a 16-bit candidate local address from the object identity plus layer/domain salt.
4. Canonicalize to `C(x)`; record whether the caller addressed the canonical or mirrored orientation.
5. Resolve through the address register and canonical index table.
6. If an address is occupied by a different typed object, use collision-chain/overflow metadata or allocate a secondary sparse reference. Never alias two objects because their 16-bit candidates collide.
7. Write the forward relation to `s+`; reverse lookup uses `s-`; `q+`/`q-` hold independently computed validation or shadow evidence.
8. Store exact provenance and object identity in the ledger/hyperedge side tables.

The 16-bit address is a local coordinate, not a globally unique object ID. Full identity is the tuple of universe/chart path, canonical address, generation, object type and stable object reference.

### 4.5 Map evidence, not just words

Examples of useful pair relationships:

- token ↔ token (co-occurrence, adjacency, dependency);
- token ↔ field name (schema role);
- field ↔ extracted span (exact provenance);
- span ↔ source document (origin);
- claim ↔ supporting passage (grounding);
- claim ↔ contradicting passage (conflict);
- query ↔ document (rerank evidence);
- decision ↔ criterion (decision rationale);
- decision ↔ alternative (probability distribution);
- injection evidence ↔ source trust class;
- pipeline step ↔ prior/next step;
- scratch revision ↔ CLOCKED request/result;
- local prediction ↔ CLOCKED teacher distribution;
- local prediction ↔ independently observed outcome.

These relations are naturally n-ary. Store them as typed hyperedges, not only pairwise co-occurrence. For example, a single Extract atom should connect source, request, field, exact span, returned value, schema, and response digest in one hyperedge.

---

## 5. Use the existing 8 MiB register chart intelligently

### 5.1 Do not invent another 8 MiB brain

The existing register-file document specifies one 8 MiB chart with:

- 65,536 address registers × 32 bytes;
- 32,896 shared pair/head registers × 64 bytes;
- 32,896 descriptors × 48 bytes;
- 256 head records;
- adjacency bitmap;
- dirty maps and checksums;
- 256 × 1 KiB head scratchpads;
- 64 KiB chart scratch;
- approximately 1.77 MiB extension area for head scratch, hyperedges, mailboxes and future metadata.

The precise offsets and sizes are in `NaNLMind/docs/04_REGISTER_FILE.md`. Keep that format authoritative. CLOCKED should be a versioned overlay/profile in the available extension region, not a new independent 8 MiB image or an unbounded allocation.

### 5.2 Proposed extension-region allocation

Treat the approximately 1.77 MiB extension as a bounded metadata/cache arena, with a versioned descriptor and measured quotas. An initial *budget proposal* (not yet a committed binary layout):

| Extension class | Initial budget | Contents |
|---|---:|---|
| CLOCKED object directory | 192 KiB | typed refs, address resolution, compact object descriptors |
| evidence/span index | 320 KiB | source spans, token refs, field/claim anchors |
| probability/calibration metadata | 128 KiB | quantized distributions, thresholds, calibration buckets |
| task/pipeline graph metadata | 192 KiB | request IDs, step edges, task states, dependency indexes |
| scratch hot-window metadata | 256 KiB | active scratch revisions, lane offsets, CAS and lease metadata |
| hyperedge staging | 256 KiB | bounded n-ary evidence relations pending ledger commit |
| NANNET mailbox/receipt cache | 128 KiB | bounded frames, idempotency records, ACK/receipt summaries |
| transform/codec registry | 96 KiB | M0–M9 mapping profile IDs, versions, transform parameters |
| validation/shadow metadata | 96 KiB | q-rail comparison summaries, checksum/validation flags |
| reserve | 100 KiB | future compatibility and fragmentation margin |
| **Total** | **1,764 KiB** | Must be reconciled to the actual extension allocator before use |

This budget is deliberately conservative and provisional. It does not replace the register-file offsets or prove that every region is physically free in the deployed build. The exact allocator, alignment, reserved bytes, maximum entry sizes and compaction policy must be verified against the current implementation.

### 5.3 What belongs in the register versus persistent volumes

**Register chart / extra register:**
- compact object references and type tags;
- bit-level and pair-level mappings;
- token/span indexes;
- small probability vectors or quantized calibration summaries;
- hyperedge descriptors and IDs;
- task/pipeline dependencies;
- scratch hot-window indexes and CAS metadata;
- provenance digests, generation and lease references;
- NaN16 transformation state.

**Persistent data volume / object storage / HERMES state:**
- full original documents, PDFs and images;
- full raw CLOCKED request and response JSON;
- full scratch content and long transcripts;
- marked/redacted PDFs;
- large corpora and train/validation/test artifacts;
- experiment logs and complete receipts.

The register stores the mathematical *map into* the data, not every byte of every document. Large data should be addressed by immutable object references and SHA-256 digests.

### 5.4 Scratch and Koyeb placement

NaNROUTER owns the physical-to-logical Koyeb volume binding and health. The existing logical volume identities and mount roots are already specified. Proposed placement, subject to the live registry and ACL:

- **BS0**: HW3:0 NANNET ingress/egress, auth/session routing, bounded queue and receipt cache.
- **MC0**: Runner Ring handoff metadata, leases, checkpoints and per-epoch packet coordination.
- **SC0**: CLOCKED demo scratch objects, normalized evidence objects and bounded experiment artifacts.
- **GM0**: global registry/index metadata only where the owning service grants access; never a casual scratch bucket.

Do not hardcode Koyeb provider IDs or mount roots in HERMES or NaNLMind_CLOCKED. Do not report green unless the signed Router volume observation says both `health=green` and `mount_verified=true`.

---

## 6. The ten mathematical layers: CLOCKED profile

Use the existing M0–M9 mapping layers in NaNROUTER. They are ten mappings inside one universe, not ten separate minds. Add CLOCKED-specific semantics as a profile:

| Layer | Existing mathematical role | CLOCKED-specific mapping | Example object |
|---|---|---|---|
| **M0** | bit identity / Boolean truth | raw byte bits, NaN16 class, truth-table features, bit masks, exact flags | one source byte or verdict bit |
| **M1** | byte/word composition | UTF-8 code units, nibble/byte tokens, field names, typed scalar packing | token and field-value atom |
| **M2** | head/address binding | bind evidence classes, source positions and task roles to explicit head/pair refs | Extract span → pair address |
| **M3** | vector/bin mapping | sparse evidence vectors, probability vectors, retrieval bins, feature quantization | Decide distribution / Rerank scores |
| **M4** | temporal sequence | user/scratch revisions, API request order, Pipeline steps, result timing and logical stamps | scratch revision chain |
| **M5** | hyperedge mapping | source + span + field + claim + evidence + request/result relations | grounded extraction hyperedge |
| **M6** | logic/rule mapping | decision criteria, alternatives, truth constraints, entailment/support/refute, policy rules | Decide criterion proof graph |
| **M7** | route mapping | HW3 ports, NANNET frame, Router point 3, BSR runner placement, object routes | HW3:0 → CLOCKED adapter |
| **M8** | merge/consensus mapping | multiple CLOCKED calls, repeated evidence, conflict retention, confidence/calibration and merge proposals | multi-source synthesis |
| **M9** | meta-map/policy | provenance, ACL, trust, cost/quota, model-vs-teacher-vs-fact status, cross-layer invariants | final verified synthesis receipt |

### 6.1 Layer invariants

- Every layer object has a versioned type, source reference and digest.
- M0/M1 must preserve exact source bytes and offsets.
- M2 must resolve through the canonical address directory, not hash collisions.
- M3 scores are task-conditioned and calibrated only against an identified outcome set.
- M4 orders events with the canonical logical clock and ledger sequence; wall time is separate.
- M5 preserves contradictions and multiple provenance paths.
- M6 does not turn probabilistic judgments into formal proofs.
- M7 resolves only committed Router routes and signed ACLs.
- M8 never silently averages away contradictory sources.
- M9 is a policy/consistency layer, not a magic all-purpose confidence score.

### 6.2 Transform chain

A single CLOCKED response should pass through an explicit, replayable transform chain:

```text
raw input bytes
  -> UTF-8 + byte-offset validation
  -> typed tokenization
  -> endpoint-specific response parser
  -> evidence atom normalization
  -> M0 bit/flag representation
  -> M1 token/field/span composition
  -> M2 head + canonical mirror-pair binding
  -> M3 sparse vector / probability representation
  -> M4 temporal and pipeline linkage
  -> M5 n-ary evidence hyperedges
  -> M6 criteria / logic / support constraints
  -> M7 authorized route and object location
  -> M8 multi-call synthesis / conflict-aware merge
  -> M9 trust, provenance, policy and calibration checks
  -> immutable event + native learning proposal
```

Each transform emits an input digest, output digest, transform version, parameters, and validation status. If any transform is not reversible, record the before-image or immutable source object reference. The shadow rails should hold independently recomputed checks, not merely copies of the primary result.

---

## 7. CLOCKED-specific learning style

### 7.1 Do not train a generic next-token model on CLOCKED JSON

A naïve approach would concatenate API inputs and JSON outputs into text and train the existing byte predictor. That would discard the most useful information: types, offsets, probability distributions, source-document IDs, evidence links, and pipeline dependencies.

Instead, use **typed observation learning**. The model learns to predict and associate CLOCKED structures:

- Which evidence atoms belong together?
- Which source spans support a returned field?
- Which criterion distinguishes two decision alternatives?
- How does a probability distribution change with a new evidence atom?
- Which document should be used, expanded or skipped for a query?
- Which claims are supported, contradicted or not covered by the supplied documents?
- Which pipeline stage should follow a prior stage?
- When should a local prediction abstain and ask CLOCKED or a human?
- Which output properties are invariant under byte-preserving or mirror transformations?

A byte-level language objective can remain a supporting objective, but it is not the primary CLOCKED learning target.

### 7.2 Stage A — logic foundation before CLOCKED training

Run the existing mandatory Boolean foundation and formal reasoning curriculum before accepting CLOCKED teacher examples as training updates.

**A0 — deterministic Boolean gate**
- all 16 Boolean functions;
- XOR, AND, OR, NAND, NOR, implication and equivalence;
- mirror/transpose identities;
- truth-table round-trip;
- exact integer score learning.

**A1 — propositional and relational logic**
- modus ponens, modus tollens, hypothetical syllogism;
- Barbara syllogism and transitivity;
- contradiction containment;
- polarity and negation;
- incomplete/unknown evidence remains unknown.

**A2 — source/evidence logic**
- exact span-to-source binding;
- claim-to-evidence support/refutation;
- no source, no provenance;
- conflicting evidence retained rather than collapsed;
- distinction between absence of evidence and evidence of absence.

**A3 — task logic**
- decision criteria and alternatives;
- multi-label/multiselect constraints;
- threshold and abstention behavior;
- ranking order and score monotonicity tests;
- Pipeline dependency and stop-condition logic.

**A4 — frozen logic challenge**
- deterministic held-out tests across all ten layers;
- proof and puzzle controls already present in NaNLMind;
- cross-run same-digest comparability;
- no CLOCKED examples in this foundation split.

Only when these gates pass should CLOCKED observations enter the CLOCKED-specific training phase. The logic foundation must remain an immutable parent checkpoint; CLOCKED training is an additive child experiment, not a destructive overwrite.

### 7.3 Stage B — CLOCKED teacher-observation training

For each supported API family:

1. construct a request from a frozen prompt/task template;
2. store the exact input and request digest;
3. invoke CLOCKED with a stable idempotency key;
4. store the raw response, status, model timing, credits/cost metadata and SDK version;
5. parse and validate the typed response;
6. convert it into typed evidence atoms with exact source refs;
7. map the atoms through M0–M9;
8. append the observation event to the ledger;
9. train the relevant local objective using only the designated train split;
10. evaluate against frozen CLOCKED-labeled and independently outcome-labeled sets;
11. record a mutation receipt and checkpoint digest.

Do not call CLOCKED repeatedly to create an illusion of more independent labels. A replay under the same idempotency key is the same request result, not a new observation. Multiple paraphrases can be useful robustness probes, but they are correlated examples and must be grouped in the same split family.

### 7.4 Objectives by endpoint

| Endpoint | Primary local objective | Important negative/control cases |
|---|---|---|
| Decide | predict answer type and full answer distribution from state + criteria | criteria ambiguity, negation, missing approval, distractors |
| Extract | identify field/value and exact span alignment | near-duplicate distractor values, old vs current sections, missing field |
| Fill | schema-constrained record completion | omitted optional fields, conflicting values, malformed schema |
| PII | entity span/type and transform policy | false positives, adjacent entities, partial masking |
| Injection | source trust + malicious instruction evidence classification | benign quoted instructions, hostile text in retrieved docs, indirect injection |
| Script | operation/risk/evidence classification | harmless commands, dangerous flags, obfuscated commands |
| Grounding | claim-to-source support relation and abstention | unsupported claim, partially supported claim, conflicting sources |
| Compare | duplicate/conflict/equivalence relation | same fact different wording, version changes, false duplicate |
| Rerank | query-conditioned use/expand/skip ordering and score calibration | same topic wrong case, irrelevant documents, answer in neighboring chunk |
| Pipeline | next-step/stop-condition and typed stage-result prediction | stage failure, guard stop, continue-on-error |

### 7.5 Learn the distribution, not only the argmax

For Decide and Rerank, preserve the full probability/score vector when the API returns one. A one-hot label destroys uncertainty and makes calibration impossible.

Use fixed-point/quantized values with an explicitly documented scale and rounding mode. Store the original decimal/JSON representation in the evidence object. Never assume all endpoints use the same score semantics: Decide answer probabilities, Rerank relevance, document score and level probabilities are distinct typed fields.

### 7.6 Local learning is an approximation, not an API replacement claim

NaNLMind may learn a useful local predictor or evidence retriever. It should be allowed to return:

- prediction with calibrated confidence;
- abstain / call CLOCKED;
- request more evidence;
- escalate to human review;
- cite exact source refs and evidence spans.

Do not label a local prediction “CLOCKED verified” unless it was actually sent to CLOCKED and a verified response was received. Do not claim local parity with CLOCKED until a frozen, independently evaluated benchmark demonstrates it.

---

## 8. Baselines, controls, ablations and evaluation

This part is mandatory. A system that only measures its own improvement after training on CLOCKED outputs can easily report teacher imitation as independent intelligence.

### 8.1 Core baselines

Run the same frozen test set through:

- **B0 — deterministic/rule baseline:** schema, byte, Boolean, simple lexical and exact-match rules where applicable.
- **B1 — HERMES provider alone:** prompt + active provider, no CLOCKED and no CLOCKED-trained NaNLMind.
- **B2 — CLOCKED alone:** direct API result, the teacher/oracle reference, with exact request and cost/timing recorded.
- **B3 — NaNLMind logic foundation only:** logic-pretrained topology, no CLOCKED-specific updates.
- **B4 — NaNLMind CLOCKED-trained:** logic foundation plus CLOCKED teacher observations.
- **B5 — hybrid:** NaNLMind prediction, confidence/abstention gate, CLOCKED fallback, and HERMES synthesis.
- **B6 — simple classical baseline:** task-appropriate count/rule/TF-IDF or small conventional classifier/ranker where feasible.

B2 is not automatically ground truth. For correctness claims, use independent human adjudication or an external downstream outcome set.

### 8.2 Controls

- shuffled labels / shuffled document IDs;
- shuffled source spans;
- offset +1 / byte-vs-codepoint corruption;
- swapped mirror orientation;
- inverted forward/reverse rails;
- removed provenance;
- paraphrase-only duplicates;
- conflicting evidence with same confidence;
- empty evidence and missing fields;
- source injection embedded in quoted or retrieved text;
- repeated request under the same idempotency key;
- same source with a new prompt revision;
- deliberately stale route generation;
- stale scratch revision / CAS collision;
- one runner unavailable and then rejoining;
- replay after process restart.

The model must fail these controls in predictable ways. A high score on shuffled spans is a serious signal that the learner is ignoring provenance.

### 8.3 Metrics by task

| Task | Metrics |
|---|---|
| Decide | accuracy, macro-F1, Brier score, log loss, ECE, coverage-risk curve, abstention quality |
| Extract | exact-match, span precision/recall/F1, byte-offset exactness, field-level coverage |
| Fill | field accuracy, schema validity, required-field recall, hallucinated-field rate |
| PII | entity-level precision/recall, exact span overlap, transform correctness, false-positive rate |
| Injection/Script | confusion matrix, recall at fixed false-positive rate, evidence-span quality, abstention |
| Grounding | claim-level support/refute/unknown macro-F1, citation coverage, evidence-span accuracy |
| Compare | duplicate/conflict precision/recall, pairwise F1, version-change detection |
| Rerank | nDCG@k, MRR, Recall@k, action accuracy, score calibration |
| Pipeline | per-step accuracy, stop/continue correctness, dependency-order validity, error containment |
| System | latency, credits/request, cost, throughput, retry count, memory bytes, replay determinism |

Always report per-endpoint metrics. A single aggregate score can hide that extraction improved while injection detection regressed.

### 8.4 Frozen splits and leakage prevention

- Split by source document or source family, not individual extracted fields.
- Keep all paraphrases, retries and Pipeline variants of the same source family in one split.
- Freeze the challenge set before training.
- Record exact input, output, prompt-template and capability/schema digests.
- Keep a separate independent-outcome split where ground truth exists.
- Never train on the CLOCKED response for an example before evaluating the local model on that example.
- Do not use test outputs for threshold tuning.
- Report same-digest cross-run deltas only; changed test digest means non-comparable.
- Maintain a no-CLOCKED holdout to test whether the model learned transferable structure or merely memorized the provider's output distribution.

### 8.5 Ablations

Measure each of:
- no M0/M1 bit/token alignment;
- no M2 mirror-pair binding;
- no M3 probability/vector representation;
- no M4 temporal sequence;
- no M5 hyperedges;
- no M6 logic gate;
- no M7 route metadata;
- no M8 multi-result merge;
- no M9 provenance/policy;
- forward-only rail vs bidirectional rails;
- primary rail without shadow validation vs q-rail checks;
- full evidence graph vs flat JSON/text;
- one CLOCKED call vs multi-call synthesis;
- local-only vs CLOCKED fallback.

This is how the topology earns its keep. Do not assume every layer helps every endpoint.

---

## 9. Scratch-space interaction loop

### 9.1 One scratch, multiple writers, separate lanes

The scratch is the user's working document and the integration's message bus. It is not an unversioned text blob.

Required lanes:

| Lane | Writer | Content |
|---|---|---|
| `user` | user via HERMES | user-authored text, questions, corrections, selected source material |
| `hermes_plan` | HERMES | intent, prompt draft, selected operations, synthesis plan |
| `clocked_request` | HERMES adapter | exact typed request snapshot and digest |
| `clocked_result` | CLOCKED adapter | raw response ref, normalized result ref, timing/cost/status |
| `nanlm_observation` | NaNLMind intake | typed evidence atoms, layer mapping refs and validation |
| `nanlm_response` | NaNLMind runner | local synthesis/prediction, evidence refs, abstention or recommendation |
| `hermes_synthesis` | HERMES | cross-call synthesis, answer draft, unresolved questions |
| `validation` | validators | schema, digest, offset, provenance, ACL and calibration checks |
| `decision` | user/HERMES | approve, revise, export, continue or discard |

Each lane has an ACL and append permission. Entries are immutable. Writers append against an expected revision. HERMES must not overwrite NaNLMind's response, and NaNLMind must not rewrite the user's original text.

### 9.2 Scratch object

```text
ClockedScratch {
  scratch_id
  owner_installation_ref
  user_ref?                    // opaque local reference; avoid PII
  target_universe_ref
  target_hw_identity: HW3
  revision
  parent_revision
  state
  created_wall_time
  updated_wall_time
  logical_stamp?               // only when admitted to canonical ledger
  lanes[]
  content_digest
  acl_digest
  retention_policy
  request_refs[]
  result_refs[]
  schema_version
}
```

Each append includes `expected_revision`, lane, writer identity, content/object ref, content digest, idempotency key and signature. A stale revision is a conflict, not permission to overwrite. The server fetches/reconciles; it never drops a concurrent edit.

### 9.3 Main chat loop

```text
USER edits scratch
  -> HERMES reads current revision
  -> HERMES parses intent and identifies candidate CLOCKED operations
  -> HERMES asks CLOCKED Guard/Protect where appropriate
  -> HERMES previews exact request plan and expected credit use if known
  -> user approves execution where required
  -> CLOCKED receives immutable request snapshot
  -> raw response + receipt appended to clocked_result
  -> NaNLMind intake normalizes and maps result through M0..M9
  -> NaNLMind reads prior scratch/evidence context
  -> NaNLMind appends local response to nanlm_response
  -> HERMES reads both CLOCKED and NaNLMind lanes
  -> HERMES synthesizes, cites exact evidence and flags disagreements
  -> user edits/continues in the same scratch
```

### 9.4 Multi-CLOCKED synthesis

A single user question may require several API operations. HERMES should construct a small *typed task graph* rather than blindly call all endpoints:

Example: “Read these two policies, extract the relevant requirements, compare them, decide which applies to my case, and explain whether the answer is supported.”

1. Guard/Protect the input where sensitive or untrusted content warrants it.
2. Extract fields and exact spans from each source.
3. Compare documents for duplicates/conflicts.
4. Rerank passages against the user's query.
5. Decide among the applicable policy options using explicit criteria.
6. Ground the proposed answer against the supplied source passages.
7. NaNLMind links all returned atoms in one synthesis hypergraph.
8. HERMES presents the answer with source references, confidence/uncertainty and conflicts.

Use Pipeline when its sequential single-text semantics match the plan. Use separate calls when operations need different inputs, separate PDFs, independent retry/cost controls or fan-out. Do not force a multi-document task into a Pipeline if the endpoint semantics do not support it.

### 9.5 Scratch states and failure behavior

```text
DRAFT -> PLANNED -> AWAITING_APPROVAL -> SUBMITTED
      -> CLOCKED_RETURNED -> NORMALIZED -> LEARNED
      -> SYNTHESIZED -> COMPLETE
```

Failure states: `AUTH_REQUIRED`, `SCOPE_DENIED`, `QUOTA_EXCEEDED`, `CREDIT_LIMIT`, `STALE_REVISION`, `ROUTE_STALE`, `CLOCKED_REJECTED`, `UNKNOWN_OUTCOME`, `RESULT_INVALID`, `RUNNER_UNAVAILABLE`, `ABSTAINED`.

On network timeout, preserve the original idempotency key and recover the same request outcome. Do not generate a new key after an unknown outcome unless CLOCKED explicitly reports that the prior attempt ended and a new attempt is required. The SDK documents this distinction via `retryAsNew`. A replayed result is the same observation, not a second learning event.

---

## 10. HERMES integration and user experience

### 10.1 Two modes, same plugin and scratch store

HERMES should expose:

- **Chat mode** — default. User talks naturally; HERMES may use CLOCKED when the task benefits from structured decisions, exact extraction, security inspection, grounding, comparison or reranking. It should not consume credits silently for ordinary chat.
- **CLOCKED mode** — explicit workspace for direct API requests, endpoint exploration, scratch editing, multi-call synthesis, result inspection and experiment runs.

The plugin should use one adapter and one shared scratch protocol in both modes. Do not implement two independent clients.

### 10.2 Proposed CLI

These names are proposals; reconcile with existing HERMES command parsing before adding:

```text
/nanlm clocked
/nanlm clocked status
/nanlm clocked capabilities
/nanlm clocked credits
/nanlm clocked scratch new
/nanlm clocked scratch open <id>
/nanlm clocked scratch show
/nanlm clocked scratch append <text>
/nanlm clocked scratch plan
/nanlm clocked scratch run
/nanlm clocked scratch continue <instruction>
/nanlm clocked retrieve <request>
/nanlm clocked decide <question>
/nanlm clocked extract <fields>
/nanlm clocked fill <schema>
/nanlm clocked protect
/nanlm clocked guard
/nanlm clocked inspect
/nanlm clocked verify
/nanlm clocked compare
/nanlm clocked rerank <query>
/nanlm clocked pipeline <plan>
/nanlm clocked train plan
/nanlm clocked train run
/nanlm clocked eval
/nanlm clocked exit
```

A dedicated `nanclock` CLI may also be useful for headless CI, batch corpora and runner experiments. Both CLI surfaces should call the same domain service and NaN16 protocol state machine.

### 10.3 HERMES prompt architect

HERMES converts user intent into an executable, reviewable plan:

1. identify objective, source set, constraints and output contract;
2. inspect CLOCKED capability/API version and selected endpoint schemas;
3. select only the needed operations;
4. classify input sensitivity and injection risk;
5. build exact request objects and preserve source bytes/offsets;
6. estimate request size and display available cost/credit information;
7. identify writes, exports, training mutations and approval needs;
8. preview the prompt/task graph;
9. submit with idempotency and provenance;
10. read normalized results and synthesize with explicit uncertainty.

HERMES must not hallucinate endpoint fields or schemas. Pin the official SDK/API contract and validate requests locally before network calls.

### 10.4 HERMES plugin tools

Proposed tool surface:
- `clocked_status`
- `clocked_capabilities`
- `clocked_decide`
- `clocked_extract`
- `clocked_fill`
- `clocked_protect`
- `clocked_guard`
- `clocked_inspect`
- `clocked_verify`
- `clocked_compare`
- `clocked_rerank`
- `clocked_pipeline`
- `clocked_scratch_read`
- `clocked_scratch_append`
- `clocked_scratch_submit`
- `clocked_scratch_synthesize`
- `clocked_training_plan`
- `clocked_evaluate`

Prefer a generic typed request tool plus endpoint-specific convenience tools only where they improve usability. The domain service remains the single implementation of validation, auth, idempotency, mapping and receipts.

---

## 11. Authentication, demo access and HW3 trust

### 11.1 Two independent credentials

HERMES already has a NANNET installation identity with Ed25519 signing, pairing, scoped tokens, issuer pinning, replay protection and revocation. CLOCKED's official SDK documents a separate API key, normally supplied through `CLOCKED_API_KEY`, with an account key prefix such as `clk_live_`.

Never use:
- a NANNET bearer token as a CLOCKED API key;
- the HW3 identity as a CLOCKED API key;
- a CLOCKED API key as a NANNET identity;
- the HERMES installation private key as a service credential.

These identities have different issuers, audiences, purposes and revocation authorities.

### 11.2 Demo access model

The desired UX is that HERMES users can try the demo without manually configuring a CLOCKED key. That is a product/deployment entitlement, not a property the current public SDK proves.

Two safe options:

**A. Sponsored demo proxy (recommended if Rezolve permits it):**
- a controlled service operator owns the demo CLOCKED API key;
- the key exists only in a server-side secret manager;
- HW3:0 authenticates HERMES installations through NANNET;
- a quota/rate-limit broker issues per-installation demo grants;
- the proxy enforces demo-only operation allowlists, byte caps, credit caps and abuse controls;
- the CLOCKED key never reaches the HERMES client, model prompt, scratch or GitHub;
- operator can rotate/revoke the upstream key and disable the demo.

**B. Bring-your-own-key:**
- user creates a CLOCKED account and supplies their own API key through the OS secret store;
- HERMES sends the key only to CLOCKED over TLS;
- the plugin stores only an encrypted secret reference;
- HERMES displays credits/cost metadata returned by the SDK.

Do not promise automatic access until the service owner confirms sponsored proxy use is allowed by the CLOCKED terms and provides a supported account/credential arrangement. NANNET pairing alone cannot grant CLOCKED account credits.

### 11.3 HW3 registration

HW3 should be provisioned by the authority/Router as a distinct service identity with:
- immutable identity ID and public-key binding;
- service role `clocked-demo`;
- node point binding 3;
- HW3:0 NANNET interface;
- registered universe/tenant scope;
- allowed operation list;
- quota and byte/concurrency limits;
- signed route generation and ACL digest;
- revocation and rotation policy.

HERMES retains its own HW2 identity and installation key. It asks for a constrained capability to access HW3; it does not claim HW3 or copy its private key.

### 11.4 Scope separation

Suggested logical scopes (names subject to NANNET authority vocabulary):
- `clocked:capabilities:read`
- `clocked:demo:read`
- `clocked:request:execute`
- `clocked:scratch:read`
- `clocked:scratch:write`
- `clocked:corpus:propose`
- `clocked:corpus:export`
- `clocked:training:propose`

Ordinary demo grants must not include global topology mutation, route commit, volume administration, universe registration, secret management or model merge. Training mutations remain local/demo-scoped until an explicit authority gate allows otherwise.

---

## 12. NaNNet, NaNROUTER, Koyeb and Runner Ring

### 12.1 End-to-end route

```text
HERMES user / CLI
   |
   | NANNET installation identity + signed request
   v
Router point 2 (HERMES)
   |
   | resolve authorized HW3:0
   v
NaNROUTER committed route + ACL + generation
   |
   v
Koyeb BS0:0 persistent gateway
   |
   | N16B / NaNNet bridge frame
   v
HW3:0 CLOCKED interface
   |
   +---- CLOCKED API adapter ----> clocked.rezolve.ai/clocked
   |
   +---- scratch/task intake ----> NaNLMind canonical topology
                                  |
                                  v
                             MC0:0 runner ring
                                  |
                     six runner slots / 256 heads
                                  |
                     HeadPackets + barrier + ledger
                                  |
                                  v
                           committed result
                                  |
                                  v
                      scratch result lane -> HERMES
```

The diagram is a target logical flow. It does not claim that HW3, its live API proxy, or the full NANNET intake path has already been deployed.

### 12.2 Delivery guarantees

Use the existing NaNNet durable leased-delivery pattern:

- sender creates a request ID and idempotency key;
- receiver persists the inbox item before ACK;
- duplicate frame is a safe no-op;
- task lease and status are queryable;
- sender consumes the receipt;
- a dropped ACK does not duplicate learning;
- result append is revision-checked and digest-bound;
- replay recovers from the last committed state.

CLOCKED SDK idempotency and NaNNet frame/task idempotency are different layers. Preserve both. One API call should map to one stable upstream Idempotency-Key and one distinct transport/task ID.

### 12.3 Runner Ring participation

The current NaNLMind head-ring design assigns internal head ownership by `owner(head) = head mod 6` across six runner slots. The six runners are regions of one object, not six independent CLOCKED learners.

The CLOCKED scheduler should:
- partition work by typed head/pair ownership;
- send each runner only its assigned head/pair packet set;
- use the existing prepare/commit barrier;
- verify all 256 unique heads and one common logical epoch;
- merge one validated handoff round into the single ledger;
- never allow independent concurrent writers to mutate the same journal.

A CLOCKED task can be queued while one runner is unavailable, but the commit barrier must not pretend the whole epoch completed. On rejoin, the runner verifies the committed base digest and replays from the last accepted generation.

### 12.4 Koyeb does not learn

Koyeb is the persistent gateway/control and storage host. It should not:
- own private semantic histories;
- host an unregistered duplicate head topology;
- accept unscoped writes directly into the global route cache;
- become the model runner by implication;
- claim volume health without a verified observation.

The actual model/head work remains with the authorized local or runner-ring executor.

---

## 13. Pseudocode for the core loop

### 13.1 CLOCKED intake

```text
CLOCKED_INTAKE(scratch_id, revision, endpoint, request):
    assert scratch_revision_is_current(scratch_id, revision)
    assert user_or_policy_authorized(endpoint)
    capability = ROUTER.resolve(HW3, port=0, scope=endpoint)
    assert capability.route_generation_is_committed
    assert capability.acl_allows(endpoint)

    source_bytes = scratch.read_immutable_input(revision)
    source_digest = SHA256(source_bytes)
    request_key = stable_idempotency_key(
        installation_id, scratch_id, revision, endpoint, request_digest
    )

    persist_outbox_before_send(request_key, source_digest, request)
    response = CLOCKED_ADAPTER.call(
        endpoint, request, idempotency_key=request_key
    )

    persist_raw_response(response, request_key)
    normalized = CLOCKED_CODEC.normalize(endpoint, response)
    validate_offsets(normalized, source_bytes)
    validate_schema_and_provenance(normalized)

    proposal = NAN16_MAP(normalized, layers=M0..M9)
    append_scratch_lane("clocked_result", normalized.ref)
    enqueue_native_observation(proposal)
    return signed_receipt(response, normalized, proposal)
```

### 13.2 Multi-call scratch synthesis

```text
SYNTHESIZE_SCRATCH(scratch_id, revision, user_goal):
    plan = HERMES.plan(user_goal, verified_capabilities)
    preview(plan)
    require_approval_if_policy_says_so(plan)

    results = []
    for node in plan.topological_order:
        inputs = resolve_typed_inputs(node, scratch, results)
        result = CLOCKED_INTAKE(scratch_id, current_revision, node.endpoint, inputs)
        results.append(result)

    graph = BUILD_EVIDENCE_HYPERGRAPH(results)
    local = NANLMIND.reason(graph, frozen_base_generation)
    checks = VERIFY_PROVENANCE_OFFSETS_CALIBRATION(graph, local)

    append_scratch("nanlm_observation", graph.ref)
    append_scratch("nanlm_response", local.ref)
    append_scratch("validation", checks.ref)

    if checks.has_conflict:
        preserve_all_sources()
        mark_synthesis_uncertain()
    return HERMES.compose(local, results, checks)
```

### 13.3 CLOCKED-specific training

```text
TRAIN_CLOCKED_PROFILE(dataset_manifest, base_checkpoint):
    assert logic_foundation_receipt_is_valid(base_checkpoint)
    assert dataset_manifest.splits_are_frozen
    assert dataset_manifest.has_raw_request_and_response_digests

    for example in dataset_manifest.train:
        atoms = normalize_clocked_result(example)
        assert atoms.provenance_valid
        mapped = transform_M0_to_M9(atoms)
        update_task_specific_integer_scores(mapped)
        append_one_ledger_event(example.id, mapped.digest)

    evaluate_all_frozen_controls()
    compare_B0_through_B6()
    write_checkpoint_and_experiment_receipt()
```

Pseudocode is conceptual. Exact NaN16 instruction encoding and existing native command contracts must be derived from the current NaN0S/NaNLMind implementations before any code is written.

---

## 14. CLI and experiment workflow

The standalone CLOCKED project should have a CLI with three audiences: interactive developer, HERMES orchestration and headless CI/runner.

Proposed command families:

```text
nanclock status
nanclock auth status
nanclock auth test
nanclock capabilities
nanclock credits
nanclock request <endpoint> --input <file-or-scratch>
nanclock scratch create
nanclock scratch open <id>
nanclock scratch append --lane user --file prompt.txt
nanclock scratch show
nanclock scratch plan
nanclock scratch run
nanclock scratch synthesize
nanclock corpus build --profile <endpoint-family>
nanclock pretrain logic --suite frozen-logic
nanclock train --profile clocked --manifest <manifest>
nanclock eval --baseline-set B0-B6
nanclock map inspect --layer M0..M9
nanclock map resolve --hw HW3 --port 17
nanclock pair inspect --address 0x....
nanclock ring status
nanclock receipt verify <id>
nanclock replay <experiment-id>
```

CLI requirements:
- JSON output for automation, readable text for interactive use;
- exact request preview and explicit cost/credit display where known;
- no secret values in logs or shell history;
- bounded file and payload sizes;
- idempotency key shown only as a safe identifier/digest;
- stable exit codes for validation, auth, quota, route, service and training errors;
- offline inspection/replay commands where possible;
- explicit `--dry-run` for prompt and route plans;
- no hidden training mutation from a read-only query.

---

## 15. API adapter and SDK strategy

### 15.1 Prefer the official SDK initially

The official Python package already provides sync and async clients, typed errors, keep-alive connections, idempotent retries, PDF/image handling, response timing, credit/cost metadata and Pipeline support. Reimplementing the HTTP contract in the first iteration adds unnecessary risk.

Recommended first adapter:
- pin an exact `clocked-sdk` version in the HERMES/NaNLMind_CLOCKED dependency manifest;
- wrap it behind a narrow NaNLMind_CLOCKED interface;
- validate endpoint request bodies against pinned schemas;
- normalize `Result` objects to versioned internal envelopes;
- expose a mock transport for tests;
- preserve SDK errors and `retry_as_new` semantics;
- retain the raw body and response headers with secrets removed.

Longer-term, NaN16 guest code should own the typed protocol/state machine and deterministic transformations. A thin Python host boundary can continue to invoke the SDK because TLS, HTTPX and API-key storage are host concerns. Do not rewrite TLS or the provider's service implementation in NaN16.

### 15.2 Cost-aware orchestration

The SDK exposes model time, credits, cost basis, cost in USD and server timing when the gateway returns those headers. The integration should:
- store per-request cost/credit metadata;
- display estimate/actual distinctly;
- allow per-user and per-demo quotas;
- cache only when the operation's semantics and freshness permit;
- avoid redundant repeated calls;
- use Pipeline where it saves round trips and preserves semantics;
- provide a user-configurable approval threshold for paid/expensive calls.

Do not hardcode free-credit amounts or current plan entitlements in the plugin.

### 15.3 Retry policy

Preserve the SDK's documented retry behavior:
- 429 is a concurrency/plan in-flight limit and may be retried under the same key according to SDK policy;
- network timeout/no response is an unknown outcome: retry the same key;
- 5xx without `retryAsNew` is an unknown outcome: retry the same key;
- 409 while the earlier request is running: query/retry the same key;
- `retryAsNew=true` means the prior attempt ended; a new attempt is a new billable operation and requires a new key;
- other 4xx require fixing the request/auth/plan before retry.

Never convert an unknown outcome into a new idempotency key automatically.

---

## 16. Security, privacy and trust

- Keep NANNET and CLOCKED credentials separate.
- Use TLS and secret-manager/OS-key-store storage for CLOCKED keys.
- Do not put credentials in scratch, prompts, manifests, logs, test fixtures or Git.
- PII detection is not equivalent to a complete privacy guarantee. Decide what is allowed to leave the local device before sending data.
- Use Protect/PII and Guard/Injection where appropriate, but do not rely on them as the only security boundary.
- Treat all user, retrieved, document and API text as untrusted data.
- An injection verdict does not authorize executing or obeying the content.
- Script Inspect is a classifier, not a sandbox. Never execute a script because CLOCKED classified it benign.
- Grounding is bounded by the supplied source documents. Record the exact document set and digest.
- A probability is not a proof. Keep score type, threshold, alternatives and calibration dataset.
- Preserve original source documents and exact offsets; redacted output is a derived artifact.
- Use scoped HW3 grants and separate demo from production/global namespaces.
- Enforce byte limits, concurrency limits, credit caps, retention TTLs and per-installation rate limits.
- Verify route generation, ACL digest, task lease, scratch revision and result signature/receipt.
- Fail closed on revoked/expired credentials, schema drift, invalid digest, stale route or unauthorized object.
- Never expose internal service keys or raw auth headers in model-visible content.

---

## 17. Failure model and recovery

| Failure | Required behavior |
|---|---|
| CLOCKED 401 | report invalid/missing CLOCKED credential; never retry with NANNET token |
| CLOCKED 402 | preserve scratch; report credit/spending limit; do not create a new key |
| CLOCKED 403 | distinguish account/plan authorization from NANNET route authorization |
| CLOCKED 409 | follow idempotency state; same key for running/unknown outcome |
| CLOCKED 429 | respect concurrency limit and Retry-After |
| CLOCKED 5xx / timeout | unknown outcome; preserve key and recover |
| schema mismatch | quarantine response; no learning update |
| offset mismatch | reject source alignment; preserve raw response for diagnosis |
| stale scratch revision | fetch/reconcile; no last-writer-wins overwrite |
| stale route generation | re-resolve via Router; no direct fallback mount |
| runner loss | retain task lease and committed base; wait/replay; no partial global commit |
| invalid q-rail/shadow | mark proposal invalid; do not merge |
| credit exhaustion | local-only continuation and explicit user notice |
| user revokes demo | revoke HW3 grant; local HERMES chat remains functional |

A request can be accepted by CLOCKED but not yet learned by NaNLMind. Track separate states: API returned, response validated, scratch appended, task enqueued, runner prepared, topology committed, evaluation complete.

---

## 18. Proposed repository layout

After creating `shemshallah/NaNLMind_CLOCKED`, start with a docs-first skeleton. No code should be written until the schemas, endpoint semantics, register allocation and authority bindings are reconciled.

```text
NaNLMind_CLOCKED/
  README.md
  CLOCKED_HERMES_BRAINSTORM.md       # canonical architecture file
  docs/
    API_CONTRACT.md                  # pinned official SDK/API mapping
    HW3_ADDRESSING.md                # HW3, HW3:0, HW3:1..255
    EVIDENCE_CODEC.md                # typed result atoms + source offsets
    M0_M9_CLOCKED_PROFILE.md         # ten-layer mapping profile
    SCRATCH_PROTOCOL.md              # lanes, revisions, CAS, leases
    LEARNING_OBJECTIVES.md           # logic-first + endpoint-specific learning
    BASELINES_AND_CONTROLS.md        # frozen evaluation plan
    AUTH_AND_ROUTING.md              # NANNET, Router, Koyeb, ring
    CLI_SPEC.md                      # nanclock UX and exit codes
    DECISIONS.md                     # design decisions and open questions
  schemas/
    clocked-result-envelope.schema.json
    clocked-evidence-atom.schema.json
    clocked-scratch.schema.json
    clocked-task.schema.json
    clocked-receipt.schema.json
    hw3-head-port.schema.json
  nan16/
    README.md                        # NaN16-first guest module plan
  experiments/
    logic-foundation/
    clocked-decide/
    clocked-extract/
    clocked-grounding/
    clocked-rerank/
    multi-endpoint-synthesis/
  corpora/
    manifests/                       # manifests only; no private source docs
  tests/
    fixtures/                        # synthetic/public-safe fixtures
    controls/
```

Keep raw private CLOCKED user data, API keys, personal documents and generated large corpora out of Git. The repo contains schemas, code, public-safe fixtures, manifests and experiment summaries.

---

## 19. Phased build plan

### Phase 0 — contract and identity reconciliation (docs only)
- Pin official CLOCKED docs and SDK version.
- Confirm exact request/response schemas for all ten methods.
- Confirm whether demo proxy/sponsored credentials are permitted.
- Define HW3 identity ownership, HW3:0 endpoint and point-3 Router binding.
- Verify actual NaNNet framing and route selector grammar for HW3.
- Reconcile 255 HW3 ports with 256 internal heads and six BSR control heads.
- Verify exact 8 MiB allocator offsets and extension availability.
- Confirm live Koyeb volume registry and ring health from signed observations.

### Phase 1 — read-only adapter and scratch
- capability/status/auth diagnostics;
- official SDK wrapper;
- typed response persistence and digest;
- scratch lanes, immutable revisions and CAS;
- endpoint preview and receipts;
- no native learning mutation yet.

### Phase 2 — deterministic codec and address mapping
- exact UTF-8/source-offset handling;
- typed evidence atoms for all endpoints;
- canonical mirror-pair address resolver;
- collision-safe object directory;
- M0–M9 mapping receipts;
- NaN16 guest parser and validation tests.

### Phase 3 — logic foundation and endpoint corpora
- run immutable logic foundation;
- create public-safe, synthetic and consented CLOCKED benchmark sets;
- generate frozen splits;
- direct CLOCKED reference runs;
- implement baseline/control harness;
- establish no-CLOCKED holdout.

### Phase 4 — CLOCKED learning profile
- endpoint-specific integer-score and relation objectives;
- distribution-aware prediction/calibration;
- abstention and CLOCKED fallback;
- q-rail validation;
- per-endpoint evaluation and mutation receipts.

### Phase 5 — HERMES mode and multi-call synthesis
- CLOCKED mode and CLI;
- same scratch loop;
- endpoint task planner;
- multi-result hypergraph synthesis;
- user-visible source evidence and conflict handling;
- approval and credit/quota UX.

### Phase 6 — HW3 / Router / Runner Ring deployment
- provision HW3 identity and HW3:0 NANNET interface;
- register HW3:1–255 port map;
- commit signed route and ACL generation;
- deploy gateway proxy if authorized;
- connect Runner Ring task handoff;
- verify full end-to-end request/response/replay;
- staged rollout with per-installation quotas.

### Phase 7 — controlled demo and research
- authenticated HERMES users can enter CLOCKED mode;
- demo access is automatically delegated only if the sponsored proxy is approved and provisioned;
- otherwise use BYOK;
- evaluate all baselines and ablations;
- publish reproducible, privacy-safe results;
- do not promote experimental CLOCKED mappings into global topology without explicit validation and authorization.

---

## 20. Acceptance criteria

A first end-to-end demo is not complete until all of the following pass:

1. HERMES authenticates with its own NANNET installation identity.
2. HERMES resolves Router point 3 and HW3 without confusing them with BSR IDs or internal head IDs.
3. HW3:0 completes a signed NANNET handshake and returns a capability manifest.
4. A scoped demo grant or BYOK CLOCKED key authenticates independently to CLOCKED.
5. HERMES creates a scratch; user text persists in the user lane.
6. HERMES previews and submits a Decide or Extract request with a stable idempotency key.
7. The raw CLOCKED response is preserved and schema-validated.
8. Exact source offsets round-trip to the submitted bytes.
9. NaN16 maps the evidence through M0–M9 and resolves canonical mirror-pair references.
10. NaNLMind reads the same scratch revision and appends a response in its own lane.
11. HERMES reads both results and synthesizes with source evidence and uncertainty.
12. Replaying the same request does not create a duplicate learning event or charge.
13. A stale scratch revision is rejected without data loss.
14. A stale route/ACL generation is rejected.
15. One runner outage does not produce a partial topology commit.
16. Logic foundation, B0–B6 baselines and frozen controls run reproducibly.
17. API credits/costs and local training metrics are reported separately.
18. Revoking the demo grant prevents subsequent remote calls while local HERMES chat remains usable.

---

## 21. Open decisions to resolve before implementation

1. Is HW3 provisioned by the NANNET authority, NaNROUTER, or a CLOCKED-owned service identity that Router binds?
2. Does the canonical NaNNet grammar already support an HW3:0 interface selector, or must the grammar/schema be versioned?
3. Does the CLOCKED provider permit a sponsored multi-user demo proxy, and what account/key/quota arrangement is allowed?
4. What exact official API version and schemas are pinned for the ten SDK methods?
5. Does CLOCKED provide a formal capability-discovery endpoint, or should the adapter pin the SDK's known endpoint set?
6. Which response fields are guaranteed for every API version, and which are optional?
7. Which offsets are byte offsets versus character offsets for each endpoint and PDF mode?
8. Which HW3:1–255 ports should be dedicated versus dynamically scheduled?
9. How should the external 255-port namespace map to the six BSR runners and the existing 256 internal heads?
10. Which extension-region offsets are truly free in the current 8 MiB implementation?
11. Should raw scratch objects live on SC0 or in a separate object store? What are retention/backup requirements?
12. Which task outcomes can be independently verified for calibration rather than merely imitated from CLOCKED?
13. Which CLOCKED operations should be automatic in Chat mode, and which require per-call approval?
14. What is the maximum demo concurrency and credit budget per installation?
15. What exact receipt is required before a CLOCKED observation may update the global ledger?

---

## 22. Final architecture decision

**HERMES is the operator and conversational surface. CLOCKED is the external structured-reasoning teacher/assessor. NaNLMind is the one mathematical memory and learning substrate. NaNNet is the authenticated delivery fabric. NaNROUTER owns address resolution, ACLs, route generations and volume bindings. Koyeb is the persistent gateway. The Runner Ring executes the distributed head work. NaN16 owns the protocol semantics and deterministic transformations.**

HW3 is the registered CLOCKED service identity. HW3:0 is its NANNET interface. HW3:1–255 are stable logical head ports mapped explicitly into the existing head/pair topology. The 256 internal heads, six BSR control heads, one global ledger and one 8 MiB chart remain authoritative.

The register chart maps CLOCKED data down to bits and mirror-pair cells; the extension region stores compact connection and transform metadata; durable source/result content remains in registered persistent storage. The M0–M9 stack carries the evidence from byte/token identity to meta-policy and consensus. Logic foundation precedes CLOCKED-specific training. CLOCKED outputs are typed teacher observations; external outcomes determine whether predictions are actually correct. Baselines, controls, frozen splits and ablations prevent us from mistaking memorization or teacher imitation for learning.

The user works in one scratch. HERMES plans and calls CLOCKED; CLOCKED returns structured evidence; NaNLMind maps, learns and responds in the same scratch; HERMES synthesizes multiple results and continues the conversation. This is the core product experience and the central research loop.

**No implementation code is included in this design round.**
