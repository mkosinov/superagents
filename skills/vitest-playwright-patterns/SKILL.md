---
name: vitest-playwright-patterns
description: >-
  Frontend testing patterns for Memo project — vitest unit tests and Playwright E2E tests.
  Use when writing React component tests with vitest + testing-library, mocking contexts
  and API calls, creating shared mock data, writing Playwright E2E scenarios with Full Cycle
  pattern (setup → action → verify UI → verify DB → cleanup), using fixture factories and
  DB verification helpers. Does NOT cover backend tests (use pytest-patterns).
license: MIT
compatibility: 'Node 20+, vitest 2+, @testing-library/react, Playwright 1.40+'
metadata:
  author: platform-team
  version: '1.0.0'
  sdlc-phase: testing
allowed-tools: Read Edit Write Bash(npm:*) Bash(npx:*) Bash(vitest:*) Bash(playwright:*)
context: fork
---

# Vitest + Playwright Patterns — Memo Project

## When to Use

Activate this skill when:
- Writing unit tests for React components (vitest + @testing-library/react)
- Creating or updating shared mock data modules (`__tests__/helpers/`)
- Mocking React contexts (ScheduleContext, RecordsContext, UIContext)
- Writing Playwright E2E scenarios
- Setting up E2E fixture factories (`e2e/fixtures/`)
- Verifying DB state from E2E tests (direct SQL via sqlite3)
- Configuring Playwright for CI (dual webServer)

Do NOT use this skill for:
- Backend Python tests with pytest (use `pytest-patterns`)
- TDD workflow enforcement (use `test-driven-development`)

## Instructions

### Test Architecture

```
frontend/admin/
├── __tests__/                    # Unit tests (vitest + jsdom)
│   ├── setup.ts                  # Global setup (jest-dom matchers)
│   ├── helpers/                  # Shared test utilities
│   │   ├── mockData.ts          # Mock artists, services, locations
│   │   ├── mockContexts.ts      # Context mock factories
│   │   └── renderWithProviders.tsx  # Custom render with providers
│   ├── ActivityDetailsModal.test.tsx
│   └── ... (other component tests)
│
├── e2e/                          # E2E tests (Playwright + real browser)
│   ├── activity-details-modal.spec.ts
│   ├── fixtures/                 # Shared E2E utilities
│   │   ├── factories.ts         # createTestClient, createTestActivity
│   │   ├── db-query.ts          # Direct SQLite verification
│   │   ├── helpers.ts           # openModal, waitForScheduleReady
│   │   └── global-setup.ts     # Seed data before E2E suite
│   └── screenshots/             # Visual regression baselines
```

**Two layers, two tools:**

| Layer | Tool | What it tests | Speed |
|-------|------|---------------|-------|
| **Unit** | vitest + @testing-library/react | Component rendering, props, callbacks | ~100ms |
| **E2E** | Playwright | Full user flows in real browser + backend | ~5s |

**Rule of thumb:**
- Component renders correctly? → Unit test
- User clicks button and data persists in DB? → E2E test

### Unit Test Patterns

#### Mock Infrastructure

**Problem:** Every test file defines its own mock data → ~100 lines boilerplate per file.

**Solution:** Shared mock modules in `__tests__/helpers/`.

**Import pattern:**
```typescript
import { mockArtists, mockServices, mockLocations, mockActivity } from './helpers/mockData';
import { createScheduleContextMock, createRecordsContextMock, createUIContextMock } from './helpers/mockContexts';
```

#### Component Test Template

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { mockActivity } from './helpers/mockData';
import { createScheduleContextMock, createUIContextMock } from './helpers/mockContexts';

// 1. Mock context modules
vi.mock('@/contexts/ScheduleContext', () => ({ useSchedule: vi.fn() }));
vi.mock('@/contexts/UIContext', () => ({ useUI: vi.fn() }));

import { useSchedule } from '@/contexts/ScheduleContext';
import { useUI } from '@/contexts/UIContext';

const mockUseSchedule = vi.mocked(useSchedule);
const mockUseUI = vi.mocked(useUI);

// 2. Set up default mocks
beforeEach(() => {
  mockUseSchedule.mockReturnValue(createScheduleContextMock());
  mockUseUI.mockReturnValue(createUIContextMock());
});

afterEach(() => vi.restoreAllMocks());

