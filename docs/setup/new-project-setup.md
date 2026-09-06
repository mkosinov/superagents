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

## Step 2: Shared Agent Rules (AGENTS.md) + container board script

Both tools read `AGENTS.md` at the project root natively (zcode workspace instructions, opencode project instructions). Seed it from the canon:

```bash
cp /root/workspace/superagents/.opencode/agents/AGENTS.md AGENTS.md
```

Sections are universal except "Subagents: report your session ID first" — that one is opencode-only and marked as such inline. (A no-session-id variant ships as `.zcode/AGENTS.seed.md` for zcode-only setups.)

The container manager runs the board script from the project's `.opencode/scripts/` — seed it from the copy you adapted in Step 0:

```bash
cp .zcode/scripts/gh_board.py .opencode/scripts/gh_board.py
```

## Step 3: Configure opencode.jsonc

```jsonc
{
  "default_agent": "manager",
  "permission": {
    "skill": {
      "*": "deny",
      "brainstorming": "allow",
      "writing-plans": "allow",
      "using-git-worktrees": "allow",
      "test-driven-development": "allow",
      "subagent-driven-development": "allow",
      "finishing-a-development-branch": "allow",
      "systematic-debugging": "allow",
      "fast-track-protocol": "allow",
      "github-board": "allow",
      "find-specialist": "allow"
    }
  }
}
```

## Step 4: Configure Spec Review Panel models

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

## Step 5: Create Project Directories

```bash
mkdir -p docs/specs docs/plans
mkdir -p .worktrees
echo ".worktrees/" >> .gitignore
```

## Step 6: Create Scratchpad

```bash
touch .opencode/scratchpad.md
```

Leave it empty. The container manager seeds its own section per trajectory at IMPL start (plan-only entry: architect's IMPL task_id + "gates G1a/G1b/G2 passed per board" + plan path). Do NOT pre-fill a legacy workflow template.

## Step 7: Restart OpenCode Container

```bash
cd /root/docker && docker compose down opencode && docker compose up -d opencode
```

**Required:** Container caches agents and skills at startup. Restart after any `.opencode/agents/*.md` or `.opencode/skills/**/SKILL.md` changes.

## Step 8: Start Workflow

- **DESIGN phase** — on the host: open the project in ZCode and say `design` / `design #NNN` (the `design-phase` skill runs gates G1a–G2; see docs/workflow/design-phase.md).
- **IMPL phase** — in the container: when the card is at `Ready to IMPL (G2)`, tell @manager «продолжаем траекторию #NNN» (plan-only entry; see docs/workflow/impl-phase.md).

The in-container DESIGN flow (brainstorming via @manager → @architect) remains available as a fallback for non-split deployments.

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
