# Plan: Host/Container Phase Split — DESIGN on host (zcode), IMPL in container (opencode)

Date: 2026-09-05
Status: DRAFT r2 — review round 1 applied (verdict APPROVE_WITH_AMENDMENTS: opencode review ses_f8d1344c1ffeFWb6k2x9kFZG3h, qwen3.8-max read-only, 2026-09-05; 2 blockers + 9 amendments folded in; reviewer's card-state claim corrected — see §8.1)
Related: decision recorded in memory `host-container-phase-split`; depth-limit=2 finding (spikes 2026-09-03/04, sessions sess_0af312ae, sess_e371ca29)

## 1. Goal

Move the DESIGN phase (brainstorm, spec, panel review, plan, plan review — gates G1a/G1b/G2) to host zcode sessions. Keep the IMPL phase (worktree, dev loop, tester, visual gate, finishing, PR — gates G3–G7) in the opencode container. Zero harness migration: each tool stays where it already lives. The split is the only topology compatible with the zcode depth limit (main session → subagents, no deeper nesting), because DESIGN needs only 1-level parallel dispatch, while IMPL needs the full nested pipeline that only opencode can run.

## 2. Verified current state (facts, 2026-09-05)

Pipeline (superagents v3.2, `agents/manager.md`, `agents/architect.md`, `docs/workflow/README.md`):

```
Phase 0 BRAINSTORM (manager + user, interactive)            → G1a human
DESIGN (architect, dispatched by manager):
  Step 1  spec  → docs/specs/YYYY-MM-DD-<feature>-design.md → G1b panel + human (HARD)
  Step 2  plan  → docs/plans/YYYY-MM-DD-<feature>-plan.md   → G2 plan review + human
  Step 3  worktree (create-worktree.sh) + baseline tests    → G3 auto
IMPL (architect, second dispatch, prompt = plan path + worktree path):
  Step 4  dev loop per plan task (TDD, two-stage review)    → G4–G6 auto
  Step 4.5 visual compliance check                          → G4.5 auto
  Step 5  docs (docser) into feature branch
  Step 6  finishing: push, gh pr create, auto-merge on CI   → G7 human (errors only)
```

The DESIGN→IMPL boundary is already a serialized contract: **plan file path + worktree path + spec/plan commits pushed to main**. Doc commits are pushed to main immediately after gate approval. Confirmed by live practice (#214, #142): every DESIGN ends with spec+plan pushed, IMPL starts in a fresh session.

State stores and their reachability across the seam:

| Store | Location | Crosses git? | Reachable from host? |
|---|---|---|---|
| Specs, plans, domain-rules | `docs/` in repo | yes | yes (clone) |
| GH Project board | GitHub (projectsV2) | n/a | yes — `gh` authed, `project` scope present |
| `.opencode/` (scratchpad, skills incl. `gh_board.py`, agents, scripts) | repo dir, **gitignored** (`.gitignore:66`) | no | only via `docker exec opencode …` |
| `.worktrees/` | repo dir, gitignored | no | only via `docker exec` |

Clone topology (verified today):

- `~/dev/memo` (host) and `/root/workspace/memo` (container) — same GitHub origin.
- **Host was 21 commits behind origin/main** (container is the active pusher). The two clones drift silently; nothing warns either side.
- Divergence is the worse failure mode and has a live precedent: container-local WIP commit cc8bc52 (#218 FasTP) rode to origin as a passenger of #142's spec push — container main was diverged (ahead+behind), not just behind.
- `~/dev/superagents` (host) and `/root/workspace/superagents` (container) — same pattern (host has unpushed `d9d5585`; container at `bfde996`; container clone also carries pre-existing local dirt: `M .gitignore`, `?? tools/` — not ours, commit separately or clean before any sync).
- Both memo clones embed a GitHub PAT in the remote URL (hygiene note, §7).

Live container state (scratchpad, 2026-09-05): #140 plan approved (G2 passed, awaiting IMPL), #142 at G1b stage, #218 FasTP Phase 2 in flight. Next Up: 1) #140 2) #142 3) #141.

## 3. Target topology — what runs where

| Pipeline step | Today | Target | Executor on host |
|---|---|---|---|
| Phase 0 brainstorm, G1a | container (manager + user) | **host** | zcode main session (interactive) |
| Spec writing + self-review | container (architect) | **host** | zcode main session |
| Spec panel (5 panelists, parallel) | container | **host** | zcode parallel subagents (1 level — enough), models `omniroute/panel-*` |
| G1b consolidation + spec fixes | container | **host** | zcode main session |
| Plan writing (`writing-plans`) | container | **host** | zcode main session |
| Plan review (spec-reviewer, Plan Review Mode) | container | **host** | zcode subagent |
| G2 | container | **host** | user, in host session |
| Step 3 worktree + baseline (G3) | container (architect, DESIGN) | **container — architect's FIRST action of IMPL (plan-only start)** | — |
| IMPL dev loop G4–G6, visual gate | container | container (unchanged) | — |
| Docs, finishing, PR (G7) | container | container (unchanged) | — |
| Board ops (status, next-up) | container (manager-only) | **both sides, per phase ownership** | DESIGN-stage flips from host; IMPL-stage flips from container manager |
| FasTP (quick-fix track) | container | container (unchanged, out of scope) | — |

On the host, the zcode main session merges the manager and architect DESIGN roles: it talks to the user directly (gates) and dispatches 1-level subagents (panel, plan reviewer, explore). It never needs nested dispatch, so the depth limit is not hit.

## 4. Seam contract (what crosses the boundary — nothing else does)

1. **Git**: DESIGN DoD = spec commit + plan commit (+ domain-rules if any) **pushed to origin/main**, AND **all design decisions folded into those pushed artifacts** — G2 amendments ("contract addendum: …") and cross-trajectory ordering constraints ("#142 strictly after #140 merge — shared file") must live in the spec/plan text, not in the DESIGN session's scratchpad: git+board do not carry scratchpad context across the seam.
2. **Board**: the issue moves `In Design (G1a) → Spec OK (G1b) → Ready to IMPL (G2)` during host DESIGN. The GH Project board stays the single cross-session trajectory source (already its design role); statuses are gate-anchored (see github-board skill).
3. **IMPL entry**: user tells the container manager «продолжаем траекторию #NNN». The manager finds the issue `Ready to IMPL (G2)`, fetches main, verifies the plan file exists, dispatches architect IMPL with the plan path (**plan-only start**: no worktree path in the dispatch — the architect creates the worktree and runs the baseline as its FIRST action, today's DESIGN Step 3 mechanics), and sets `In IMPL`.
4. **Return path (exception — one-time bounce-back, not a live channel)**: if IMPL hits a problem that invalidates the spec or the plan, the **architect reports BLOCKED** (per architect.md: "plan wrong → report BLOCKED") → the **manager presents it to the user** → the **user decides** → the **manager** (board is the manager's zone; the architect is forbidden to touch it) posts a comment on the GH issue describing the problem and moves the card back: spec invalid → `In Design (G1a)`; spec intact, plan broken → `Spec OK (G1b)`. The trajectory's scratchpad section closes with an Idle line carrying the return reason, the new status, and the comment URL. **Worktree/branch on return is a real gap** — finishing-cleanup covers only merged/discard paths, an abandoned "task 3 of 11" worktree is covered by no one: the manager asks the user keep-vs-discard; discard → `remove-worktree.sh`; the outcome goes into the Idle line. The next host DESIGN session picks the issue up from the board with the issue comment as input and re-runs the affected gates. Threshold: "cannot proceed / the plan is wrong" — an architect-level decision, not a coder's alternative idea; otherwise this degrades into the ping-pong the design rejected. Live questions during IMPL still stay inside the container (opencode interface).

Explicitly NOT crossing the seam: `.opencode/scratchpad.md` (container-internal; the container manager creates its own section at IMPL start, seeded from board + plan), `.opencode/*` skills/agents, worktrees, env state.

## 5. Bridges to build

### B1. Git sync discipline (no code, rules only)
- DESIGN DoD (host): push to origin. A DESIGN session never ends with local-only doc commits.
- IMPL pre-flight (container): `git fetch origin && git status -sb` — **behind** → fast-forward then proceed; **diverged** (ahead+behind) → **STOP and ask the user** (the only existing policy for this state is finishing's "STOP, contact user, no reset --hard"); verify plan file present at expected path.
- Host session start (DESIGN): same fetch check. Today's 21-commit lag is the proof this must be mechanical, not habitual.
- **While a host DESIGN session is in flight, no local-only commits on the container's main** (FasTP WIP goes to a branch). Precedent: cc8bc52 rode to origin as a passenger of #142's spec push.
- Immediate action: `git -C ~/dev/memo pull` (host is behind right now).

### B2. GH board from host — via docker exec, single source of truth
```
docker exec opencode python3 /root/workspace/memo/.opencode/skills/github-board/scripts/gh_board.py next-up
docker exec opencode python3 /root/workspace/memo/.opencode/skills/github-board/scripts/gh_board.py status <N> "Spec OK (G1b)"
```
Do NOT copy `gh_board.py` to the host (drift). Fallback: host `gh` CLI directly. Verified live 2026-09-05 (read path + `next-up` smoke test). Board writes: one writer per issue — DESIGN-stage flips come from the host DESIGN session, IMPL-stage flips from the container manager.

### B3. Host agent set for panel + plan review
Port from `~/dev/superagents/agents/` to `~/.zcode/agents/` (user-scope custom agents; mechanism proven by the 2026-09-04 spike):
- `spec-review-completeness.md`, `spec-review-consistency.md`, `spec-review-feasibility.md`, `spec-review-simplicity.md`, `spec-review-best-practices.md` — models `omniroute/panel-*`;
- `spec-reviewer.md` (Plan Review Mode only on host) — appropriate omniroute model.

Porting notes (review round 1):
- 5 of 6 files port clean. Strip frontmatter `mode: subagent`; **permission blocks must be RE-EXPRESSED in the zcode mechanism (tools allowlist in frontmatter), not just dropped** — they are the read-only-leaf guarantee.
- `task_id` printing is NOT in the agent files (it comes from the project AGENTS.md) — nothing to strip there.
- **best-practices is the exception**: its research step is mandatory ("MUST dispatch researcher-agent ≥1; without research → Verdict: FAILED"). Decision: **rewrite the Research Flow to the host's web tools (WebSearch/WebFetch), preserving the `[VERIFIED via research]` semantics** — not "researches itself or skips". Fallback only if the pilot shows weak research: accept a permanent skip of the perspective, recorded as a decision.
- The panel **dispatch protocol** lives in `skills/panel-spec-review/SKILL.md`, not in agent files → covered by B5, not B3. Same for the availability policy (retry→skip + `subagent-audit.py` salvage): container-only tooling → B5 needs a host adaptation (zcode has no subagent-audit; host fallback: one rerun, then mark the panelist skipped in the consolidation report).

### B4. Pipeline edits in superagents (the only prompt changes)
1. `agents/manager.md`:
   - **Plan-only IMPL entry**: new branch in the Session Start Ritual and the routing table — card at `Ready to IMPL (G2)` + plan file on fetched main + no worktree → IMPL-entry, **no brainstorm** (by current rules the manager would re-brainstorm an already-approved feature).
   - **IMPL dispatch template**: new variant `## Phase: IMPL (plan-only start)` carrying ONLY `## Plan: <path>` — no `## Worktree:` line (today's template requires it; "architect gets the path later" needs this variant, not a resume-twist).
   - **The manager does NOT create worktrees or run baselines** — that violates its own bash allowlist (git/gh/ls/cat) and "You NEVER run tests". Step 3 stays with the architect (see below).
   - Scratchpad seeding for split trajectories: the section is created at IMPL start with the **architect's IMPL task_id** (there is no DESIGN task_id from a host session) + "gates G1a/G1b/G2 passed per board" + plan path.
   - Explicitly void the dead clauses for split trajectories: "verify push" and "architect DONE → immediately dispatch IMPL" (they assume DESIGN ran in-container).
   - Root README is in the change checklist (workflow README's rollout list) — update it too, not only docs/workflow/.
2. `agents/architect.md`: the IMPL precondition gains the plan-only variant — dispatch without `## Worktree:` → create worktree + run baseline as the FIRST action of IMPL (today's Step 3 mechanics, relocated), then the dev loop.
3. Workflow README: document the split mode, the seam contract (§4), and the return path (§4.4) — including the manager's RETURNED handling (issue comment + board move back + Idle line; worktree keep-vs-discard is the user's call).
4. Per house rule: commit to superagents (host) → resolve the unpushed `d9d5585` first → push → container pulls → **atomic sync into `memo/.opencode/` (SKILL.md + gh_board.py together — it is half-synced right now: chain line new, touchpoints old)** → **container restart** (workflow README requires it after `.opencode` sync).

### B5. Host DESIGN kit (checklist as a host skill)
Create `~/.zcode/skills/design-phase/SKILL.md` (or a section in `~/.zcode/AGENTS.md`): the DESIGN role on host — artifact paths and naming, gates G1a/G1b/G2 semantics, **panel dispatch protocol (ported from `skills/panel-spec-review/SKILL.md`) + host availability policy**, plan review dispatch, **DoD = push + fold amendments/ordering constraints into the artifacts (§4.1)**, board calls (B2), pre-flight fetch (B1). This is what makes any fresh host session able to run DESIGN without re-explaining.

### B6. Read-only peeks (optional, convenience)
The host session MAY read container state for context: `docker exec opencode tail -40 /root/workspace/memo/.opencode/scratchpad.md`. Read-only; never write scratchpad from host.

## 6. Pilot — simulation on a real task

Candidate: a small feature from the queue after the current wave (#221 / #220 / #133 / #223), or #141 once #140/#142 IMPL waves finish. NOT #140/#142 — they are already in flight in the container.

**Step 0 (user decision, before anything)**: the user places the pilot issue in Next Up (or sanctions an off-queue run — precedent #218). Next Up changes only by the manager on the user's word; "queue after the current wave" has no operator by itself. Pre-check shared files against in-flight #140/#142 (the "#142 strictly after #140 — shared file" constraint is exactly this failure mode, and per §4.1 it must survive the seam in the plan text).

Expected run with checkpoints (each validates one bridge):

1. Host: `git pull` (in sync with origin/main) → `gh_board.py next-up` (B2) → pick issue, board `In Design (G1a)`.
2. Host: brainstorm G1a → spec draft → panel dispatch, 5 parallel (B3 + models) → consolidation → G1b user approval → spec commit + **push** (B1) → board `Spec OK (G1b)`.
3. Checkpoint: `docker exec` container `git fetch && git log origin/main -1` shows the spec commit.
4. Host: plan (writing-plans conventions) → spec-reviewer Plan Review Mode (B3) → G2 approval → fold amendments + ordering constraints into the plan (§4.1) → plan commit + push → board `Ready to IMPL (G2)`.
5. Container: manager «продолжаем траекторию #NNN» → plan-only start (B4): fetch/ff check, architect IMPL dispatch (plan path only), architect creates worktree + baseline, board `In IMPL`.
6. Container: IMPL → finishing → PR merged → board `In-main` → host pulls.

Success criteria: the container needed only the plan path + board status (no verbal context from the host session); zero manual re-explanations at the seam; no host writes to scratchpad; friction log kept during pilot, folded back into B5 kit.

## 7. Risks and open questions

- **Silent clone drift** (proven today, 21 commits): mitigated only mechanically — fetch checks in B1 at every session start and pre-flight; **diverged main = STOP + user** (B1), not just "behind".
- **Escalation coder→architect→manager in opencode doesn't reach** (pre-existing, user-known): out of scope here, but with DESIGN on host this becomes the top risk for autonomous IMPL — landscape-changing findings stay inside IMPL and are invisible to the host until the trajectory ends. Track as a separate container-side task. Note: the §4.4 return path is the bounded escape valve for exactly these findings, but until the escalation chain is fixed, the return can realistically be triggered only by the user or a manager-visible session — the return decision rides on the same broken chain.
- **Unverified assumptions gating the pilot** (must be smoke-tested in §8.2 before the pilot): live dispatch of `omniroute/panel-*` from host zcode (registered in config, never smoke-tested end-to-end); host `gh` project-scope **writes** (reads verified); host-side panel availability policy (B5).
- **Concurrent board writers**: host DESIGN session and container manager can both write statuses — rule: one writer per issue, phase ownership decides (§4.2/B2).
- **PAT embedded in remote URLs** on both clones — violates the infra secrets rule; replace with gh credential helper. Small hygiene task, independent.
- **Container main hygiene**: untracked `.zcode/`, `kimi_quota_correlation.*` in the container memo clone (the token-optimization plan file stays per user request); container superagents clone carries its own pre-existing dirt (`M .gitignore`, `?? tools/`) — clean or commit separately, never mixed with board-skill changes.
- **`pre-commit-g1b-gate.sh`** (exists in repo, not installed) is incompatible with the split — caution line in the file when B4 lands.
- **Panel prompt drift**: host copies (B3) can rot while superagents evolves; keep superagents canonical, re-port on change.
- **Parallelism rule**: host DESIGN on issue X + container IMPL on issue Y is fine (separate worktrees); the same issue must never run both phases at once — board status is the guard.

## 8. Rollout checklist (ordered)

1. **Board migration — DONE 2026-09-05** (verify, don't redo): 8 gate-anchored options live and matching `STATUSES`; cards carried through the rename (2× In IMPL, 1× In Design (G1a) — the reviewer's "cards stuck on In Progress" was based on pre-captured data and is outdated). Remaining in step 4: the memo `.opencode` skill copies must be re-synced atomically (currently half-synced: chain new, touchpoints old) and the container restarted.
2. B3: port 6 agent files to `~/.zcode/agents/` (best-practices research rewritten to host web tools; permission blocks re-expressed as zcode tool allowlists) + **smoke-test one panelist dispatch and one `gh` project write from host** (gates the pilot, §7 assumptions).
3. B2: verified live 2026-09-05 (`next-up` via docker exec).
4. B4: edit superagents (manager.md / architect.md / workflow README / root README) → commit (host) → **resolve unpushed `d9d5585`** → push → container pull → **atomic sync** of `memo/.opencode` github-board SKILL.md + gh_board.py → **container restart**.
5. B5: write the host DESIGN kit (skill/AGENTS section; includes panel dispatch protocol + host availability policy).
6. Run the pilot (§6, starting at step 0); keep a friction log; adjust B4/B5 from findings.
7. Hygiene (optional, any time): PAT out of remote URLs; container clones' untracked files.
