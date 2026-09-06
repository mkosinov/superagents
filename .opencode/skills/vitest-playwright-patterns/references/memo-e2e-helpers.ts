/**
 * memo-e2e-helpers.ts — UI interaction helpers for Playwright E2E tests.
 *
 * Place at: frontend/admin/e2e/fixtures/helpers.ts
 *
 * These helpers encapsulate complex UI interactions (opening modals,
 * waiting for data, navigating tabs) so test files stay readable.
 */

import { type Page, expect } from '@playwright/test';

/**
 * Wait for schedule page to load with activity cards.
 * Navigates to /schedule and waits for at least one activity card to appear.
 */
export async function waitForScheduleReady(page: Page) {
  await page.goto('/schedule');
  await page.waitForSelector('[data-testid^="activity-"]', { timeout: 15000 });
}

/**
 * Get the activity data from the first visible activity card.
 * Uses React fiber tree traversal to extract the activity prop.
 */
async function getFirstActivity(page: Page) {
  return page.evaluate(() => {
    const card = document.querySelector('[data-testid^="activity-"]');
    if (!card) return null;
    const fiberKey = Object.keys(card).find((k: string) => k.startsWith('__reactFiber'));
    if (!fiberKey) return null;
    let current = (card as any)[fiberKey];
    while (current) {
      if (current.memoizedProps?.activity) return current.memoizedProps.activity;
      current = current.return;
    }
    return null;
  });
}

/**
 * Open the activity details modal for the first visible activity.
 * Dispatches a custom event that the modal listens to.
 */
export async function openModal(page: Page) {
  const activity = await getFirstActivity(page);
  if (!activity) throw new Error('No activity found on page');

  await page.evaluate((act: any) => {
    document.dispatchEvent(new CustomEvent('__memo-open-modal', { detail: { activity: act } }));
  }, activity);

  await page.waitForSelector('[data-testid="activity-details-modal"]', {
    state: 'visible',
    timeout: 10000,
  });
}

/**
 * Open the modal directly on the "new booking" (+) tab.
 * Useful for testing record creation flows.
 */
export async function openAddTab(page: Page) {
  const activity = await getFirstActivity(page);
  if (!activity) throw new Error('No activity found on page');

  await page.evaluate((act: any) => {
    document.dispatchEvent(new CustomEvent('__memo-quick-add', { detail: { activity: act } }));
  }, activity);

  await page.waitForSelector('[data-testid="activity-details-modal"]', {
    state: 'visible',
    timeout: 10000,
  });
  await expect(page.locator('[data-testid="new-booking-tab"]')).toBeVisible();
}

/**
 * Wait for a toast notification to appear.
 */
export async function waitForToast(page: Page, textPattern?: string | RegExp) {
  const toast = page.locator('[role="status"]');
  await toast.first().waitFor({ state: 'visible', timeout: 5000 });
  if (textPattern) {
    await expect(toast.first()).toContainText(textPattern);
  }
}

/**
 * Click a specific tab in the modal by tab ID.
 */
export async function clickModalTab(page: Page, tabTestId: string) {
  await page.locator(`[data-testid="${tabTestId}"]`).click();
}

// ─── Usage Example ─────────────────────────────────────────────────────────────
//
// test.beforeEach(async ({ page }) => {
//   await waitForScheduleReady(page);
// });
//
// test('Open modal and verify settings', async ({ page }) => {
//   await openModal(page);
//   await expect(page.locator('[data-testid="settings-tab"]')).toBeVisible();
// });
//
// test('Create record via add tab', async ({ page }) => {
//   await openAddTab(page);
//   await page.locator('[data-testid="input-phone"]').fill('+79990001122');
//   // ...
//   await waitForToast(page, /запись создана/i);
// });
