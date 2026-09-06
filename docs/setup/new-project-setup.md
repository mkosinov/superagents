# New Project Setup

> How to initialize SuperAgents workflow in a new project.

## Prerequisites

- ZCode on the host (DESIGN phase) and OpenCode in the container (IMPL phase)
- Docker (for isolated worktrees)
- Git repository initialized

## Step 0: Host DESIGN Pipeline (.zcode)

The workflow is split: DESIGN (gates G1a/G1b/G2) runs on the host in ZCode; IMPL runs in the container in OpenCode. The host part deploys from the canon's `.zcode/` (DESIGN executors only):

```bash
cp -R <superagents-checkout>/.zcode/ .zcode/
```

Then adapt for the project:

- `.zcode/scripts/gh_board.py` — create a GitHub Project for the new repo and bake its constants (`PROJECT_ID`, field/option IDs via the graphql query in the script header). Shipped values are the reference project (memo, Project #3) — replace them.
- `.zcode/skills/design-phase/SKILL.md` — repo paths (pre-flight git directory), board statuses if your chain differs.
- Models resolve via the shared omniroute gateway combos (`omniroute/panel-*`, `omniroute/plan-reviewer`) — machine-level user config, nothing per-project.

Restart ZCode after copying: the agent registry seeds at app start.

**Sync discipline:** the canon's `.zcode/` is the seed source for NEW projects. Each project's `.zcode/` is its living copy — per-project adaptations are committed in the project's repo, and cross-project improvements are back-ported into the canon manually.

## Step 1: Container Pipeline (.opencode — the whole pipeline)

The container part deploys wholesale from the canon's `.opencode/` (all agents, skills, scripts — the full workflow lives there):

```bash
cp -R /root/workspace/superagents/.opencode/ .opencode/
```

Adapt per project: agent bodies reference project deltas (models, test commands) — see the Customization section below and manager/architect headers.

## Step 2: Configure opencode.jsonc

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

## Step 3: Configure Spec Review Panel models

The brainstorming skill runs a 5-perspective **Spec Panel Review** before the user approves any spec. Each panelist agent (`spec-panel-*.md`) needs its configured model to be resolvable by the project's providers.

Reference default (memo project): shared omniroute gateway combos:

| Panelist | Model |
|----------|-------|
| spec-panel-completeness | `omniroute/panel-completeness` |
| spec-panel-feasibility | `omniroute/panel-feasibility` |
| spec-panel-consistency | `omniroute/panel-consistency` |
| spec-panel-simplicity | `omniroute/panel-simplicity` |
| spec-panel-best-practices | `omniroute/panel-best-practices` |

(`plan-reviewer` — `omniroute/plan-reviewer`.)

**Model substitution:** to swap a panelist's model, edit the `model:` line in the corresponding agent file — or re-target the combo in the omniroute dashboard without touching files.

If no suitable free models are available in a project, the panel degrades gracefully: the architect retries, skips unavailable perspectives, or skips the panel entirely with an explicit warning (see the availability policy in the brainstorming skill).

## Step 4: Create Project Directories

```bash
mkdir -p docs/specs docs/plans
mkdir -p .worktrees
echo ".worktrees/" >> .gitignore
```

## Step 5: Create Scratchpad

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

## Step 6: Restart OpenCode Container

```bash
cd /root/docker && docker compose down opencode && docker compose up -d opencode
```

**Required:** Container caches agents and skills at startup. Restart after any `.opencode/agents/*.md` or `.opencode/skills/**/SKILL.md` changes.

## Step 7: Start Workflow

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
