from backend.app.services.printer_providers.moonraker import MoonrakerPrinterClient


def _moonraker_status_with_cfs(active_filament="A"):
    return {
        "print_stats": {
            "state": "printing",
            "filename": "Cube_PLA_19m27s.gcode",
            "print_duration": 120.0,
        },
        "virtual_sdcard": {"progress": 0.25},
        "display_status": {"progress": 0.25},
        "extruder": {"temperature": 215.0, "target": 220.0},
        "heater_bed": {"temperature": 59.0, "target": 60.0},
        "box": {
            "filament": 1,
            "state": "connect",
            "auto_refill": 1,
            "enable": 1,
            "same_material": [
                ["101001", "00A2989", ["T1A"], "PLA"],
                ["001001", "0fff014", ["T1B"], "PLA"],
                ["001001", "0ffffff", ["T1C"], "PLA"],
                ["001001", "09ea7ae", ["T1D"], "PLA"],
            ],
            "T1": {
                "state": "connect",
                "filament": active_filament,
                "temperature": "25",
                "dry_and_humidity": "48",
                "version": "1.4.2",
                "sn": "10000949645L325LWVB",
                "mode": "2",
                "remain_len": ["41", "100", "100", "100"],
                "color_value": ["00A2989", "0fff014", "0ffffff", "09ea7ae"],
                "material_type": ["101001", "001001", "001001", "001001"],
                "vender": [
                    "7C2250276A210100100A29890165000001000000",
                    "unknown",
                    "unknown",
                    "unknown",
                ],
                "change_color_num": ["0", -1, -1, -1],
            },
            "T2": {"state": "None"},
            "T3": {"state": "None"},
            "T4": {"state": "None"},
        },
        "filament_rack": {
            "remain_material_color": "0ffffff",
            "remain_material_type": "001001",
            "remain_material_velocity": 575.0,
        },
        "filament_switch_sensor filament_sensor": {"filament_detected": True},
    }


def _moonraker_status_with_snapmaker_u1():
    return {
        "print_stats": {
            "state": "printing",
            "filename": "U1_four_nozzle_test.gcode",
            "print_duration": 300.0,
            "estimated_time": 900.0,
            "info": {"current_layer": 8, "total_layer": 25},
        },
        "virtual_sdcard": {"progress": 0.2656660911143578, "file_position": 30003, "file_size": 112935},
        "display_status": {"progress": 0.41},
        "heater_bed": {"temperature": 60.0, "target": 65.0},
        "toolhead": {"extruder": "extruder2"},
        "temperature_sensor cavity": {"temperature": 34.5},
        "extruder": {"temperature": 205.0, "target": 210.0, "nozzle_diameter": 0.4},
        "extruder1": {"temperature": 35.0, "target": 0.0, "nozzle_diameter": 0.4},
        "extruder2": {"temperature": 215.0, "target": 220.0, "nozzle_diameter": 0.6},
        "extruder3": {"temperature": 31.0, "target": 0.0, "nozzle_diameter": 0.8},
        "filament_feed left": {
            "extruder1": {
                "module_exist": True,
                "filament_detected": True,
                "channel_state": "preload_finish",
                "channel_error": "ok",
            },
            "extruder0": {
                "module_exist": True,
                "filament_detected": True,
                "channel_state": "preload_finish",
                "channel_error": "ok",
                "filament_info": {
                    "MAIN_TYPE": "PLA",
                    "SUB_TYPE": "Matte",
                    "VENDOR": "Snapmaker",
                    "RGB_1": 0x3366CC,
                    "WEIGHT": 1000,
                    "remaining_weight": 640,
                    "CARD_UID": "ABC123",
                },
            },
        },
        "filament_feed right": {
            "extruder2": {
                "module_exist": True,
                "filament_detected": True,
                "channel_state": "load_finish",
                "channel_action_state": "load_finish",
                "channel_error": "ok",
                "tray_type": "PETG",
                "tray_color": "#ff8800",
                "remain": 42,
            },
            "extruder3": {
                "module_exist": True,
                "filament_detected": False,
                "channel_state": "wait_insert",
                "channel_error": "ok",
            },
        },
        "print_task_config": {
            "filament_vendor": ["Snapmaker", "Snapmaker", "Polymaker", "NONE"],
            "filament_type": ["PLA", "PLA", "PLA", "NONE"],
            "filament_sub_type": ["SnapSpeed", "SnapSpeed", "PolyLite", "NONE"],
            "filament_color_rgba": ["E72F1DFF", "080A0DFF", "1E88E5FF", "FFFFFFFF"],
            "filament_official": [True, True, False, False],
            "filament_sku": [900002, 900001, 0, 0],
            "filament_edit": [False, False, True, True],
            "filament_exist": [True, True, True, False],
        },
    }


