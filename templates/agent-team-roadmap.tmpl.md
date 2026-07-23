# Agent-Team Roadmap Workflow (portable template)

A reusable orchestrator → specialist-team → synthesizer → reviewer pattern for producing a
**full product roadmap + path-to-production plan** in any repository, using Claude Code's
`Workflow` tool. Port this file into another repo (keep it in `templates/` or `docs/`), fill
the placeholders, then ask Claude Code to *"run the agent-team roadmap workflow from
templates/agent-team-roadmap.tmpl.md"*.

---

## The pattern

```
 YOU (orchestrator)                                    YOU (reviewer)
      │                                                     ▲
      ▼                                                     │
 ┌─ Phase 1: Research & Analysis (parallel) ─┐   ┌─ Phase 2 ─┐
 │  A1 market researcher   (opus,  xhigh, web)│   │ synthesizer│──► docs/roadmap/*.md
 │  A2 production-gap analyst (sonnet, xhigh) │──►│ (opus,     │
 │  A3 deploy-path engineer   (sonnet, xhigh) │   │  xhigh)    │
 │  A4 UX/monetization auditor(sonnet, xhigh) │   └────────────┘
 └────────────────────────────────────────────┘
```

Rules of the pattern:

1. **Orchestrate, don't do.** The main session writes the workflow and reviews the output;
   the specialists do the reading/searching/analysis. Keeps the main context clean for judgment.
2. **Structured outputs.** Every specialist returns a JSON schema (below), so the synthesizer
   consumes clean data instead of prose. Schemas force S/M/L efforts, evidence citations, and
   blocking/non-blocking verdicts.
3. **Barrier before synthesis.** `parallel()` is correct here (not `pipeline()`) because the
   synthesizer genuinely needs all four results at once.
4. **Review loop.** After the workflow returns, the orchestrator READS the produced roadmap and
   grades it against the review checklist (bottom of this file). If unsatisfied: edit the
   persisted script (the Workflow tool prints its path) to sharpen the weak specialist's prompt,
   then re-invoke with `{scriptPath, resumeFromRunId}` — unchanged agents replay from cache, only
   the edited one re-runs. Repeat until it passes.
5. **Model/effort mix.** Judgment-heavy roles (market research, synthesis) → `opus` + `xhigh`.
   Code-reading roles (gaps, deploy, UX) → `sonnet` + `xhigh`. Adjust per budget.
6. **Specialists are context-blind.** They cannot see your conversation. Everything they need —
   product description, current state, repo paths — must be in `PRODUCT` / `STATE` below.

## Placeholders to fill

