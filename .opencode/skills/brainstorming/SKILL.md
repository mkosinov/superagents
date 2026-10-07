---
name: brainstorming
description: Standalone brainstorm dialogue — turns an idea into a build / deliberately-NOT-build concept for user approval: explore context → clarifying questions one at a time → divergence phase (problem reframing, wide sweep with deferred judgment, one wild card) → 2-3 approaches with trade-offs → present the concept including User Scenarios. Explicit-only invocation: the user asks for it («побрейнштормим X»); no design gate routes through it (gate A auto-selects concepts since 2026-09-18). Run by @manager — the only role that talks to the user.
---

# Brainstorming: idea → concept

The dialogue core, run by @manager (the only role that talks to the user). Phase orchestration — scout, spec, spec panel, plan, plan review (gates A/B/C) — belongs to the DESIGN phase (host `design-phase` skill; in-container `@architect` fallback). This skill is a standalone dialogue on explicit user request; DESIGN never routes through it.

## Contract

- Input: an idea or change request from the user; the skill gathers context itself (files, docs, recent commits) — compact, no raw dumps.
- Output: a concept — what we build / what we deliberately do NOT build (scope boundaries) — plus a User Scenarios list (3-7 user tasks the feature enables, each mapping to an E2E test). Terminal state: explicit user approval. Then stop — if the user wants the feature designed, they hand the concept to DESIGN (in-container fallback: @manager dispatches @architect (DESIGN) with the concept as source material). v2: no scratchpad record — the concept travels in the dispatch prompt.
- Diverge before converging: the dialogue widens the option space (reframe → sweep → wild card) before narrowing it; the widening scales with the idea — full treatment for a large functional block, one quick reframe + short sweep for a small one.
- No implementation actions, no spec writing, no plan writing inside this skill.
- Anti-pattern "this is too simple to need a brainstorm": everything goes through the dialogue. A trivial concept may be 2-3 sentences, but it must be presented and approved — simple tasks are exactly where unexamined assumptions cost the most.
- Anti-pattern "the obvious solution wins by default": for a large functional block the first obvious approach must survive comparison against reframed and wild alternatives — it may still win, but it earns it.

## Process

1. **Explore project context** — files, docs, recent commits. Bulk recon → dispatch `explore` with a precise question (the manager never reads implementation sources itself).
2. **Ask clarifying questions** — one at a time; multiple choice preferred. Focus: purpose / constraints / success criteria. If the request spans several independent subsystems — flag decomposition to the user first; don't spend questions refining an undecomposed scope.
3. **Divergence phase — deferred judgment** (scale to the idea: full treatment for a large functional block; a small idea may collapse it to one alternative reframe + a short sweep, saying so out loud):
   - **Reframe the problem**: offer 2-3 alternative problem statements, including the "are we solving the right problem at all" check (classic: "make the elevator faster" → "make the waiting pleasant"). The user picks which problem is actually worth solving.
   - **Wide idea sweep**: generate MANY candidate directions for the chosen problem statement — quantity over quality, wild ideas explicitly welcome, **no evaluation yet**: feasibility, YAGNI, "existing patterns first" are parked until convergence (judging mid-sweep kills exactly the ideas the sweep exists to surface).
   - **One wild card**: at least one deliberately unconstrained direction — as if budget, technology, and the repo's current rules did not exist. It usually dies at convergence; its job is to expose the assumptions the "obvious" approach hides.
   - **Converge**: filter the sweep — real constraints, YAGNI (fires HERE, not during generation), genuine reuse — down to the 2-3 working approaches of the next step; one line each on what died and why.
4. **Propose 2-3 approaches** with trade-offs and a recommendation — recommended first, with the reasoning; the divergence survivors, never generated from thin air when a sweep exists.
5. **Present the design** in sections scaled to their complexity; ask after each section whether it looks right so far. Cover: architecture, components, data flow, error handling, testing. **Must include a User Scenarios list — 3-7 user tasks the feature enables, each mapping to an E2E test** (it seeds the spec's `## User Scenarios` section; the plan's E2E-in-DoD rule and the completeness panelist consume it). Design for isolation and clarity: every unit has one clear purpose, a defined interface, and can be understood and tested independently. In an existing codebase — existing patterns first; targeted improvements that affect the work belong in the design, unrelated refactoring does not.
6. **Finish:** present the concept (build / deliberately NOT build + scenarios) for explicit approval. Be ready to go back and clarify when something does not add up.

## Key Principles

- One question at a time — don't overwhelm with a list of questions.
- Multiple choice preferred — easier to answer than to formulate.
- Defer judgment — critique is parked while ideas are generated; it returns in full force at convergence.
- YAGNI ruthlessly — at convergence: cut everything without an explicit need. Never during the sweep.
- Explore alternatives before settling, not after — the divergence phase exists so the obvious approach must earn its win.
- Be flexible — go back and clarify when something doesn't make sense.
