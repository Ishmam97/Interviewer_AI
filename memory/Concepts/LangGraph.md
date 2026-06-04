---
type: concept
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - concept
  - langgraph
  - ai
  - workflow
---
# LangGraph

LangGraph is a library from LangChain for building stateful, graph-based AI workflows. It models AI pipelines as directed graphs where nodes are processing steps and edges define flow (including conditional branching).

## How it's used in this project

`services/workflow_manager.py` builds a `StateGraph(InterviewState)`. The graph has 7 nodes (document_processor, planner, question_generator, rag_retriever, response_analyzer, note_taker, report_generator) connected with edges and one conditional edge (`_should_continue_interview`).

## Important caveat for this project

The LangGraph graph is **defined but not invoked end-to-end** in the REST API. The `execute_workflow()` method exists but is never called by `server.py`. Instead, the REST handlers call `workflow_manager` methods directly and sequentially per HTTP request.

This means:
- LangGraph's checkpointing and replay features are not used
- LangGraph adds a dependency (~heavy) for what is essentially a structural diagram
- If the API were ever refactored to use `execute_workflow()`, it would run the full interview in one synchronous call and break the turn-by-turn REST model

See [[LangGraph Workflow]] for the full graph definition.

[[Concepts MOC]] · [[LangGraph Workflow]] · [[Interview System]]