| Placeholder | What goes there |
|---|---|
| `{{REPO_ROOT}}` | Absolute path to the repo |
| `{{PRODUCT_DESCRIPTION}}` | 5–15 lines: what the product does, every major feature, the stack, what does NOT exist yet (payments, mobile, i18n…), team size |
| `{{CURRENT_STATE}}` | What is already DONE and verified (so agents don't re-litigate it), plus the KNOWN OPEN ITEMS you already know belong in the roadmap. Be exhaustive — this is the single highest-leverage input. |
| `{{KEY_DOCS}}` | Paths to existing audits/assessments/ADRs agents should read first |
| `{{DEPLOY_RAILS}}` | The existing deployment target ("Cloud Run + Firebase Hosting", "Vercel + Supabase", …) — tells the deploy agent not to replatform |
| `{{COMPETITORS}}` | Named competitor list for the market researcher (or "discover them") |

## The workflow script

Paste the filled-in version into the `Workflow` tool (`script` input). It is plain JavaScript —
no TypeScript syntax, no `Date.now()`/`Math.random()`.

```js
export const meta = {
  name: 'production-roadmap-team',
  description: 'Agent team: market research + gap analysis + deploy path + UX audit, synthesized into a production roadmap',
  phases: [
    { title: 'Research & Analysis', detail: '4 parallel specialists (opus/sonnet, xhigh)' },
    { title: 'Synthesize', detail: 'opus xhigh writes docs/roadmap/production-roadmap.md' },
  ],
}

const ROOT = '{{REPO_ROOT}}'

const PRODUCT = `
PRODUCT: {{PRODUCT_DESCRIPTION}}
`

const STATE = `
CURRENT STATE (do NOT re-litigate — DONE and verified):
{{CURRENT_STATE}}

KNOWN OPEN ITEMS (these belong IN the roadmap):
{{KNOWN_OPEN_ITEMS}}

Key repo docs: {{KEY_DOCS}}
`

// ── Schemas: force decision-ready output ─────────────────────────────────────
const RESEARCH_SCHEMA = {
  type: 'object',
  required: ['pain_points', 'competitors', 'pricing_recommendation', 'feature_recommendations', 'anti_recommendations'],
  properties: {
    pain_points: { type: 'array', items: { type: 'object', required: ['pain', 'evidence', 'our_coverage'], properties: {
      pain: { type: 'string' }, evidence: { type: 'string' },
      our_coverage: { type: 'string', enum: ['yes', 'partial', 'no'] } } } },
    competitors: { type: 'array', items: { type: 'object', required: ['name', 'pricing', 'differentiator', 'weakness'], properties: {
      name: { type: 'string' }, pricing: { type: 'string' }, differentiator: { type: 'string' }, weakness: { type: 'string' } } } },
    pricing_recommendation: { type: 'string' },
    feature_recommendations: { type: 'array', items: { type: 'object', required: ['feature', 'evidence', 'build_size', 'monetization_signal'], properties: {
      feature: { type: 'string' }, evidence: { type: 'string' }, build_size: { type: 'string', enum: ['S', 'M', 'L'] },
      monetization_signal: { type: 'string', enum: ['strong', 'moderate', 'weak'] } } } },
    anti_recommendations: { type: 'array', items: { type: 'string' } },
    positioning: { type: 'string' },
  },
}

const GAP_SCHEMA = {
  type: 'object',
  required: ['items', 'readiness_verdict'],
  properties: {
    items: { type: 'array', items: { type: 'object', required: ['area', 'description', 'effort', 'blocking_launch'], properties: {
      area: { type: 'string' }, description: { type: 'string' },
      effort: { type: 'string', enum: ['S', 'M', 'L'] },
      blocking_launch: { type: 'boolean' }, rationale: { type: 'string' } } } },
    readiness_verdict: { type: 'string' },
  },
}

const DEPLOY_SCHEMA = {
  type: 'object',
  required: ['launch_steps', 'user_decisions_needed', 'post_launch_ops'],
  properties: {
    launch_steps: { type: 'array', items: { type: 'object', required: ['order', 'step', 'detail'], properties: {
      order: { type: 'number' }, step: { type: 'string' }, detail: { type: 'string' },
      user_action: { type: 'boolean' } } } },
    user_decisions_needed: { type: 'array', items: { type: 'object', required: ['decision', 'options', 'recommendation'], properties: {
      decision: { type: 'string' }, options: { type: 'string' }, recommendation: { type: 'string' } } } },
    post_launch_ops: { type: 'array', items: { type: 'string' } },
    estimated_monthly_cost: { type: 'string' },
  },
}

const UX_SCHEMA = {
  type: 'object',
  required: ['ui_worklist', 'monetization_surfaces', 'quick_wins'],
  properties: {
    ui_worklist: { type: 'array', items: { type: 'object', required: ['item', 'files', 'effort', 'impact'], properties: {
      item: { type: 'string' }, files: { type: 'string' }, effort: { type: 'string', enum: ['S', 'M', 'L'] },
      impact: { type: 'string', enum: ['high', 'medium', 'low'] } } } },
    monetization_surfaces: { type: 'array', items: { type: 'object', required: ['surface', 'mechanism', 'files'], properties: {
      surface: { type: 'string' }, mechanism: { type: 'string' }, files: { type: 'string' } } } },
    quick_wins: { type: 'array', items: { type: 'string' } },
    recommended_palette_strategy: { type: 'string' },
  },
}

phase('Research & Analysis')
log('Spawning 4 specialists: market (opus), gaps (sonnet), deploy (sonnet), UX (sonnet) — all xhigh')

const COMMON = `You are one specialist on a team producing a production roadmap for this product. Your output feeds a synthesis agent, so return dense, concrete, decision-ready data — no filler.\n${PRODUCT}\n${STATE}\n`

const [research, gaps, deploy, ux] = await parallel([
  () => agent(
    COMMON + `YOUR ROLE: Market researcher. You have web access — use ToolSearch to load WebSearch and WebFetch, then run AT LEAST 10 distinct searches and fetch the most promising sources. Prefer recent sources.

Research four threads:
1. PAIN POINTS: what target users say is hard / frustrating about existing solutions (relevant subreddits, HN, forums). Verbatim quotes where possible. Map each to whether OUR product covers it (yes/partial/no).
2. COMPETITORS: {{COMPETITORS}}. Exact pricing tiers, core features, positioning, and CITED user complaints (Trustpilot/G2/app stores/Reddit) — their weaknesses are our openings.
3. WILLINGNESS TO PAY: what these users demonstrably pay for today. Price points and the outcomes that open wallets.
4. TRENDS: what is growing vs gimmick in this space right now, with demand evidence.

Every claim needs a real fetched/found source. Be honest about monetization_signal strength. Recommendations must be feasible for this team on this stack.`,
    { label: 'market-research', phase: 'Research & Analysis', model: 'opus', effort: 'xhigh', schema: RESEARCH_SCHEMA },
  ),
  () => agent(
    COMMON + `YOUR ROLE: Production-gap analyst. READ-ONLY on the repo at ${ROOT}. Read the key docs listed above first, then verify against current code (the CURRENT STATE section is authoritative on what's done; verify anything you doubt by reading the code).

Produce the honest, complete list of what remains between today's codebase and a public launch: correctness gaps, data-integrity gaps, security/rules gaps, observability (what breaks silently in prod and how would the owner know), test coverage of the riskiest paths, scaling constraints. For each item: concrete description with file refs, S/M/L effort, and whether it truly BLOCKS a public launch or is post-launch acceptable. Resist gold-plating: calibrate to this team going to FIRST users, not a bank.`,
    { label: 'gap-analysis', phase: 'Research & Analysis', model: 'sonnet', effort: 'xhigh', schema: GAP_SCHEMA },
  ),
  () => agent(
    COMMON + `YOUR ROLE: Deployment-path engineer. READ-ONLY on the repo at ${ROOT}. Read the CI/CD configs, Dockerfiles, env examples, and app config.

Produce the exact, ordered launch runbook from today's state to a live public deployment on the EXISTING rails ({{DEPLOY_RAILS}} — do not propose replatforming). Include console actions (secrets manager, IAM, DB rules), CI/CD file changes needed, required env vars and where each comes from, build-time frontend vars, custom domain + CORS updates, and a smoke-test checklist for first deploy. Flag every step only the owner can perform (user_action=true). Then post-launch ops for the first 30 days (uptime checks, alerting, cost caps, backups) and a rough monthly cost estimate at 0/100/1000 MAU.`,
    { label: 'deploy-path', phase: 'Research & Analysis', model: 'sonnet', effort: 'xhigh', schema: DEPLOY_SCHEMA },
  ),
  () => agent(
    COMMON + `YOUR ROLE: UX + monetization-surface auditor. READ-ONLY on the frontend source at ${ROOT}.

TASK A — UI/polish worklist: enumerate visual inconsistency, asset-weight problems, dead theming infra, a11y basics, naming inconsistency — file-by-file with S/M/L effort and user-visible impact, plus a decisive recommendation where designs conflict.
TASK B — monetization surfaces: for a future freemium model, identify WHERE in this specific codebase free/paid boundaries would live: the cost-expensive user actions, which backend routes would enforce a usage counter and where the counter would be stored, what a Stripe integration would touch, and which existing UI components would host upgrade prompts. Concrete file refs throughout.
TASK C — quick wins: under-1-hour items with outsized perceived-quality impact.`,
    { label: 'ux-monetization', phase: 'Research & Analysis', model: 'sonnet', effort: 'xhigh', schema: UX_SCHEMA },
  ),
])

