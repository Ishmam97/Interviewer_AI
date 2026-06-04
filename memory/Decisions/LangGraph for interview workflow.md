---
type: decision
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - decision
  - langgraph
  - architecture
  - interview
---
# Decision: LangGraph for Interview Workflow

The interview system uses LangGraph (`StateGraph`) to define the question-answer-score-report pipeline.

**Why:** LangGraph was chosen to make the interview pipeline explicit, extensible, and inspectable. It provides a clear visual model of how state flows through the system: document processing → planning → Q&A loop → report. It also makes it easy to add new nodes (e.g. follow-up questions, hints, adaptive difficulty) without rewriting the control flow.

**Trade-off:**
- LangGraph is a heavy dependency for what is currently executed as a simple sequential pipeline
- The graph is **defined but never invoked end-to-end** in the REST API — individual methods are called directly by route handlers, making the graph more of a structural diagram than an actual runtime
- LangGraph's stateful features (checkpointing, replay, streaming) are not used
- The `execute_workflow()` method exists but calling it from a REST handler would run the entire interview synchronously in one HTTP request — breaking the turn-by-turn model

**How to apply:** Continue using LangGraph as the structural backbone — its graph definition documents the flow clearly. Do NOT call `execute_workflow()` from REST handlers. Add new interview steps as new graph nodes, but wire them into the REST flow imperatively. If the architecture ever moves to a streaming or websocket-first model, LangGraph's streaming support could be exploited properly.

[[Decisions Log]] · [[LangGraph]] · [[LangGraph Workflow]] · [[Interview System]]
