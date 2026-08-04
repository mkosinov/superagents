# New Project Setup

> How to initialize SuperAgents workflow in a new project.

## Prerequisites

- OpenCode installed
- Docker (for isolated worktrees)
- Git repository initialized

## Step 1: Copy Agent Definitions

```bash
mkdir -p .opencode/agents
cp /root/workspace/superagents/agents/*.md .opencode/agents/
```

This includes the 5 spec review panel agents (`spec-review-*.md`) used by the brainstorming skill's Spec Panel Review step.

## Step 2: Copy Skills

```bash
mkdir -p .opencode/skills
for skill in brainstorming writing-plans using-git-worktrees \
             test-driven-development subagent-driven-development \
             finishing-a-development-branch systematic-debugging; do
  mkdir -p ".opencode/skills/$skill"
  cp "/root/workspace/superagents/skills/$skill/SKILL.md" ".opencode/skills/$skill/"
done
```

## Step 3: Copy Reviewer Templates

```bash
mkdir -p .opencode/skills/reviewers
cp /root/workspace/superagents/templates/reviewers/*.md .opencode/skills/reviewers/
```

## Step 4: Configure opencode.jsonc

```jsonc
{
  "default_agent": "plan",
  "permission": {
    "skill": {
      "*": "deny",
      "brainstorming": "allow",
      "writing-plans": "allow",
      "using-git-worktrees": "allow",
      "test-driven-development": "allow",
      "subagent-driven-development": "allow",
       "finishing-a-development-branch": "allow",
       "systematic-debugging": "allow"
    }
  }
}
```

## Step 5: Configure Spec Review Panel models

The brainstorming skill runs a 5-perspective **Spec Panel Review** before the user approves any spec. Each panelist agent (`spec-review-*.md`) needs its configured model to be resolvable by the project's providers.

Reference default (memo project): free OpenCode Zen models via the `omniroute` provider:

| Panelist | Model |
|----------|-------|
| spec-review-completeness | `omniroute/opencode-zen/big-pickle` |
| spec-review-feasibility | `omniroute/opencode-zen/mimo-v2.5-free` |
| spec-review-consistency | `omniroute/opencode-zen/nemotron-3-ultra-free` |
| spec-review-simplicity | `omniroute/opencode-zen/deepseek-v4-flash-free` |
| spec-review-best-practices | `omniroute/opencode-zen/ling-3.0-flash-free` |

**Model substitution:** to swap a panelist's model, edit the `model:` line in the corresponding `.opencode/agents/spec-review-*.md`. Reserve pool in the zen tier: `opencode-zen/north-mini-code-free`, `opencode-zen/laguna-s-2.1-free` — or use any capable model available to the project.

If no suitable free models are available in a project, the panel degrades gracefully: the architect retries, skips unavailable perspectives, or skips the panel entirely with an explicit warning (see the availability policy in the brainstorming skill).

## Step 6: Create Project Directories

```bash
mkdir -p docs/specs docs/plans
mkdir -p .worktrees
echo ".worktrees/" >> .gitignore
```

## Step 7: Create Scratchpad

```bash
cat > .opencode/scratchpad.md << 'EOF'
# Current Mission

## Feature: [name]
## Branch: [branch name]
## Worktree: [path]

## Workflow Status
- [ ] Step 0: Project Reconnaissance
- [ ] Step 1: Brainstorming (design approved)
- [ ] Step 2: Writing Plans (plan approved)
- [ ] Step 3: Git Worktree (created, baseline clean)
- [ ] Step 4: Subagent-Driven Development
- [ ] Step 5: Documentation Commit
- [ ] Step 6: Finishing
EOF
```

## Step 8: Restart OpenCode Container

```bash
cd /root/docker && docker compose down opencode && docker compose up -d opencode
```

**Required:** Container caches agents and skills at startup. Restart after any `.opencode/agents/*.md` or `.opencode/skills/**/SKILL.md` changes.

## Step 9: Start Workflow

Invoke `@architect` agent and request a new feature. The workflow begins at **G1 (Brainstorming)**.

## Customization

### Project-Specific Agents

Modify agent files for your tech stack:

- `frontend-coder.md` — change framework references (Next.js → Vue, etc.)
- `backend-coder.md` — change backend stack (FastAPI → Django, etc.)
- `architect.md` — update project context, design system paths

### Adding New Skills

1. Create `.opencode/skills/<skill-name>/SKILL.md`
2. Add to `opencode.jsonc` permissions
3. Restart container

### Visual Regression Testing

For Playwright visual testing:

1. Install `@playwright/test` in `package.json`
2. Add to `Dockerfile`:
   ```dockerfile
   RUN npm install -g @playwright/test \
       && npx playwright install chromium \
       && npx playwright install-deps chromium
   ```
3. Add `test:all` script: `vitest run && playwright test`
4. Add rule to `architect.md`: "UI changes → `test:all`, else → `test`"
