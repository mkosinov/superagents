# Token Economy

> Minimize token usage while preserving quality.
> Cost model for SuperAgents workflow v3.1.

## Per-Subagent Spawn Cost

Each `task()` call creates a **new LLM API request with zero context inheritance**. No shared conversation history between subagent sessions.

**What prompt caching saves:**

| Component | Cached? | Details |
|-----------|---------|---------|
| Implementer `agent.md` (system prompt) | ✅ from 2nd+ spawn | Same agent type, identical system prompt → provider may cache. Saves ~1K tokens on repeated dispatches. |
| Reviewer `agent.md` (system prompt) | ✅ from 2nd+ spawn | Same. Saves ~500 tokens per repeated review. |
| Task `prompt` (user message) | ❌ NEVER | Unique per task: different feature, different context, different diff. |
| Git diff embedded in prompt | ❌ NEVER | Unique per task. |
| Output tokens | ❌ NEVER | Unique response per agent. |

## Duplicate Read Elimination

In v1.0, reviewers used `read` tool to read files independently. This caused **duplicate file reads** (10K tokens × 2 reviewers = 20K waste per task).

**In v3.0:** @architect embeds `git diff` output directly in reviewer prompts. Reviewers analyze embedded diff, NOT `read` tool. **Zero duplicate file reads.**

## Per-Task Cost Model by Tier

Assume average diff: 3 files changed, 200 lines, ~2K tokens of diff text.

| Tier | Pipeline | Cost per task |
|------|----------|---------------|
| **Trivial** | Implementer + architect spot-check | ~4K tokens |
| **Small** | Implementer + spec-reviewer (no fix) | ~12K tokens |
| **Standard** | Implementer + spec-reviewer + quality-reviewer (no fix) | ~20K tokens |
| **Large** | Implementer + spec-reviewer + quality-reviewer + final reviewer | ~30K tokens |

**With 1 fix-loop (typical):**

| Tier | +1 fix-loop | Total |
|------|-------------|-------|
| Small | +8K | ~20K |
| Standard | +16K | ~36K |
| Large | +24K | ~54K |

## Fix-Loop Budget (Circuit Breaker)

- **Max 3 iterations per reviewer.** If 3rd iteration ❌ → STOP, escalate to human.
- **Trivial tasks:** No reviewers, no fix-loops.
- **Per-task max budget:**
  - Trivial: 6K tokens
  - Small: 28K tokens (3 spec loops)
  - Standard: 52K tokens (3 spec + 3 quality loops)
  - Large: 78K tokens + final review
- **If exceeded → human escalation.**

## Feature Cost Projection

A medium feature (5 tasks: 2 trivial, 2 small, 1 standard, 1 fix-loop average):

- **Trivial (2):** 2 × 4K = 8K
- **Small (2):** 2 × 20K = 40K
- **Standard (1):** 1 × 36K = 36K
- **+ docser:** ~5K
- **+ finishing:** ~5K
- **Total feature:** **~94K tokens**

At typical model pricing, a single feature costs **~$0.40–$1.80** for subagents.

## Model Selection Guidance

| Role | Model | Why |
|------|-------|-----|
| @architect | Most capable (kimi-k2.6, etc.) | Planning, delegation, context management |
| @frontend-coder / @backend-coder | Standard (qwen3.6-plus) | Implementation, clear specs |
| @spec-reviewer | Fast, cheap (deepseek-v4-flash) | Read-only, pattern matching |
| @code-quality-reviewer | Fast, cheap (deepseek-v4-flash) | Read-only + test execution |
| @debugger | Standard (qwen3.6-plus) | Reasoning, investigation |
| @docser | Fast, cheap (deepseek-v4-flash) | Structured writing |
| @deployer | Fast, cheap (deepseek-v4-flash) | Command execution |

**Rule:** Use the least powerful model that can handle each role to conserve cost and increase speed.

## Why This Works

- **Architect** loads workflow skills (generic, reusable).
- **Implementer** loads `agent.md` (domain-specific) ONCE per subagent dispatch.
- **Project context** lives in `agent.md`, NOT in task prompts. @architect sends only task-specific text + scene-setting.
- **Reviewers** use cheap models because they only read diffs and report, no generation.
- **No project skill** — avoids loading full project context into @architect session repeatedly.
- **Git diff in reviewer prompts** — eliminates duplicate file reads.
- **Task complexity classification** — trivial tasks skip reviewers entirely (~34K savings).
