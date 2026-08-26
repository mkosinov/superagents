# Decision Log

> Architecture decisions for SuperAgents workflow v3.2.

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | @manager merged into @architect | Single entry point, single controller for workflow |
| 2 | @tester removed | TDD absorbed into implementers; review is two-stage automatic |
| 3 | Separate spec-reviewer and code-quality-reviewer agents | Dedicated roles, read-only permissions, cheap models |
| 4 | Reviewer prompts stored as markdown templates (NOT skills) | Read by architect via `read` tool, filled, passed as prompt to `task()` |
| 5 | No project skill for context | Token economy — domain knowledge lives in `agent.md` |
| 6 | Auto-create PR as default (Option 2) | Standard for feature work, user can still choose others |
| 7 | Docser commits into feature branch before finishing | PR includes documentation, reviewer sees full picture |
| 8 | Spec.md in docs/harness/ | Easy to find, not buried in hidden directories |
| 9 | No project skill, agents read docs on-demand | Surgical context — controller minimal, agents responsible for their domain |
| 10 | Reviewers receive git diff in prompt, not file paths | Eliminates duplicate file reads across sessions; biggest cost driver |
| 11 | Code-quality-reviewer runs test suite | Closes verification gap — reviewers don't just read code, they verify tests pass |
| 12 | Keep two separate reviewers (not consolidated) | Two-stage review is core principle. Cost solved by git diff |
| 13 | Doc tier separation (product vs meta) | Product docs (README) in implementer tasks, meta docs (PLAN/CHANGELOG) by docser post-feature. Prevents acceptance criteria deadlock |
| 14 | Max 3 review iterations + escalation | Circuit breaker for infinite fix-loops. Token budget protection |
| 15 | Task complexity classification (trivial/small/standard/large) | Trivial skips reviewers (~34K savings). Small skips quality reviewer. Token optimization without quality loss |
| 16 | Scratchpad resume protocol | Enables workflow recovery after session interruption. Architect-only, updated after every step |
| 17 | Backend workflow explicit (FastAPI + SQLite + uv) | Balanced spec: frontend not dominant. TestClient, fixtures, :memory: DB |
| 18 | Skills fully localized, plugin removed from opencode.jsonc | `.opencode/skills/` — no external plugin needed, no dependency on upstream repo |
| 19 | Controller Never Implements — hard rule in workflow | Prevents architect from editing code, running test fixes, or bypassing review pipeline. Re-dispatch implementer instead |
| 20 | Playwright visual regression testing | Catches UI/layout bugs that functional tests miss. Baseline screenshots in git. Browsers pre-installed in Docker image. No temporary tool installation |
| 21 | @tester reintroduced — narrow scope: env prep + test runs only | Reverses #2 for a DIFFERENT role: test WRITING stays in implementers (TDD), but env forensics (servers, ports, seeds, health, sleeps) and full-suite/e2e runs move to a cheap agent (`deepseek-v4-flash`). Fixes GH #10: env fighting was the #1 token waster in e2e tasks (memo GH #191 T12: 7.04M tokens, 56 bash calls, 34 exploration + ~15 env fighting) |
| 22 | @manager re-introduced as separate agent from @architect | Reverses #1: @manager is the primary entry point (brainstorming, gates, scratchpad, board, phase dispatch), @architect is a phase executor (DESIGN or IMPL, never talks to user). Rationale: the merged controller was doing too many things — conversational UI, gate management, scratchpad ownership, AND phase execution. Splitting gives @manager clean ownership of user interaction and @architect clean ownership of orchestration. The architect dispatch prompt is now a single phase (`## Phase: DESIGN` or `## Phase: IMPL`), not the full workflow. |
