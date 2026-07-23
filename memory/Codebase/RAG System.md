---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-07-19'
tags:
  - codebase
  - rag
  - faiss
  - embeddings
  - security
---
# RAG System

`services/rag_system.py` — `RAGSystem` class. Wraps a FAISS vector store for retrieval-augmented generation during classic (LangGraph) interviews.

## How it works

1. At interview start, `InterviewSystem.setup_rag_system()` builds (or loads) a FAISS index from the resume + JD text
2. For each candidate answer, `_retrieve_context()` runs `similarity_search(question + answer, k=3)`
3. The top 3 matching chunks are concatenated into `rag_context` and injected into the `ResponseAnalyzer` prompt

## Index lifecycle — now per-session (fixed 2026-07, was a cross-user data leak)

#gotcha **Fixed bug, keep for context:** `InterviewConfig.index_path` used to default to a single shared path (`./interview_faiss_index`) for every session. `setup_rag_system()`'s `load_existing_index()` would silently load whatever index was already on disk if `force_rebuild` wasn't set — meaning **user B's interview could be scored against RAG context built from user A's resume**, since the FAISS file wasn't session-scoped. Fixed by generating the `session_id` *before* constructing `InterviewConfig` in `/interview/start`, then setting `index_path = os.path.join(settings.VECTOR_STORE_PATH, f"interview_{session_id}")` (`server.py` ~1276). Each session now gets a fresh, unique path, so `load_existing_index()` correctly finds nothing and always rebuilds — no cross-user leak is possible by construction. Verified via a regression test asserting two sequential `/interview/start` calls get distinct `index_path` values containing their own `session_id`.

| Event | What happens |
|---|---|
| Session start | Fresh per-session `vector_stores/interview_{session_id}/` — `FAISS.from_documents(splits, embedding)` → `save_local(index_path)` |
| Any later session | Different `session_id` → different path → always rebuilds, never loads another session's index |
| Pod restart / process loss | The `InterviewSystem` object (LLM clients, RAG) is gone from `_active_sessions` entirely — there's no reconstruction path at all (see [[Backend]]), so this is moot for FAISS specifically |

Leftover per-session index directories under `vector_stores/` are **not cleaned up** after a session ends — a known, documented gap (disk growth over time), tracked in the production roadmap but not yet fixed.

## Document processing

`services/document_processor.py` — `DocumentProcessor`:
- Loads PDF via `PyPDF2` / TXT files
- Splits into chunks: `chunk_size=800`, `chunk_overlap=150` (from `InterviewConfig`)
- Returns `List[Document]` for FAISS ingestion

## Embeddings

| Provider | Model |
|---|---|
| `"openai"` / AIML API | `text-embedding-3-small` |
| `"gemini"` | `models/gemini-embedding-2-preview` |
| `"anthropic"` | Falls back to system key → `text-embedding-3-small` via AIML API |

## FAISS availability — import hardened (2026-07)

#gotcha **Fixed:** `rag_system.py` used to `try: import faiss` then, on `ImportError`, run `subprocess.check_call([sys.executable, "-m", "pip", "install", "faiss-cpu"])` at **module import time** — a blocking network install that could hang startup (no egress in some containers) or silently fail on a read-only filesystem, and risked installing an untested version outside the `faiss-cpu==1.11.0` pin in `requirements.txt`. Simplified to a plain top-level `from langchain_community.vectorstores import FAISS` — `faiss-cpu` is a hard dependency; a missing import is now a build/deploy bug that fails loudly, not something papered over at runtime.

`allow_dangerous_deserialization=True` is still set on `FAISS.load_local()` (required by langchain-community). Acceptable since the index is written by the same process, but worth remembering if index files are ever shared or received externally.

## Context fallback

If FAISS similarity search fails (exception), `_retrieve_context` sets `rag_context = ""` and continues. The analyzer receives no context, which degrades answer quality but doesn't crash the interview.

[[Codebase Map]] · [[Interview System]] · [[LangGraph Workflow]] · [[Session-scoped FAISS index]]