// 3. Write tests
describe('MyComponent', () => {
  it('renders the component', () => {
    render(<MyComponent activity={mockActivity} onClose={vi.fn()} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn();
    render(<MyComponent activity={mockActivity} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('Закрыть'));
    expect(onClose).toHaveBeenCalled();
  });
});
```

#### Testing User Interactions

```typescript
describe('NewBookingTab', () => {
  it('adds a visitor row when button clicked', () => {
    render(<NewBookingTab {...defaultProps} />);
    expect(screen.queryAllByTestId('visitor-form-row').length).toBe(0);
    fireEvent.click(screen.getByText(/\+ Добавить посетителя/));
    expect(screen.getAllByTestId('visitor-form-row').length).toBe(1);
  });

  it('validates name before submit', () => {
    const showToast = vi.fn();
    render(<NewBookingTab {...defaultProps} showToast={showToast} />);
    fireEvent.click(screen.getByTestId('btn-create-record'));
    expect(showToast).toHaveBeenCalledWith('Заполните имя');
  });
});
```

#### Mocking API Calls

```typescript
vi.mock('@memo/api-client', () => ({
  createRecord: vi.fn(),
  deleteRecord: vi.fn(),
  createPayment: vi.fn(),
}));

import { createRecord } from '@memo/api-client';

beforeEach(() => {
  vi.mocked(createRecord).mockResolvedValue({
    id: 'r_new', status: 'pending', /* ... */
  });
});
```

### E2E Test Patterns

#### The Full Cycle Pattern

Every E2E test follows this exact pattern:

```
1. SETUP:     Create test data via API (factories)
2. ACTION:    User interaction in browser (click, type, navigate)
3. VERIFY UI: What the user SEES (toHaveText, toHaveValue)
4. VERIFY DB: What's STORED in backend (API GET or SQL)
5. CLEANUP:   Delete test data via API (cleanup helper)
```

#### E2E Scenario Template

```typescript
import { test, expect } from '@playwright/test';
import { createTestClient, createTestActivity, createTestRecord, cleanup } from './fixtures/factories';
import { waitForScheduleReady, openModal, openAddTab } from './fixtures/helpers';

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page }) => {
    await waitForScheduleReady(page);
  });

  test('Scenario description', async ({ page, request }) => {
    // 1. SETUP
    const client = await createTestClient(request);
    const activity = await createTestActivity(request);
    const record = await createTestRecord(request, activity.id, client.id);

    await page.goto('/schedule');
    await page.waitForSelector('[data-testid^="activity-"]', { timeout: 15000 });

    // 2. ACTION
    await openModal(page);
    // ... user interactions ...

    // 3. VERIFY UI
    await expect(page.locator('[data-testid="some-element"]')).toBeVisible();

    // 4. VERIFY DB (via API)
    const resp = await request.get(`${BACKEND}/api/v1/records/${record.id}`);
    expect((await resp.json()).status).toBe('confirmed');

    // 5. CLEANUP
    await cleanup(request, `/api/v1/records/${record.id}`);
    await cleanup(request, `/api/v1/clients/${client.id}`);
  });
});
```

### DB Verification

**When to use API vs SQL:**

| Check type | Use API | Use SQL |
|------------|---------|---------|
| Record was created | `GET /api/v1/records/{id}` | |
| Status was updated | `GET /api/v1/records/{id}` | |
| Soft delete flag set | | `SELECT is_active FROM records` |
| FK constraint | | `SELECT client_id FROM records` |
| Cascade behavior | | `SELECT COUNT(*) FROM visits WHERE record_id=...` |
| Payment total | | `SELECT SUM(amount) FROM payments WHERE record_id=...` |

```typescript
import { queryDBRow } from './fixtures/db-query';

// Verify soft delete at DB level
const row = queryDBRow(`SELECT is_active FROM records WHERE id='${recordId}'`);
expect(row!.is_active).toBe(0);  // SQLite stores bool as 0/1
```

### Backend Startup (CI vs Local)

**Local:** Start backend manually before E2E:
```bash
cd backend && uv run uvicorn src.main:app --port 8000 &
cd frontend/admin && npm run test:e2e
```

**CI:** Both started automatically via `webServer` in `playwright.config.ts`.

### Common Mistakes

| # | Mistake | Fix |
|---|---------|-----|
| 1 | Checking existence, not content (`toBeVisible()` on empty div) | Verify `textContent()` is truthy and non-empty |
| 2 | Trusting HTTP 200 without DB check | Verify via API GET or SQL after mutation |
| 3 | Hardcoded test data (specific IDs) | Use factories (`createTestActivity`) |
| 4 | Not cleaning up test data | Always `cleanup()` in `finally` block |
| 5 | Mocking everything in unit tests | Mock only direct dependencies; use `renderWithProviders` for real context |
| 6 | Using `page.waitForTimeout()` for sync | Wait for specific condition: `expect(locator).toBeVisible({ timeout })` |
| 7 | Duplicating mock data across files | Import from `__tests__/helpers/mockData` |

### Running Tests

```bash
# Unit tests (fast, ~2s)
cd frontend/admin
npm run test              # single pass
npm run test:watch        # watch mode

# E2E tests (slow, ~60s)
npm run test:e2e          # headless
npm run test:e2e:ui       # with browser UI

# All tests
npm run test:all          # vitest run && playwright test
```

## Examples

See `references/memo-mock-data.ts` for shared mock data (artists, services, locations).
See `references/memo-mock-contexts.ts` for context mock factories.
See `references/memo-render-with-providers.tsx` for custom render utility.
See `references/memo-e2e-factories.ts` for E2E data creation factories.
See `references/memo-e2e-helpers.ts` for E2E UI interaction helpers.
See `references/memo-e2e-db-query.ts` for direct SQLite verification.
See `references/memo-e2e-scenarios.md` for E2E scenario templates and examples.
