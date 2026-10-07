---
name: brainstorming
description: Brainstorm dialogue — idea → clarifying questions one at a time → divergence phase (problem reframing, wide sweep with deferred judgment, one wild card) → 2-3 approaches with trade-offs → a "build / deliberately NOT build" concept for user approval. Explicit-only invocation: the user asks for it (/brainstorming, «побрейнштормим X»). Never auto-fires from a task description; no design gate routes through it anymore (design-phase auto-selects concepts at gate A since 2026-09-18).
---

# Brainstorming: idea → concept

Host port of `.opencode/skills/brainstorming` (superagents canon), trimmed to the dialogue core: phase orchestration (spec, panel, plan, board, seam) belongs to the `design-phase` skill.

## Contract

- Input: an idea or an issue; the skill gathers context itself (files, docs, recent commits) — compact, no raw dumps.
- Output: a concept — what we build / what we deliberately do NOT build (scope boundaries) — plus a User Scenarios list (3-7 user tasks the feature enables, each mapping to an E2E test). Terminal state: explicit user approval. Then stop — spec, panel and plan are run by `design-phase` if the user hands the concept over («design #NNN» with the concept in context).
- Diverge before converging: the dialogue widens the option space (reframe → sweep → wild card) before narrowing it; the widening scales with the idea — full treatment for a large functional block, one quick reframe + short sweep for a small one.
- No implementation actions, no spec writing, no plan writing inside this skill.
- Anti-pattern "this is too simple to need a brainstorm": everything goes through the dialogue. A trivial concept may be 2-3 sentences, but it must be presented and approved — simple tasks are exactly where unexamined assumptions cost the most.
- Anti-pattern "the obvious solution wins by default": for a large functional block the first obvious approach must survive comparison against reframed and wild alternatives — it may still win, but it earns it.

## Process

1. **Survey the context** — what exists on the topic: files, docs, recent commits (in a DESIGN session — scout reports only).
2. **Clarifying questions** — one per message; multiple choice preferred. Goal: purpose / constraints / success criteria. If the idea splits into several independent subsystems — flag decomposition to the user first; don't interrogate details of an undecomposed scope.
3. **Divergence phase — deferred judgment** (scale to the idea: full treatment for a large functional block; a small idea may collapse it to one alternative reframe + a short sweep, saying so out loud):
   - **Reframe the problem**: offer 2-3 alternative problem statements, including the "are we solving the right problem at all" check (classic: "make the elevator faster" → "make the waiting pleasant"). The user picks which problem is actually worth solving.
   - **Wide idea sweep**: generate MANY candidate directions for the chosen problem statement — quantity over quality, wild ideas explicitly welcome, **no evaluation yet**: feasibility, YAGNI, "existing patterns first" are parked until convergence (judging mid-sweep kills exactly the ideas the sweep exists to surface).
   - **One wild card**: at least one deliberately unconstrained direction — as if budget, technology, and the repo's current rules did not exist. It usually dies at convergence; its job is to expose the assumptions the "obvious" approach hides.
   - **Converge**: filter the sweep — real constraints, YAGNI (fires HERE, not during generation), genuine reuse — down to the 2-3 working approaches of the next step; one line each on what died and why.
4. **2-3 approaches** with trade-offs and a recommendation; recommended first, with the why — the divergence survivors, never generated from thin air when a sweep exists.
5. **Present the concept** in sections scaled to their complexity; after each — "does this look right?". Cover: architecture, components, data flows, error handling, testing. **Include a User Scenarios list — 3-7 user tasks the feature enables, each mapping to an E2E test** (it seeds the spec's `## User Scenarios` section; the plan's E2E-in-DoD rule and the completeness panelist consume it). Design for isolation: every unit — one clear purpose, a usable interface, independently understandable and testable; internals changeable behind the boundary without breaking consumers. In an existing codebase — existing patterns first; improvements that touch the work belong in the design, unrelated refactoring does not.
6. **Finish:** the build / NOT-build concept + scenarios → explicit user approval. Then stop.

## Key Principles

- One question at a time — don't overwhelm with a list of questions.
- Multiple choice preferred — easier to answer than to formulate.
- Defer judgment — critique is parked while ideas are generated; it returns in full force at convergence.
- YAGNI ruthlessly — at convergence: cut everything without an explicit need. Never during the sweep.
- Explore alternatives before committing, not after — the divergence phase exists so the obvious approach must earn its win.
- Be flexible — go back and clarify when something doesn't add up.
