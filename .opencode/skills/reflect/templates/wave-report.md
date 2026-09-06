# Wave Report: {wave_name}

> Generated: {timestamp}
> Mode: wave-driven
> Sessions analyzed: {session_count}

## Summary
- **Compliance score:** {compliance_score}%
- **Total cost:** ${total_cost}
- **Total tokens:** {total_tokens}
- **First-time-right rate:** {first_time_right}%

## Subagent results

| Agent | Sessions | Completion | Avg cost | Notes |
|-------|----------|-----------|----------|-------|
{subagent_table}

## Workflow violations

| Severity | Check | Session | Message |
|----------|-------|---------|---------|
{violations_table}

## Proposals
{proposals_section}
