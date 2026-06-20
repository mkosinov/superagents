---
name: reflect
description: Analyze opencode session history for workflow compliance violations and propose improvements
when_to_use: When user runs /reflect, or after suspecting workflow issues, or when a bug is found
---

# Reflection Mode

Self-analysis tool for SuperAgents workflow. Reads `opencode.db` (read-only), detects workflow compliance violations, and produces human-approved proposals for improvement.

## When to use

- After a complex feature/wave: `/reflect` to check compliance
- After a bug: `/reflect <notes about what was wrong>` to investigate
- Periodically (nightly cron): automatic summary

## CLI

```bash
reflect.sh post-mortem --target=path/to/file   # file → sessions → post-mortem
reflect.sh wave --name="Wave 4.5"             # sessions in wave → report
reflect.sh nightly [--days=7]                  # last N days → digest (cron-friendly)
reflect.sh in_session --session=ses_xxx        # current session + subagents
reflect.sh status                              # health summary
```

## What it detects

16 workflow compliance checks (5 critical, 8 warning, 3 info), mapped to SuperAgents Key Principles. Examples:
- `controller_never_implements` — architect editing code (Principle 1)
- `mandatory_reviewer_for_code` — skipped reviewers (Principle 2)
- `tdd_red_first` — first tool not a test (Principle 7)
- `stuck_in_retry` — same command 3+ times
- `same_error_repeated` — same error in 3+ sessions

## Output

- `~/.config/opencode/reflection/reports/` — human-readable markdown
- `~/.config/opencode/reflection/proposals/` — pending proposals
- `~/.config/opencode/reflection/decisions/` — applied/rejected history

## Architecture

See `superagents/docs/architecture/reflection-mode.md` for design details.
