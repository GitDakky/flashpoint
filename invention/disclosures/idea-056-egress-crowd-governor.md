# INVENTION DISCLOSURE — Egress Crowd Governor

## 1. Field of the invention

Distributed computing, multi-agent systems, API gateways, delegated authorization, request coalescing, credential brokering, and tamper-evident auditing.

## 2. Problem addressed

When thousands of ephemeral construction agents concurrently invoke external APIs, many requests are semantically equivalent but originate under different identities, permissions, privacy constraints, freshness requirements, and quota accounts. Conventional request coalescing or caching may execute such requests once and distribute the result without establishing that every participating agent is authorized to observe the same response. Conversely, executing each request independently causes excessive external load, cost, throttling, and credential exposure. A gateway is needed that coalesces requests only when doing so preserves each agent’s authorization and privacy boundaries while retaining individual attribution, quota allocation, and auditability.

## 3. The inventive mechanism

The **Authorization-Safe Coalescing Protocol (“ASCP”)** comprises:

1. **Normalize:** An API-schema-aware canonicalizer converts each agent request into a canonical representation while retaining the original request.
2. **Fingerprint:** The gateway computes a canonical request fingerprint over at least: semantic operation and normalized arguments, API version, tenant, authorization-scope-equivalence class, privacy policy, freshness window, and side-effect classification.
3. **Prove visibility equivalence:** A policy engine independently evaluates each requesting agent and admits it to a short-lived cohort only upon determining that the agent may receive the same response bytes under the applicable authorization, field-level disclosure, tenant, privacy, purpose, and freshness policies. Requests having equal syntax but unequal visibility are separated.
4. **Single-flight execution:** For an admitted cohort, a credential broker derives a least-privilege execution credential sufficient for the cohort’s common authorized operation. A single-flight table elects one execution and associates the admitted agents with it. Side-effecting requests are rejected from coalescing or coalesced only where declared idempotency and shared-effect semantics permit one execution.
5. **Controlled distribution:** The resulting bytes are encrypted at rest and released only to admitted agents, subject to revalidation where policy or cohort validity has expired.
6. **Per-agent receipt:** The gateway creates a signed, append-only receipt for each agent linking a digest of that agent’s original request, its admission decision, cohort and shared-execution identifiers, a digest of the returned bytes, policy/version identifiers, execution credential metadata, timing/freshness data, and the agent’s allocated cost or quota.

## 4. Independent claim

**A computer-implemented method comprising:** receiving, at an egress gateway, external-tool requests from a plurality of agents; generating, for each external-tool request, a canonical request fingerprint that represents semantic intent, an application-programming-interface version, a tenant, an authorization-scope-equivalence class, a privacy policy, a freshness window, and a side-effect classification; determining, separately for each agent, whether response-visibility equivalence exists between the agent and one or more other agents associated with matching canonical request fingerprints; admitting only agents for which response-visibility equivalence is established into a time-bounded coalescing cohort; obtaining, from a credential broker, a least-privilege credential constrained to an operation authorized for the admitted agents; causing a single external execution of the operation on behalf of the coalescing cohort; distributing bytes returned by the single external execution only to the admitted agents; and generating, for each admitted agent, a tamper-evident receipt cryptographically linking the agent’s original external-tool request, an admission decision, the single external execution, the bytes distributed to the agent, an applied policy version, and a cost or quota allocation.

## 5. Key dependent claims

1. The method wherein canonicalization uses an API schema to normalize parameter ordering, defaults, aliases, encodings, and semantically equivalent argument forms.  
2. The method wherein response-visibility equivalence includes tenant isolation, field- or row-level disclosure, purpose limitation, geographic restrictions, and effective authorization scopes.  
3. The method wherein side-effecting requests are coalesced only when an idempotency key and policy establish that one shared effect is authorized for every admitted agent.  
4. The method wherein returned bytes are stored in an encrypted cache indexed by the fingerprint and are released only after policy and freshness revalidation.  
5. The method wherein receipts are signed and entered into a hash-chained or Merkle-tree append-only log supporting inclusion and consistency verification.

## 6. Closest prior art and the specific distinguishing delta

Generic request-coalescing materials, including the cited Go request-coalescing discussions, disclose collapsing concurrent equivalent calls but do not condition cohort admission on proven per-agent response-visibility equivalence or produce per-agent accountability receipts. The cited delegated-authorization and credential-broker materials address scope selection or credential isolation, not authorization-safe shared execution. Trillian and the cited tamper-evident logging work provide append-only audit mechanisms but do not bind individual authorization decisions and cost allocations to a coalesced execution. Cache, deduplication, and fingerprint references concern storage, chunking, or identification rather than policy-qualified multi-agent egress. The distinguishing delta is the combined protocol in which the fingerprint includes authorization, privacy, freshness, and effect semantics; cohort membership requires response-visibility equivalence; execution uses a brokered common least-privilege credential; and each participant receives a cryptographically linked individual receipt.

## 7. Anticipated obviousness objection and the rebuttal

An examiner may characterize the invention as a predictable combination of request coalescing, authorization checks, credential brokering, and audit logging. The rebuttal is that ordinary coalescing treats request equivalence as a syntactic or cache-key property, whereas ASCP makes **safe shareability** a separately proved, per-agent protocol invariant. Authorization and privacy state participate both in cohort identity and admission; the execution credential is derived from the cohort’s common permissible operation; and receipts preserve individual provenance and allocation despite one physical execution. This coordinated data flow prevents cross-principal information leakage while retaining single-flight efficiency—an issue not solved by independently placing conventional authorization or logging around a coalescer.

## 8. Enablement: minimum build to practice the invention

Implement an egress proxy containing: (i) an OpenAPI- or equivalent schema-aware canonicalizer; (ii) a policy engine that computes authorization-scope classes and response-visibility equivalence; (iii) a short-lived, fingerprint-indexed single-flight cohort table; (iv) a credential broker issuing scoped, expiring credentials; (v) an external API executor; (vi) an encrypted response cache with freshness enforcement; and (vii) a signing service and append-only hash-chained or Merkle audit log. Each request record stores the original-request digest, canonical fingerprint, agent identity, policy decision, cohort/execution identifier, response digest, and cost or quota allocation.