log(`Specialists done: ${JSON.stringify({ research: !!research, gaps: !!gaps, deploy: !!deploy, ux: !!ux })}`)

phase('Synthesize')
const synthesis = await agent(
  `You are the roadmap synthesizer. Below: product context, current state, and structured outputs from 4 specialists (some may be null — work with what exists and note gaps).
${PRODUCT}
${STATE}
MARKET RESEARCH:\n${JSON.stringify(research, null, 2)}
PRODUCTION GAPS:\n${JSON.stringify(gaps, null, 2)}
DEPLOY PATH:\n${JSON.stringify(deploy, null, 2)}
UX + MONETIZATION:\n${JSON.stringify(ux, null, 2)}

Write the definitive roadmap to ${ROOT}/docs/roadmap/production-roadmap.md. Structure:
1. Executive summary — product standing, positioning wedge, recommended sequence (~10 lines).
2. Path to production — phased plan: Phase A "Launchable" (blocking items + launch runbook, OWNER-ONLY actions marked), Phase B "Presentable" (UI worklist + quick wins), Phase C "Sellable" (pricing tiers, usage-gating routes, Stripe scope), Phase D "Growable" (ops, deferred ADRs, top researched features). Each phase: goal, itemized S/M/L work, rough calendar estimate, explicit exit criteria.
3. Feature roadmap — research recommendations ranked by monetization signal vs build size, evidence cited, mapped to phases; include anti-recommendations.
4. Pricing — recommended freemium structure with competitor-grounded price points.
5. Open decisions for the owner — each with a recommendation.
6. Cost model — monthly estimate at 0/100/1000 MAU.
7. Risks — top 5 with mitigations.
Rules: every feature claim cites research evidence; every code claim keeps file refs; efforts stay S/M/L; be decisive. Final message: file path + 10-line executive summary.`,
  { label: 'synthesize-roadmap', phase: 'Synthesize', model: 'opus', effort: 'xhigh' },
)

