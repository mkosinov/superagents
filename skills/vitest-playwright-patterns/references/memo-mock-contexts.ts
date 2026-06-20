/**
 * memo-mock-contexts.ts — Factory functions for mocking React contexts.
 *
 * Place at: frontend/admin/__tests__/helpers/mockContexts.ts
 *
 * Use these in beforeEach() to set up context mocks consistently.
 * Each factory returns a complete context value with vi.fn() for all callbacks.
 * Override specific values with the overrides parameter.
 */

import { vi } from 'vitest';
import { mockArtists, mockServices, mockLocations } from './mockData';

// ─── ScheduleContext Mock ──────────────────────────────────────────────────────

export function createMockScheduleContext(overrides?: Record<string, any>) {
  return {
    artists: mockArtists,
    services: mockServices,
    locations: mockLocations,
    activities: [],
    scheduleIndex: {
      byId: new Map(),
      byDate: new Map(),
      byMasterId: new Map(),
      byLocation: { all: { byDate: new Map(), byServiceId: new Map() } },
    },
    currentWeek: new Date(),
    stamp: { masterId: null, serviceId: null, locations: new Set(), ready: false },
    setCurrentWeek: vi.fn(),
    addActivity: vi.fn(),
    updateActivity: vi.fn(),
    deleteActivity: vi.fn(),
    setStamp: vi.fn(),
    copyLastWeek: vi.fn(),
    loading: false,
    error: null,
    filterMasterId: null,
    filterLocationId: null,
    setFilterMasterId: vi.fn(),
    setFilterLocationId: vi.fn(),
    ...overrides,
  };
}

// ─── RecordsContext Mock ───────────────────────────────────────────────────────

export function createMockRecordsContext(overrides?: Record<string, any>) {
  return {
    records: [],
    clients: new Map(),
    payments: new Map(),
    activities: new Map(),
    masters: new Map(),
    services: new Map(),
    locations: new Map(),
    loading: false,
    error: null,
    ...overrides,
  };
}

// ─── UIContext Mock ─────────────────────────────────────────────────────────────

export function createMockUIContext(overrides?: Record<string, any>) {
  return {
    deleteMode: false,
    toggleDeleteMode: vi.fn(),
    toasts: [],
    showToast: vi.fn(),
    hideToast: vi.fn(),
    sidebarCollapsed: false,
    toggleSidebar: vi.fn(),
    rightPanelCollapsed: true,
    toggleRightPanel: vi.fn(),
    theme: 'light' as const,
    toggleTheme: vi.fn(),
    ...overrides,
  };
}

// ─── Usage Example ─────────────────────────────────────────────────────────────
//
// import { createMockScheduleContext, createMockRecordsContext, createMockUIContext }
//   from './helpers/mockContexts';
//
// vi.mock('@/contexts/ScheduleContext', () => ({ useSchedule: vi.fn() }));
// vi.mock('@/contexts/RecordsContext', () => ({ useRecords: vi.fn() }));
// vi.mock('@/contexts/UIContext', () => ({ useUI: vi.fn() }));
//
// import { useSchedule } from '@/contexts/ScheduleContext';
// import { useRecords } from '@/contexts/RecordsContext';
// import { useUI } from '@/contexts/UIContext';
//
// const mockUseSchedule = vi.mocked(useSchedule);
// const mockUseRecords = vi.mocked(useRecords);
// const mockUseUI = vi.mocked(useUI);
//
// beforeEach(() => {
//   mockUseSchedule.mockReturnValue(createMockScheduleContext());
//   mockUseRecords.mockReturnValue(createMockRecordsContext());
//   mockUseUI.mockReturnValue(createMockUIContext());
// });
//
// // Override specific values:
// it('shows loading state', () => {
//   mockUseSchedule.mockReturnValue(
//     createMockScheduleContext({ loading: true })
//   );
//   render(<MyComponent />);
//   expect(screen.getByText('Загрузка...')).toBeInTheDocument();
// });
