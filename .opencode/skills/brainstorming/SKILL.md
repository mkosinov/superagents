---
name: brainstorming
description: Phase 0 dialogue — turns an idea into an approved design concept (gate G1a): explore context → clarifying questions one at a time → 2-3 approaches with trade-offs → present the concept including User Scenarios. Invoked by @manager for new features / significant changes; after G1a the manager dispatches @architect (DESIGN) — spec, panel and plan are NOT part of this skill.
---

# Brainstorming: idea → concept (G1a)

The dialogue core of Phase 0, run by @manager (the only role that talks to the user). Phase orchestration — spec, spec panel, plan, plan review (gates G1b/G2) — belongs to @architect's DESIGN phase. In split mode DESIGN runs on the host and this skill is not used; in-container it serves the full-pipeline fallback path.

## Contract

- Input: an idea or change request from the user.
- Output: an approved design concept — what we build / what we deliberately do NOT build (scope boundaries) + a User Scenarios list. Terminal state: gate G1a (explicit user approval). Then stop — dispatch @architect (DESIGN) with the full design sections (the manager's Phase DESIGN protocol). v2: no scratchpad record — the concept travels in the dispatch prompt.
- No implementation actions, no spec writing, no plan writing inside this skill.
- Anti-pattern "this is too simple to need a brainstorm": everything goes through the dialogue. A trivial concept may be 2-3 sentences, but it must be presented and approved — simple tasks are exactly where unexamined assumptions cost the most.

## Process

1. **Explore project context** — files, docs, recent commits. Bulk recon → dispatch `explore` with a precise question (the manager never reads implementation sources itself).
2. **Ask clarifying questions** — one at a time; multiple choice preferred. Focus: purpose / constraints / success criteria. If the request spans several independent subsystems — flag decomposition to the user first; don't spend questions refining an undecomposed scope.
3. **Propose 2-3 approaches** with trade-offs and a recommendation — recommended first, with the reasoning.
4. **Present the design** in sections scaled to their complexity; ask after each section whether it looks right so far. Cover: architecture, components, data flow, error handling, testing. **Must include a User Scenarios list — 3-7 user tasks the feature enables, each mapping to an E2E test** (it seeds the spec's `## User Scenarios` section; the plan's E2E-in-DoD rule and the completeness panelist consume it). Design for isolation and clarity: every unit has one clear purpose, a defined interface, and can be understood and tested independently. In an existing codebase — existing patterns first; targeted improvements that affect the work belong in the design, unrelated refactoring does not.
5. **Gate G1a:** present the concept (build / deliberately NOT build + scenarios) for explicit approval. Be ready to go back and clarify when something does not add up.

## Key Principles

- One question at a time — don't overwhelm with a list of questions.
- Multiple choice preferred — easier to answer than to formulate.
- YAGNI ruthlessly — cut everything without an explicit need.
- Explore alternatives — 2-3 approaches before settling, not after.
- Be flexible — go back and clarify when something doesn't make sense.
