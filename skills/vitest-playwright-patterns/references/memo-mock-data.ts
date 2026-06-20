/**
 * memo-mock-data.ts — Shared mock data for all Memo unit tests.
 *
 * Place at: frontend/admin/__tests__/helpers/mockData.ts
 *
 * Import this instead of defining mock data in each test file.
 * Contains: mockArtists, mockServices, mockLocations, mockActivity,
 *           mockClient, mockRecord, mockVisitor, mockPayment, mockTariffs
 * Plus factory functions: createMockActivity, createMockRecord, createMockClient
 */

import type { Activity } from '@memo/domain';

// ─── Reference Data ────────────────────────────────────────────────────────────

export const mockArtists = [
  { id: 'm1', name: 'Ольга Середа', shortName: 'Ольга', color: '#5B8C7A' },
  { id: 'm2', name: 'Юлия Большакова', shortName: 'Юлия', color: '#6B7E9C' },
];

export const mockServices = [
  {
    id: 's1', name: 'Картина маслом', duration: 2.5, maxCapacity: 8,
    minAge: '12', maxAge: '99',
    defaultAdultPrice: 3500, defaultChildPrice: 2500, defaultIndividualPrice: 5000,
    tariffs: [
      { id: 't1', service_id: 's1', title: 'Взрослый', price: 3500, description: null },
      { id: 't2', service_id: 's1', title: 'Детский', price: 2500, description: null },
    ],
  },
  {
    id: 's2', name: 'Картина акрилом', duration: 2, maxCapacity: 10,
    minAge: '6', maxAge: '99',
    defaultAdultPrice: 2800, defaultChildPrice: 2000, defaultIndividualPrice: 4000,
    tariffs: [
      { id: 't3', service_id: 's2', title: 'Взрослый', price: 2800, description: null },
    ],
  },
];

export const mockLocations = [
  { id: 'alpika', name: 'Альпика', address: 'Альпика, 1 этаж' },
  { id: 'grand', name: 'Гранд Отель Поляна', address: 'Гранд Отель, лобби' },
];

export const mockActivity: Activity = {
  id: 'ev_1',
  day: 5,
  masterId: 'm1',
  startTime: 14,
  duration: 2.5,
  serviceId: 's1',
  serviceName: 'Картина маслом',
  minAge: '12',
  locationId: 'grand',
  occupied: 3,
  capacity: 8,
  isPrivate: false,
};

// ─── Client / Record / Visitor Mocks ───────────────────────────────────────────

export const mockClient = {
  id: 'c1',
  name: 'Анна Иванова',
  phone: '+7 (900) 123-45-67',
  email: null,
  channel: 'telegram',
  created_at: '2026-01-01T00:00:00',
  updated_at: '2026-01-01T00:00:00',
  is_active: true,
};

export const mockVisitor = {
  id: 'vis1',
  client_id: 'c1',
  name: 'Анна Иванова',
  age: 28,
  created_at: '2026-01-01T00:00:00',
  updated_at: '2026-01-01T00:00:00',
  is_active: true,
};

export const mockRecord = {
  id: 'r1',
  activity_id: 'ev_1',
  client_id: 'c1',
  status: 'confirmed' as const,
  seats: 1,
  comment: null,
  created_at: '2026-05-10T10:00:00',
  updated_at: '2026-05-10T10:00:00',
  is_active: true,
  visits: [
    {
      id: 'v1',
      record_id: 'r1',
      visitor_id: 'vis1',
      price: 3500,
      status: 'visited' as const,
      created_at: '2026-05-10T10:00:00',
      updated_at: '2026-05-10T10:00:00',
      is_active: true,
    },
  ],
};

export const mockPayment = {
  id: 'p1',
  record_id: 'r1',
  amount: 3500,
  method: 'card' as const,
  created_at: '2026-05-10T10:00:00',
  updated_at: '2026-05-10T10:00:00',
  is_active: true,
};

export const mockTariffs = [
  { id: 't1', service_id: 's1', title: 'Взрослый', price: 3500, description: null },
  { id: 't2', service_id: 's1', title: 'Детский', price: 2500, description: null },
];

// ─── Factory Functions ─────────────────────────────────────────────────────────

let counter = 0;

export function createMockActivity(overrides?: Partial<Activity>): Activity {
  counter++;
  return {
    ...mockActivity,
    id: `ev_test_${counter}`,
    ...overrides,
  };
}

export function createMockRecord(overrides?: Record<string, any>) {
  counter++;
  return {
    id: `r_test_${counter}`,
    activity_id: 'ev_1',
    client_id: 'c1',
    status: 'confirmed',
    seats: 1,
    comment: null,
    created_at: '2026-05-10T10:00:00',
    updated_at: '2026-05-10T10:00:00',
    is_active: true,
    visits: [],
    ...overrides,
  };
}

export function createMockClient(overrides?: Record<string, any>) {
  counter++;
  return {
    id: `c_test_${counter}`,
    name: `Test Client ${counter}`,
    phone: `+7999${String(counter).padStart(7, '0')}`,
    email: null,
    channel: 'telegram',
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
    is_active: true,
    ...overrides,
  };
}
