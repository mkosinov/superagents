# SuperAgents — Shared Agent Rules

This file is auto-loaded by all agents in the superagents framework.
It defines cross-cutting rules that apply regardless of the specific agent role.

---

## User input types

A message ending with `?` is a question. The agent answers with text and **takes no actions** (no tools, commits, file edits).

**Exception:** if the answer needs info not in context — read-only gathering (read a file, `git log`). After gathering — text answer immediately.
