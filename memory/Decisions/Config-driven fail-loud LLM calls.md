---
type: decision
status: active
created: '2026-07-19'
updated: '2026-07-19'
tags:
  - decision
  - ai
  - llm
  - architecture
---
# Decision: Config-driven model IDs + fail-loud LLM error handling

Two related fixes made together on 2026-07-06, both correcting the same underlying pattern: every LLM-calling step in `resume_analyzer_service.py` and `dream_job_analyzer_service.py` hardcoded its model ID as a string literal, AND wrapped its call in `try/except Exception` returning a zero-filled default dict on any failure.

**Why this was CRITICAL:** the AIML API key was disabled at one point during testing (confirmed by the user directly — "i disabled the api key"). Because failures were swallowed, this meant every resume analysis and Dream Job run still reported `status: "completed"` with `score: 0` and empty lists — a fully-formed but meaningless report, with zero indication to the user or operator that anything had failed. The background-task handler *already* had correct logic to flip `status: "failed"` on an exception — the inner `except` blocks in the analyzer steps were the only thing preventing that logic from ever firing.

**The fix:**
1. Every model ID moved to `Settings` in `core/config.py` as an env-overridable field (`RESUME_PARSE_MODEL`, `RESUME_SECTION_MODEL`, `RESUME_HOLISTIC_MODEL`, `DREAM_JOB_NORMALIZE_MODEL`, `DREAM_JOB_FIT_MODEL`, `SUGGESTION_APPLY_MODEL`, `AIML_BASE_URL`). A retired/changed model ID is now an env edit, not a code change.
2. Every analyzer step's inner `except Exception: return {zero-filled defaults}` was changed to `except Exception: log; raise` — errors now propagate to the background-task handler, which correctly marks the Firestore doc `failed` with the real error message.

**Trade-off:** none identified — this is strictly a correctness fix. The only reason the old behavior might have seemed intentional is that it kept the API "always returning 200-shaped data," but that's exactly the problem: a caller (or the sweeper, or a human) needs to be able to tell "no opinion" apart from "this section legitimately wasn't found" apart from "the whole call failed."

**How to apply:** any new LLM-calling step must NOT swallow exceptions into a default return value. If a step can legitimately produce "no data" (e.g. a section genuinely absent from the resume), that must come from the model's own structured output (e.g. `"found": false`), never from a caught exception.

Regression tests: `tests/test_analyzer_fail_loud.py` — asserts a provider error or malformed JSON raises, not returns zeros. Also flipped 4 pre-existing tests that had encoded the *old, buggy* "returns empty structure on error" contract.

[[Decisions Log]] · [[AI Pipeline]] · [[Resume Analysis]] · [[Dream Job]]
