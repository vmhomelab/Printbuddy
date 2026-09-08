/**
 * Tests for AddPrinterModal discovery subnet auto-detection.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '../utils';
import { PrintersPage } from '../../pages/PrintersPage';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';

const mockPrinters = [
  {
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
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
];

const mockPrinterStatus = {
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

describe('AddPrinterModal Discovery', () => {
  beforeEach(() => {
    server.use(
      http.get('/api/v1/printers/', () => {
        return HttpResponse.json(mockPrinters);
      }),
      http.get('/api/v1/printers/:id/status', () => {
        return HttpResponse.json(mockPrinterStatus);
      }),
      http.get('/api/v1/queue/', () => {
        return HttpResponse.json([]);
      })
    );
  });

  it('auto-populates subnet from discovery info in Docker mode', async () => {
    server.use(
      http.get('/api/v1/discovery/info', () => {
        return HttpResponse.json({
          is_docker: true,
          ssdp_running: false,
          scan_running: false,
          subnets: ['10.0.0.0/24'],
        });
      })
    );

    render(<PrintersPage />);

    // Wait for printer page to load
    await waitFor(() => {
      expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
    });

    // Click the Add Printer button
    const addButton = screen.getByText(/add printer/i);
    await userEvent.click(addButton);

    // Wait for the modal and discovery info to load
    await waitFor(() => {
      // Should show subnet dropdown with detected subnet
      const subnetSelect = screen.getByDisplayValue('10.0.0.0/24');
      expect(subnetSelect).toBeInTheDocument();
    });
  });

  it('shows dropdown when multiple subnets detected in Docker mode', async () => {
    server.use(
      http.get('/api/v1/discovery/info', () => {
        return HttpResponse.json({
          is_docker: true,
          ssdp_running: false,
          scan_running: false,
          subnets: ['192.168.1.0/24', '10.0.0.0/24'],
        });
      })
    );

    render(<PrintersPage />);

    await waitFor(() => {
      expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
    });

    const addButton = screen.getByText(/add printer/i);
    await userEvent.click(addButton);

    await waitFor(() => {
      // Should show a select element (dropdown) with both subnets + Custom
      const selectElement = screen.getByDisplayValue('192.168.1.0/24');
      expect(selectElement.tagName).toBe('SELECT');

      const options = selectElement.querySelectorAll('option');
      expect(options).toHaveLength(3);
      expect(options[0].textContent).toBe('192.168.1.0/24');
      expect(options[1].textContent).toBe('10.0.0.0/24');
      expect(options[2].textContent).toMatch(/custom cidr/i);
    });
  });

  it('allows entering a custom CIDR when subnets are detected', async () => {
    server.use(
      http.get('/api/v1/discovery/info', () => {
        return HttpResponse.json({
          is_docker: true,
          ssdp_running: false,
          scan_running: false,
          subnets: ['10.2.0.0/24'],
        });
      })
    );

    render(<PrintersPage />);

    await waitFor(() => {
      expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText(/add printer/i));

    await waitFor(() => {
      expect(screen.getByDisplayValue('10.2.0.0/24')).toBeInTheDocument();
    });

    await userEvent.selectOptions(screen.getByDisplayValue('10.2.0.0/24'), '__custom__');

    const textInput = await screen.findByPlaceholderText('192.168.1.0/24');
    expect(textInput.tagName).toBe('INPUT');
    await userEvent.type(textInput, '10.0.0.0/24');
    expect(textInput).toHaveValue('10.0.0.0/24');
  });

  it('shows text input when no subnets detected in Docker mode', async () => {
    server.use(
      http.get('/api/v1/discovery/info', () => {
        return HttpResponse.json({
          is_docker: true,
          ssdp_running: false,
          scan_running: false,
          subnets: [],
        });
      })
    );

    render(<PrintersPage />);

    await waitFor(() => {
      expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
    });

    const addButton = screen.getByText(/add printer/i);
    await userEvent.click(addButton);

    await waitFor(() => {
      // Should show a text input with placeholder
      const textInput = screen.getByPlaceholderText('192.168.1.0/24');
      expect(textInput).toBeInTheDocument();
      expect(textInput.tagName).toBe('INPUT');
    });
  });

  it('does not show subnet field in non-Docker mode', async () => {
    server.use(
      http.get('/api/v1/discovery/info', () => {
        return HttpResponse.json({
          is_docker: false,
          ssdp_running: false,
          scan_running: false,
          subnets: ['192.168.1.0/24'],
        });
      })
    );

    render(<PrintersPage />);

    await waitFor(() => {
      expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
    });

    const addButton = screen.getByText(/add printer/i);
    await userEvent.click(addButton);

    await waitFor(() => {
      // Should show the discover button but NOT the subnet field
      expect(screen.getByText(/discover printers/i)).toBeInTheDocument();
    });

    // Subnet field should not exist
    expect(screen.queryByPlaceholderText('192.168.1.0/24')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('192.168.1.0/24')).not.toBeInTheDocument();
  });

  it('shows Moonraker subnet scan UI when Fluidd is selected', async () => {
    server.use(
      http.get('/api/v1/discovery/info', () => {
        return HttpResponse.json({
          is_docker: true,
          ssdp_running: false,
          scan_running: false,
          moonraker_scan_running: false,
          subnets: ['10.2.0.0/24', '10.0.0.0/24'],
        });
      })
    );

    render(<PrintersPage />);

    await waitFor(() => {
      expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText(/add printer/i));

    await waitFor(() => {
      expect(screen.getByLabelText(/printer type/i)).toBeInTheDocument();
    });

    await userEvent.selectOptions(screen.getByLabelText(/printer type/i), 'fluidd');

    await waitFor(() => {
      expect(screen.getByText(/scan subnet for moonraker/i)).toBeInTheDocument();
      expect(screen.getByDisplayValue('10.2.0.0/24')).toBeInTheDocument();
    });
  });

  it('prefills Moonraker IP and API URL from scan result', async () => {
    server.use(
      http.get('/api/v1/discovery/info', () => {
        return HttpResponse.json({
          is_docker: true,
          ssdp_running: false,
          scan_running: false,
          moonraker_scan_running: false,
          subnets: ['10.0.0.0/24'],
        });
      }),
      http.post('/api/v1/discovery/moonraker/scan', () => {
        return HttpResponse.json({ running: true, scanned: 0, total: 1 });
      }),
      http.get('/api/v1/discovery/moonraker/scan/status', () => {
        return HttpResponse.json({ running: false, scanned: 1, total: 1 });
      }),
      http.get('/api/v1/discovery/moonraker/printers', () => {
        return HttpResponse.json([
          {
            serial: 'KLIPPER-10-0-0-42',
            name: 'voron',
            ip_address: '10.0.0.42',
            api_url: 'http://10.0.0.42:7125',
            needs_auth: false,
            model: null,
            discovered_at: '2026-08-05T00:00:00Z',
          },
        ]);
      }),
      http.post('/api/v1/discovery/moonraker/scan/stop', () => {
        return HttpResponse.json({ running: false, scanned: 1, total: 1 });
      }),
    );

    render(<PrintersPage />);

    await waitFor(() => {
      expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText(/add printer/i));
    await userEvent.selectOptions(screen.getByLabelText(/printer type/i), 'klipper');

    await waitFor(() => {
      expect(screen.getByText(/scan subnet for moonraker/i)).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText(/scan subnet for moonraker/i));

    await waitFor(() => {
      expect(screen.getByText('voron')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('voron'));

    await waitFor(() => {
      expect(screen.getByDisplayValue('10.0.0.42')).toBeInTheDocument();
      expect(screen.getByDisplayValue('http://10.0.0.42:7125')).toBeInTheDocument();
      expect(screen.getByDisplayValue('voron')).toBeInTheDocument();
    });
  });
});