return { synthesis, specialistResults: { research, gaps, deploy, ux } }
```

## Reviewer checklist (the orchestrator runs this AFTER the workflow)

Read the produced `docs/roadmap/production-roadmap.md` and grade it. Re-run (via
`{scriptPath, resumeFromRunId}` with a sharpened prompt for the failing specialist) until ALL pass:

- [ ] **Grounded** — every feature recommendation cites real, named evidence (a source, a review, a price page), not vibes. Spot-check 2–3 citations.
- [ ] **Honest efforts** — S/M/L sizes are plausible against the actual code; no "add Stripe: S".
- [ ] **Blocking discipline** — Phase A contains ONLY genuine launch blockers; nothing gold-plated in, nothing critical deferred out.
- [ ] **Owner actions explicit** — every step requiring keys/billing/console access is marked; the owner could execute Phase A from the doc alone.
- [ ] **Decisive** — recommendations everywhere, option menus only in the "Open decisions" section.
- [ ] **Anti-recommendations present** — the doc says what NOT to build.
- [ ] **Costs sanity-check** — the MAU cost model states its LLM-usage assumptions.
- [ ] **Consistency** — phases don't contradict the gap analysis; pricing doesn't contradict the competitor table.

## Porting notes

- Roles are swappable: for a library/API product, replace the UX auditor with a DX auditor
  (docs, examples, error messages) and monetization surfaces with adoption surfaces.
- If the repo has no existing audit doc, add a 5th specialist that produces one first, and make
  the gap analyst consume it (`pipeline` those two, keep the rest `parallel`).
- Rate limits: specialists that die on session limits return `null`; the synthesizer is
  instructed to tolerate nulls. Re-run later with `resumeFromRunId` — completed agents are cached.
- Keep `STATE` current between runs: after acting on the roadmap, update the CURRENT STATE /
  KNOWN OPEN ITEMS blocks before re-running, or agents will re-report solved problems.
