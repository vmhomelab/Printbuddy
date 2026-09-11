/**
 * Tests for the Edit-Printer setup-time pre-flight.
 *
 * Editing a printer runs the same connection diagnostic on save as the
 * Add-Printer dialog, and warns (rather than blocks) when a check fails.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '../utils';
import { PrintersPage } from '../../pages/PrintersPage';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';

const mockPrinter = {
  id: 1,
  name: 'X1 Carbon',
  ip_address: '192.168.1.100',
  serial_number: '00M09A350100001',
  access_code: '12345678',
  model: 'X1C',
  enabled: true,
  nozzle_diameter: 0.4,
  nozzle_type: 'hardened_steel',
  location: null,
  auto_archive: true,
  reconnect_interval_seconds: 30,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

const mockPrusaPrinter = {
  ...mockPrinter,
  id: 2,
  name: 'Prusa Mock Server',
  ip_address: '10.17.1.96',
  serial_number: 'PRUSALINK-10-17-1-96',
  access_code: '',
  auth_token: null,
  provider: 'prusalink',
  api_url: 'http://10.17.1.96:8087',
  provider_options: JSON.stringify({ prusalink_api_mode: 'modern', prusalink_auth_mode: 'digest' }),
  model: 'MK4S',
};

const mockStatus = {
  connected: true,
  state: 'IDLE',
  progress: 0,
  layer_num: 0,
  total_layers: 0,
  temperatures: { nozzle: 25, bed: 25, chamber: 25 },
  remaining_time: 0,
  filename: null,
  wifi_signal: -50,
  vt_tray: [],
};

async function openEditModal() {
  render(<PrintersPage />);
  await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

  // Open the per-printer actions menu (kebab button), then click Edit.
  const menuBtn = [...document.querySelectorAll('button')].find((b) =>
    b.querySelector('.lucide-ellipsis-vertical'),
  )!;
  await userEvent.click(menuBtn);
  await userEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
  await screen.findByText('Edit Printer');
}

describe('EditPrinterModal pre-flight', () => {
  beforeEach(() => {
    server.use(
      http.get('/api/v1/printers/', () => HttpResponse.json([mockPrinter])),
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json(mockStatus)),
      http.get('/api/v1/queue/', () => HttpResponse.json([])),
    );
  });

  it('warns instead of saving when a connection check fails', async () => {
    server.use(
      http.post('/api/v1/printers/diagnostic', () =>
        HttpResponse.json({
          printer_id: null,
          ip_address: '192.168.1.100',
          overall: 'problems',
          checks: [{ id: 'developer_mode', status: 'fail', params: {} }],
        }),
      ),
    );

    await openEditModal();
    await userEvent.click(screen.getByRole('button', { name: /save changes/i }));

    expect(await screen.findByText(/Some connection checks failed/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save anyway/i })).toBeInTheDocument();
  });

  it('saves directly when all connection checks pass', async () => {
    let updated = false;
    server.use(
      http.post('/api/v1/printers/diagnostic', () =>
        HttpResponse.json({
          printer_id: null,
          ip_address: '192.168.1.100',
          overall: 'ok',
          checks: [{ id: 'developer_mode', status: 'pass', params: {} }],
        }),
      ),
      http.patch('/api/v1/printers/:id', async () => {
        updated = true;
        return HttpResponse.json({ ...mockPrinter, name: 'X1 Carbon' });
      }),
    );

    await openEditModal();
    await userEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(updated).toBe(true));
    expect(screen.queryByText(/Some connection checks failed/i)).not.toBeInTheDocument();
  });

  it('lets PrusaLink printers update secret and auth mode without Bambu access-code wording', async () => {
    let updatePayload: Record<string, unknown> | null = null;
    server.use(
      http.get('/api/v1/printers/', () => HttpResponse.json([mockPrusaPrinter])),
      http.patch('/api/v1/printers/:id', async ({ request }) => {
        updatePayload = await request.json() as Record<string, unknown>;
        return HttpResponse.json({ ...mockPrusaPrinter, ...updatePayload });
      }),
    );

    render(<PrintersPage />);
    await waitFor(() => expect(screen.getByText('Prusa Mock Server')).toBeInTheDocument());

    const menuBtn = [...document.querySelectorAll('button')].find((b) =>
      b.querySelector('.lucide-ellipsis-vertical'),
    )!;
    await userEvent.click(menuBtn);
    await userEvent.click(await screen.findByRole('button', { name: /^edit$/i }));

    expect(await screen.findByText('PrusaLink password / API key')).toBeInTheDocument();
    expect(screen.queryByText(/^Access Code$/)).not.toBeInTheDocument();
    expect(screen.getByText('PrusaLink API / authentication mode')).toBeInTheDocument();
    const reconnectInterval = screen.getByLabelText('Offline reconnect interval (seconds)') as HTMLInputElement;
    expect(reconnectInterval.value).toBe('30');
    await userEvent.clear(reconnectInterval);
    await userEvent.type(reconnectInterval, '90');

    await userEvent.type(screen.getByLabelText('PrusaLink password / API key'), 'new-secret');
    await userEvent.selectOptions(
      screen.getByLabelText('PrusaLink API / authentication mode'),
      'legacy_x_api_key',
    );
    await userEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(updatePayload).not.toBeNull());
    expect(updatePayload?.auth_token).toBe('new-secret');
    expect((updatePayload as unknown as Record<string, unknown>).reconnect_interval_seconds).toBe(90);
    expect(updatePayload?.access_code).toBeUndefined();
    expect(JSON.parse(updatePayload?.provider_options as string)).toEqual({
      prusalink_api_mode: 'legacy',
      prusalink_auth_mode: 'x_api_key',
    });
  });
});
