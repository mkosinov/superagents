---
name: brainstorming
description: "You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by understanding the current project context, then ask questions one at a time to refine the idea. Once you understand what you're building, present the design and get user approval.

<HARD-GATE>
Do NOT invoke any implementation skill, write any code, scaffold any project, or take any implementation action until:
1. You have presented a design and the user has approved it (design concept approval)
2. You have written the design to a spec file and the user has EXPLICITLY approved the WRITTEN SPEC (file review approval)

Both approvals are REQUIRED. The second approval (written spec) is the gate that blocks all implementation. No exceptions.
</HARD-GATE>

## Anti-Pattern: "This Is Too Simple To Need A Design"

Every project goes through this process. A todo list, a single-function utility, a config change — all of them. "Simple" projects are where unexamined assumptions cause the most wasted work. The design can be short (a few sentences for truly simple projects), but you MUST present it and get approval.

## Checklist

You MUST create a task for each of these items and complete them in order:

1. **Explore project context** — check files, docs, recent commits
2. **Ask clarifying questions** — one at a time, understand purpose/constraints/success criteria
3. **Propose 2-3 approaches** — with trade-offs and your recommendation
4. **Present design sections** — in sections scaled to their complexity, get user approval after each section. **Must include a `## User Scenarios` section** listing 3-7 user tasks the feature enables. Each scenario maps to an E2E test (see testing-strategy-v2 / User Scenario workflow).
5. **Write design doc** — save to `docs/specs/YYYY-MM-DD-<topic>-design.md` and commit
6. **Spec self-review** — quick inline check for placeholders, contradictions, ambiguity, scope
7. **Spec Panel Review** — run the 5-perspective spec review panel (see "Spec Panel Review" section below), present consolidated findings with the spec
8. **User reviews written spec** — ask user to review the spec file before proceeding
9. **Get EXPLICIT written spec approval** — user must confirm they reviewed the file and approve it as-is
10. **Transition to implementation** — ONLY after step 9, invoke writing-plans skill to create implementation plan

**CRITICAL:** Steps 4 and 9 are TWO SEPARATE approvals. Step 4 is "design concept looks right". Step 9 is "the written spec file is correct and I approve it for implementation". Do NOT skip step 9.

## Process Flow

```
Explore project context → Ask clarifying questions → Propose 2-3 approaches → Present design sections → User approves? → Write design doc → Spec self-review → Spec panel review → User reviews spec? → Invoke writing-plans skill
```

**The terminal state is invoking writing-plans.** Do NOT invoke frontend-design, mcp-builder, or any other implementation skill. The ONLY skill you invoke after brainstorming is writing-plans.

## The Process

**Understanding the idea:**

- Check out the current project state first (files, docs, recent commits)
- Before asking detailed questions, assess scope: if the request describes multiple independent subsystems, flag this immediately. Don't spend questions refining details of a project that needs to be decomposed first.
- For appropriately-scoped projects, ask questions one at a time to refine the idea
- Prefer multiple choice questions when possible, but open-ended is fine too
- Only one question per message
- Focus on understanding: purpose, constraints, success criteria

**Exploring approaches:**

- Propose 2-3 different approaches with trade-offs
- Present options conversationally with your recommendation and reasoning
- Lead with your recommended option and explain why

**Presenting the design:**

- Once you believe you understand what you're building, present the design
- Scale each section to its complexity: a few sentences if straightforward, up to 200-300 words if nuanced
- Ask after each section whether it looks right so far
- Cover: architecture, components, data flow, error handling, testing
- Be ready to go back and clarify if something doesn't make sense

**Design for isolation and clarity:**

- Break the system into smaller units that each have one clear purpose, communicate through well-defined interfaces, and can be understood and tested independently
- For each unit, you should be able to answer: what does it do, how do you use it, and what does it depend on?
- Can someone understand what a unit does without reading its internals? Can you change the internals without breaking consumers? If not, the boundaries need work.

**Working in existing codebases:**

