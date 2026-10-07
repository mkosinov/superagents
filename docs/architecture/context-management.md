# Context Management Strategy

> Two-tier context model for the SuperAgents workflow. Role names are theory roles (controller, implementers); examples use one reference project («Memo») — substitute your own paths and docs.

## Two-Tier Context Model

The controller and implementers own different layers of context:

| Tier | Owner | Contains | Example |
|------|-------|----------|---------|
| **Architectural** | Controller | Component tree, data flow, task dependencies, interface contracts, scene-setting, classification | "ActivityCard renders inside DayColumn, receives data from useSchedule(), depends on Sidebar being ready. Task classification: standard." |
| **Implementation** | Implementers | Design tokens, API schemas, mock data, stack conventions, code patterns, test strategies | Colors #1E2D2F/#004D56, Tailwind classes, import paths, Pydantic models, TestClient fixtures |

## What the controller passes in the task prompt

**Required:**
- Task description verbatim from plan
- **Classification** (trivial/small/standard/large)
- Architectural position: where this fits, what it depends on, what depends on it
- Interface contracts: props, context shape, API signatures of adjacent components
- Document references (paths, NOT content — subagent reads them)
- Working directory path
- Required skill invocation (TDD, etc.)

**NOT passed** (subagent reads from docs via its own agent-definition instructions):
- Color hex codes, font sizes, spacing values → `docs/v4-design-system.md`
- API endpoint URLs, request/response schemas → `docs/memo-full-spec.md`
- Mock data structures → `docs/mock-data.md`
- FastAPI test patterns → the backend implementer's own knowledge

## Why this works

- The implementer's agent definition already instructs which docs to read before starting
- Controller doesn't duplicate design system in every prompt
- If implementer uses wrong color → implementer's fault (failed to read design system)
- If implementer doesn't know Sidebar exists → controller's fault (failed to provide architectural context)

## Boundary

| If this goes wrong | It's whose fault | Fix |
|---|---|---|
| Wrong color, font, spacing | Implementer | Update the implementer's agent definition |
| Component doesn't integrate with sibling | Controller | Improve architectural handoff |
| Missing edge case in tests | Implementer (TDD) | Add to acceptance criteria in plan |
| Implementation doesn't match plan spec | Both | The compliance reviewer catches this |
| Wrong test DB setup in FastAPI | Backend implementer | Update the backend implementer's agent definition |
| Acceptance criteria include meta doc update | Controller (plan error) | Separate product docs (implementer) from meta docs (scribe) |
| Controller edits code to "fix quickly" | Controller (leak) | Re-read "Controller Never Implements" rule |

## Example Contrast

**Wrong (controller holds all context):**
```
Task: Create ScheduleGrid. Design: #1E2D2F sidebar, #004D56 brand, 
cards with semi-transparent fill. API: /api/v1/schedule. 
Previous impl in memo-v1 uses React Context...
```

**Right (surgical, agent reads what it needs):**
```
Task: Create ScheduleGrid component in app/admin/schedule/
Classification: standard
Design reference: docs/v4-design-system.md
API reference: docs/memo-full-spec.md (Schedule section)
Previous impl reference: /root/workspace/memo-v1/memo-frontend/
Required skill: test-driven-development
```
