# Token Economy

> Minimize token usage while preserving quality.
> Cost model for the SuperAgents workflow. Role names are theory roles (controller, implementer, reviewers); concrete dispatch tools and model assignments live in each harness adapter.

## Per-Subagent Spawn Cost

Each subagent dispatch creates a **new LLM API request with zero context inheritance** — true for every harness's dispatch tool. No shared conversation history between subagent sessions.

**What prompt caching saves:**

| Component | Cached? | Details |
|-----------|---------|---------|
| Implementer agent definition (system prompt) | ✅ from 2nd+ spawn | Same agent type, identical system prompt → provider may cache. Saves ~1K tokens on repeated dispatches. |
| Reviewer agent definition (system prompt) | ✅ from 2nd+ spawn | Same. Saves ~500 tokens per repeated review. |
| Task `prompt` (user message) | ❌ NEVER | Unique per task: different feature, different context, different diff. |
| Git diff embedded in prompt | ❌ NEVER | Unique per task. |
| Output tokens | ❌ NEVER | Unique response per agent. |

## Duplicate Read Elimination

In v1.0, reviewers used the file-read tool to read files independently. This caused **duplicate file reads** (10K tokens × 2 reviewers = 20K waste per task).

**Current:** the controller saves `git diff` to a file and passes the file PATH to reviewers — diff contents are never pasted into chat prompts. Reviewers analyze the diff file. **Zero duplicate file reads.**

## Per-Task Cost Model by Tier

Assume average diff: 3 files changed, 200 lines, ~2K tokens of diff text.

| Tier | Pipeline | Cost per task |
|------|----------|---------------|
| **Trivial** | Implementer + architect spot-check | ~4K tokens |
| **Small** | Implementer + code-compliance-reviewer (no fix) | ~12K tokens |
| **Standard** | Implementer + code-compliance-reviewer + quality-reviewer (no fix) | ~20K tokens |
| **Large** | Implementer + code-compliance-reviewer + quality-reviewer + final reviewer | ~30K tokens |

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
- **+ scribe:** ~5K
- **+ finishing:** ~5K
- **Total feature:** **~94K tokens**

At typical model pricing, a single feature costs **~$0.40–$1.80** for subagents.

## Model Selection Guidance

| Role | Model tier | Why |
|------|-------|-----|
| Controller | Most capable | Planning, delegation, context management |
| Implementers | Standard | Implementation, clear specs |
| Compliance reviewer | Fast, cheap | Read-only, pattern matching |
| Quality reviewer | Fast, cheap | Read-only + test execution |
| Investigator | Standard | Reasoning, investigation |
| Scribe | Fast, cheap | Structured writing |
| Deployer | Fast, cheap | Command execution |

**Rule:** Use the least powerful model that can handle each role to conserve cost and increase speed. Which concrete model id fills each tier is adapter config, not theory.

## Why This Works

- **Controller** loads workflow skills (generic, reusable).
- **Implementer** loads its agent definition (domain-specific) ONCE per subagent dispatch.
- **Project context** lives in the implementer's agent definition, NOT in task prompts. The controller sends only task-specific text + scene-setting.
- **Reviewers** use cheap models because they only read diffs and report, no generation.
- **No project skill** — avoids loading full project context into the controller session repeatedly.
- **Diff file for reviewers** — the controller passes paths, not contents; eliminates duplicate file reads.
- **Task complexity classification** — trivial tasks skip reviewers entirely (~34K savings).
