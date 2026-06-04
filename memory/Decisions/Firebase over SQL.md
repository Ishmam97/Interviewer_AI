---
type: decision
status: active
created: '2026-06-02'
updated: '2026-06-02'
tags:
  - decision
  - architecture
  - firebase
  - database
---
# Decision: Firebase Auth + Firestore over a Relational DB

The app uses Firebase Auth for identity and Firestore (NoSQL) for all persistence. No SQL database, no Redis.

**Why:** Firebase provides auth + db in one managed service with no infra to operate. For a personal demo project, this eliminates a whole infrastructure layer. Firestore's document model fits the session/profile data shapes well.

**Trade-off:**
- No transactions across documents → duplicates in `interview_reports` are possible without careful app-level guards
- No schema enforcement → fields can drift silently between versions
- No unique constraints → `(user_id, session_id)` in `interview_reports` must be enforced in code
- No native pagination → sessions list will slow down for prolific users
- No SQL joins → related data (session + report) requires multiple reads

**How to apply:** When querying related data, always fetch documents separately and join in Python. When writing data that must be unique, check for existing records first in the same transaction context (Firestore batch writes). Don't add SQL or Redis without a deliberate decision.

[[Decisions Log]] · [[Data Model]] · [[Backend]]
