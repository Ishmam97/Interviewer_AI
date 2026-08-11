---
name: session-persistence-strategy
description: ADR — how (and whether) to persist interview session state across restarts / multiple instances
metadata:
  type: decision
---

# ADR: Session-persistence strategy

**Status:** accepted (interim) — 2026-07-27 · revisit when concurrency data justifies it.

## Context

Active interviews live entirely in two in-memory dicts in `server.py`: `_active_sessions` (classic REST/LangGraph flow) and `_live_sessions` (live WebSocket flow). There is **no `_reconstruct_session()`** — on a process restart, or a request landing on a different Cloud Run instance, the session is gone and `/interview/answer` returns a clean 404 ("session expired, start a new interview"). The classic flow's `InterviewSystem` object (LLM clients + a per-session FAISS index — see [[Session-scoped FAISS index]]) is not serializable/reconstructable cheaply. This is why deploy is pinned to `--max-instances 1 --min-instances 1`: it prevents both scale-to-zero (which would drop idle sessions) and multi-instance routing (which would 404 mid-interview). The cost: **no horizontal scaling**, and a crash mid-interview loses that one interview.

## Decision drivers

- Solo dev, pre-launch, near-zero concurrency — real scaling need is unproven.
- Correctness: don't silently corrupt/lose interviews (a graceful 404 already exists).
- Operational simplicity and cost (no new infra unless it earns its place — see [[BackgroundTasks over Celery]] for the same posture).
- The FAISS index and the live WS in-flight generation state are the genuinely hard parts to persist, not the plain conversation state.

## Options

1. **Accept single-instance, non-resumable (status quo + `--max-instances 1`).** Zero work, simplest. Can't scale horizontally; a restart loses the in-flight interview.
2. **Firestore-backed session state.** No new infra (Firestore is already the datastore); survives restarts + multi-instance for the *serializable* classic-flow state. But FAISS RAG context is still lost on reconstruction (rebuild lazily or accept degraded RAG), and the live WS agent's mid-stream state is impractical to persist.
3. **Redis (Memorystore / Upstash).** Fast shared session store, enables real horizontal scaling. New infra + cost + ops; overkill pre-launch; still doesn't solve FAISS/WS state.

## Decision

**Option 1 for launch** — ship at `--max-instances 1`, document the single-instance constraint, rely on the existing graceful 404. Revisit **only when concurrent-session logs show the single instance is actually a bottleneck** (i.e. real users hitting contention), not preemptively.

**When revisiting, prefer Option 2** for the classic REST interview: its `InterviewState` is a serializable TypedDict, so persist it to Firestore and rebuild FAISS lazily (or accept no-RAG on reconstruction — the interview still works). Keep the **live WS interview inherently single-instance** — a WebSocket is pinned to one instance for its lifetime anyway, so use session affinity rather than trying to migrate an open socket. Reach for Redis (Option 3) only if Firestore round-trip latency on the hot answer-path becomes the measured bottleneck.

## Consequences

- Near-term: one Cloud Run instance; a mid-interview crash loses that interview (user restarts).
- No horizontal scaling until this is reopened — acceptable at pre-launch/low traffic.
- Add a concurrency/instance-saturation signal to observability (Phase D) so the "revisit" trigger is data-driven, not a guess.

Related: [[Backend]] · [[Session-scoped FAISS index]] · [[Live Interview]] · [[project_roadmap]] (Phase D).
