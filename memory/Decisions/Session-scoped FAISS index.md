---
type: decision
status: active
created: '2026-07-19'
updated: '2026-07-19'
tags:
  - decision
  - rag
  - faiss
  - security
---
# Decision: Session-scoped FAISS index path (cross-user data-leak fix)

Fixed 2026-07-06, found by a parallel production-readiness audit.

**The bug:** `InterviewConfig.index_path` defaulted to a single shared path (`./interview_faiss_index`) for the classic (LangGraph) interview mode. `RAGSystem.load_existing_index()` — if it found a file at that path — would load it and skip rebuilding, unless `force_rebuild=True` was passed. Since every session used the same default path and `/interview/start` never set a session-specific one, **a later user's interview could silently load and be scored against the FAISS index built from an earlier, different user's resume and job description.** This is a real cross-tenant data leak, not just a correctness bug.

**The fix:** `/interview/start` now generates `session_id` *before* constructing `InterviewConfig`, and sets `config.index_path = os.path.join(settings.VECTOR_STORE_PATH, f"interview_{session_id}")`. Every session therefore gets a guaranteed-unique path; `load_existing_index()` correctly finds nothing for a fresh session and always rebuilds. No shared-path collision is possible by construction, so there's no need to reason about `force_rebuild` correctness at all.

**Trade-off:** leftover per-session FAISS directories are never cleaned up after a session ends — a disk-growth concern over time, not yet addressed. Tracked as a known gap, not silently ignored.

**How to apply:** any future per-session artifact (index, cache, temp state) must derive its storage key from the session/request identity, never from a shared default that could be reused across requests. When reviewing code that reads-then-writes a shared resource keyed only by a type (not an identity), ask "whose data is this, and could two different callers collide on this key?"

Regression test: `test_interview.py::TestInterviewStart::test_start_uses_session_scoped_faiss_index_path` — asserts two sequential `/interview/start` calls produce distinct `index_path` values, each containing its own `session_id`.

[[Decisions Log]] · [[RAG System]] · [[Backend]] · [[Security Hardening]]
