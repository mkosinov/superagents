#!/usr/bin/env bash
# panel_review.sh — D-flow review runner for superagents (2026-10-10).
# Ported from the memo project's runner (2026-09-26) — behavior identical;
# this repo owns its copy (user decision 2026-10-10: no cross-repo dependency).
#
# Runs review agents (zen free models via `opencode run`) against a dedicated
# clean clone, in parallel. The IMPL clone (/root/workspace/superagents) is never
# touched beyond `git fetch` (reads .git only, never the worktree).
#
# Usage:
#   panel_review.sh <run-id> <input-dir> <agent> [<agent>...]
#
#   <run-id>     unique id; reports land in /root/workspace/panel-out/<run-id>/
#   <input-dir>  directory with review inputs (spec.md, prev-spec.md, plan.md)
#   <agent>      agent names from the repo's .opencode/agents/
#                (spec-panel-* / plan-reviewer; models are baked in the files)
#
# Per-agent hard timeout: PANEL_TIMEOUT seconds (default 1500 = 25 min).
# Inputs are copied into <clone>/.panel-review/ (untracked, wiped by sync).
# stdout: one summary line per agent. Reports: <agent>.md (+ <agent>.err).

set -u

RUN_ID="${1:?run-id required}"
INPUT_DIR="${2:?input dir required}"
shift 2
AGENTS=("$@")
[ ${#AGENTS[@]} -gt 0 ] || { echo "ERROR: no agents given"; exit 2; }
[ -d "$INPUT_DIR" ] || { echo "ERROR: input dir not found: $INPUT_DIR"; exit 2; }

MAIN_CLONE="/root/workspace/superagents"
CLONE="/root/workspace/panel-superagents"
OUT="/root/workspace/panel-out/$RUN_ID"
IN_TARGET="$CLONE/.panel-review"
TIMEOUT="${PANEL_TIMEOUT:-1500}"

mkdir -p "$OUT"

# 1. Sync the clean clone. It fetches from the main clone (which tracks
#    origin), so network credentials stay the main clone's concern.
#    Superagents port: the main clone may hold unpublished local commits
#    (mirror ports ahead of origin) — the review clone resets to the main
#    clone's refs/remotes/origin/main (PUBLISHED main), never its local branch.
if [ ! -d "$CLONE/.git" ]; then
  echo "clone: creating $CLONE from $MAIN_CLONE"
  git clone --no-hardlinks -q "$MAIN_CLONE" "$CLONE"
fi
git -C "$MAIN_CLONE" fetch origin --prune -q || echo "WARN: main-clone fetch failed; using last fetched origin state"
git -C "$CLONE" fetch origin -q "+refs/remotes/origin/main:refs/remotes/origin/main"
git -C "$CLONE" reset --hard -q origin/main
git -C "$CLONE" clean -fdq
# 1b. Strip sibling specs/plans from the review clone — the submitted inputs
#     are the ONLY documents under review. Tracked docs/specs + docs/plans in
#     the clone act as decoys: 2026-10-10 (#359 run), a consistency reviewer
#     left the submitted spec and reviewed the freshly-pushed #357 spec from
#     docs/ instead. Code and docs/domain-rules stay — reviewers verify
#     against them.
rm -rf "$CLONE/docs/specs" "$CLONE/docs/plans"
echo "sync: $CLONE at $(git -C "$CLONE" rev-parse --short origin/main)"

# 2. Copy review inputs into the clone.
mkdir -p "$IN_TARGET"
cp -R "$INPUT_DIR"/. "$IN_TARGET"/
echo "inputs: $(ls "$IN_TARGET" | tr '\n' ' ')"

# 3. Launch agents in parallel — each spawns its own ephemeral opencode server
#    with fresh agent definitions; the long-running :4096 server is not involved.
for A in "${AGENTS[@]}"; do
  S=$(date +%s)
  (
    timeout "$TIMEOUT" opencode run \
      --agent "$A" \
      --dir "$CLONE" \
      --title "panel-$RUN_ID-$A" \
      "The files in $IN_TARGET are the ONLY documents under review — read every file there first; everything else in the repo is reference material, never the review subject. Hard limit: 15 tool calls. Produce your findings report as the final message." \
      > "$OUT/$A.md" 2> "$OUT/$A.err"
    echo "$A rc=$? seconds=$(( $(date +%s) - S ))" >> "$OUT/_summary.txt"
  ) &
done
wait

# 4. Summary (one line per agent; rc=0 + report >= 300 bytes = ok,
#    124 = timeout; a tiny report = the model collapsed — treat as failure).
FAIL=0
while IFS= read -r line; do
  R="${line%% *}"
  SZ=$(wc -c < "$OUT/$R.md" 2>/dev/null || echo 0)
  [ "$SZ" -ge 300 ] && OK=ok || OK=EMPTY
  echo "$line report=$OK file=$OUT/$R.md"
  { echo "$line" | grep -q "rc=0"; } && [ "$OK" = ok ] || FAIL=1
done < "$OUT/_summary.txt"
rm -f "$OUT/_summary.txt"
exit $FAIL
