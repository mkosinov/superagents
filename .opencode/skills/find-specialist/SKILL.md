---
name: find-specialist
description: Return which agent best covers a given topic. Use before delegating when you don't know which specialist to dispatch.
---

To find the right specialist for topic X:

1. Check agent files in priority order:
   - **Project copies** (live, may have project-specific overrides): `<project>/.opencode/agents/*.md`
   - **User-level**: `~/.config/opencode/agents/*.md`
   - **Golden source**: `<superagents>/agents/*.md`

2. For each file, read `description` from YAML frontmatter. If `covers:` or `specialization:` field exists, include it.

3. Match topic → agent. Return:
   - **1 agent** (clear match): `@name — short reason`
   - **2-3 agents** (ambiguous): ranked list, best first
   - **0 agents**: "no specialist found, handle yourself or escalate to user"

Keep response short. The goal is "who do I dispatch to?", not full agent descriptions.
