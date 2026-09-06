---
name: vitest-playwright-patterns
description: >-
  Writing tests for the Memo frontend? Use this skill. Covers React component
  unit tests (vitest + @testing-library/react), context mocking, shared mock
  data, and Playwright E2E tests with the Full Cycle pattern. Activate whenever
  the user asks to write, fix, or review any test in frontend/admin/ — unit or
  E2E — even if they don't say "vitest" or "Playwright" explicitly.
license: MIT
compatibility: 'Node 20+, vitest 2+, @testing-library/react, Playwright 1.40+'
metadata:
  author: platform-team
  version: '2.0.0'
  sdlc-phase: testing
allowed-tools: Read Edit Write Bash(npm:*) Bash(npx:*) Bash(vitest:*) Bash(playwright:*)
context: fork
---

# Vitest + Playwright Patterns — Memo Project

## Agent Decision Protocol

```
WHEN user asks to write a test:
  IF "component renders" / "props" / "callback" / "hook returns"
    → write vitest UNIT test (see Unit Test Patterns)
  IF "user clicks" / "persists" / "DB" / "full flow" / "browser"
    → write Playwright E2E test (see E2E Test Patterns)
  IF unclear → ask: "Это проверка рендера компонента или полный флоу через браузер + бэкенд?"

BEFORE writing any unit test:
  READ references/memo-mock-data.ts        ← real mock objects + factory functions
  READ references/memo-mock-contexts.ts    ← context factory signatures
  NEVER define mock data inline — always import from helpers

BEFORE writing any E2E test:
  READ references/memo-e2e-factories.ts    ← createTestClient / createTestActivity / createTestRecord
  READ references/memo-e2e-helpers.ts      ← openModal / openAddTab / waitForToast
  DECIDE: API check or SQL check? (see DB Verification table)

AFTER writing code:
  RUN the relevant test command (see Running Tests)
  FIX compilation errors before declaring done

NEVER disable a test without a GitHub issue link:
  test.skip(true, 'GH #176')        ← GOOD — tracked, CI warns when #176 closes
  test.fixme('GH #156: flaky …')    ← GOOD
  test.skip(true, 'waiting for X')  ← BAD — no issue, gets lost
  Conditional skips inside test body (missing seed data: if (!row) { test.skip(); return; })
  are fine without a link.
  CI job `skip-tracker` (scripts/check_skipped_tests.py) checks linked issue status.
```

---

## Project Structure

```
frontend/admin/
├── __tests__/
│   ├── setup.ts
│   ├── helpers/
│   │   ├── mockData.ts             ← shared mock objects + factory functions
│   │   ├── mockContexts.ts         ← context mock factories
│   │   └── renderWithProviders.tsx
│   └── ComponentName.test.tsx
│
└── e2e/
    ├── feature-name.spec.ts
    └── fixtures/
        ├── factories.ts            ← createTestClient, createTestActivity, createTestRecord, cleanup
        ├── helpers.ts              ← waitForScheduleReady, openModal, openAddTab, waitForToast
        ├── db-query.ts             ← queryDB, queryDBRow, queryDBRows
        └── global-setup.ts
```

## Import Aliases

```typescript
// Source alias
@/               → frontend/admin/src/

// Domain types
@memo/domain     → Activity, Record, Client, Visit types
@memo/api-client → API call functions (createRecord, deleteRecord, createPayment, …)

// Context hooks
import { useSchedule } from '@/contexts/ScheduleContext';
import { useRecords }  from '@/contexts/RecordsContext';
import { useUI }       from '@/contexts/UIContext';

// Test helpers (relative from __tests__/)
import { mockActivity, mockRecord, mockClient, mockArtists,
         mockServices, mockLocations, mockVisitor, mockPayment,
         mockTariffs, createMockActivity, createMockRecord,
         createMockClient } from './helpers/mockData';

import { createMockScheduleContext,
         createMockRecordsContext,
         createMockUIContext }  from './helpers/mockContexts';

import { renderWithProviders } from './helpers/renderWithProviders';

// E2E fixtures (relative from e2e/)
import { createTestClient, createTestActivity,
         createTestRecord, cleanup }       from './fixtures/factories';
import { waitForScheduleReady, openModal,
         openAddTab, waitForToast,
         clickModalTab }                   from './fixtures/helpers';
import { queryDB, queryDBRow, queryDBRows } from './fixtures/db-query';
```

---

## Unit Test Patterns

### Standard Template

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { mockActivity, mockRecord, createMockRecord } from './helpers/mockData';
import { createMockScheduleContext, createMockUIContext,
         createMockRecordsContext } from './helpers/mockContexts';

// 1. Mock context modules (before importing hooks)
vi.mock('@/contexts/ScheduleContext', () => ({ useSchedule: vi.fn() }));
vi.mock('@/contexts/UIContext',       () => ({ useUI: vi.fn() }));
vi.mock('@/contexts/RecordsContext',  () => ({ useRecords: vi.fn() }));

