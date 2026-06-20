# E2E Scenario Templates — Memo Project

Quick reference for writing Playwright E2E scenarios using the Full Cycle pattern.

## The Full Cycle Pattern

Every E2E test follows this exact pattern:

```
1. SETUP:     Create test data via API (factories)
2. ACTION:    User interaction in browser (click, type, navigate)
3. VERIFY UI: What the user SEES (toHaveText, toHaveValue)
4. VERIFY DB: What's STORED in backend (API GET or SQL)
5. CLEANUP:   Delete test data via API (cleanup helper)
```

## Scenario Template

```typescript
import { test, expect } from '@playwright/test';
import { createTestClient, createTestActivity, createTestRecord, cleanup } from './fixtures/factories';
import { waitForScheduleReady, openModal, openAddTab } from './fixtures/helpers';
import { queryDBRow } from './fixtures/db-query';

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

    // Reload to pick up new data
    await page.goto('/schedule');
    await page.waitForSelector('[data-testid^="activity-"]', { timeout: 15000 });

    // 2. ACTION
    await openModal(page);
    // ... user interactions ...

    // 3. VERIFY UI
    await expect(page.locator('[data-testid="some-element"]')).toBeVisible();
    await expect(page.locator('[data-testid="some-text"]')).toHaveText('Expected');

    // 4. VERIFY DB (via API or SQL)
    const resp = await request.get(`${BACKEND}/api/v1/records/${record.id}`);
    expect((await resp.json()).status).toBe('confirmed');

    // Or via SQL for deep checks:
    const row = queryDBRow(`SELECT status FROM records WHERE id='${record.id}'`);
    expect(row!.status).toBe('confirmed');

    // 5. CLEANUP
    await cleanup(request, `/api/v1/records/${record.id}`);
    await cleanup(request, `/api/v1/clients/${client.id}`);
  });
});
```

## Concrete Example: Create Record Flow

```typescript
test('Create new record — data persists in backend', async ({ page, request }) => {
  const testPhone = `+7999${String(Date.now()).slice(-7)}`;

  // 1. SETUP — just navigate to add tab
  await openAddTab(page);

  // 2. ACTION — fill form
  await page.locator('[data-testid="input-phone"]').fill(testPhone);
  await page.locator('[data-testid="input-phone"]').blur();
  await page.locator('[data-testid="input-client-name"]').fill('E2E Client');
  await page.locator('[data-testid="btn-create-record"]').click();

  // 3. VERIFY UI — success toast
  await page.waitForFunction(() => {
    const toasts = document.querySelectorAll('[role="status"]');
    return toasts.length > 0;
  }, { timeout: 5000 });

  // 4. VERIFY DB — client was created with correct phone
  const clientsResp = await request.get(`${BACKEND}/api/v1/clients`);
  const clients = await clientsResp.json();
  const testClient = clients.find((c: any) => c.phone === testPhone);
  expect(testClient).toBeTruthy();
  expect(testClient.name).toBe('E2E Client');

  // 5. CLEANUP
  if (testClient) await cleanup(request, `/api/v1/clients/${testClient.id}`);
});
```

## Concrete Example: Delete with Undo

```typescript
test('Delete record — undo within 5s preserves it', async ({ page, request }) => {
  // 1. SETUP
  const client = await createTestClient(request);
  const activity = await getFirstActivity(page);
  const record = await createTestRecord(request, activity.id, client.id);

  await page.goto('/schedule');
  await page.waitForSelector('[data-testid^="activity-"]', { timeout: 15000 });
  await openModal(page);

  // 2. ACTION — navigate to client tab and delete
  const clientTab = page.locator(`[data-testid="tab-client-${record.id}"]`);
  await clientTab.click();
  await page.locator('[data-testid="btn-delete-record"]').click();

  // 3. VERIFY UI — undo toast appears
  await expect(page.locator('text=Запись удалена через 5 секунд')).toBeVisible({ timeout: 3000 });

  // Click undo
  await page.locator('text=Отмена').click();
  await page.waitForTimeout(1000);

  // 4. VERIFY DB — record still exists
  const resp = await request.get(`${BACKEND}/api/v1/records/${record.id}`);
  expect(resp.ok()).toBeTruthy();

  // 5. CLEANUP
  await cleanup(request, `/api/v1/records/${record.id}`);
  await cleanup(request, `/api/v1/clients/${client.id}`);
});
```

## Concrete Example: Add Payment

```typescript
test('Add payment — financial summary updates', async ({ page, request }) => {
  // 1. SETUP
  const client = await createTestClient(request);
  const activity = await getFirstActivity(page);
  const record = await createTestRecord(request, activity.id, client.id);

  await page.goto('/schedule');
  await page.waitForSelector('[data-testid^="activity-"]', { timeout: 15000 });
  await openModal(page);

  // 2. ACTION — navigate to client tab, add payment
  const clientTab = page.locator(`[data-testid="tab-client-${record.id}"]`);
  await clientTab.click();
  await page.locator('input[placeholder="Сумма"]').fill('1500');
  await page.locator('[data-testid="btn-add-payment"]').click();
  await page.waitForTimeout(1000);

  // 3. VERIFY UI — footer updated (check specific values, not just visibility)
  const footer = page.locator('[data-testid="modal-footer"]');
  await expect(footer).toBeVisible();

  // 4. VERIFY DB — payment persisted
  const paymentsResp = await request.get(`${BACKEND}/api/v1/payments?record_id=${record.id}`);
  const payments = await paymentsResp.json();
  expect(payments.length).toBeGreaterThan(0);
  expect(payments[0].amount).toBe(1500);

  // Or via SQL:
  const total = queryDB(
    `SELECT COALESCE(SUM(amount), 0) FROM payments WHERE record_id='${record.id}' AND is_active=1`
  );
  expect(Number(total)).toBe(1500);

  // 5. CLEANUP
  await cleanup(request, `/api/v1/records/${record.id}`);
  await cleanup(request, `/api/v1/clients/${client.id}`);
});
```

## Scenario Checklist

Use this checklist when writing new E2E scenarios:

- [ ] Does the test create its own data via factories? (not rely on seed data)
- [ ] Does the test verify WHAT the user sees? (not just element existence)
- [ ] Does the test verify what's STORED in DB? (not just HTTP 200)
- [ ] Does the test clean up ALL created data? (in finally block)
- [ ] Does the test use `waitForSelector` instead of `waitForTimeout`?
- [ ] Is the test independent — can it run alone and in any order?
- [ ] Are assertions specific — checking content, not just visibility?
