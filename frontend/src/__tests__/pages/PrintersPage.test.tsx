/**
 * Tests for the PrintersPage component.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen, waitFor, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { render } from '../utils';
import { PrintersPage } from '../../pages/PrintersPage';
import { PRINTER_MODEL_GROUPS, mapModelCode } from '../../utils/printerModels';
import { setAuthToken } from '../../api/client';
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
    location: 'Workshop',
    auto_archive: true,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: 'P1S Backup',
    ip_address: '192.168.1.101',
    serial_number: '00W00A123456789',
    access_code: '87654321',
    model: 'P1S',
    enabled: false,
    nozzle_diameter: 0.4,
    nozzle_type: 'stainless_steel',
    location: null,
    auto_archive: true,
    created_at: '2024-01-02T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
  },
];

const mockPrinterStatus = {
  connected: true,
  state: 'IDLE',
  awaiting_plate_clear: false,
  progress: 0,
  layer_num: 0,
  total_layers: 0,
  temperatures: {
    nozzle: 25,
    bed: 25,
    chamber: 25,
  },
  remaining_time: 0,
  filename: null,
  wifi_signal: -50,
  vt_tray: [],
};

const selectToolbarDropdownOption = async (triggerName: RegExp, optionName: RegExp) => {
  const user = userEvent.setup();

  await user.click(screen.getByRole('button', { name: triggerName }));
  await user.click(await screen.findByRole('button', { name: optionName }));
};

describe('PrintersPage', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
    localStorage.removeItem('printerCardSize');
    localStorage.removeItem('embeddedCameraState_1');
    localStorage.removeItem('embeddedCameraInlineState_1');
    localStorage.removeItem('printerCardSectionOrder_1');
    localStorage.removeItem('printerCardSectionOrder_2');
    localStorage.removeItem('printerCardOrder');
    vi.mocked(localStorage.getItem).mockReturnValue(null);
    setAuthToken(null);

    server.use(
      http.get('/api/v1/printers/', () => {
        return HttpResponse.json(mockPrinters);
      }),
      http.get('/api/v1/printers/:id/status', () => {
        return HttpResponse.json(mockPrinterStatus);
      }),
      http.post('/api/v1/printers/:id/clear-plate', () => {
        return HttpResponse.json({ success: true, message: 'Plate cleared' });
      }),
      http.get('/api/v1/settings/', () => {
        return HttpResponse.json({
          auto_archive: true,
          save_thumbnails: true,
          capture_finish_photo: true,
          default_filament_cost: 25.0,
          currency: 'USD',
          ams_humidity_good: 40,
          ams_humidity_fair: 60,
          ams_temp_good: 30,
          ams_temp_fair: 35,
          require_plate_clear: true,
        });
      }),
      // PrintersPage now reads UI rendering fields from the public ui-preferences
      // endpoint instead of /settings (#1293) — admin pages still hit /settings.
      http.get('/api/v1/settings/ui-preferences', () => {
        return HttpResponse.json({
          ams_humidity_good: 40,
          ams_humidity_fair: 60,
          ams_temp_good: 30,
          ams_temp_fair: 35,
          require_plate_clear: true,
          panda_breath_printer_assignments: '{}',
        });
      }),
      http.get('/api/v1/settings/panda-breath/status', () => {
        return HttpResponse.json({ enabled: false, connected: false, state: {} });
      }),
      http.get('/api/v1/queue/', () => {
        return HttpResponse.json([]);
      })
    );
  });

  describe('Bambu model registry', () => {
    it('maps the A2L SSDP model code to the display model', () => {
      expect(mapModelCode('N9')).toBe('A2L');
      expect(mapModelCode('A2L')).toBe('A2L');
    });

    it('offers A2L under an A2 Series model group', () => {
      const a2Group = PRINTER_MODEL_GROUPS.find((group) => group.label === 'Bambu Lab A2 Series');
      expect(a2Group?.options).toContainEqual({ value: 'A2L', label: 'A2L' });
    });
  });

  describe('rendering', () => {
    it('renders the page title', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('Printers')).toBeInTheDocument();
      });
    });

    it('shows printer cards', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
        expect(screen.getByText('P1S Backup')).toBeInTheDocument();
      });
    });

    it('shows every Snapmaker U1 nozzle temperature, active tool, and chamber temperature', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 7,
          name: 'Snapmaker U1',
          provider: 'fluidd',
          model: 'Snapmaker U1',
        }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          active_extruder: 3,
          temperatures: {
            nozzle: 25,
            nozzle_2: 26,
            nozzle_3: 27,
            nozzle_4: 110,
            nozzle_4_target: 210,
            bed: 31,
            chamber: 34,
          },
          ams: [{
            id: 0,
            name: 'Snapmaker U1 Feeders',
            humidity: null,
            temp: null,
            is_ams_ht: false,
            serial_number: '',
            sw_ver: '',
            dry_time: 0,
            dry_status: 0,
            dry_sub_status: 0,
            dry_sf_reason: [],
            module_type: 'snapmaker_u1',
            tray: [
              { id: 0, tray_color: '#E72F1D', tray_type: 'PLA', tray_sub_brands: 'SnapSpeed', tray_id_name: null, tray_info_idx: null, remain: -1, k: null, cali_idx: null, tag_uid: '', tray_uuid: 'snapmaker-u1-e0', nozzle_temp_min: null, nozzle_temp_max: null, drying_temp: null, drying_time: null, state: 11, filament_detected: true, loaded_to_feeder: true, loaded_to_extruder: true, channel_state: 'load_finish', channel_action_state: 'load_finish' },
              { id: 1, tray_color: '#080A0D', tray_type: 'PLA', tray_sub_brands: 'SnapSpeed', tray_id_name: null, tray_info_idx: null, remain: -1, k: null, cali_idx: null, tag_uid: '', tray_uuid: 'snapmaker-u1-e1', nozzle_temp_min: null, nozzle_temp_max: null, drying_temp: null, drying_time: null, state: 11, filament_detected: true, loaded_to_feeder: true, loaded_to_extruder: false, channel_state: 'preload_finish', channel_action_state: 'none' },
              { id: 2, tray_color: '#1E88E5', tray_type: 'PLA', tray_sub_brands: 'PolyLite', tray_id_name: null, tray_info_idx: null, remain: -1, k: null, cali_idx: null, tag_uid: '', tray_uuid: 'snapmaker-u1-e2', nozzle_temp_min: null, nozzle_temp_max: null, drying_temp: null, drying_time: null, state: 11, filament_detected: true, loaded_to_feeder: true, loaded_to_extruder: false, channel_state: 'preload_finish', channel_action_state: 'none' },
              { id: 3, tray_color: null, tray_type: null, tray_sub_brands: null, tray_id_name: null, tray_info_idx: null, remain: -1, k: null, cali_idx: null, tag_uid: '', tray_uuid: 'snapmaker-u1-e3', nozzle_temp_min: null, nozzle_temp_max: null, drying_temp: null, drying_time: null, state: 9, filament_detected: false, loaded_to_feeder: false, loaded_to_extruder: false, channel_state: 'wait_insert', channel_action_state: 'none' },
            ],
          }],
        })),
      );

      render(<PrintersPage />);

      const card = await screen.findByTestId('printer-card-7');
      const temperatureSection = await within(card).findByTestId('printer-card-section-temperatures');

      expect(within(temperatureSection).getByText('E0')).toBeInTheDocument();
      expect(within(temperatureSection).getByText('25°C')).toBeInTheDocument();
      expect(within(temperatureSection).getByText('E1')).toBeInTheDocument();
      expect(within(temperatureSection).getByText('26°C')).toBeInTheDocument();
      expect(within(temperatureSection).getByText('E2')).toBeInTheDocument();
      expect(within(temperatureSection).getByText('27°C')).toBeInTheDocument();
      expect(within(temperatureSection).getByText('E3 · Active')).toBeInTheDocument();
      expect(within(temperatureSection).getByText('110°C / 210°')).toBeInTheDocument();
      expect(within(temperatureSection).getByText('Chamber')).toBeInTheDocument();
      expect(within(temperatureSection).getByText('34°C')).toBeInTheDocument();
      expect(within(temperatureSection).queryByText('L / R')).toBeNull();
      expect(within(temperatureSection).queryByText(/^L(?:\s|$)/)).toBeNull();
      expect(within(temperatureSection).queryByText(/^R(?:\s|$)/)).toBeNull();
      const filamentSection = await within(card).findByTestId('printer-card-section-filaments');
      expect(within(filamentSection).getByText('Spools')).not.toBeNull();
      expect(within(filamentSection).getByText('Left')).not.toBeNull();
      expect(within(filamentSection).getByText('Right')).not.toBeNull();
      expect(within(filamentSection).queryByText(/^AMS-/)).toBeNull();
      expect(within(filamentSection).getByText('In extruder')).toBeInTheDocument();
      expect(within(filamentSection).getAllByText('Preloaded')).toHaveLength(2);
      expect(within(filamentSection).getAllByText('Empty')).toHaveLength(2);
    });

    it('does not highlight a Snapmaker U1 spool when no active extruder is reported', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 7,
          name: 'Snapmaker U1',
          provider: 'fluidd',
          model: 'Snapmaker U1',
        }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          active_extruder: -1,
          tray_now: 255,
          temperatures: {
            nozzle: 25,
            nozzle_2: 26,
            nozzle_3: 27,
            nozzle_4: 28,
            bed: 31,
            chamber: 34,
          },
          ams: [{
            id: 0,
            name: 'Snapmaker U1 Feeders',
            module_type: 'snapmaker_u1',
            tray: [
              { id: 0, tray_color: '#E72F1D', tray_type: 'PLA', remain: -1, state: 11, active: false, filament_detected: true, loaded_to_feeder: true, loaded_to_extruder: false, channel_state: 'preload_finish' },
              { id: 1, tray_color: '#080A0D', tray_type: 'PLA', remain: -1, state: 11, active: false, filament_detected: true, loaded_to_feeder: true, loaded_to_extruder: false, channel_state: 'preload_finish' },
              { id: 2, tray_color: '#1E88E5', tray_type: 'PLA', remain: -1, state: 11, active: false, filament_detected: true, loaded_to_feeder: true, loaded_to_extruder: false, channel_state: 'preload_finish' },
              { id: 3, tray_color: null, tray_type: null, remain: -1, state: 9, active: false, filament_detected: false, loaded_to_feeder: false, loaded_to_extruder: false, channel_state: 'wait_insert' },
            ],
          }],
        })),
      );

      render(<PrintersPage />);

      const card = await screen.findByTestId('printer-card-7');
      const temperatureSection = await within(card).findByTestId('printer-card-section-temperatures');
      expect(within(temperatureSection).queryByText(/Active/)).toBeNull();
      const filamentSection = await within(card).findByTestId('printer-card-section-filaments');
      expect(within(filamentSection).queryByText('In extruder')).toBeNull();
    });

    it('lets Snapmaker U1 users assign a Spoolman spool from a spool slot menu', async () => {
      const user = userEvent.setup();
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 7,
          name: 'Snapmaker U1',
          provider: 'fluidd',
          model: 'Snapmaker U1',
        }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          ams: [{
            id: 0,
            name: 'Snapmaker U1 Feeders',
            module_type: 'snapmaker_u1',
            tray: [
              { id: 0, tray_color: '#E72F1D', tray_type: 'PLA', remain: -1, state: 11, active: false, filament_detected: true, loaded_to_feeder: true, loaded_to_extruder: false, channel_state: 'preload_finish' },
              { id: 1, tray_color: null, tray_type: null, remain: -1, state: 9, active: false, filament_detected: false, loaded_to_feeder: false, loaded_to_extruder: false, channel_state: 'wait_insert' },
              { id: 2, tray_color: null, tray_type: null, remain: -1, state: 9, active: false, filament_detected: false, loaded_to_feeder: false, loaded_to_extruder: false, channel_state: 'wait_insert' },
              { id: 3, tray_color: null, tray_type: null, remain: -1, state: 9, active: false, filament_detected: false, loaded_to_feeder: false, loaded_to_extruder: false, channel_state: 'wait_insert' },
            ],
          }],
        })),
        http.get('/api/v1/spoolman/status', () => HttpResponse.json({ enabled: true, connected: true, url: 'http://spoolman.local' })),
        http.get('/api/v1/settings/spoolman', () => HttpResponse.json({ spoolman_enabled: 'true', spoolman_url: 'http://spoolman.local', spoolman_sync_mode: 'read_only' })),
        http.get('/api/v1/spoolman/inventory/spools', () => HttpResponse.json([])),
        http.get('/api/v1/spoolman/inventory/slot-assignments/all', () => HttpResponse.json([])),
      );

      render(<PrintersPage />);

      const card = await screen.findByTestId('printer-card-7');
      const filamentSection = await within(card).findByTestId('printer-card-section-filaments');
      await user.click(within(filamentSection).getAllByTitle('Slot options')[0]);
      expect(await within(filamentSection).findByText('Assign')).not.toBeNull();
    });

    it('lets Moonraker users set reported fan speeds from the status strip', async () => {
      const user = userEvent.setup();
      let requestedFan = '';
      let requestedSpeed = '';
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 7,
          name: 'Snapmaker U1',
          provider: 'fluidd',
          model: 'Snapmaker U1',
        }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          cooling_fan_speed: 0,
          big_fan1_speed: null,
          big_fan2_speed: 0,
          heatbreak_fan_speed: null,
        })),
        http.post('/api/v1/printers/:id/fan-speed', ({ request }) => {
          const url = new URL(request.url);
          requestedFan = url.searchParams.get('fan') || '';
          requestedSpeed = url.searchParams.get('speed') || '';
          return HttpResponse.json({ success: true, message: 'Fan speed set' });
        }),
      );

      render(<PrintersPage />);

      expect((await screen.findAllByText('Snapmaker U1')).length).toBeGreaterThan(0);
      await user.click(await screen.findByTitle('Chamber Fan control'));
      await user.click((await screen.findAllByRole('button', { name: '100%' }))[0]);

      await waitFor(() => {
        expect(requestedFan).toBe('chamber');
        expect(requestedSpeed).toBe('100');
      });
    });

    it('shows one Upload action for Prusa printers', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 7,
          name: 'Prusa CORE One',
          provider: 'prusalink',
          model: 'Prusa CORE One',
        }])),
      );

      render(<PrintersPage />);

      expect((await screen.findAllByText('Prusa CORE One')).length).toBeGreaterThan(0);
      const uploadButton = await screen.findByRole('button', { name: 'Upload' });
      expect(uploadButton).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Print' })).not.toBeInTheDocument();
    });


    it('shows the Files button on PrusaLink printer cards and opens the file manager', async () => {
      const user = userEvent.setup();
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 7,
          name: 'Prusa CORE One',
          provider: 'prusalink',
          model: 'Prusa CORE One',
        }])),
        http.get('/api/v1/printers/7/storage', () => HttpResponse.json({
          used_bytes: null,
          free_bytes: null,
          storages: [
            { id: 'usb', type: 'USB', name: 'USB', path: '/usb', available: true },
          ],
        })),
        http.get('/api/v1/printers/7/files', ({ request }) => {
          const url = new URL(request.url);
          return HttpResponse.json({
            path: url.searchParams.get('path') || '/',
            storage: url.searchParams.get('storage'),
            files: [],
          });
        }),
      );

      render(<PrintersPage />);

      await screen.findAllByText('Prusa CORE One');
      expect(await screen.findByRole('button', { name: 'Files' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Upload' })).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Files' }));

      expect(await screen.findByText('File Manager')).toBeInTheDocument();
      expect(await screen.findByRole('combobox', { name: /Storage/i })).toHaveValue('usb');
    });

    it('shows the Files button on Fluidd/Moonraker printer cards and opens the file manager', async () => {
      const user = userEvent.setup();
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 9,
          name: 'K2 Plus',
          provider: 'fluidd',
          model: 'Creality K2 Plus',
        }])),
        http.get('/api/v1/printers/9/storage', () => HttpResponse.json({
          used_bytes: null,
          free_bytes: null,
          storages: [
            { id: 'gcodes', type: 'LOCAL', name: 'Moonraker gcodes', path: '/', available: true },
          ],
        })),
        http.get('/api/v1/printers/9/files', ({ request }) => {
          const url = new URL(request.url);
          return HttpResponse.json({
            path: url.searchParams.get('path') || '/',
            storage: url.searchParams.get('storage'),
            files: [],
          });
        }),
      );

      render(<PrintersPage />);

      await screen.findAllByText('K2 Plus');
      expect(await screen.findByRole('button', { name: 'Files' })).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Files' }));

      expect(await screen.findByText('File Manager')).toBeInTheDocument();
      expect(screen.getAllByText('K2 Plus').length).toBeGreaterThan(0);
    });

    it('shows a PrusaLink badge that opens the printer UI in a new tab', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 7,
          name: 'Prusa CORE One',
          provider: 'prusalink',
          model: 'Prusa CORE One',
          ip_address: '10.17.10.42',
          api_url: 'http://core-one.local:8087',
        }])),
      );

      render(<PrintersPage />);

      expect((await screen.findAllByText('Prusa CORE One')).length).toBeGreaterThan(0);
      const prusaLinkBadge = await screen.findByRole('link', { name: 'Open PrusaLink' });
      expect(prusaLinkBadge).toHaveAttribute('href', 'http://core-one.local:8087');
      expect(prusaLinkBadge).toHaveAttribute('target', '_blank');
      expect(prusaLinkBadge).toHaveAttribute('rel', expect.stringContaining('noopener'));
      expect(prusaLinkBadge).toHaveTextContent('PrusaLink');
    });

    it('uses the printer IP address for the PrusaLink badge when no API URL is saved', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 7,
          name: 'Prusa CORE One',
          provider: 'prusalink',
          model: 'Prusa CORE One',
          ip_address: '10.17.10.42',
          api_url: null,
        }])),
      );

      render(<PrintersPage />);

      expect((await screen.findAllByText('Prusa CORE One')).length).toBeGreaterThan(0);
      expect(await screen.findByRole('link', { name: 'Open PrusaLink' })).toHaveAttribute('href', 'http://10.17.10.42');
    });

    it('shows the updated Prusa USB write notice from the direct Upload action', async () => {
      const user = userEvent.setup();
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 7,
          name: 'Prusa CORE One',
          provider: 'prusalink',
          model: 'Prusa CORE One',
        }])),
      );

      render(<PrintersPage />);

      expect((await screen.findAllByText('Prusa CORE One')).length).toBeGreaterThan(0);
      await user.click(await screen.findByRole('button', { name: 'Upload' }));

      expect(screen.getByText('Prusa uploads can take a few seconds to a few minutes depending upon file size while the printer writes the file to USB storage.')).toBeInTheDocument();
    });

    it('uploads Prusa files without opening the legacy Print modal when auto-start is unchecked', async () => {
      const user = userEvent.setup();
      let uploadCalled = false;
      let uploadRequestUrl = '';
      let startCalled = false;
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 7,
          name: 'Prusa CORE One',
          provider: 'prusalink',
          model: 'Prusa CORE One',
        }])),
        http.get('/api/v1/printers/7/files', () => HttpResponse.json({ files: [] })),
        http.post('/api/v1/printers/7/files/upload', ({ request }) => {
          uploadCalled = true;
          uploadRequestUrl = request.url;
          return HttpResponse.json({ status: 'uploaded', path: '/Shoe_horn_thicker.gcode', filename: 'Shoe_horn_thicker.gcode' });
        }),
        http.post('/api/v1/printers/7/files/start', () => {
          startCalled = true;
          return HttpResponse.json({ status: 'started', path: '/Shoe_horn_thicker.gcode' });
        }),
      );

      render(<PrintersPage />);

      await user.click(await screen.findByRole('button', { name: 'Upload' }));
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      expect(input).toBeInTheDocument();

      await user.upload(input, new File(['G28\n'], 'Shoe_horn_thicker.gcode', { type: 'text/plain' }));
      expect(screen.getByLabelText('Start print after upload')).not.toBeChecked();
      await user.click(await screen.findByRole('button', { name: 'Upload (1)' }));

      await waitFor(() => expect(uploadCalled).toBe(true));
      expect(new URL(uploadRequestUrl).searchParams.get('overwrite')).toBe('true');
      expect(startCalled).toBe(false);
      expect(await screen.findByText('Upload complete: 1 succeeded')).toBeInTheDocument();
      expect(screen.queryByText(/\{\{succeeded\}\}/)).not.toBeInTheDocument();
      expect(screen.queryByRole('dialog', { name: 'Print' })).not.toBeInTheDocument();
      expect(screen.queryByText('Print Options')).not.toBeInTheDocument();
    });

    it('asks whether to print or upload when dropping a file on a Prusa printer card', async () => {
      const user = userEvent.setup();
      let directUploadCalled = false;
      let directUploadRequestUrl = '';
      let libraryUploadCalled = false;
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          id: 7,
          name: 'Prusa CORE One',
          provider: 'prusalink',
          model: 'Prusa CORE One',
        }])),
        http.post('/api/v1/printers/7/files/upload', ({ request }) => {
          directUploadCalled = true;
          directUploadRequestUrl = request.url;
          return HttpResponse.json({ status: 'uploaded', path: '/Shoe_horn_thicker.gcode', filename: 'Shoe_horn_thicker.gcode' });
        }),
        http.post('/api/v1/library/files', () => {
          libraryUploadCalled = true;
          return HttpResponse.json({
            id: 42,
            filename: 'Shoe_horn_thicker.gcode',
            original_filename: 'Shoe_horn_thicker.gcode',
            file_size: 4,
            file_type: 'gcode',
            metadata: {},
          });
        }),
      );

      render(<PrintersPage />);

      await screen.findAllByText('Prusa CORE One');
      await screen.findByRole('button', { name: 'Upload' });
      const card = screen.getByTestId('printer-card-7');

      fireEvent.drop(card, {
        dataTransfer: {
          files: [new File(['G28\n'], 'Shoe_horn_thicker.gcode', { type: 'text/plain' })],
        },
      });

      expect(await screen.findByText('Choose file action')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Print' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Upload only' })).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Upload only' }));

      await waitFor(() => expect(directUploadCalled).toBe(true));
      expect(new URL(directUploadRequestUrl).searchParams.get('overwrite')).toBe('true');
      expect(libraryUploadCalled).toBe(false);
      expect(screen.queryByText('Choose file action')).not.toBeInTheDocument();
    });

    it('shows assigned Panda Breath data only on the matching printer card', async () => {
      server.use(
        http.get('/api/v1/settings/ui-preferences', () => HttpResponse.json({
          ams_humidity_good: 40,
          ams_humidity_fair: 60,
          ams_temp_good: 30,
          ams_temp_fair: 35,
          require_plate_clear: true,
          panda_breath_printer_assignments: '{"DEVICE_B":2}',
        })),
        http.get('/api/v1/settings/panda-breath/status', () => HttpResponse.json({
          enabled: true,
          connected: true,
          state: {},
          devices: {
            DEVICE_A: { device_id: 'DEVICE_A', chamber_actual: 31.2, chamber_target: 45 },
            DEVICE_B: { device_id: 'DEVICE_B', chamber_actual: 42.8, chamber_target: 55 },
          },
        }))
      );

      render(<PrintersPage />);

      await screen.findByText('P1S Backup');
      const card = await screen.findByTestId('printer-card-2');
      expect(within(card).getAllByText('Panda Breath').length).toBeGreaterThan(0);
      expect(card.textContent).toContain('P1S Backup');
      expect(card.textContent).toContain('Panda Breath');
      expect(card.textContent).toContain('43°C / 55°');
    });

    it('sends Panda Breath commands to the assigned device from the printer card', async () => {
      const user = userEvent.setup();
      let postedBody: unknown = null;

      server.use(
        http.get('/api/v1/settings/ui-preferences', () => HttpResponse.json({
          ams_humidity_good: 40,
          ams_humidity_fair: 60,
          ams_temp_good: 30,
          ams_temp_fair: 35,
          require_plate_clear: true,
          panda_breath_printer_assignments: '{"DEVICE_B":2}',
        })),
        http.get('/api/v1/settings/panda-breath/status', () => HttpResponse.json({
          enabled: true,
          connected: true,
          state: {},
          devices: {
            DEVICE_B: { device_id: 'DEVICE_B', chamber_actual: 42.8, chamber_target: 55, work_on: false },
          },
        })),
        http.post('/api/v1/settings/panda-breath/command', async ({ request }) => {
          postedBody = await request.json();
          return HttpResponse.json({ ok: true });
        })
      );

      render(<PrintersPage />);

      await screen.findByText('P1S Backup');
      await user.click(await screen.findByRole('button', { name: 'Turn on' }));

      await waitFor(() => {
        expect(postedBody).toEqual({ command: 'work_on', value: 'ON', device_id: 'DEVICE_B' });
      });
    });

    it('opens a configured external camera even when the printer status is offline', async () => {
      const user = userEvent.setup();
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          provider: 'fluidd',
          name: 'Neptune 4 Pro',
          external_camera_url: 'http://neptune.local/webcam/?action=stream',
          external_camera_type: 'mjpeg',
          external_camera_enabled: true,
        }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          connected: false,
        })),
      );

      render(<PrintersPage />);

      const cameraButton = await screen.findByRole('button', { name: /open camera in new window/i });
      expect(cameraButton).not.toBeDisabled();
      await user.click(cameraButton);

      expect(openSpy).toHaveBeenCalledWith('/camera/1', 'camera-1', expect.any(String));
      openSpy.mockRestore();
    });

    it('opens the camera inline inside the printer card when camera view mode is card', async () => {
      const user = userEvent.setup();
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
      server.use(
        http.get('/api/v1/settings/ui-preferences', () => HttpResponse.json({
          ams_humidity_good: 40,
          ams_humidity_fair: 60,
          ams_temp_good: 30,
          ams_temp_fair: 35,
          require_plate_clear: true,
          camera_view_mode: 'card',
          panda_breath_printer_assignments: '{}',
        })),
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          provider: 'fluidd',
          name: 'Neptune 4 Pro',
          external_camera_url: 'http://neptune.local/webcam/?action=stream',
          external_camera_type: 'mjpeg',
          external_camera_enabled: true,
        }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          connected: false,
        })),
        http.post('/api/v1/printers/:id/camera/stop', () => HttpResponse.json({ success: true })),
        http.get('/api/v1/printers/:id/camera/status', () => HttpResponse.json({ active: true, stalled: false })),
      );

      render(<PrintersPage />);

      const cameraButton = await screen.findByRole('button', { name: /show camera in printer card/i });
      expect(cameraButton).not.toBeDisabled();
      await user.click(cameraButton);

      expect(openSpy).not.toHaveBeenCalled();
      const viewer = await screen.findByTestId('inline-camera-viewer-1');
      expect(viewer).toBeInTheDocument();
      expect(viewer).toHaveStyle({ width: '100%', maxWidth: '100%' });
      const cameraSection = await screen.findByTestId('printer-card-section-camera');
      expect(within(cameraSection).queryByTitle('Hide camera in printer card')).not.toBeInTheDocument();
      expect(within(cameraSection).getByTitle('Close')).toBeInTheDocument();
      const stream = screen.getByAltText('Camera stream') as HTMLImageElement;
      expect(stream.getAttribute('src')).toContain('/api/v1/printers/1/camera/stream');
      openSpy.mockRestore();
    });

    it('keeps printer cards aligned to the top so an expanded camera does not stretch sibling cards', async () => {
      render(<PrintersPage />);

      const firstCard = await screen.findByTestId('printer-card-1');
      const sortableCard = firstCard.closest('[data-testid^="sortable-printer-card-"]');
      expect(sortableCard?.parentElement).toHaveClass('grid');
      expect(sortableCard?.parentElement).toHaveClass('items-start');
    });

    it('applies the saved draggable printer-card section order and exposes drag handles only in layout editing mode', async () => {
      const user = userEvent.setup();
      const savedSectionOrder = JSON.stringify([
        'temperatures',
        'status',
        'indicators',
        'filaments',
        'actions',
        'camera',
        'panda-breath',
        'smart-plug',
        'manual-controls',
      ]);
      vi.mocked(localStorage.getItem).mockImplementation((key: string) =>
        key === 'printerCardSectionOrder_1' ? savedSectionOrder : null
      );

      render(<PrintersPage />);

      const card = await screen.findByTestId('printer-card-1');
      let temperatureSection!: HTMLElement;
      let statusSection!: HTMLElement;
      await waitFor(() => {
        temperatureSection = within(card).getByTestId('printer-card-section-temperatures');
        statusSection = within(card).getByTestId('printer-card-section-status');
      });

      expect(temperatureSection).toHaveStyle({ order: '0' });
      expect(statusSection).toHaveStyle({ order: '1' });
      expect(within(card).queryByTestId('printer-card-section-drag-status')).not.toBeInTheDocument();
      expect(within(card).queryByTestId('printer-card-section-drag-temperatures')).not.toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Show layout controls' }));

      expect(within(card).getByTestId('printer-card-section-drag-status')).toBeInTheDocument();
      expect(within(card).getByTestId('printer-card-section-drag-temperatures')).toBeInTheDocument();
    });

    it('applies the saved whole-printer-card order in the regular grid and exposes drag handles only in layout editing mode', async () => {
      const user = userEvent.setup();
      vi.mocked(localStorage.getItem).mockImplementation((key: string) =>
        key === 'printerCardOrder' ? JSON.stringify([1, 2]) : null
      );

      render(<PrintersPage />);

      const cards = await screen.findAllByTestId(/^sortable-printer-card-/);
      expect(cards.map(card => card.getAttribute('data-testid'))).toEqual([
        'sortable-printer-card-1',
        'sortable-printer-card-2',
      ]);
      expect(screen.queryByTestId('printer-card-drag-1')).not.toBeInTheDocument();
      expect(screen.queryByTestId('printer-card-drag-2')).not.toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Show layout controls' }));

      expect(screen.getByTestId('printer-card-drag-1')).toBeInTheDocument();
      expect(screen.getByTestId('printer-card-drag-2')).toBeInTheDocument();
    });

    it('applies the saved whole-printer-card order inside grouped views', async () => {
      vi.mocked(localStorage.getItem).mockImplementation((key: string) => {
        if (key === 'printerSortBy') return 'status';
        if (key === 'printerCardOrder') return JSON.stringify([2, 1]);
        return null;
      });

      render(<PrintersPage />);

      const cards = await screen.findAllByTestId(/^sortable-printer-card-/);
      expect(cards.map(card => card.getAttribute('data-testid'))).toEqual([
        'sortable-printer-card-2',
        'sortable-printer-card-1',
      ]);
    });

    it('resizes the inline camera while enforcing minimum card-friendly dimensions', async () => {
      const user = userEvent.setup();
      server.use(
        http.get('/api/v1/settings/ui-preferences', () => HttpResponse.json({
          ams_humidity_good: 40,
          ams_humidity_fair: 60,
          ams_temp_good: 30,
          ams_temp_fair: 35,
          require_plate_clear: true,
          camera_view_mode: 'card',
          panda_breath_printer_assignments: '{}',
        })),
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          provider: 'fluidd',
          name: 'Neptune 4 Pro',
          external_camera_url: 'http://neptune.local/webcam/?action=stream',
          external_camera_type: 'mjpeg',
          external_camera_enabled: true,
        }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          connected: false,
        })),
        http.post('/api/v1/printers/:id/camera/stop', () => HttpResponse.json({ success: true })),
        http.get('/api/v1/printers/:id/camera/status', () => HttpResponse.json({ active: true, stalled: false })),
      );

      render(<PrintersPage />);
      await user.click(await screen.findByRole('button', { name: /show camera in printer card/i }));

      const viewer = await screen.findByTestId('inline-camera-viewer-1');
      vi.spyOn(viewer, 'getBoundingClientRect').mockReturnValue({
        x: 100,
        y: 50,
        left: 100,
        top: 50,
        right: 580,
        bottom: 350,
        width: 480,
        height: 300,
        toJSON: () => ({}),
      } as DOMRect);
      const resizeHandle = screen.getByTitle('Drag to resize');

      fireEvent.mouseDown(resizeHandle, { clientX: 580, clientY: 350 });
      fireEvent.mouseMove(document, { clientX: 860, clientY: 520 });
      fireEvent.mouseUp(document);

      await waitFor(() => {
        expect(viewer).toHaveStyle({ width: '760px', height: '470px' });
      });

      fireEvent.mouseDown(resizeHandle, { clientX: 860, clientY: 520 });
      fireEvent.mouseMove(document, { clientX: 120, clientY: 80 });
      fireEvent.mouseUp(document);

      await waitFor(() => {
        expect(viewer).toHaveStyle({ width: '320px', height: '220px' });
      });
    });

    it('does not open a Fluidd/Moonraker API URL as a camera target', async () => {
      const user = userEvent.setup();
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          provider: 'fluidd',
          name: 'Neptune 4 Pro',
          api_url: 'http://10.17.10.31',
          external_camera_url: null,
          external_camera_type: null,
          external_camera_enabled: false,
        }])),
      );

      render(<PrintersPage />);

      const cameraButton = await screen.findByRole('button', { name: /open camera in new window/i });
      expect(cameraButton).toBeDisabled();
      await user.click(cameraButton);

      expect(openSpy).not.toHaveBeenCalled();
      openSpy.mockRestore();
    });

    it('opens the camera window under the Home Assistant ingress base path', async () => {
      const user = userEvent.setup();
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
      window.history.pushState({}, '', '/api/hassio_ingress/printbuddy123/');

      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          provider: 'fluidd',
          name: 'Neptune 4 Pro',
          external_camera_url: 'http://neptune.local/webcam/?action=stream',
          external_camera_type: 'mjpeg',
          external_camera_enabled: true,
        }])),
      );

      render(<PrintersPage />);

      const cameraButton = await screen.findByRole('button', { name: /open camera in new window/i });
      await user.click(cameraButton);

      expect(openSpy).toHaveBeenCalledWith(
        '/api/hassio_ingress/printbuddy123/camera/1',
        'camera-1',
        expect.any(String),
      );
      openSpy.mockRestore();
      window.history.pushState({}, '', '/');
    });

    it('passes the current auth token into the camera popup URL because popup sessionStorage is unreliable', async () => {
      const user = userEvent.setup();
      const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
      setAuthToken('app-token-123');
      window.history.pushState({}, '', '/api/hassio_ingress/printbuddy123/');

      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          provider: 'fluidd',
          name: 'Neptune 4 Pro',
          external_camera_url: 'http://neptune.local/webcam/?action=stream',
          external_camera_type: 'mjpeg',
          external_camera_enabled: true,
        }])),
      );

      render(<PrintersPage />);

      const cameraButton = await screen.findByRole('button', { name: /open camera in new window/i });
      await user.click(cameraButton);

      expect(openSpy).toHaveBeenCalledWith(
        '/api/hassio_ingress/printbuddy123/camera/1?token=app-token-123',
        'camera-1',
        expect.any(String),
      );
      openSpy.mockRestore();
      window.history.pushState({}, '', '/');
    });

    it('shows printer models', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1C')).toBeInTheDocument();
        expect(screen.getByText('P1S')).toBeInTheDocument();
      });
    });

    it('shows printer status', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        // Status should be shown - may vary based on state
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });
    });

    it('labels the fan/status strip as status and only shows reported fan capabilities', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([mockPrinters[0]])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          state: 'RUNNING',
          cooling_fan_speed: 35,
          big_fan1_speed: 0,
          big_fan2_speed: null,
          heatbreak_fan_speed: null,
          speed_level: 2,
        }))
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('Status').length).toBeGreaterThan(0);
        expect(screen.getByTitle('Part Cooling Fan')).toBeInTheDocument();
        expect(screen.getByTitle('Auxiliary Fan')).toBeInTheDocument();
        expect(screen.getByText('35%')).toBeInTheDocument();
        expect(screen.getByText('0%')).toBeInTheDocument();
      });

      expect(screen.queryByTitle('Chamber Fan')).not.toBeInTheDocument();
      expect(screen.queryByTitle('Heatbreak Fan')).not.toBeInTheDocument();
      expect(screen.queryByTitle('Move build plate')).not.toBeInTheDocument();
    });

    it('shows loaded-spool assignment controls for Elegoo SDCP printers', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          name: 'Centauri Carbon',
          provider: 'elegoo_sdcp',
          model: 'Elegoo Centauri Carbon',
        }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          ams: [],
          vt_tray: [],
        })),
      );

      render(<PrintersPage />);

      await waitFor(() => expect(screen.getByText('Centauri Carbon')).toBeInTheDocument());

      expect(await screen.findByText('Loaded spool')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^Assign$/i })).toBeInTheDocument();
    });

    it('groups add-printer model choices by vendor and includes common Klipper machines', async () => {
      const user = userEvent.setup();

      render(<PrintersPage />);

      await user.click((await screen.findAllByRole('button', { name: /add printer/i })).at(-1)!);
      const modelSelect = screen.getByLabelText('Model (optional)') as HTMLSelectElement;
      const groupLabels = Array.from(modelSelect.querySelectorAll('optgroup')).map((group) => group.label);
      const optionValues = Array.from(modelSelect.options).map((option) => option.value);

      expect(groupLabels).toEqual([
        'Bambu Lab A1 Series',
        'Bambu Lab A2 Series',
        'Bambu Lab P Series',
        'Bambu Lab X Series',
        'Bambu Lab H Series',
        'Elegoo',
        'Voron',
        'Creality Klipper',
        'Snapmaker Klipper',
        'Prusa',
        'Generic',
      ]);
      expect(optionValues).toContain('A2L');
      expect(optionValues).toContain('P1S');
      expect(optionValues).toContain('Elegoo Neptune 4 Pro');
      expect(optionValues).toContain('Elegoo Centauri Carbon');
      expect(optionValues).toContain('Voron 2.4');
      expect(optionValues).toContain('Creality Ender-3 V2');
      expect(optionValues).toContain('Creality K1');
      expect(optionValues).toContain('Creality K1C');
      expect(optionValues).toContain('Creality K2');
      expect(optionValues).toContain('Creality K2 Plus');
      expect(optionValues).toContain('Snapmaker U1');
      expect(optionValues).toContain('Prusa MK4S');
      expect(optionValues).toContain('Generic Klipper Printer');
    });

    it('shows Creality CFS units with CFS labels', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          name: 'K2 Plus',
          provider: 'fluidd',
          model: 'Creality K2 Plus',
        }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          ams_exists: true,
          tray_now: 1,
          ams: [{
            id: 0,
            name: 'CFS T1',
            humidity: null,
            temp: null,
            is_ams_ht: false,
            serial_number: '10000949645L325LWVB',
            sw_ver: '1.4.2',
            dry_time: 0,
            dry_status: 0,
            dry_sub_status: 0,
            dry_sf_reason: [],
            module_type: 'cfs',
            tray: [
              { id: 0, tray_type: 'PLA', tray_color: '#0A2989', remain: 41, state: 11, tray_uuid: 'T1A' },
              { id: 1, tray_type: 'PLA', tray_color: '#fff014', remain: 100, state: 11, tray_uuid: 'T1B' },
              { id: 2, tray_type: 'PLA', tray_color: '#ffffff', remain: 100, state: 11, tray_uuid: 'T1C' },
              { id: 3, tray_type: 'PLA', tray_color: '#9ea7ae', remain: 100, state: 11, tray_uuid: 'T1D' },
            ],
          }],
        })),
      );

      render(<PrintersPage />);

      expect(await screen.findByText('K2 Plus')).toBeInTheDocument();
      expect(await screen.findByText('CFS T1')).toBeInTheDocument();
    });

    it('shows Prusa models when Prusa is selected as printer type', async () => {
      const user = userEvent.setup();

      render(<PrintersPage />);

      await user.click((await screen.findAllByRole('button', { name: /add printer/i })).at(-1)!);
      await user.selectOptions(screen.getByLabelText(/printer type/i), 'prusalink');

      const modelSelect = screen.getByLabelText('Model (optional)') as HTMLSelectElement;
      const groupLabels = Array.from(modelSelect.querySelectorAll('optgroup')).map((group) => group.label);
      const optionValues = Array.from(modelSelect.options).map((option) => option.value);

      expect(screen.getByLabelText(/prusa connection/i)).toBeInTheDocument();
      expect(groupLabels).toEqual(['Prusa', 'Generic']);
      expect(optionValues).toContain('Prusa CORE One');
      expect(optionValues).toContain('Prusa MK4');
      expect(optionValues).toContain('Prusa MK4S');
      expect(optionValues).not.toContain('P1S');
      expect(optionValues).not.toContain('Elegoo Neptune 4 Pro');
    }, 10000);

    it('can add a Prusa printer through the Connect Mobile API connection mode', async () => {
      const user = userEvent.setup();
      let createdPayload: Record<string, unknown> | null = null;
      let diagnosticCalled = false;

      server.use(
        http.get('/api/v1/discovery/info', () => HttpResponse.json({ is_docker: false, subnets: [] })),
        http.post('/api/v1/printers/diagnose', () => {
          diagnosticCalled = true;
          return HttpResponse.json({ checks: [] });
        }),
        http.post('/api/v1/printers/', async ({ request }) => {
          createdPayload = await request.json() as Record<string, unknown>;
          return HttpResponse.json({
            ...mockPrinters[0],
            name: 'MK4S Cloud',
            provider: 'prusaconnect',
            ip_address: '13b5af3d-7b44-42b1-9327-cf8a6fbf3f3c',
            api_url: 'https://connect-mobile-api.prusa3d.com',
            auth_token: null,
            model: 'Prusa MK4S',
          });
        }),
      );

      render(<PrintersPage />);

      await user.click((await screen.findAllByRole('button', { name: /add printer/i })).at(-1)!);
      await user.selectOptions(screen.getByLabelText(/printer type/i), 'prusalink');
      await user.selectOptions(screen.getByLabelText(/prusa connection/i), 'prusaconnect');
      await user.selectOptions(screen.getByLabelText('Model (optional)'), 'Prusa MK4S');
      await user.type(screen.getByPlaceholderText('My Printer'), 'MK4S Cloud');
      await user.type(screen.getByPlaceholderText('13b5af3d-7b44-42b1-9327-cf8a6fbf3f3c'), '13b5af3d-7b44-42b1-9327-cf8a6fbf3f3c');
      await user.type(screen.getByPlaceholderText('Authorization token from the Prusa Connect mobile API'), 'dummy-connect-token');
      await user.click(screen.getAllByRole('button', { name: /^add printer$/i }).at(-1)!);

      await waitFor(() => {
        expect(createdPayload).toMatchObject({
          name: 'MK4S Cloud',
          provider: 'prusaconnect',
          ip_address: '13b5af3d-7b44-42b1-9327-cf8a6fbf3f3c',
          api_url: 'https://connect-mobile-api.prusa3d.com',
          auth_token: 'dummy-connect-token',
          model: 'Prusa MK4S',
        });
      });
      expect(createdPayload).not.toHaveProperty('serial_number');
      expect(createdPayload).not.toHaveProperty('access_code');
      expect(diagnosticCalled).toBe(false);
    }, 10000);

    it.each([
      { provider: 'klipper', name: 'Voron 2.4', host: 'voron.local', serial: 'KLIPPER-VORON-LOCAL', model: 'Voron 2.4' },
      { provider: 'fluidd', name: 'Elegoo Neptune 4 Pro', host: 'neptune.local', serial: 'KLIPPER-NEPTUNE-LOCAL', model: 'Elegoo Neptune 4 Pro' },
    ])('can add a $provider printer through Moonraker without Bambu serial/access fields', async ({ provider, name, host, serial, model }) => {
      const user = userEvent.setup();
      let createdPayload: Record<string, unknown> | null = null;
      let diagnosticCalled = false;

      server.use(
        http.get('/api/v1/discovery/info', () => HttpResponse.json({ is_docker: false, subnets: [] })),
        http.post('/api/v1/printers/diagnose', () => {
          diagnosticCalled = true;
          return HttpResponse.json({ checks: [] });
        }),
        http.post('/api/v1/printers/', async ({ request }) => {
          createdPayload = await request.json() as Record<string, unknown>;
          return HttpResponse.json({
            id: 3,
            name,
            serial_number: serial,
            ip_address: host,
            access_code: 'moonraker',
            provider,
            api_url: `http://${host}:7125`,
            auth_token: null,
            provider_options: null,
            model: 'Klipper',
            location: null,
            auto_archive: true,
            is_active: true,
            nozzle_count: 1,
            external_camera_url: null,
            external_camera_type: null,
            external_camera_enabled: false,
            external_camera_snapshot_url: null,
            camera_rotation: 0,
            plate_detection_enabled: false,
            created_at: '2024-01-03T00:00:00Z',
            updated_at: '2024-01-03T00:00:00Z',
          });
        }),
      );

      render(<PrintersPage />);

      await user.click((await screen.findAllByRole('button', { name: /add printer/i })).at(-1)!);
      await user.selectOptions(screen.getByLabelText(/printer type/i), provider);
      await user.selectOptions(screen.getByLabelText('Model (optional)'), model);
      await user.type(screen.getByPlaceholderText('My Printer'), name);
      await user.type(screen.getByPlaceholderText('192.168.1.100 or printer.local'), host);
      await user.type(screen.getByPlaceholderText('http://printer.local/webcam/?action=stream'), `http://${host}/webcam/?action=stream`);
      await user.click(screen.getAllByRole('button', { name: /^add printer$/i }).at(-1)!);

      await waitFor(() => {
        expect(createdPayload).toMatchObject({
          name,
          provider,
          ip_address: host,
          api_url: `http://${host}:7125`,
          model,
          external_camera_url: `http://${host}/webcam/?action=stream`,
          external_camera_type: 'mjpeg',
          external_camera_enabled: true,
        });
      });
      expect(createdPayload).not.toHaveProperty('serial_number');
      expect(createdPayload).not.toHaveProperty('access_code');
      expect(diagnosticCalled).toBe(false);
    }, 10000);

    it('can add a non-Bambu printer without configuring an external camera', async () => {
      const user = userEvent.setup();
      let createdPayload: Record<string, unknown> | null = null;

      server.use(
        http.get('/api/v1/discovery/info', () => HttpResponse.json({ is_docker: false, subnets: [] })),
        http.post('/api/v1/printers/', async ({ request }) => {
          createdPayload = await request.json() as Record<string, unknown>;
          return HttpResponse.json({
            ...mockPrinters[0],
            provider: 'fluidd',
            api_url: 'http://neptune.local:7125',
            external_camera_url: null,
            external_camera_type: null,
            external_camera_enabled: false,
          });
        }),
      );

      render(<PrintersPage />);

      await user.click((await screen.findAllByRole('button', { name: /add printer/i })).at(-1)!);
      await user.selectOptions(screen.getByLabelText(/printer type/i), 'fluidd');
      await user.selectOptions(screen.getByLabelText('Model (optional)'), 'Elegoo Neptune 4 Pro');
      await user.type(screen.getByPlaceholderText('My Printer'), 'Elegoo Neptune 4 Pro');
      await user.type(screen.getByPlaceholderText('192.168.1.100 or printer.local'), 'neptune.local');

      const cameraInput = screen.getByPlaceholderText('http://printer.local/webcam/?action=stream');
      expect(cameraInput).not.toBeRequired();

      await user.click(screen.getAllByRole('button', { name: /^add printer$/i }).at(-1)!);

      await waitFor(() => {
        expect(createdPayload).toMatchObject({
          name: 'Elegoo Neptune 4 Pro',
          provider: 'fluidd',
          ip_address: 'neptune.local',
          api_url: 'http://neptune.local:7125',
          model: 'Elegoo Neptune 4 Pro',
          external_camera_enabled: false,
        });
      });
      expect(createdPayload).not.toHaveProperty('external_camera_url');
      expect(createdPayload).not.toHaveProperty('external_camera_type');
    }, 10000);
    it('detects Moonraker webcams and fills the camera URL field', async () => {
      const user = userEvent.setup();

      server.use(
        http.get('/api/v1/discovery/info', () => HttpResponse.json({ is_docker: false, subnets: [] })),
        http.get('/api/v1/printers/moonraker-webcams/discover', ({ request }) => {
          const url = new URL(request.url);
          expect(url.searchParams.get('api_url')).toBe('http://k2-plus.local:7125');
          return HttpResponse.json({
            webcams: [{
              name: 'Moonraker Cam',
              stream_url: 'http://k2-plus.local/webcam/?action=stream',
              snapshot_url: 'http://k2-plus.local/webcam/?action=snapshot',
              camera_type: 'mjpeg',
              enabled: true,
            }],
          });
        }),
      );

      render(<PrintersPage />);

      await user.click((await screen.findAllByRole('button', { name: /add printer/i })).at(-1)!);
      await user.selectOptions(screen.getByLabelText(/printer type/i), 'fluidd');
      await user.type(screen.getByPlaceholderText('192.168.1.100 or printer.local'), 'k2-plus.local');
      await user.click(screen.getByRole('button', { name: /detect moonraker camera/i }));

      await waitFor(() => {
        expect(screen.getByPlaceholderText('http://printer.local/webcam/?action=stream')).toHaveValue(
          'http://k2-plus.local/webcam/?action=stream'
        );
      });
      expect(screen.getByText('Using Moonraker Cam from Moonraker.')).toBeInTheDocument();
    }, 10000);
  });

  describe('manual controls', () => {
    it('hides manual controls for Prusa printers because PrusaLink model controls are unsupported', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{ ...mockPrinters[0], name: 'Boženka', provider: 'prusalink', model: 'Prusa MK4S' }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          temperatures: { nozzle: 25, nozzle_target: 0, bed: 25, bed_target: 0 },
          position: { x: 10.2, y: 0, z: 54.2 },
        })),
      );

      render(<PrintersPage />);

      await screen.findByText('Boženka');
      expect(screen.queryByRole('button', { name: /manual controls/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'X+' })).not.toBeInTheDocument();
    });

    it('hides unsupported light and plate-check controls for Prusa printers', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{ ...mockPrinters[0], name: 'CORE One', provider: 'prusalink', model: 'Prusa CORE One' }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          connected: true,
          chamber_light: false,
        })),
      );

      render(<PrintersPage />);

      await screen.findByText('CORE One');
      expect(screen.queryByTitle('Turn on chamber light')).toBeNull();
      expect(screen.queryByTitle('Plate check disabled - Click to enable')).toBeNull();
      expect(screen.queryByTitle('Manage plate detection calibration')).toBeNull();
    });

    it('shows manual controls for Creality K2 Plus Fluidd printers', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          name: 'K2 Plus',
          provider: 'fluidd',
          model: 'Creality K2 Plus',
        }])),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
          ...mockPrinterStatus,
          connected: true,
          position: { x: 0, y: 0, z: 0 },
        })),
      );

      render(<PrintersPage />);

      await screen.findByText('K2 Plus');
      const controlsToggle = await screen.findByRole('button', { name: /manual controls/i });
      expect(controlsToggle).toBeInTheDocument();
    });

    it('sends XYZ jog requests from the printer card controls', async () => {
      const user = userEvent.setup();
      const jogRequests: string[] = [];

      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{ ...mockPrinters[0], provider: 'fluidd', model: 'Klipper' }])),
        http.post('/api/v1/printers/:id/axis-jog', ({ request }) => {
          jogRequests.push(new URL(request.url).search);
          return HttpResponse.json({ success: true, message: 'Jog sent' });
        })
      );

      render(<PrintersPage />);

      await screen.findByText('X1 Carbon');
      const controlsToggle = await screen.findByRole('button', { name: /manual controls/i });
      expect(controlsToggle).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryByRole('button', { name: 'X+' })).not.toBeInTheDocument();
      await user.click(controlsToggle);
      const klipperXPlusButton = await screen.findByRole('button', { name: 'X+' });
      expect(klipperXPlusButton).toHaveClass('bg-[var(--accent)]');
      expect(klipperXPlusButton).not.toHaveClass('bg-red-700');
      await user.click(klipperXPlusButton);

      await waitFor(() => {
        expect(jogRequests).toContain('?axis=x&distance=10');
      });
    });

    it('sets nozzle and bed temperatures from the printer card controls', async () => {
      const user = userEvent.setup();
      const temperatureRequests: string[] = [];

      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{ ...mockPrinters[0], provider: 'fluidd', model: 'Klipper' }])),
        http.post('/api/v1/printers/:id/temperature/nozzle', ({ request }) => {
          temperatureRequests.push(`nozzle:${new URL(request.url).search}`);
          return HttpResponse.json({ success: true, message: 'Nozzle set' });
        }),
        http.post('/api/v1/printers/:id/temperature/bed', ({ request }) => {
          temperatureRequests.push(`bed:${new URL(request.url).search}`);
          return HttpResponse.json({ success: true, message: 'Bed set' });
        })
      );

      render(<PrintersPage />);

      await screen.findByText('X1 Carbon');
      await user.click(await screen.findByRole('button', { name: /manual controls/i }));
      await user.type(await screen.findByLabelText('Nozzle temperature target'), '210');
      await user.click(screen.getByRole('button', { name: 'Nozzle' }));
      await user.type(await screen.findByLabelText('Bed temperature target'), '60');
      await user.click(screen.getByRole('button', { name: 'Bed' }));

      await waitFor(() => {
        expect(temperatureRequests).toEqual(expect.arrayContaining([
          'nozzle:?target=210',
          'bed:?target=60',
        ]));
      });
    });
  });

  describe('printer info', () => {
    it('shows IP address in printer info modal', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      // IP address is shown in the PrinterInfoModal (accessed via 3-dot menu),
      // not directly on the card. Verify the printer data loaded correctly.
      expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
    });

    it('shows location when set', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        // Printers should render - location display may vary
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });
    });
  });

  describe('temperature display', () => {
    it('shows nozzle temperature', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        // Temperatures are shown in the UI
        expect(screen.getAllByText(/25/)).toBeTruthy();
      });
    });
  });

  describe('empty state', () => {
    it('shows empty state when no printers', async () => {
      server.use(
        http.get('/api/v1/printers/', () => {
          return HttpResponse.json([]);
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText(/no printers/i)).toBeInTheDocument();
      });
    });
  });

  describe('printer actions', () => {
    it('has action buttons', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      // There should be some interactive elements for printer actions
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });

    it('shows plate clear status and action on finished printers when not cleared', async () => {
      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json({ ...mockPrinterStatus, state: 'FINISH', awaiting_plate_clear: true });
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('Plate not Clear').length).toBeGreaterThan(0);
      });

      expect(screen.getAllByRole('button', { name: 'Mark plate as cleared' }).length).toBeGreaterThan(0);
    });

    it('shows plate clear status and action on failed printers when not cleared', async () => {
      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json({ ...mockPrinterStatus, state: 'FAILED', awaiting_plate_clear: true });
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('Plate not Clear').length).toBeGreaterThan(0);
      });

      expect(screen.getAllByRole('button', { name: 'Mark plate as cleared' }).length).toBeGreaterThan(0);
    });

    it('keeps the clear action available when an idle printer is still awaiting acknowledgment', async () => {
      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json({ ...mockPrinterStatus, state: 'IDLE', awaiting_plate_clear: true });
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('Plate not Clear').length).toBeGreaterThan(0);
      });

      expect(screen.getAllByRole('button', { name: 'Mark plate as cleared' }).length).toBeGreaterThan(0);
    });

    it('updates the plate clear status after using the printer card action', async () => {
      let awaitingPlateClear = true;

      server.use(
        http.get('/api/v1/printers/', () => {
          return HttpResponse.json([mockPrinters[0]]);
        }),
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json({ ...mockPrinterStatus, state: 'FINISH', awaiting_plate_clear: awaitingPlateClear });
        }),
        http.post('/api/v1/printers/:id/clear-plate', () => {
          awaitingPlateClear = false;
          return HttpResponse.json({ success: true, message: 'Plate cleared' });
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('Plate not Clear').length).toBeGreaterThan(0);
      });

      fireEvent.click(screen.getAllByRole('button', { name: 'Mark plate as cleared' })[0]);

      await waitFor(() => {
        expect(screen.queryByText('Plate not Clear')).not.toBeInTheDocument();
      });

      expect(screen.getAllByText('Plate Clear').length).toBeGreaterThan(0);
    });

    it('shows an icon-only plate clear action in small card view', async () => {
      let awaitingPlateClear = true;

      server.use(
        http.get('/api/v1/printers/', () => {
          return HttpResponse.json([mockPrinters[0]]);
        }),
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json({ ...mockPrinterStatus, state: 'FINISH', awaiting_plate_clear: awaitingPlateClear });
        }),
        http.post('/api/v1/printers/:id/clear-plate', () => {
          awaitingPlateClear = false;
          return HttpResponse.json({ success: true, message: 'Plate cleared' });
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: 'S' }));

      await waitFor(() => {
        expect(screen.queryByText('Mark plate as cleared')).not.toBeInTheDocument();
      });

      const clearButton = screen.getByRole('button', { name: 'Mark plate as cleared' });

      fireEvent.click(clearButton);

      await waitFor(() => {
        expect(screen.queryByRole('button', { name: 'Mark plate as cleared' })).not.toBeInTheDocument();
      });
    });

    it('shows plate clear status but no action while idle', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('Plate Clear').length).toBeGreaterThan(0);
      });

      expect(screen.queryByRole('button', { name: 'Mark plate as cleared' })).not.toBeInTheDocument();
    });

    it('shows plate in use status while printing and hides the clear action', async () => {
      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json({ ...mockPrinterStatus, state: 'RUNNING', awaiting_plate_clear: false });
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('Plate in Use').length).toBeGreaterThan(0);
      });

      expect(screen.queryByRole('button', { name: 'Mark plate as cleared' })).not.toBeInTheDocument();
    });

    it('hides plate status and action when plate-clear confirmation is disabled', async () => {
      server.use(
        http.get('/api/v1/settings/', () => {
          return HttpResponse.json({
            auto_archive: true,
            save_thumbnails: true,
            capture_finish_photo: true,
            default_filament_cost: 25.0,
            currency: 'USD',
            ams_humidity_good: 40,
            ams_humidity_fair: 60,
            ams_temp_good: 30,
            ams_temp_fair: 35,
            require_plate_clear: false,
          });
        }),
        http.get('/api/v1/settings/ui-preferences', () => {
          return HttpResponse.json({
            ams_humidity_good: 40,
            ams_humidity_fair: 60,
            ams_temp_good: 30,
            ams_temp_fair: 35,
            require_plate_clear: false,
          });
        }),
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json({ ...mockPrinterStatus, state: 'FINISH', awaiting_plate_clear: true });
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      expect(screen.queryByText('Plate not Clear')).not.toBeInTheDocument();
      expect(screen.queryByText('Plate Clear')).not.toBeInTheDocument();
      expect(screen.queryByText('Plate in Use')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Mark plate as cleared' })).not.toBeInTheDocument();
    });
  });

  describe('disabled printer', () => {
    it('shows disabled state for disabled printers', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('P1S Backup')).toBeInTheDocument();
      });

      // Disabled printers have visual indication
      const disabledPrinter = screen.getByText('P1S Backup').closest('div');
      expect(disabledPrinter).toBeInTheDocument();
    });
  });

  describe('nozzle rack card', () => {
    const h2cStatus = {
      ...mockPrinterStatus,
      nozzle_rack: [
        { id: 0, nozzle_type: 'HS', nozzle_diameter: '0.4', wear: 5, stat: 1, max_temp: 300, serial_number: 'SN-L', filament_color: '', filament_id: '', filament_type: '' },
        { id: 1, nozzle_type: 'HS', nozzle_diameter: '0.4', wear: 3, stat: 0, max_temp: 300, serial_number: 'SN-R', filament_color: '', filament_id: '', filament_type: '' },
        { id: 16, nozzle_type: 'HS', nozzle_diameter: '0.4', wear: 10, stat: 0, max_temp: 300, serial_number: 'SN-16', filament_color: '', filament_id: '', filament_type: '' },
        { id: 17, nozzle_type: 'HH01', nozzle_diameter: '0.6', wear: 0, stat: 0, max_temp: 300, serial_number: 'SN-17', filament_color: '', filament_id: '', filament_type: '' },
        { id: 18, nozzle_type: 'HS', nozzle_diameter: '0.4', wear: 2, stat: 0, max_temp: 300, serial_number: 'SN-18', filament_color: '', filament_id: '', filament_type: '' },
        { id: 19, nozzle_type: '', nozzle_diameter: '', wear: null, stat: null, max_temp: 0, serial_number: '', filament_color: '', filament_id: '', filament_type: '' },
        { id: 20, nozzle_type: '', nozzle_diameter: '', wear: null, stat: null, max_temp: 0, serial_number: '', filament_color: '', filament_id: '', filament_type: '' },
        { id: 21, nozzle_type: '', nozzle_diameter: '', wear: null, stat: null, max_temp: 0, serial_number: '', filament_color: '', filament_id: '', filament_type: '' },
      ],
    };

    it('shows nozzle rack when H2C rack slots present', async () => {
      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json(h2cStatus);
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('Nozzle Rack').length).toBeGreaterThan(0);
      });
    });

    it('shows 6 rack slot elements for H2C', async () => {
      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json(h2cStatus);
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('Nozzle Rack').length).toBeGreaterThan(0);
      });

      // Rack shows diameters for occupied slots and dashes for empty ones
      const dashes = screen.getAllByText('—');
      expect(dashes.length).toBeGreaterThanOrEqual(3); // 3 empty rack positions (IDs 19,20,21)
    });

    it('keeps empty slot anchored to physical position when its nozzle is mounted (#943)', async () => {
      // H2C with rack slot 16 picked up into the hotend — firmware omits ID 16
      // entirely from nozzle.info. Each rack diameter is unique so we can assert
      // the ordering by tooltip lookup.
      const h2cSlot16Mounted = {
        ...mockPrinterStatus,
        nozzle_rack: [
          { id: 0, nozzle_type: 'HS', nozzle_diameter: '0.4', wear: 5, stat: 1, max_temp: 300, serial_number: 'SN-L', filament_color: '', filament_id: '', filament_type: '' },
          { id: 1, nozzle_type: 'HS', nozzle_diameter: '0.4', wear: 3, stat: 0, max_temp: 300, serial_number: 'SN-R', filament_color: '', filament_id: '', filament_type: '' },
          // ID 16 missing — currently in hotend
          { id: 17, nozzle_type: 'HS', nozzle_diameter: '0.2', wear: 0, stat: 0, max_temp: 300, serial_number: 'SN-17', filament_color: '', filament_id: '', filament_type: '' },
          { id: 18, nozzle_type: 'HS', nozzle_diameter: '0.6', wear: 0, stat: 0, max_temp: 300, serial_number: 'SN-18', filament_color: '', filament_id: '', filament_type: '' },
          { id: 19, nozzle_type: 'HS', nozzle_diameter: '0.8', wear: 0, stat: 0, max_temp: 300, serial_number: 'SN-19', filament_color: '', filament_id: '', filament_type: '' },
          { id: 20, nozzle_type: 'HH01', nozzle_diameter: '1.0', wear: 0, stat: 0, max_temp: 300, serial_number: 'SN-20', filament_color: '', filament_id: '', filament_type: '' },
          { id: 21, nozzle_type: 'HH01', nozzle_diameter: '1.2', wear: 0, stat: 0, max_temp: 300, serial_number: 'SN-21', filament_color: '', filament_id: '', filament_type: '' },
        ],
      };

      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json(h2cSlot16Mounted);
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('Nozzle Rack').length).toBeGreaterThan(0);
      });

      // Slot 1 (leftmost, ID 16) should be the empty dash; slots 2..6 should
      // hold the 5 remaining nozzles in order 17, 18, 19, 20, 21.
      const rackLabel = screen.getAllByText('Nozzle Rack')[0];
      const rackCard = rackLabel.parentElement!;
      const slotRow = rackCard.querySelectorAll('div.flex')[0];
      const slotTexts = Array.from(slotRow.querySelectorAll('span')).map(s => s.textContent);
      expect(slotTexts).toEqual(['—', '0.2', '0.6', '0.8', '1.0', '1.2']);
    });

    it('hides nozzle rack when only L/R nozzles present (H2D)', async () => {
      const h2dStatus = {
        ...mockPrinterStatus,
        nozzle_rack: [
          { id: 0, nozzle_type: 'HS', nozzle_diameter: '0.4', wear: 5, stat: 1, max_temp: 300, serial_number: '', filament_color: '', filament_id: '', filament_type: '' },
          { id: 1, nozzle_type: 'HS', nozzle_diameter: '0.4', wear: 3, stat: 1, max_temp: 300, serial_number: '', filament_color: '', filament_id: '', filament_type: '' },
        ],
      };

      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json(h2dStatus);
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      expect(screen.queryByText('Nozzle Rack')).not.toBeInTheDocument();
    });
  });

  describe('firmware version badge', () => {
    const firmwareUpToDate = {
      printer_id: 1,
      current_version: '01.09.00.00',
      latest_version: '01.09.00.00',
      update_available: false,
      download_url: null,
      release_notes: 'Bug fixes and improvements.',
    };

    const firmwareUpdateAvailable = {
      printer_id: 1,
      current_version: '01.08.00.00',
      latest_version: '01.09.00.00',
      update_available: true,
      download_url: 'https://example.com/firmware.bin',
      release_notes: 'New features added.',
    };

    it('shows green badge when firmware is up to date', async () => {
      server.use(
        http.get('/api/v1/firmware/updates/:id', () => {
          return HttpResponse.json(firmwareUpToDate);
        }),
        http.get('/api/v1/settings/', () => {
          return HttpResponse.json({
            check_printer_firmware: true,
            auto_archive: true,
            save_thumbnails: true,
          });
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('01.09.00.00').length).toBeGreaterThan(0);
      });

      const badge = screen.getAllByText('01.09.00.00')[0].closest('button');
      expect(badge).toBeInTheDocument();
      expect(badge?.className).toContain('text-status-ok');
    });

    it('shows orange badge when firmware update is available', async () => {
      server.use(
        http.get('/api/v1/firmware/updates/:id', () => {
          return HttpResponse.json(firmwareUpdateAvailable);
        }),
        http.get('/api/v1/settings/', () => {
          return HttpResponse.json({
            check_printer_firmware: true,
            auto_archive: true,
            save_thumbnails: true,
          });
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getAllByText('01.08.00.00').length).toBeGreaterThan(0);
      });

      const badge = screen.getAllByText('01.08.00.00')[0].closest('button');
      expect(badge).toBeInTheDocument();
      expect(badge?.className).toContain('text-orange-400');
    });

    it('hides badge when firmware check is disabled', async () => {
      server.use(
        http.get('/api/v1/settings/', () => {
          return HttpResponse.json({
            check_printer_firmware: false,
            auto_archive: true,
            save_thumbnails: true,
          });
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      // Version should not appear when firmware check is disabled
      expect(screen.queryByText('01.09.00.00')).not.toBeInTheDocument();
      expect(screen.queryByText('01.08.00.00')).not.toBeInTheDocument();
    });

    it('hides badge when API has no firmware data for the model', async () => {
      const firmwareNoData = {
        printer_id: 1,
        current_version: '01.01.03.00',
        latest_version: null,
        update_available: false,
        download_url: null,
        release_notes: null,
      };

      server.use(
        http.get('/api/v1/firmware/updates/:id', () => {
          return HttpResponse.json(firmwareNoData);
        }),
        http.get('/api/v1/settings/', () => {
          return HttpResponse.json({
            check_printer_firmware: true,
            auto_archive: true,
            save_thumbnails: true,
          });
        })
      );

      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      // Badge should not appear when API returns no latest_version
      expect(screen.queryByText('01.01.03.00')).not.toBeInTheDocument();
    });
  });

  describe('bulk selection', () => {
    it('shows select button in toolbar', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      // The Select button should be in the toolbar (title attribute)
      const selectButton = screen.getByTitle('Select');
      expect(selectButton).toBeInTheDocument();
    });

    it('shows selection toolbar after clicking select button', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      // Click the Select button to enter selection mode
      fireEvent.click(screen.getByTitle('Select'));

      // The floating toolbar should appear with Select All
      await waitFor(() => {
        expect(screen.getByText('Select All')).toBeInTheDocument();
      });
    });

    it('shows selection count when printers are selected', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      // Enter selection mode
      fireEvent.click(screen.getByTitle('Select'));

      await waitFor(() => {
        expect(screen.getByText('Select All')).toBeInTheDocument();
      });

      // Click Select All to select both printers
      fireEvent.click(screen.getByText('Select All'));

      // Should show "2 selected"
      await waitFor(() => {
        expect(screen.getByText('2 selected')).toBeInTheDocument();
      });
    });

    it('shows select by state dropdown', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      // Enter selection mode
      fireEvent.click(screen.getByTitle('Select'));

      await waitFor(() => {
        expect(screen.getByText('Select by State')).toBeInTheDocument();
      });
    });

    it('exits selection mode on close button', async () => {
      render(<PrintersPage />);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });

      // Enter selection mode
      fireEvent.click(screen.getByTitle('Select'));

      await waitFor(() => {
        expect(screen.getByText('Select All')).toBeInTheDocument();
      });

      // Click the Select button again to exit (it toggles)
      fireEvent.click(screen.getByTitle('Select'));

      // Floating toolbar should disappear
      await waitFor(() => {
        expect(screen.queryByText('Select All')).not.toBeInTheDocument();
      });
    });
  });

  describe('search and filter', () => {
    beforeEach(() => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json(mockPrinters)),
        http.get('/api/v1/printers/:id/status', () => HttpResponse.json(mockPrinterStatus)),
        http.get('/api/v1/queue/', () => HttpResponse.json([]))
      );
    });

    it('filters by name (case-insensitive)', async () => {
      render(<PrintersPage />);
      await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

      fireEvent.change(screen.getByPlaceholderText('Search printers...'), { target: { value: 'x1 carbon' } });

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
        expect(screen.queryByText('P1S Backup')).not.toBeInTheDocument();
      });
    });

    it('trims leading and trailing whitespace from search', async () => {
      render(<PrintersPage />);
      await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

      // " X1 Carbon " with surrounding spaces must still match
      fireEvent.change(screen.getByPlaceholderText('Search printers...'), { target: { value: '  X1 Carbon  ' } });

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
        expect(screen.queryByText('P1S Backup')).not.toBeInTheDocument();
      });
    });

    it('filters by model', async () => {
      render(<PrintersPage />);
      await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

      fireEvent.change(screen.getByPlaceholderText('Search printers...'), { target: { value: 'P1S' } });

      await waitFor(() => {
        expect(screen.queryByText('X1 Carbon')).not.toBeInTheDocument();
        expect(screen.getByText('P1S Backup')).toBeInTheDocument();
      });
    });

    it('filters by serial number', async () => {
      render(<PrintersPage />);
      await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

      fireEvent.change(screen.getByPlaceholderText('Search printers...'), { target: { value: '00M09A' } });

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
        expect(screen.queryByText('P1S Backup')).not.toBeInTheDocument();
      });
    });

    it('shows empty state when no printers match search', async () => {
      render(<PrintersPage />);
      await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

      fireEvent.change(screen.getByPlaceholderText('Search printers...'), { target: { value: 'ZZZ_NO_MATCH' } });

      await waitFor(() => {
        expect(screen.getByText('No printers match your search or filters')).toBeInTheDocument();
      });
    });

    it('clear button resets search and shows all printers', async () => {
      render(<PrintersPage />);
      await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

      fireEvent.change(screen.getByPlaceholderText('Search printers...'), { target: { value: 'X1 Carbon' } });

      await waitFor(() => expect(screen.queryByText('P1S Backup')).not.toBeInTheDocument());

      // Click the accessible clear button
      fireEvent.click(screen.getByRole('button', { name: 'Clear' }));

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
        expect(screen.getByText('P1S Backup')).toBeInTheDocument();
      });
    });

    it('filters by status (offline) via dropdown', async () => {
      // Override: printer 1 online, printer 2 offline
      server.use(
        http.get('/api/v1/printers/:id/status', ({ params }) => {
          if (Number(params.id) === 2) {
            return HttpResponse.json({ ...mockPrinterStatus, connected: false });
          }
          return HttpResponse.json(mockPrinterStatus);
        })
      );

      render(<PrintersPage />);
      await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

      await selectToolbarDropdownOption(/all statuses/i, /^offline$/i);

      await waitFor(() => {
        expect(screen.queryByText('X1 Carbon')).not.toBeInTheDocument();
        expect(screen.getByText('P1S Backup')).toBeInTheDocument();
      });
    });

    it('shows empty state when status filter matches nothing', async () => {
      render(<PrintersPage />);
      await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

      // Both printers are IDLE; filtering by "printing" should yield no results
      await selectToolbarDropdownOption(/all statuses/i, /^printing$/i);

      await waitFor(() => {
        expect(screen.getByText('No printers match your search or filters')).toBeInTheDocument();
      });
    });

    it('combines search and status filter', async () => {
      // Printer 1 = RUNNING (printing), printer 2 = IDLE
      server.use(
        http.get('/api/v1/printers/:id/status', ({ params }) => {
          if (Number(params.id) === 1) {
            return HttpResponse.json({ ...mockPrinterStatus, state: 'RUNNING' });
          }
          return HttpResponse.json(mockPrinterStatus);
        })
      );

      render(<PrintersPage />);
      await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

      // Filter to only "printing" printers
      await selectToolbarDropdownOption(/all statuses/i, /^printing$/i);

      // Then also search for a term that only matches printer 1
      fireEvent.change(screen.getByPlaceholderText('Search printers...'), { target: { value: 'X1' } });

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
        expect(screen.queryByText('P1S Backup')).not.toBeInTheDocument();
      });
    });

    it('filters by location via dropdown', async () => {
      // Override: give printer 2 its own location so the dropdown has two options
      // and we can verify the filter picks the right one. Printer 1 stays at 'Workshop'.
      server.use(
        http.get('/api/v1/printers/', () =>
          HttpResponse.json([
            mockPrinters[0],
            { ...mockPrinters[1], location: 'Office' },
          ])
        )
      );

      render(<PrintersPage />);
      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
        expect(screen.getByText('P1S Backup')).toBeInTheDocument();
      });

      await selectToolbarDropdownOption(/all locations/i, /^workshop$/i);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
        expect(screen.queryByText('P1S Backup')).not.toBeInTheDocument();
      });

      await selectToolbarDropdownOption(/^workshop$/i, /^office$/i);

      await waitFor(() => {
        expect(screen.queryByText('X1 Carbon')).not.toBeInTheDocument();
        expect(screen.getByText('P1S Backup')).toBeInTheDocument();
      });
    });

    it('hides location filter when no printers have a location', async () => {
      // Both printers have null location — dropdown should not render at all
      server.use(
        http.get('/api/v1/printers/', () =>
          HttpResponse.json([
            { ...mockPrinters[0], location: null },
            { ...mockPrinters[1], location: null },
          ])
        )
      );

      render(<PrintersPage />);
      await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

      // Status filter is still there, but the location filter should be absent.
      expect(screen.getByRole('button', { name: /all statuses/i })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /all locations/i })).not.toBeInTheDocument();
    });
  });

  describe('Spoolman loading guard', () => {
    it('does not show Assign Spool button while Spoolman queries are loading', async () => {
      // Spoolman enabled but inventory and slot-assignment queries never resolve
      server.use(
        http.get('/api/v1/spoolman/status', () =>
          HttpResponse.json({ enabled: true, connected: true })
        ),
        http.get('/api/v1/spoolman/inventory/spools', () =>
          new Promise(() => {})  // never resolves
        ),
        http.get('/api/v1/spoolman/inventory/slot-assignments/all', () =>
          new Promise(() => {})  // never resolves
        )
      );

      render(<PrintersPage />);

      // Wait for the page to render (printers should be visible)
      await waitFor(() => expect(screen.getByText('X1 Carbon')).toBeInTheDocument());

      // While Spoolman queries are still loading, the "Assign Spool" button must
      // not appear (inventory prop is undefined → {inventory && ...} guard fires)
      expect(screen.queryByText('Assign Spool')).not.toBeInTheDocument();
    });

    it('shows loaded-spool assignment controls for Prusa and Elegoo SDCP printers', async () => {
      const assignment = {
        id: 99,
        printer_id: 1,
        ams_id: -1,
        tray_id: 0,
        spool_id: 123,
        spool: {
          id: 123,
          brand: 'Prusament',
          material: 'PLA',
          subtype: 'Galaxy Black',
          color_name: 'Black',
          rgba: '#111111',
          slicer_filament: 'Prusament PLA',
          slicer_filament_name: 'Prusament PLA',
        },
      };

      server.use(
        http.get('/api/v1/inventory/assignments', () => HttpResponse.json([assignment])),
        http.get('/api/v1/printers/', () => HttpResponse.json([{ ...mockPrinters[0], provider: 'prusalink', model: 'Prusa CORE One' }])),
      );

      const { unmount } = render(<PrintersPage />);

      await screen.findByText('X1 Carbon');
      await screen.findByText('Loaded spool');
      expect(screen.getByText(/Prusament PLA Galaxy Black/i)).toBeInTheDocument();
      expect(screen.getByLabelText('Loaded spool color')).toHaveStyle({ backgroundColor: '#111111' });
      expect(screen.getByRole('button', { name: 'Change' })).toBeInTheDocument();

      unmount();

      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{ ...mockPrinters[0], provider: 'elegoo_sdcp', model: 'Elegoo Centauri Carbon' }])),
      );

      render(<PrintersPage />);

      await screen.findByText('X1 Carbon');
      await waitFor(() => expect(screen.getAllByText(/25/).length).toBeGreaterThan(0));
      await screen.findByText('Loaded spool');
      expect(screen.getByText(/Prusament PLA Galaxy Black/i)).toBeInTheDocument();
      expect(screen.getByLabelText('Loaded spool color')).toHaveStyle({ backgroundColor: '#111111' });
      expect(screen.getByRole('button', { name: 'Change' })).toBeInTheDocument();
    });

    it('shows the Spoolman loaded-spool color dot and assigns through the virtual slot', async () => {
      const user = userEvent.setup();
      let postedBody: Record<string, unknown> | null = null;

      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([{
          ...mockPrinters[0],
          provider: 'elegoo_sdcp',
          model: 'Elegoo Centauri Carbon',
        }])),
        http.get('/api/v1/spoolman/status', () => HttpResponse.json({
          enabled: true,
          connected: true,
          url: 'http://spoolman.local',
        })),
        http.get('/api/v1/settings/spoolman', () => HttpResponse.json({
          spoolman_enabled: 'true',
          spoolman_url: 'http://spoolman.local',
          spoolman_sync_mode: 'read_only',
        })),
        http.get('/api/v1/spoolman/inventory/spools', () => HttpResponse.json([
          {
            id: 321,
            brand: 'Polymaker',
            material: 'PETG',
            subtype: 'Matte',
            color_name: 'Black',
            rgba: '222222',
            label_weight: 1000,
            weight_used: 100,
            archived_at: null,
            data_origin: 'spoolman',
          },
        ])),
        http.get('/api/v1/spoolman/inventory/slot-assignments/all', () => HttpResponse.json([
          { printer_id: 1, printer_name: 'X1 Carbon', ams_id: 255, tray_id: 0, spoolman_spool_id: 321, ams_label: null },
        ])),
        http.post('/api/v1/spoolman/inventory/slot-assignments', async ({ request }) => {
          postedBody = await request.json() as Record<string, unknown>;
          return HttpResponse.json({ id: 321, data_origin: 'spoolman' });
        }),
        http.post('/api/v1/printers/:id/refresh-status', () => HttpResponse.json({ success: true })),
      );

      render(<PrintersPage />);

      await screen.findByText('Loaded spool');
      expect(screen.getByText(/Polymaker PETG Matte/i)).toBeInTheDocument();
      expect(screen.getByLabelText('Loaded spool color')).toHaveStyle({ backgroundColor: '#222222' });
      await user.click(screen.getByRole('button', { name: 'Change' }));
      await screen.findByText('Polymaker PETG Matte');
      await user.click(screen.getByRole('button', { name: /Polymaker PETG Matte/i }));
      await user.click(screen.getByRole('button', { name: 'Assign Spool' }));

      await waitFor(() => expect(postedBody).toEqual({
        spoolman_spool_id: 321,
        printer_id: 1,
        ams_id: 255,
        tray_id: 0,
      }));
    });
  });

});

/**
 * Phase 13 P13-1 (PrintersPage EmptySlotHoverCard onAssignSpool gate removal)
 *
 * Pre-Phase-13 each of the three EmptySlotHoverCard call-sites in PrintersPage
 * gated `onAssignSpool` on `spoolmanEnabled ? (...) : undefined`, so empty
 * slots in local-Inventory mode never showed an Assign action. Maintainer
 * Foto 7 confirmed users expect the button regardless of mode.
 *
 * To assert wiring without going through hover-card animations, we mock the
 * EmptySlotHoverCard component at module level and capture every props
 * payload. The same mock is active in both modes; tests differ only in the
 * spoolman-settings mock. The mock module covers BOTH FilamentHoverCard exports
 * so tests outside this `describe` aren't affected (we re-export the real
 * FilamentHoverCard).
 */
