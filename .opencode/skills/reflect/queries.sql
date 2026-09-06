-- Reflection Mode SQL queries
-- Schema source: ~/.local/share/opencode/opencode.db
-- All queries use JSON extraction on `data` columns (message.data, part.data)

-- Q1: Sessions for time window
-- Used by: time-driven mode
SELECT id, title, parent_id, agent, model, cost, tokens_input, tokens_output,
       time_created, time_updated, time_archived, path, time_compacting
FROM session
WHERE time_created > ?
ORDER BY time_created DESC;

-- Q2: Tool calls with errors
-- Used by: stuck-in-retry, same-error-repeated, workflow_checks
SELECT session_id,
       json_extract(data, '$.tool') AS tool,
       json_extract(data, '$.state.status') AS status,
       json_extract(data, '$.state.error') AS error,
       json_extract(data, '$.state.metadata.input.command') AS cmd,
       time_created,
       (time_updated - time_created) AS duration_ms
FROM part
WHERE json_extract(data, '$.type') = 'tool'
  AND time_created > ?;

-- Q3: Subagent counts per main session
-- Used by: over-orchestration
SELECT parent_id, COUNT(*) AS subagent_count
FROM session
WHERE parent_id IS NOT NULL
  AND time_created > ?
GROUP BY parent_id;

-- Q4: Cost aggregates
-- Used by: cost trends
SELECT agent,
       COUNT(*) AS sessions,
       SUM(cost) AS total_cost,
       AVG(cost) AS avg_cost
FROM session
WHERE time_created > ?
GROUP BY agent;

-- Q5: Compaction events
-- Used by: context-overflow
SELECT id, title, agent, time_compacting
FROM session
WHERE time_compacting IS NOT NULL
  AND time_created > ?;

-- Q6: Wave identification by title pattern
-- Used by: wave-driven mode
SELECT id, title, parent_id, agent, time_created
FROM session
WHERE title LIKE '%Wave%'
  AND time_created > ?
ORDER BY time_created DESC;

-- Q7: Distinct tool usage stats
-- Used by: duration trends, regression detection
SELECT json_extract(data, '$.tool') AS tool,
       COUNT(*) AS uses,
       AVG(time_updated - time_created) AS avg_duration_ms,
       MIN(time_created) AS first_used,
       MAX(time_created) AS last_used
FROM part
WHERE json_extract(data, '$.type') = 'tool'
  AND time_created > ?
GROUP BY tool
ORDER BY uses DESC;
