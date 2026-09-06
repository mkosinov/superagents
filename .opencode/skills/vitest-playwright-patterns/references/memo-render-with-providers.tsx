/**
 * memo-render-with-providers.tsx — Custom render that wraps component in providers.
 *
 * Place at: frontend/admin/__tests__/helpers/renderWithProviders.tsx
 *
 * Use for integration-style unit tests where you want real context behavior.
 * For most unit tests, prefer mocking contexts directly (see mockContexts.ts).
 * Use this when testing component interactions with real providers.
 */

import { render, type RenderOptions } from '@testing-library/react';
import React, { type ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

interface ProviderOptions extends Omit<RenderOptions, 'wrapper'> {
  queryClient?: QueryClient;
}

/**
 * Render a component wrapped in necessary providers (QueryClient, etc.).
 *
 * Usage:
 *   const { queryClient } = renderWithProviders(<MyComponent />);
 *
 *   // With custom QueryClient:
 *   const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
 *   renderWithProviders(<MyComponent />, { queryClient: qc });
 */
export function renderWithProviders(
  ui: ReactElement,
  options?: ProviderOptions,
) {
  const queryClient = options?.queryClient ?? new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...options }),
    queryClient,
  };
}

// ─── Usage Example ─────────────────────────────────────────────────────────────
//
// import { renderWithProviders } from './helpers/renderWithProviders';
// import { screen, fireEvent } from '@testing-library/react';
//
// describe('MyComponent with real providers', () => {
//   it('renders without crashing', () => {
//     renderWithProviders(<MyComponent activity={mockActivity} />);
//     expect(screen.getByRole('dialog')).toBeInTheDocument();
//   });
//
//   it('invalidates queries on mutation', async () => {
//     const { queryClient } = renderWithProviders(<MyComponent />);
//     // ... trigger mutation ...
//     // queryClient.invalidateQueries will be called by the real useMutation
//   });
// });
