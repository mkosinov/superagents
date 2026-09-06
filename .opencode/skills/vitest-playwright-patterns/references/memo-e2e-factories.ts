/**
 * memo-e2e-factories.ts — Data creation factories for Playwright E2E tests.
 *
 * Place at: frontend/admin/e2e/fixtures/factories.ts
 *
 * Each factory creates test data via the backend API.
 * Always use these instead of hardcoding test data.
 *
 * Usage:
 *   const client = await createTestClient(request);
 *   const activity = await createTestActivity(request);
 *   const record = await createTestRecord(request, activity.id, client.id);
 *   await cleanup(request, `/api/v1/records/${record.id}`);
 */

import { type APIRequestContext, expect } from '@playwright/test';

const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000';

let testCounter = 0;
function uid(): string {
  testCounter++;
  return `e2e_${Date.now()}_${testCounter}`;
}

/**
 * Create a test client via backend API.
 * Always use this instead of hardcoding client data.
 */
export async function createTestClient(
  api: APIRequestContext,
  overrides?: { name?: string; phone?: string },
) {
  const name = overrides?.name || `Test Client ${uid()}`;
  const phone = overrides?.phone || `+7999${String(Date.now()).slice(-7)}`;
  const resp = await api.post(`${BACKEND}/api/v1/clients`, {
    data: { name, phone, channel: 'telegram' },
  });
  expect(resp.ok()).toBeTruthy();
  return resp.json();
}

/**
 * Create a test activity via backend API.
 * Uses first available master, service, location from seed data.
 */
export async function createTestActivity(
  api: APIRequestContext,
  overrides?: Record<string, any>,
) {
  const [mastersResp, servicesResp, locationsResp] = await Promise.all([
    api.get(`${BACKEND}/api/v1/masters`),
    api.get(`${BACKEND}/api/v1/services`),
    api.get(`${BACKEND}/api/v1/locations`),
  ]);
  const masters = await mastersResp.json();
  const services = await servicesResp.json();
  const locations = await locationsResp.json();

  const resp = await api.post(`${BACKEND}/api/v1/activities`, {
    data: {
      master_id: masters[0].id,
      service_id: services[0].id,
      location_id: locations[0].id,
      start: new Date().toISOString().slice(0, 19),
      duration: services[0].duration || 90,
      capacity: 8,
      is_private: false,
      ...overrides,
    },
  });
  expect(resp.ok()).toBeTruthy();
  return resp.json();
}

/**
 * Create a test record via backend API.
 */
export async function createTestRecord(
  api: APIRequestContext,
  activityId: string,
  clientId: string,
  overrides?: Record<string, any>,
) {
  const resp = await api.post(`${BACKEND}/api/v1/records`, {
    data: {
      activity_id: activityId,
      client_id: clientId,
      visits: [{ price: 3500 }],
      ...overrides,
    },
  });
  expect(resp.ok()).toBeTruthy();
  return resp.json();
}

/**
 * Delete entity via API (ignore errors — used in cleanup).
 * Always call this in test cleanup to prevent data leaking between tests.
 */
export async function cleanup(api: APIRequestContext, path: string) {
  try {
    await api.delete(`${BACKEND}${path}`);
  } catch {
    // Ignore cleanup errors
  }
}

// ─── Usage Example ─────────────────────────────────────────────────────────────
//
// test('Create and verify record', async ({ page, request }) => {
//   // Setup
//   const client = await createTestClient(request);
//   const activity = await createTestActivity(request);
//   const record = await createTestRecord(request, activity.id, client.id);
//
//   try {
//     // ... test actions ...
//   } finally {
//     // Cleanup (always!)
//     await cleanup(request, `/api/v1/records/${record.id}`);
//     await cleanup(request, `/api/v1/clients/${client.id}`);
//   }
// });
