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

FAISS is stored in-memory + on local disk (Docker volume). If the session is reconstructed from Firestore after a pod restart, the FAISS index is gone. RAG silently falls back to empty context.

[[Concepts MOC]] · [[RAG System]] · [[Interview System]]