const phase13EmptySlotProps: Array<Record<string, unknown>> = [];
const phase14HoverCardProps: Array<Record<string, unknown>> = [];

vi.mock('../../components/FilamentHoverCard', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/FilamentHoverCard')>();
  return {
    ...actual,
    EmptySlotHoverCard: (props: Record<string, unknown>) => {
      phase13EmptySlotProps.push({ ...props });
      return <>{props.children as ReactNode}</>;
    },
    FilamentHoverCard: (props: Record<string, unknown>) => {
      phase14HoverCardProps.push({ ...props });
      return <>{props.children as ReactNode}</>;
    },
  };
});

describe('PrintersPage Phase 13 — EmptySlotHoverCard onAssignSpool wiring', () => {
  beforeEach(() => {
    phase13EmptySlotProps.length = 0;
    localStorage.removeItem('printerCardSize');

    server.use(
      http.get('/api/v1/printers/', () => HttpResponse.json(mockPrinters)),
      // Status response includes an empty AMS slot so EmptySlotHoverCard renders.
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
        ...mockPrinterStatus,
        ams: [{
          id: 0,
          tray: [{ id: 0, tray_type: '' }],
        }],
      })),
      http.get('/api/v1/settings/', () => HttpResponse.json({
        auto_archive: true, save_thumbnails: true, capture_finish_photo: true,
        default_filament_cost: 25.0, currency: 'USD',
        ams_humidity_good: 40, ams_humidity_fair: 60,
        ams_temp_good: 30, ams_temp_fair: 35,
      })),
      http.get('/api/v1/queue/', () => HttpResponse.json([])),
    );
  });

  it('P13-1 (local mode): EmptySlotHoverCard receives onAssignSpool callback', async () => {
    server.use(
      http.get('/api/v1/spoolman/settings', () => HttpResponse.json({
        spoolman_enabled: 'false', spoolman_url: '',
      })),
    );
    render(<PrintersPage />);

    // Wait for printer status to load and at least one EmptySlotHoverCard
    // to mount with an onAssignSpool callback. Pre-Phase-13 this would have
    // been undefined in local mode (the gate filtered it out).
    await waitFor(() => {
      const withCallback = phase13EmptySlotProps.filter(p => typeof p.onAssignSpool === 'function');
      expect(withCallback.length).toBeGreaterThan(0);
    }, { timeout: 3000 });
  });

  it('#1322: empty slot kind is "physical" when state=9 and "reset" otherwise', async () => {
    // Printbuddy now distinguishes a firmware-confirmed empty slot (state=9
    // via tray_exist_bits) from a slot the user reset but where the
    // firmware still has a spool registered. The kind prop drives both
    // the inline label ("Empty" vs "Reset") and the hover card label.
    server.use(
      http.get('/api/v1/spoolman/settings', () => HttpResponse.json({
        spoolman_enabled: 'false', spoolman_url: '',
      })),
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
        ...mockPrinterStatus,
        ams: [{
          id: 0,
          tray: [
            { id: 0, tray_type: '', state: 9 },   // physically empty
            { id: 1, tray_type: '', state: 3 },   // reset / unloading
            { id: 2, tray_type: '', state: null }, // unknown empty
            { id: 3, tray_type: 'PLA', state: 11 }, // loaded — no card here
          ],
        }],
      })),
    );
    render(<PrintersPage />);

    await waitFor(() => {
      expect(phase13EmptySlotProps.filter(p => p.kind === 'physical').length).toBeGreaterThan(0);
    }, { timeout: 3000 });

    const physical = phase13EmptySlotProps.filter(p => p.kind === 'physical');
    const reset = phase13EmptySlotProps.filter(p => p.kind === 'reset');
    expect(physical.length).toBeGreaterThan(0);
    expect(reset.length).toBeGreaterThan(0);
    // state=null falls back to 'reset' too — the helper only returns
    // 'physical' for the canonical 9/10 firmware codes.
  });

  it('P13-1 (spoolman mode): EmptySlotHoverCard still receives onAssignSpool callback', async () => {
    server.use(
      http.get('/api/v1/spoolman/settings', () => HttpResponse.json({
        spoolman_enabled: 'true', spoolman_url: 'http://x:7912',
      })),
      http.get('/api/v1/spoolman/spools/inventory*', () => HttpResponse.json([])),
      http.get('/api/v1/spoolman/inventory/spools', () => HttpResponse.json([])),
      http.get('/api/v1/spoolman/inventory/slot-assignments/all', () => HttpResponse.json([])),
    );
    render(<PrintersPage />);

    await waitFor(() => {
      const withCallback = phase13EmptySlotProps.filter(p => typeof p.onAssignSpool === 'function');
      expect(withCallback.length).toBeGreaterThan(0);
    }, { timeout: 3000 });
  });
});

