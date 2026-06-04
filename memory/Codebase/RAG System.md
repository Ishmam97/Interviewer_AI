---
type: codebase-note
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - codebase
  - rag
  - faiss
  - embeddings
---
# RAG System

`services/rag_system.py` — `RAGSystem` class. Wraps a FAISS vector store for retrieval-augmented generation during interviews.

## How it works

1. At interview start, `InterviewSystem.setup_rag_system()` builds (or loads) a FAISS index from the resume + JD text
2. For each candidate answer, `_retrieve_context()` runs `similarity_search(question + answer, k=3)`
3. The top 3 matching chunks are concatenated into `rag_context` and injected into the `ResponseAnalyzer` prompt

## Index lifecycle

| Event | What happens |
|---|---|
| Session start (no existing index) | `FAISS.from_documents(splits, embedding)` → `save_local(index_path)` |
| Session start (index exists) | `FAISS.load_local(index_path)` + re-load document content (no re-embedding) |
| Pod restart / cache miss | Index is NOT available — `_reconstruct_session()` from Firestore doesn't restore FAISS |

Index path: `./vector_stores/interview_faiss_index` (Docker volume mount, survives container restarts but not pod-to-pod migrations).

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

## FAISS availability

`rag_system.py` tries `faiss-gpu` first, then auto-installs `faiss-cpu` as a fallback. If neither works, `RAGSystem.__init__` raises `ImportError`. In practice, containers ship with `faiss-cpu` in `requirements.txt`.

#gotcha `allow_dangerous_deserialization=True` is set on `FAISS.load_local()`. This is required by langchain-community but means the index file is trusted. The index is written by the same process so this is acceptable, but it's a security note worth remembering if index files are ever shared or received externally.

## Context fallback

If FAISS similarity search fails (exception), `_retrieve_context` sets `rag_context = ""` and continues. The analyzer receives no context, which degrades answer quality but doesn't crash the interview.

[[Codebase Map]] · [[Interview System]] · [[LangGraph Workflow]]
