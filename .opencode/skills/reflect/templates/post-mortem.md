# Post-mortem: {bug_title}

> Generated: {timestamp}
> Mode: bug-driven
> Target: `{target_file}`

## Bug summary
{bug_description}

## Originating workflow
**Wave:** {wave_name}
**Main session:** {main_session_id}
**Subagent sessions:**
{subagent_tree}

## Workflow gaps found

| Gap | Severity | Check |
|-----|----------|-------|
{gaps_table}

## Detailed analysis
{detailed_analysis}

## Proposed workflow changes
{proposals_section}

## Action required
- [ ] Review proposals
- [ ] Approve selected
- [ ] Apply diff
- [ ] Re-run bug fix