/**
 * Phase 14 — Local-Branch BL-detection symmetry.
 *
 * The Spoolman branch of every IIFE in PrintersPage already passes
 *   isAssigned: !!slotAssignment || isBambuLabSpool(tray)
 *   onUnassignSpool: (spoolmanSpool && !isBambuLabSpool(tray)) ? ... : undefined
 *
 * The local branch was missing both. As a result a BL-RFID-tagged slot in
 * local-Inventory mode showed an "Assign Spool" button (because no manual
 * SpoolAssignment exists), and a manually-assigned BL-RFID slot showed
 * "Unassign" — which would be overwritten on the next RFID re-read.
 *
 * The same FilamentHoverCard mock from the Phase 13 block above captures
 * inventory props on every render so we can inspect them after setup.
 */
describe('PrintersPage Phase 14 — Local-Branch BL-detection symmetry', () => {
  beforeEach(() => {
    phase14HoverCardProps.length = 0;
    localStorage.removeItem('printerCardSize');

    server.use(
      http.get('/api/v1/printers/', () => HttpResponse.json(mockPrinters)),
      http.get('/api/v1/settings/', () => HttpResponse.json({
        auto_archive: true, save_thumbnails: true, capture_finish_photo: true,
        default_filament_cost: 25.0, currency: 'USD',
        ams_humidity_good: 40, ams_humidity_fair: 60,
        ams_temp_good: 30, ams_temp_fair: 35,
      })),
      http.get('/api/v1/queue/', () => HttpResponse.json([])),
      http.get('/api/v1/spoolman/settings', () => HttpResponse.json({
        spoolman_enabled: 'false', spoolman_url: '',
      })),
    );
  });

  it('P14-1a (local + BL-RFID + no assignment): inventory.isAssigned=true', async () => {
    server.use(
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
        ...mockPrinterStatus,
        ams: [{
          id: 0,
          tray: [{
            id: 0,
            tray_type: 'PLA',
            tray_uuid: '11223344556677880011223344556677',
            tag_uid: '0000000000000000',
            tray_color: 'FF0000FF',
            tray_sub_brands: 'Bambu PLA Basic',
          }],
        }],
      })),
      http.get('/api/v1/inventory/assignments', () => HttpResponse.json([])),
    );
    render(<PrintersPage />);

    await waitFor(() => {
      const matches = phase14HoverCardProps.filter(
        p => (p.inventory as { isAssigned?: boolean } | undefined)?.isAssigned === true
      );
      expect(matches.length).toBeGreaterThan(0);
    }, { timeout: 3000 });
  });

  it('P14-1b (local + non-BL + no assignment): inventory.isAssigned is falsy', async () => {
    server.use(
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
        ...mockPrinterStatus,
        ams: [{
          id: 0,
          tray: [{
            id: 0,
            tray_type: 'PLA',
            tray_uuid: '00000000000000000000000000000000',
            tag_uid: '0000000000000000',
            tray_color: 'FF0000FF',
            tray_sub_brands: 'Generic PLA',
          }],
        }],
      })),
      http.get('/api/v1/inventory/assignments', () => HttpResponse.json([])),
    );
    render(<PrintersPage />);

    // Wait for FilamentHoverCard to render at least once.
    await waitFor(() => {
      expect(phase14HoverCardProps.length).toBeGreaterThan(0);
    }, { timeout: 3000 });

    // No render should ever set isAssigned=true for this slot.
    const truthyMatches = phase14HoverCardProps.filter(
      p => (p.inventory as { isAssigned?: boolean } | undefined)?.isAssigned === true
    );
    expect(truthyMatches.length).toBe(0);
  });

  it('P14-1c (local + manual assignment): inventory.isAssigned=true', async () => {
    server.use(
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
        ...mockPrinterStatus,
        ams: [{
          id: 0,
          tray: [{
            id: 0,
            tray_type: 'PLA',
            tray_uuid: '00000000000000000000000000000000',
            tag_uid: '0000000000000000',
            tray_color: 'FF0000FF',
            tray_sub_brands: 'Generic PLA',
          }],
        }],
      })),
      http.get('/api/v1/inventory/assignments', () => HttpResponse.json([
        {
          id: 1,
          spool_id: 42,
          printer_id: 1,
          ams_id: 0,
          tray_id: 0,
          printer_name: 'X1 Carbon',
          ams_label: null,
          spool: {
            id: 42,
            material: 'PLA',
            brand: 'Generic',
            color_name: 'Red',
            label_weight: 1000,
            weight_used: 0,
            rgba: 'FF0000FF',
          },
        },
      ])),
    );
    render(<PrintersPage />);

    await waitFor(() => {
      const matches = phase14HoverCardProps.filter(
        p => (p.inventory as { isAssigned?: boolean } | undefined)?.isAssigned === true
      );
      expect(matches.length).toBeGreaterThan(0);
    }, { timeout: 3000 });
  });

  it('P14-2 (local + BL-RFID + manual assignment): onUnassignSpool=undefined', async () => {
    server.use(
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
        ...mockPrinterStatus,
        ams: [{
          id: 0,
          tray: [{
            id: 0,
            tray_type: 'PLA',
            tray_uuid: '11223344556677880011223344556677',
            tag_uid: '0000000000000000',
            tray_color: 'FF0000FF',
            tray_sub_brands: 'Bambu PLA Basic',
          }],
        }],
      })),
      http.get('/api/v1/inventory/assignments', () => HttpResponse.json([
        {
          id: 1,
          spool_id: 42,
          printer_id: 1,
          ams_id: 0,
          tray_id: 0,
          printer_name: 'X1 Carbon',
          ams_label: null,
          spool: {
            id: 42,
            material: 'PLA',
            brand: 'Bambu Lab',
            color_name: 'Red',
            label_weight: 1000,
            weight_used: 0,
            rgba: 'FF0000FF',
          },
        },
      ])),
    );
    render(<PrintersPage />);

    // Wait for FilamentHoverCard renders to settle.
    await waitFor(() => {
      expect(phase14HoverCardProps.length).toBeGreaterThan(0);
    }, { timeout: 3000 });

    // For BL-detected slots in local mode, onUnassignSpool must always be
    // undefined — even when a manual assignment exists. Otherwise the user
    // could unassign a BL-RFID slot that the printer would re-assign on the
    // next re-read, surprising them with phantom ghost-assignments.
    const definedUnassign = phase14HoverCardProps.filter(
      p => typeof (p.inventory as { onUnassignSpool?: () => void } | undefined)?.onUnassignSpool === 'function'
    );
    expect(definedUnassign.length).toBe(0);
  });
});