- Explore the current structure before proposing changes. Follow existing patterns.
- Where existing code has problems that affect the work, include targeted improvements as part of the design.
- Don't propose unrelated refactoring. Stay focused on what serves the current goal.

## After the Design

**Documentation:**

- Write the validated design (spec) to `docs/specs/YYYY-MM-DD-<topic>-design.md`
- **The spec MUST include a `## User Scenarios` section** (3-7 user tasks the feature enables, each mapping to an E2E test)
- Commit the design document to git

**Spec Self-Review:**
After writing the spec document, look at it with fresh eyes:

1. **Placeholder scan:** Any "TBD", "TODO", incomplete sections, or vague requirements? Fix them.
2. **Internal consistency:** Do any sections contradict each other?
3. **Scope check:** Is this focused enough for a single implementation plan?
4. **Ambiguity check:** Could any requirement be interpreted two different ways?

Fix any issues inline. No need to re-review — just fix and move on.

**Spec Panel Review (automated — runs BEFORE the user gate):**

After the spec self-review passes, run the spec review panel — 5 parallel subagents, each analyzing the spec from one perspective:

| Perspective | Subagent |
|-------------|----------|
| Completeness | `spec-review-completeness` |
| Feasibility | `spec-review-feasibility` |
| Consistency | `spec-review-consistency` |
| Simplicity / YAGNI | `spec-review-simplicity` |
| Best Practices | `spec-review-best-practices` |

1. Dispatch all 5 **in parallel** (single message, 5 Task calls). Each dispatch prompt MUST contain the spec file path and instruct the panelist to read it.
2. Wait for all reports.
3. Aggregate: deduplicate overlapping findings, rank BLOCKER → MAJOR → MINOR, note where perspectives agree (agreement = stronger signal).
4. Present the consolidated report to the user alongside the spec. Ask: fix, dismiss, or approve.
5. If the user requests changes → revise the spec → re-run the panel on the revision → back to step 4.

**Skip rule:** you MAY skip the panel for trivial specs (< ~50 lines). State the skip explicitly.

**Availability policy (retry → partial skip → full skip):**
- Panelist fails → retry up to 2 more times (3 attempts total). Still failing → skip that perspective, mark "perspective X unavailable (quota exhausted / error)" in the consolidated report, proceed with the rest. A panelist returning `Verdict: FAILED` in its report counts as a failing panelist under this policy (the panelist refused to produce findings because its distinguishing capability was unavailable — e.g. researcher-agent unreachable for the best-practices panelist).
- ALL 5 unavailable → skip the panel entirely, warn the user explicitly ("spec panel skipped — all free models unavailable, spec not independently reviewed"), proceed to the user review gate.

**User Review Gate (BLOCKING):**
After the spec review loop passes, ask the user to review the written spec before proceeding:

> "Spec written and committed to `<path>`. Please review the file and confirm: (1) you have read it, and (2) you approve it as the basis for implementation. **Also confirm the spec has a `## User Scenarios` section.** If you want changes, tell me now — I will NOT start the implementation plan until you explicitly approve this spec."

**This is a HARD BLOCK.** Do NOT:
- Invoke writing-plans skill
- Create any implementation plan
- Start any coding
- Proceed to Step 2 of the workflow

Until the user explicitly confirms: "I have reviewed the spec and approve it" or equivalent.

Wait for the user's response. If they request changes, make them and re-run the spec review loop. Only proceed once the user gives EXPLICIT written approval.

**Implementation:**

- Invoke the writing-plans skill to create a detailed implementation plan
- Do NOT invoke any other skill. writing-plans is the next step.

## Key Principles

- **One question at a time** - Don't overwhelm with multiple questions
- **Multiple choice preferred** - Easier to answer than open-ended when possible
- **YAGNI ruthlessly** - Remove unnecessary features from all designs
- **Explore alternatives** - Always propose 2-3 approaches before settling
- **Incremental validation** - Present design, get approval before moving on
- **Be flexible** - Go back and clarify when something doesn't make sense
