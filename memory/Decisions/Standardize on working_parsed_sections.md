---
type: decision
status: active
created: '2026-07-19'
updated: '2026-07-19'
tags:
  - decision
  - data-model
  - resume
---
# Decision: standardize resume-edit persistence on `working_parsed_sections`

Resolved 2026-07-19 — explicit user direction after being presented with the three-way split as a genuine architectural ambiguity.

**The split that existed:** three different, partially-overlapping stores for "the user's currently-edited resume":
1. `profile.edited_resume_data` — written by the single-suggestion accept/undo flow (the original implementation)
2. `resume_parsed_sections/{analysis_id}.working_parsed_sections` — written by the newer bulk-apply flow and read by Dream Job's resume input
3. A `set_working_parsed_sections` FirebaseManager method — existed, had an ownership check, but was **never actually called** by any route; the 5 backend tests that exercised it were failing because the code didn't match what the tests (written against the intended target state) expected.

**Options considered:** (a) standardize on `working_parsed_sections` — migrate the older single-suggestion path onto it; (b) standardize on `edited_resume_data` — migrate bulk-apply and Dream Job the other way, and rewrite the 5 tests to match; (c) just fix the failing tests to match whatever the code currently does, deferring the real consolidation.

**Chosen: (a).** `working_parsed_sections` was already the store two of three flows used, and it lives in a purpose-built collection (`resume_parsed_sections`, keyed by `analysis_id`) rather than piggybacking on the user's `profiles` doc — a cleaner separation of "identity/profile" from "per-analysis working state."

**What changed:** `_apply_suggestion_to_resume` and `_restore_suggestion_snapshot` (the single-suggestion accept/undo helpers) now read via `fb.get_resume_parsed_doc(analysis_id)` and write via `fb.set_working_parsed_sections(analysis_id, user_id, data)` — the same store and the same dedicated method bulk-apply already had access to (though bulk-apply itself still does a raw Firestore `.update()` rather than calling the shared method — a known minor inconsistency, low priority, untouched). Undo-snapshot keys changed from `{user_id}:{suggestion_id}` to `{user_id}:{analysis_id}:{suggestion_id}` — the 2-part key couldn't disambiguate a suggestion across two different analyses of the same user (e.g. re-uploading a resume and hitting the same suggestion id twice). `profile.edited_resume_data` is no longer read or written anywhere — verified via a full-codebase grep, frontend included (one `ProfilePage.tsx` comment references it by name only to explain what NOT to use).

**Result:** the last 5 failing backend tests now pass — the suite is 147/147 green (was 79/33 failing at the very start of the hardening sprint).

**How to apply:** any future resume-editing feature reads/writes through `working_parsed_sections` via the FirebaseManager methods (`get_resume_parsed_doc`, `set_working_parsed_sections`, `ensure_working_parsed_sections`), never a raw Firestore call and never `profile.edited_resume_data`.

[[Decisions Log]] · [[Resume Analysis]] · [[Data Model]]
