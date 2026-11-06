#!/usr/bin/env bash
set -euo pipefail
# One-shot continuation for this exact conversation. The scheduler supplies PATH.
cd /home/ishmam/github/Interviewer_AI
exec /home/ishmam/.nvm/versions/node/v24.3.0/bin/codex queue \
  --thread 01a1b01d-769e-7ea3-9342-5d2668306194 \
  --message 'Continue the authorized Interviewer AI work from the current checkout and conversation. Read docs/launch-2026 and docs/audits, preserve existing edits, finish the modern landing page and persistent beta signup, aggregate the Terra audits and Luna implementation documentation into the complete UI/UX/backend/business/monetization/B2B launch plan, and run appropriate checks. If already complete, report status without starting unrelated work. Do not expose credentials or deploy publicly without a reviewed launch configuration.' \
  --resume
