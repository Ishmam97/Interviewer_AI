---
type: concept
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - concept
  - rag
  - embeddings
  - faiss
---
# RAG (Retrieval-Augmented Generation)

RAG is a technique where relevant documents (or chunks of documents) are retrieved from a vector store and injected into the LLM prompt as context. This grounds the LLM's response in the actual content rather than relying purely on its training data.

## How it's used in this project

At interview start, the user's resume and job description are chunked and embedded into a FAISS vector index. For each interview question, the system retrieves the top-3 most semantically similar chunks using the question + answer as the search query. These chunks become `rag_context` in the response analysis prompt — so the LLM can reference actual resume content when scoring the answer.

**Result:** questions and scoring are grounded in the specific resume and JD, not generic interview logic.

## Vector store: FAISS

Facebook AI Similarity Search — an in-process vector similarity library. Chosen for simplicity (no external service needed). See [[RAG System]] for the full implementation.

## Embeddings

`text-embedding-3-small` (OpenAI/AIML API) by default. 1536-dimensional vectors. Chunk size: 800 tokens, overlap: 150 tokens.

## Limitation

FAISS is stored on local disk (Docker volume), now **per-session** (fixed 2026-07 — see [[Session-scoped FAISS index]], which closed a real cross-user data leak from the old shared-path default). There is no session reconstruction at all after a pod restart (no `_reconstruct_session()` exists) — the whole `InterviewSystem` object, FAISS included, is simply gone; `/interview/answer` returns a clean 404 rather than silently degrading.

[[Concepts MOC]] · [[RAG System]] · [[Interview System]] · [[Session-scoped FAISS index]]
