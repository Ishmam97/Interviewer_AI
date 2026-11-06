# 2026 launch documentation

This folder is the working map for the current launch-readiness effort. It connects the three read-only audits to the implementation areas they describe, records the state of the product as inspected on 2026-11-06, and provides a traceable checklist for turning findings into verified changes.

## Documents

- [Master product and launch plan](master-plan.md) — consolidated phased backlog, ownership, acceptance gates, pricing experiments, and B2B roadmap.

- [Implementation guide](implementation-guide.md) — component and API map, data flow, implementation recipes, finding-to-code traceability, and acceptance evidence.
- [Frontend reference](frontend-reference.md) — feature components, props, state, actions, API calls, and UI error behavior.
- [Backend API reference](backend-api-reference.md) — registered FastAPI routes, auth, request shapes, response shapes, storage, and async lifecycles.
- [Beta signup operations](beta-operations.md) — current endpoint behavior and operational requirements before collecting production signups.
- [Backend audit](../audits/2026-11-06-backend.md) — security, persistence, quota, operations, AI reliability, and backend roadmap.
- [Product and UX audit](../audits/2026-11-06-product-ux.md) — user journeys, frontend recovery/accessibility issues, and UX acceptance criteria.
- [Business and launch audit](../audits/2026-11-06-business.md) — customer hypothesis, monetization experiments, funnel measures, and launch gates.

## Reading order

1. Read the three audits for findings and confidence labels.
2. Use the implementation guide to locate the relevant frontend component, API method, route, service, and persistence method.
3. Implement and verify against the acceptance criteria in the source audit. Record evidence and the deployed revision before calling a launch gate complete.

## Status rules

Audit reports are dated snapshots of repository evidence, not statements that production is safe or that a finding is fixed. The implementation guide distinguishes **current code**, **audit finding**, **pending**, and **verified**. A code change is not a verified launch gate until its targeted checks pass; a deployment-specific assertion also requires evidence from the deployed revision, configuration, and rules.

The landing redesign is implemented and locally verified. The beta API is implemented with atomic Firestore deduplication; production persistence and operational controls remain separate release gates. See [verification](verification.md) for exact checks and limits. The frontend is a separate Git repository under `frontend/`; commit its changes separately from backend and documentation changes.