def test_moonraker_normalizes_creality_k2_cfs_box_to_ams_shape(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    status = _moonraker_status_with_cfs("A")
    base_status = {
        key: status[key] for key in ("print_stats", "virtual_sdcard", "display_status", "extruder", "heater_bed")
    }
    cfs_status = {key: status[key] for key in ("box", "filament_rack", "filament_switch_sensor filament_sensor")}
    monkeypatch.setattr(client, "_query_objects", lambda object_names: base_status)
    monkeypatch.setattr(client, "_query_cfs_status", lambda *args, **kwargs: cfs_status)
    monkeypatch.setattr(client, "_query_fan_status", lambda *args, **kwargs: {})

    assert client.request_status_update() is True

    assert client.state.state == "RUNNING"
    assert client.state.progress == 25.0
    assert client.state.raw_data["box"]["state"] == "connect"
    assert client.state.raw_data["filament_rack"]["remain_material_type"] == "001001"
    assert client.state.raw_data["cfs"]["active_slots"] == ["T1A"]
    assert client.state.tray_now == 0
    assert client.state.raw_data["cfs"]["filament_detected"] is True

    ams = client.state.raw_data["ams"]
    assert len(ams) == 1
    assert ams[0]["id"] == 0
    assert ams[0]["humidity"] == 48
    assert ams[0]["temp"] == 25
    assert ams[0]["name"] == "CFS T1"
    assert ams[0]["tray"] == [
        {
            "id": 0,
            "slot": "T1A",
            "tray_type": "PLA",
            "material_code": "101001",
            "tray_color": "#0A2989",
            "remain": 41,
            "active": True,
            "state": 11,
            "tray_uuid": "T1A",
            "tag_uid": "",
            "vendor": "7C2250276A210100100A29890165000001000000",
        },
        {
            "id": 1,
            "slot": "T1B",
            "tray_type": "PLA",
            "material_code": "001001",
            "tray_color": "#fff014",
            "remain": 100,
            "active": False,
            "state": 11,
            "tray_uuid": "T1B",
            "tag_uid": "",
            "vendor": "unknown",
        },
        {
            "id": 2,
            "slot": "T1C",
            "tray_type": "PLA",
            "material_code": "001001",
            "tray_color": "#ffffff",
            "remain": 100,
            "active": False,
            "state": 11,
            "tray_uuid": "T1C",
            "tag_uid": "",
            "vendor": "unknown",
        },
        {
            "id": 3,
            "slot": "T1D",
            "tray_type": "PLA",
            "material_code": "001001",
            "tray_color": "#9ea7ae",
            "remain": 100,
            "active": False,
            "state": 11,
            "tray_uuid": "T1D",
            "tag_uid": "",
            "vendor": "unknown",
        },
    ]


def test_moonraker_keeps_cfs_trays_when_active_filament_is_none(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    status = _moonraker_status_with_cfs("None")
    base_status = {
        key: status[key] for key in ("print_stats", "virtual_sdcard", "display_status", "extruder", "heater_bed")
    }
    cfs_status = {key: status[key] for key in ("box", "filament_rack", "filament_switch_sensor filament_sensor")}
    monkeypatch.setattr(client, "_query_objects", lambda object_names: base_status)
    monkeypatch.setattr(client, "_query_cfs_status", lambda *args, **kwargs: cfs_status)
    monkeypatch.setattr(client, "_query_fan_status", lambda *args, **kwargs: {})

    assert client.request_status_update() is True

    assert client.state.raw_data["cfs"]["active_slots"] == []
    assert client.state.tray_now == 255
    trays = client.state.raw_data["ams"][0]["tray"]
    assert [tray["slot"] for tray in trays] == ["T1A", "T1B", "T1C", "T1D"]
    assert all(tray["active"] is False for tray in trays)
    assert all(tray["state"] == 11 for tray in trays)


def test_moonraker_normalizes_snapmaker_u1_nozzles_chamber_and_feed_slots(monkeypatch):
    client = MoonrakerPrinterClient("http://snapmaker-u1.local:7125", printer_model="Snapmaker U1")
    status = _moonraker_status_with_snapmaker_u1()
    base_status = {
        key: status[key] for key in ("print_stats", "virtual_sdcard", "display_status", "heater_bed", "toolhead")
    }
    u1_status = {
        key: value
        for key, value in status.items()
        if key
        in {
            "temperature_sensor cavity",
            "extruder",
            "extruder1",
            "extruder2",
            "extruder3",
            "filament_feed left",
            "filament_feed right",
            "print_task_config",
        }
    }
    monkeypatch.setattr(client, "_query_objects", lambda object_names: base_status)
    monkeypatch.setattr(client, "_query_cfs_status", lambda *args, **kwargs: {})
    monkeypatch.setattr(client, "_query_snapmaker_u1_status", lambda *args, **kwargs: u1_status)
    monkeypatch.setattr(client, "_query_fan_status", lambda *args, **kwargs: {})

    assert client.request_status_update() is True

    assert client.state.state == "RUNNING"
    assert client.state.progress == 41.0
    assert client.state.remaining_time == 10
    assert client.state.layer_num == 8
    assert client.state.total_layers == 25
    assert client.state.active_extruder == 2
    assert client.state.temperatures["chamber"] == 34.5
    assert client.state.temperatures["nozzle"] == 205.0
    assert client.state.temperatures["nozzle_3"] == 215.0
    assert [nozzle.nozzle_diameter for nozzle in client.state.nozzles] == ["0.4", "0.4", "0.6", "0.8"]

    ams = client.state.raw_data["ams"]
    snapmaker = client.state.raw_data["snapmaker_u1"]
    assert ams[0]["name"] == "Snapmaker U1 Feeders"
    assert ams[0]["module_type"] == "snapmaker_u1"
    assert [tray["slot"] for tray in ams[0]["tray"]] == ["U1-E0", "U1-E1", "U1-E2", "U1-E3"]
    assert ams[0]["tray"][0]["tray_type"] == "PLA"
    assert ams[0]["tray"][0]["tray_sub_brands"] == "SnapSpeed"
    assert ams[0]["tray"][0]["tray_color"] == "#E72F1D"
    assert ams[0]["tray"][0]["remain"] == 64
    assert ams[0]["tray"][0]["remaining_weight"] == 640
    assert ams[0]["tray"][0]["filament_source"] == "rfid"
    assert ams[0]["tray"][2]["tray_type"] == "PLA"
    assert ams[0]["tray"][2]["tray_sub_brands"] == "PolyLite"
    assert ams[0]["tray"][2]["tray_color"] == "#1E88E5"
    assert ams[0]["tray"][2]["filament_source"] == "manual"
    assert ams[0]["tray"][2]["loaded_to_extruder"] is True
    assert ams[0]["tray"][2]["active"] is True
    assert ams[0]["tray"][3]["state"] == 9
    assert ams[0]["tray"][3]["tray_color"] is None
    assert snapmaker["loaded_to_extruder_slots"] == ["U1-E2"]
    assert snapmaker["loaded_to_feeder_slots"] == ["U1-E0", "U1-E1", "U1-E2"]


def test_moonraker_snapmaker_u1_clears_active_extruder_when_toolhead_reports_none(monkeypatch):
    client = MoonrakerPrinterClient("http://snapmaker-u1.local:7125", printer_model="Snapmaker U1")
    status = _moonraker_status_with_snapmaker_u1()
    status["toolhead"] = {"extruder": ""}
    base_status = {
        key: status[key] for key in ("print_stats", "virtual_sdcard", "display_status", "extruder", "heater_bed")
    }
    u1_status = {
        key: value
        for key, value in status.items()
        if key not in {"print_stats", "virtual_sdcard", "display_status", "extruder", "heater_bed"}
    }
    monkeypatch.setattr(client, "_query_objects", lambda object_names: base_status)
    monkeypatch.setattr(client, "_query_cfs_status", lambda *args, **kwargs: {})
    monkeypatch.setattr(client, "_query_fan_status", lambda *args, **kwargs: {})
    monkeypatch.setattr(client, "_query_snapmaker_u1_status", lambda *args, **kwargs: u1_status)

    assert client.request_status_update() is True

    assert client.state.active_extruder == -1
    assert client.state.tray_now == 255
    trays = client.state.raw_data["ams"][0]["tray"]
    assert [tray["slot"] for tray in trays if tray.get("active")] == []
    assert client.state.raw_data["snapmaker_u1"]["active_extruder"] is None


def test_moonraker_controls_snapmaker_u1_cavity_fan(monkeypatch):
    client = MoonrakerPrinterClient("http://snapmaker-u1.local:7125", printer_model="Snapmaker U1")
    sent: list[str] = []
    monkeypatch.setattr(client, "_available_objects", lambda: ["fan", "fan_generic cavity_fan"])
    monkeypatch.setattr(client, "send_gcode", lambda script: sent.append(script) or True)

    assert client.set_fan_speed("chamber", 50) is True
    assert sent == ["SET_FAN_SPEED FAN=cavity_fan SPEED=0.50"]


def test_moonraker_controls_part_cooling_fan_with_m106(monkeypatch):
    client = MoonrakerPrinterClient("http://moonraker.local:7125", printer_model="Generic Klipper Printer")
    sent: list[str] = []
    monkeypatch.setattr(client, "_available_objects", lambda: ["fan"])
    monkeypatch.setattr(client, "send_gcode", lambda script: sent.append(script) or True)

    assert client.set_fan_speed("part", 50) is True
    assert sent == ["M106 S128"]


def test_moonraker_complete_state_clamps_progress_and_remaining_time(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    status = _moonraker_status_with_cfs("None")
    status["print_stats"] = {
        "state": "complete",
        "filename": "short-test.gcode",
        "print_duration": 90.0,
        "total_duration": 95.0,
    }
    # K2 firmware can leave display/virtual_sdcard progress behind on very short
    # jobs after print_stats has already moved to complete. Terminal states must
    # win over stale fractional progress so the dashboard and archive lifecycle
    # don't keep showing an in-progress ETA.
    status["virtual_sdcard"] = {"progress": 0.18, "file_position": 1234}
    status["display_status"] = {"progress": 0.18}
    base_status = {
        key: status[key] for key in ("print_stats", "virtual_sdcard", "display_status", "extruder", "heater_bed")
    }
    cfs_status = {key: status[key] for key in ("box", "filament_rack", "filament_switch_sensor filament_sensor")}
    monkeypatch.setattr(client, "_query_objects", lambda object_names: base_status)
    monkeypatch.setattr(client, "_query_cfs_status", lambda *args, **kwargs: cfs_status)
    monkeypatch.setattr(client, "_query_fan_status", lambda *args, **kwargs: {})

    assert client.request_status_update() is True

    assert client.state.state == "FINISH"
    assert client.state.progress == 100.0
    assert client.state.remaining_time == 0


def test_moonraker_uses_file_position_progress_when_fractional_progress_is_stale(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    status = _moonraker_status_with_cfs("A")
    status["print_stats"] = {
        "state": "printing",
        "filename": "tiny-cube.gcode",
        "print_duration": 30.0,
        "estimated_time": 90.0,
    }
    status["virtual_sdcard"] = {"progress": 0.21, "file_position": 6000, "file_size": 10000}
    status["display_status"] = {"progress": 0.21}
    base_status = {
        key: status[key] for key in ("print_stats", "virtual_sdcard", "display_status", "extruder", "heater_bed")
    }
    cfs_status = {key: status[key] for key in ("box", "filament_rack", "filament_switch_sensor filament_sensor")}
    monkeypatch.setattr(client, "_query_objects", lambda object_names: base_status)
    monkeypatch.setattr(client, "_query_cfs_status", lambda *args, **kwargs: cfs_status)
    monkeypatch.setattr(client, "_query_fan_status", lambda *args, **kwargs: {})

    assert client.request_status_update() is True

    assert client.state.state == "RUNNING"
    assert client.state.progress == 60.0
    assert client.state.remaining_time == 1


def test_moonraker_send_gcode_treats_verified_read_timeout_as_accepted(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    refreshed = False

    def timeout_post(path, data):
        raise __import__("httpx").ReadTimeout("timed out")

    def refresh_status():
        nonlocal refreshed
        refreshed = True
        client.state.connected = True
        return True

    monkeypatch.setattr(client, "_post", timeout_post)
    monkeypatch.setattr(client, "request_status_update", refresh_status)

    assert client.send_gcode("G28") is True
    assert refreshed is True


def test_moonraker_discovers_and_normalizes_webcams(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    client.state.connected = True  # skip live connect() in discover_webcams
    monkeypatch.setattr(
        client,
        "_get",
        lambda path: {
            "webcams": [
                {
                    "name": "Nozzle Cam",
                    "stream_url": "/webcam/?action=stream",
                    "snapshot_url": "http://camera.local/snapshot.jpg",
                }
            ]
        },
    )

    assert client.discover_webcams() == [
        {
            "name": "Nozzle Cam",
            # Relative webcam paths resolve to the UI host (port 80), not Moonraker :7125
            "stream_url": "http://k2-plus.local/webcam/?action=stream",
            "snapshot_url": "http://camera.local/snapshot.jpg",
            "camera_type": "mjpeg",
            "enabled": True,
            "raw": {
                "name": "Nozzle Cam",
                "stream_url": "/webcam/?action=stream",
                "snapshot_url": "http://camera.local/snapshot.jpg",
            },
        }
    ]


def test_moonraker_webcam_discovery_returns_empty_for_k2_without_moonraker_webcams(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    client.state.connected = True
    monkeypatch.setattr(client, "_get", lambda path: {"webcams": []})

    assert client.discover_webcams() == []


def test_moonraker_relative_webcam_url_uses_ui_port_not_api_port():
    from backend.app.services.printer_providers.moonraker import _absolute_moonraker_camera_url

    assert (
        _absolute_moonraker_camera_url(
            "http://10.0.0.126:7125",
            "/webcam/?action=stream",
        )
        == "http://10.0.0.126/webcam/?action=stream"
    )
    assert (
        _absolute_moonraker_camera_url(
            "http://10.0.0.126",
            "/webcam/?action=stream",
        )
        == "http://10.0.0.126/webcam/?action=stream"
    )


def test_moonraker_cfs_load_uses_verified_m8200_slot_select(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    sent: list[str] = []

    monkeypatch.setattr(client, "send_gcode", lambda script: sent.append(script) or True)

    assert client.ams_load_filament(2) is True

    assert sent == ["M8200 P\nM8200 L I=2\nM8200 O"]


def test_moonraker_cfs_unload_uses_verified_m8200_sequence(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    sent: list[str] = []

    monkeypatch.setattr(client, "send_gcode", lambda script: sent.append(script) or True)

    assert client.ams_unload_filament(1) is True

    assert sent == ["M8200 P\nM8200 C\nM8200 R\nM8200 O"]


def test_moonraker_cfs_load_rejects_invalid_slot():
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")

    assert client.ams_load_filament(16) is False


def test_moonraker_start_print_selects_mapped_cfs_slot_before_print(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    client.state.raw_data["cfs"] = {"type": "creality_cfs"}
    client.state.raw_data["ams"] = [{"id": 0, "module_type": "cfs", "tray": []}]
    client.state.tray_now = 0
    sent: list[str] = []
    posts: list[tuple[str, dict]] = []

    def send_gcode(script: str) -> bool:
        sent.append(script)
        if "M8200 L I=1" in script:
            client.state.tray_now = 1
        elif "M8200 R" in script:
            client.state.tray_now = 255
        return True

    monkeypatch.setattr(client, "send_gcode", send_gcode)
    monkeypatch.setattr(client, "request_status_update", lambda: True)
    monkeypatch.setattr(client, "_post", lambda path, payload: posts.append((path, payload)) or {})

    assert client.start_print("models/cube.gcode", ams_mapping=[1]) is True

    assert sent == [
        "M8200 P\nM8200 C\nM8200 R\nM8200 O",
        "M8200 P\nM8200 L I=1\nM8200 O",
    ]
    assert posts == [("printer/print/start", {"filename": "models/cube.gcode"})]


def test_moonraker_start_print_does_not_reload_already_selected_cfs_slot(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    client.state.raw_data["cfs"] = {"type": "creality_cfs"}
    client.state.raw_data["ams"] = [{"id": 0, "module_type": "cfs", "tray": []}]
    client.state.tray_now = 2
    sent: list[str] = []
    posts: list[tuple[str, dict]] = []

    monkeypatch.setattr(client, "send_gcode", lambda script: sent.append(script) or True)
    monkeypatch.setattr(client, "request_status_update", lambda: True)
    monkeypatch.setattr(client, "_post", lambda path, payload: posts.append((path, payload)) or {})

    assert client.start_print("models/cube.gcode", ams_mapping=[2]) is True

    assert sent == []
    assert posts == [("printer/print/start", {"filename": "models/cube.gcode"})]


def test_moonraker_start_print_aborts_when_cfs_slot_selection_cannot_be_verified(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    client.state.raw_data["cfs"] = {"type": "creality_cfs"}
    client.state.raw_data["ams"] = [{"id": 0, "module_type": "cfs", "tray": []}]
    client.state.tray_now = 0
    sent: list[str] = []
    posts: list[tuple[str, dict]] = []

    monkeypatch.setattr(client, "send_gcode", lambda script: sent.append(script) or True)
    monkeypatch.setattr(client, "request_status_update", lambda: True)
    monkeypatch.setattr(client, "_post", lambda path, payload: posts.append((path, payload)) or {})

    assert client.start_print("models/cube.gcode", ams_mapping=[1]) is False

    assert sent == [
        "M8200 P\nM8200 C\nM8200 R\nM8200 O",
        "M8200 P\nM8200 L I=1\nM8200 O",
    ]
    assert posts == []


def test_moonraker_cfs_refresh_is_disabled_after_k2_firmware_crash_report(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    sent: list[str] = []
    monkeypatch.setattr(client, "_get", lambda path: {"objects": ["box", "gcode_macro BOX_INFO_REFRESH"]})
    monkeypatch.setattr(client, "send_gcode", lambda script: sent.append(script) or True)

    assert client.ams_refresh_tray(0, 1) == (False, "CFS RFID refresh is disabled for Creality K2 printers")
    assert sent == []


def test_moonraker_list_files_accepts_storage_keyword_and_uses_it(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    requested: list[str] = []

    def fake_get(path):
        requested.append(path)
        return {"result": [{"path": "cube.gcode", "size": 42, "modified": 1700000000}]}

    monkeypatch.setattr(client, "_get", fake_get)

    files = client.list_files("/", storage="gcodes")

    assert requested == ["server/files/list?root=gcodes"]
    assert files[0]["name"] == "cube.gcode"


def test_moonraker_list_files_tries_common_k2_roots_when_default_root_is_empty(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")
    requested: list[str] = []

    def fake_get(path):
        requested.append(path)
        if path == "server/files/list?root=gcodes":
            return {"result": []}
        if path == "server/files/list?root=local":
            return {"result": [{"path": "benchy.gcode", "size": 100}]}
        return {"result": []}

    monkeypatch.setattr(client, "_get", fake_get)

    files = client.list_files("/")

    assert requested[:2] == ["server/files/list?root=gcodes", "server/files/list?root=local"]
    assert files[0]["name"] == "benchy.gcode"


def test_moonraker_list_files_returns_empty_when_valid_root_is_empty_and_fallback_roots_fail(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")

    def fake_get(path):
        if path == "server/files/list?root=gcodes":
            return {"result": []}
        raise RuntimeError("root not found")

    monkeypatch.setattr(client, "_get", fake_get)

    assert client.list_files("/") == []


def test_moonraker_list_files_filters_flat_root_listing_to_requested_folder(monkeypatch):
    client = MoonrakerPrinterClient("http://k2-plus.local:7125", printer_model="Creality K2 Plus")

    def fake_get(path):
        assert path == "server/files/list?root=gcodes&path=cache"
        return {
            "result": [
                {"path": "cube.gcode", "size": 42},
                {"path": "cache/cached-cube.gcode", "size": 100},
                {"path": "cache/nested/hidden.gcode", "size": 200},
                {"path": "models/model.gcode", "size": 300},
            ]
        }

    monkeypatch.setattr(client, "_get", fake_get)

    files = client.list_files("/cache", storage="gcodes")

    assert [file["name"] for file in files] == ["cached-cube.gcode", "nested"]
    assert [file["type"] for file in files] == ["file", "directory"]
    assert [file["path"] for file in files] == ["/cache/cached-cube.gcode", "/cache/nested"]