import { useSchedule } from '@/contexts/ScheduleContext';
import { useUI }       from '@/contexts/UIContext';
import { useRecords }  from '@/contexts/RecordsContext';

const mockUseSchedule = vi.mocked(useSchedule);
const mockUseUI       = vi.mocked(useUI);
const mockUseRecords  = vi.mocked(useRecords);

// 2. Set up default context mocks
beforeEach(() => {
  mockUseSchedule.mockReturnValue(createMockScheduleContext());
  mockUseUI.mockReturnValue(createMockUIContext());
  mockUseRecords.mockReturnValue(createMockRecordsContext());
});

afterEach(() => vi.restoreAllMocks());

describe('MyComponent', () => {
  it('renders the dialog', () => {
    render(<MyComponent activity={mockActivity} onClose={vi.fn()} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn();
    render(<MyComponent activity={mockActivity} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('Закрыть'));
    expect(onClose).toHaveBeenCalled();
  });

  // Override one field in a context:
  it('shows loading state', () => {
    mockUseSchedule.mockReturnValue(createMockScheduleContext({ loading: true }));
    render(<MyComponent activity={mockActivity} onClose={vi.fn()} />);
    expect(screen.getByText('Загрузка...')).toBeInTheDocument();
  });
});
```

### Context Factory Signatures

| Factory | Key fields available to override |
|---------|----------------------------------|
| `createMockScheduleContext(overrides?)` | `artists`, `services`, `locations`, `activities`, `loading`, `error`, `filterMasterId`, `filterLocationId`, `addActivity`, `updateActivity`, `deleteActivity` |
| `createMockRecordsContext(overrides?)` | `records`, `clients` (Map), `payments` (Map), `loading`, `error` |
| `createMockUIContext(overrides?)` | `deleteMode`, `toasts`, `showToast`, `sidebarCollapsed`, `theme` |

### Mocking API Calls

```typescript
vi.mock('@memo/api-client', () => ({
  createRecord: vi.fn(),
  deleteRecord: vi.fn(),
  createPayment: vi.fn(),
}));

import { createRecord } from '@memo/api-client';

beforeEach(() => {
  vi.mocked(createRecord).mockResolvedValue(createMockRecord({ status: 'confirmed' }));
});
```

### renderWithProviders (for integration-style tests)

```typescript
import { renderWithProviders } from './helpers/renderWithProviders';

// Wraps in QueryClientProvider (retry: false by default)
const { queryClient } = renderWithProviders(<MyComponent activity={mockActivity} />);
```

---

## E2E Test Patterns

### The Full Cycle Pattern (mandatory for all E2E)

```
1. SETUP     → create test data via factories
2. ACTION    → user interaction in browser
3. VERIFY UI → what the user SEES
4. VERIFY DB → what's STORED in backend (API or SQL)
5. CLEANUP   → delete all created data (ALWAYS in finally block)
```

### E2E Template

```typescript
import { test, expect } from '@playwright/test';
import { createTestClient, createTestActivity, createTestRecord, cleanup }
  from './fixtures/factories';
import { waitForScheduleReady, openModal, openAddTab, waitForToast }
  from './fixtures/helpers';
import { queryDBRow } from './fixtures/db-query';

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page }) => {
    await waitForScheduleReady(page);  // navigates to /schedule, waits for activity cards
  });

  test('scenario description', async ({ page, request }) => {
    // 1. SETUP
    const client   = await createTestClient(request);
    const activity = await createTestActivity(request);
    const record   = await createTestRecord(request, activity.id, client.id);

    await page.goto('/schedule');
    await page.waitForSelector('[data-testid^="activity-"]', { timeout: 15000 });

    try {
      // 2. ACTION
      await openModal(page);
      await page.locator('[data-testid="some-button"]').click();

      // 3. VERIFY UI
      await expect(page.locator('[data-testid="some-element"]')).toBeVisible();
      await expect(page.locator('[data-testid="some-text"]')).toHaveText('Ожидаемый текст');

      // 4. VERIFY DB (via API)
      const resp = await request.get(`${BACKEND}/api/v1/records/${record.id}`);
      expect((await resp.json()).status).toBe('confirmed');

      // 4. VERIFY DB (via SQL, for deep checks)
      const row = queryDBRow(`SELECT is_active FROM records WHERE id='${record.id}'`);
      expect(row!.is_active).toBe(1);

    } finally {
      // 5. CLEANUP — always in finally
      await cleanup(request, `/api/v1/records/${record.id}`);
      await cleanup(request, `/api/v1/clients/${client.id}`);
    }
  });
});
```

### E2E Factory Signatures

```typescript
createTestClient(api, overrides?)
  // overrides: { name?, phone? }
  // → { id, name, phone, channel, created_at, … }

createTestActivity(api, overrides?)
  // fetches first master/service/location from seed data; overrides any field
  // → { id, master_id, service_id, location_id, start, duration, capacity, … }

createTestRecord(api, activityId, clientId, overrides?)
  // overrides: { visits?, comment?, … }
  // → { id, activity_id, client_id, status, visits, … }

