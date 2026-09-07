---
name: brainstorming
description: Brainstorm dialogue — idea → clarifying questions one at a time → 2-3 approaches with trade-offs → a "build / deliberately NOT build" concept for user approval (gate G1a). Explicit-only invocation: the user asks for it (/brainstorming, «побрейнштормим X») or design-phase dispatches it at G1a. Never auto-fires from a task description.
---

# Brainstorming: idea → concept (G1a)

Host port of `.opencode/skills/brainstorming` (superagents canon), trimmed to the G1a dialogue core: phase orchestration (spec, panel, plan, board, seam) belongs to the `design-phase` skill.

## Contract

- Input: an idea or an issue. In a DESIGN session `design-phase` passes the scout fact sheet + issue number; on a standalone call the skill gathers context itself (files, docs, recent commits) — compact, no raw dumps.
- Output: a concept — what we build / what we deliberately do NOT build (scope boundaries) — plus a User Scenarios list (3-7 user tasks the feature enables, each mapping to an E2E test). Terminal state: explicit user approval (G1a). Then stop — spec, panel and plan are run by `design-phase` (on a standalone call — the user's normal workflow).
- No implementation actions, no spec writing, no plan writing inside this skill.
- Anti-pattern "this is too simple to need a brainstorm": everything goes through the dialogue. A trivial concept may be 2-3 sentences, but it must be presented and approved — simple tasks are exactly where unexamined assumptions cost the most.

## Process

1. **Survey the context** — what exists on the topic: files, docs, recent commits (in a DESIGN session — scout reports only).
2. **Clarifying questions** — one per message; multiple choice preferred. Goal: purpose / constraints / success criteria. If the idea splits into several independent subsystems — flag decomposition to the user first; don't interrogate details of an undecomposed scope.
3. **2-3 approaches** with trade-offs and a recommendation; recommended first, with the why.
4. **Present the concept** in sections scaled to their complexity; after each — "does this look right?". Cover: architecture, components, data flows, error handling, testing. **Include a User Scenarios list — 3-7 user tasks the feature enables, each mapping to an E2E test** (it seeds the spec's `## User Scenarios` section; the plan's E2E-in-DoD rule and the completeness panelist consume it). Design for isolation: every unit — one clear purpose, a usable interface, independently understandable and testable; internals changeable behind the boundary without breaking consumers. In an existing codebase — existing patterns first; improvements that touch the work belong in the design, unrelated refactoring does not.
5. **Finish = the gate:** the build / NOT-build concept + scenarios → explicit user approval. In a DESIGN session this is G1a; control returns to `design-phase`.

## Key Principles

- One question at a time — don't overwhelm with a list of questions.
- Multiple choice preferred — easier to answer than to formulate.
- YAGNI ruthlessly — cut everything without an explicit need.
- Explore alternatives — 2-3 approaches before committing, not after.
- Be flexible — go back and clarify when something doesn't add up.