cleanup(api, path)
  // DELETE {BACKEND}{path}; ignores errors
  // always call in finally block
```

### E2E Helper Signatures

```typescript
waitForScheduleReady(page)     // goto /schedule + waitForSelector('[data-testid^="activity-"]')
openModal(page)                // dispatches __memo-open-modal event; waits for modal visible
openAddTab(page)               // dispatches __memo-quick-add; waits for [data-testid="new-booking-tab"]
waitForToast(page, pattern?)   // waits for [role="status"]; checks text if pattern given
clickModalTab(page, tabTestId) // clicks [data-testid="{tabTestId}"]
```

---

## DB Verification Decision Table

| What to check | Use API | Use SQL |
|---------------|---------|---------|
| Record was created | `GET /api/v1/records/{id}` | |
| Status updated | `GET /api/v1/records/{id}` | |
| Soft delete flag (`is_active`) | | `SELECT is_active FROM records` |
| FK constraint | | `SELECT client_id FROM records` |
| Cascade behavior | | `SELECT COUNT(*) FROM visits WHERE record_id=…` |
| Payment total | | `SELECT COALESCE(SUM(amount),0) FROM payments WHERE record_id=…` |

```typescript
// queryDB → raw string
const total = queryDB(`SELECT COALESCE(SUM(amount),0) FROM payments WHERE record_id='${id}'`);
expect(Number(total)).toBe(1500);

// queryDBRow → first row as object (null if no rows); SQLite bool is 0/1
const row = queryDBRow(`SELECT is_active FROM records WHERE id='${id}'`);
expect(row!.is_active).toBe(0);

// queryDBRows → all rows as array
const visits = queryDBRows(`SELECT * FROM visits WHERE record_id='${id}' AND is_active=1`);
expect(visits.length).toBe(0);
```

DB_PATH resolves as: `process.env.TEST_DB_PATH || 'backend/test_memo.db'`

---

## Output Format

| Task | Output location | Naming |
|------|----------------|--------|
| New unit test | next to component | `ComponentName.test.tsx` |
| New E2E test | `e2e/` | `feature-name.spec.ts` |
| New mock data | `__tests__/helpers/mockData.ts` | append, don't duplicate |
| New context mock | `__tests__/helpers/mockContexts.ts` | append |

**Never** modify `helpers/mockData.ts` or `helpers/mockContexts.ts` without explicit request.

---

## Common Mistakes

| # | Mistake | Fix |
|---|---------|-----|
| 1 | Defining mock objects inline | Import from `helpers/mockData.ts` |
| 2 | `toBeVisible()` on element that might be empty | Also check `toHaveText()` / `textContent()` |
| 3 | Trusting HTTP 200 without verifying state | Follow up with API GET or SQL query |
| 4 | Hardcoded IDs in E2E tests | Use factories (`createTestActivity`, etc.) |
| 5 | No `finally` block for E2E cleanup | Data leaks between test runs |
| 6 | `page.waitForTimeout()` for async sync | Use `expect(locator).toBeVisible({ timeout })` |
| 7 | Mocking transitive dependencies in unit tests | Mock only direct `@/contexts/*` dependencies |
| 8 | Using `renderWithProviders` when context mocks suffice | Use `renderWithProviders` only when testing real provider interactions |
| 9 | Treating a local screenshot e2e pixel-diff as a regression | Check CI first: `gh run list --branch main` and `gh run view <id>`. If the `e2e-tests` job in `.github/workflows/test.yml` is green on both `main` and the PR, the diff is font/OS rendering drift — baselines are recorded in CI via `.github/workflows/update-snapshots.yml`. Don't edit the code and don't re-record baselines locally. See `docs/tests_workflow.md` → "Known caveats" (precedent: 2026-07-29, IMPL #182 — 6 local failures, CI green). |

---

## Running Tests

```bash
cd frontend/admin

# Unit tests
npm run test          # single pass (~2s)
npm run test:watch    # watch mode

# E2E tests (start backend first locally)
npm run test:e2e      # headless (~60s)
npm run test:e2e:ui   # with browser UI

# All
npm run test:all      # vitest run && playwright test
```

**Local E2E:** start backend before running:
```bash
cd backend && uv run uvicorn src.main:app --port 8000 &
```
**CI:** both servers started automatically via `webServer` in `playwright.config.ts`.

---

## Reference Files

Read these on demand — don't pre-load all of them:

| File | Read when |
|------|-----------|
| `references/memo-mock-data.ts` | Need exact shape of `mockActivity`, `mockRecord`, etc. |
| `references/memo-mock-contexts.ts` | Need full field list for a context factory |
| `references/memo-render-with-providers.tsx` | Testing with real QueryClient |
| `references/memo-e2e-factories.ts` | Need factory internals or `uid()` behavior |
| `references/memo-e2e-helpers.ts` | Need to understand how `openModal` / `openAddTab` work internally |
| `references/memo-e2e-db-query.ts` | Need `execSync` / `sqlite3` details |
| `references/memo-e2e-scenarios.md` | Need full worked examples (create record, delete+undo, add payment) |
