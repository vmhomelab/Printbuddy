from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.services.elegoo_camera import (
    build_elegoo_sdcp_camera_url,
    get_effective_camera_source,
)

PrinterProvider = Literal["bambu", "klipper", "mainsail", "fluidd", "prusalink", "prusaconnect", "elegoo_sdcp"]
MOONRAKER_PROVIDERS = {"klipper", "mainsail", "fluidd"}
HTTP_PROVIDERS = MOONRAKER_PROVIDERS | {"prusalink", "prusaconnect", "elegoo_sdcp"}
PRUSA_CONNECT_MOBILE_BASE_URL = "https://connect-mobile-api.prusa3d.com"


def _synthetic_moonraker_serial(value: object) -> str:
    raw = str(value or "moonraker").strip().upper()
    # Keep synthetic serials within the existing DB column while avoiding
    # characters users commonly enter in hostnames / URLs that are awkward in
    # MQTT-topic-shaped UI assumptions elsewhere.
    normalized = "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-") or "MOONRAKER"
    return f"KLIPPER-{normalized}"[:50]


def _synthetic_prusalink_serial(value: object) -> str:
    raw = str(value or "prusalink").strip().upper()
    normalized = "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-") or "PRUSALINK"
    return f"PRUSALINK-{normalized}"[:50]


def _synthetic_prusa_connect_serial(value: object) -> str:
    raw = str(value or "prusaconnect").strip().upper()
    normalized = "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-") or "PRUSACONNECT"
    return f"PRUSACONNECT-{normalized}"[:50]


def _synthetic_elegoo_sdcp_serial(value: object) -> str:
    raw = str(value or "elegoo-sdcp").strip().upper()
    normalized = "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-") or "ELEGOO-SDCP"
    return f"ELEGOO-SDCP-{normalized}"[:50]


def infer_external_camera_type(camera_url: str) -> str:
    lower_url = camera_url.lower()
    if lower_url.startswith(("rtsp://", "rtsps://")):
        return "rtsp"
    if lower_url.startswith("/dev/video") or lower_url.startswith("usb://"):
        return "usb"
    if any(token in lower_url for token in ("/snapshot", "/frame")) or lower_url.split("?", 1)[0].endswith(
        (".jpg", ".jpeg", ".png", ".webp")
    ):
        return "snapshot"
    return "mjpeg"


def normalize_external_camera_update(update_data: dict) -> dict:
    """Normalize partial printer camera PATCH payloads.

    Creation uses PrinterBase's model validator, but settings edits arrive as a
    partial PrinterUpdate. If the UI/API patches only external_camera_url, leaving
    external_camera_enabled false means the camera button still opens the built-in
    Bambu stream path and the external camera never starts.
    """
    if "external_camera_url" not in update_data:
        return update_data

    camera_url = str(update_data.get("external_camera_url") or "").strip()
    if not camera_url:
        update_data["external_camera_url"] = None
        update_data["external_camera_enabled"] = False
        update_data["external_camera_type"] = None
        return update_data

    update_data["external_camera_url"] = camera_url
    update_data.setdefault("external_camera_enabled", True)
    if not str(update_data.get("external_camera_type") or "").strip():
        update_data["external_camera_type"] = infer_external_camera_type(camera_url)
    return update_data


class PrinterBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def _fill_http_provider_defaults(cls, data):
        if not isinstance(data, dict):
            return data
        provider = str(data.get("provider") or "bambu").strip().lower()
        if provider in MOONRAKER_PROVIDERS:
            if not str(data.get("serial_number") or "").strip():
                data["serial_number"] = _synthetic_moonraker_serial(data.get("ip_address") or data.get("api_url"))
            if not str(data.get("access_code") or "").strip():
                data["access_code"] = "moonraker"
            if not data.get("api_url") and data.get("ip_address"):
                data["api_url"] = f"http://{str(data['ip_address']).strip()}:7125"
        elif provider == "prusalink":
            if not str(data.get("serial_number") or "").strip():
                data["serial_number"] = _synthetic_prusalink_serial(data.get("ip_address") or data.get("api_url"))
            if not str(data.get("access_code") or "").strip():
                data["access_code"] = "prusalink"
            if not data.get("api_url") and data.get("ip_address"):
                data["api_url"] = f"http://{str(data['ip_address']).strip()}"
        elif provider == "prusaconnect":
            if not str(data.get("serial_number") or "").strip():
                data["serial_number"] = _synthetic_prusa_connect_serial(data.get("ip_address") or data.get("api_url"))
            if not str(data.get("access_code") or "").strip():
                data["access_code"] = "prusaconnect"
            if not data.get("api_url"):
                data["api_url"] = PRUSA_CONNECT_MOBILE_BASE_URL
        elif provider == "elegoo_sdcp":
            if not str(data.get("serial_number") or "").strip():
                data["serial_number"] = _synthetic_elegoo_sdcp_serial(data.get("ip_address"))
            if not str(data.get("access_code") or "").strip():
                data["access_code"] = "elegoo-sdcp"
            if not str(data.get("external_camera_url") or "").strip():
                data["external_camera_url"] = build_elegoo_sdcp_camera_url(data.get("ip_address"))
                data["external_camera_type"] = "mjpeg"
                data["external_camera_enabled"] = bool(data["external_camera_url"])
                return data
        if provider in HTTP_PROVIDERS:
            camera_url = str(data.get("external_camera_url") or "").strip()
            if not camera_url:
                data["external_camera_url"] = None
                data["external_camera_type"] = None
                data["external_camera_enabled"] = False
                return data
            data["external_camera_url"] = camera_url
            data["external_camera_enabled"] = True
            if not str(data.get("external_camera_type") or "").strip():
                data["external_camera_type"] = infer_external_camera_type(camera_url)
        return data

    serial_number: str = Field(..., min_length=1, max_length=50)

    @field_validator("serial_number")
    @classmethod
    def _normalize_serial_number(cls, v: str) -> str:
        """Uppercase and trim the serial number.

        Bambu serial numbers are uppercase alphanumeric, and the MQTT report
        topic ``device/<serial>/report`` is case-sensitive. A serial entered
        in the wrong case (or with stray whitespace) connects and subscribes
        without error but never receives a message — the printer publishes to
        the correctly-cased topic, so every status field stays unknown (#1465).
        Normalising on input makes the subscribed topic always match.
        """
        normalized = v.strip().upper()
        if not normalized:
            raise ValueError("serial_number must not be blank")
        return normalized

    ip_address: str = Field(
        ...,
        max_length=253,
        pattern=r"^(\d{1,3}(\.\d{1,3}){3}|[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*)$",
    )
    access_code: str = Field(..., min_length=1, max_length=20)
    provider: PrinterProvider = "bambu"
    api_url: str | None = Field(default=None, max_length=500)
    auth_token: str | None = Field(default=None, max_length=500)
    provider_options: str | None = Field(default=None, max_length=4000)
    model: str | None = None
    location: str | None = None  # Group/location name
    auto_archive: bool = True
    reconnect_interval_seconds: int = Field(default=30, ge=10, le=3600)
    external_camera_url: str | None = None
    external_camera_type: str | None = None  # "mjpeg", "rtsp", "snapshot", "usb"
    external_camera_enabled: bool = False
    external_camera_snapshot_url: str | None = None  # Optional single-frame override; #1177
    camera_rotation: int = 0  # 0, 90, 180, 270 degrees


class PrinterCreate(PrinterBase):
    pass


class PlateDetectionROI(BaseModel):
    """Region of interest for plate detection (percentages 0.0-1.0)."""

    x: float = Field(..., ge=0.0, le=1.0)  # X start %
    y: float = Field(..., ge=0.0, le=1.0)  # Y start %
    w: float = Field(..., ge=0.0, le=1.0)  # Width %
    h: float = Field(..., ge=0.0, le=1.0)  # Height %


class PrinterUpdate(BaseModel):
    name: str | None = None
    ip_address: str | None = Field(
        default=None,
        max_length=253,
        pattern=r"^(\d{1,3}(\.\d{1,3}){3}|[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*)$",
    )
    access_code: str | None = None
    provider: PrinterProvider | None = None
    api_url: str | None = Field(default=None, max_length=500)
    auth_token: str | None = Field(default=None, max_length=500)
    provider_options: str | None = Field(default=None, max_length=4000)
    model: str | None = None
    location: str | None = None
    is_active: bool | None = None
    auto_archive: bool | None = None
    reconnect_interval_seconds: int | None = Field(default=None, ge=10, le=3600)
    print_hours_offset: float | None = None
    external_camera_url: str | None = None
    external_camera_type: str | None = None
    external_camera_enabled: bool | None = None
    external_camera_snapshot_url: str | None = None  # #1177
    camera_rotation: int | None = None  # 0, 90, 180, 270 degrees
    plate_detection_enabled: bool | None = None
    plate_detection_roi: PlateDetectionROI | None = None


class PrinterResponse(PrinterBase):
    id: int
    is_active: bool
    nozzle_count: int = 1  # 1 or 2, auto-detected from MQTT
    print_hours_offset: float = 0.0
    external_camera_url: str | None = None
    external_camera_type: str | None = None
    external_camera_enabled: bool = False
    external_camera_snapshot_url: str | None = None  # #1177
    camera_rotation: int = 0  # 0, 90, 180, 270 degrees
    plate_detection_enabled: bool = False
    plate_detection_roi: PlateDetectionROI | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_roi(cls, printer) -> "PrinterResponse":
        """Create response from ORM model, converting ROI fields to nested object."""
        effective_camera = get_effective_camera_source(printer)
        data = {
            "id": printer.id,
            "name": printer.name,
            "serial_number": printer.serial_number,
            "ip_address": printer.ip_address,
            "access_code": printer.access_code,
            "provider": getattr(printer, "provider", "bambu"),
            "api_url": getattr(printer, "api_url", None),
            "auth_token": getattr(printer, "auth_token", None),
            "provider_options": getattr(printer, "provider_options", None),
            "model": printer.model,
            "location": printer.location,
            "auto_archive": printer.auto_archive,
            "reconnect_interval_seconds": getattr(printer, "reconnect_interval_seconds", 30),
            "external_camera_url": effective_camera.url,
            "external_camera_type": effective_camera.camera_type,
            "external_camera_enabled": effective_camera.enabled,
            "external_camera_snapshot_url": effective_camera.snapshot_url,
            "camera_rotation": printer.camera_rotation,
            "is_active": printer.is_active,
            "nozzle_count": printer.nozzle_count,
            "print_hours_offset": printer.print_hours_offset,
            "plate_detection_enabled": printer.plate_detection_enabled,
            "created_at": printer.created_at,
            "updated_at": printer.updated_at,
        }
        # Build ROI object if any ROI field is set
        if any(
            [
                printer.plate_detection_roi_x is not None,
                printer.plate_detection_roi_y is not None,
                printer.plate_detection_roi_w is not None,
                printer.plate_detection_roi_h is not None,
            ]
        ):
            data["plate_detection_roi"] = PlateDetectionROI(
                x=printer.plate_detection_roi_x or 0.15,
                y=printer.plate_detection_roi_y or 0.35,
                w=printer.plate_detection_roi_w or 0.70,
                h=printer.plate_detection_roi_h or 0.55,
            )
        return cls(**data)


class HMSErrorResponse(BaseModel):
    code: str
    attr: int = 0  # Attribute value for constructing wiki URL
    module: int
    severity: int  # 1=fatal, 2=serious, 3=common, 4=info


class AMSTray(BaseModel):
    id: int
    tray_color: str | None = None
    tray_type: str | None = None
    tray_sub_brands: str | None = None  # Full name like "PLA Basic", "PETG HF"
    tray_id_name: str | None = None  # Bambu filament ID like "A00-Y2" (can decode to color)
    tray_info_idx: str | None = None  # Filament preset ID like "GFA00"
    remain: int = 0
    k: float | None = None  # Pressure advance value (from tray or K-profile lookup)
    cali_idx: int | None = None  # Calibration index for K-profile lookup
    tag_uid: str | None = None  # RFID tag UID (any tag)
    tray_uuid: str | None = None  # Bambu Lab spool UUID (32-char hex)
    nozzle_temp_min: int | None = None  # Min nozzle temperature
    nozzle_temp_max: int | None = None  # Max nozzle temperature
    drying_temp: int | None = None  # RFID-recommended drying temp
    drying_time: int | None = None  # RFID-recommended drying time (hours)
    state: int | None = None  # AMS tray state: 9=empty, 10=spool present not loaded, 11=loaded


class AMSUnit(BaseModel):
    id: int
    name: str | None = None
    humidity: int | None = None
    temp: float | None = None
    is_ams_ht: bool = False  # True for AMS-HT (single spool), False for regular AMS (4 spools)
    tray: list[AMSTray] = []
    serial_number: str = ""  # AMS unit serial number (sn from MQTT)
    sw_ver: str = ""  # AMS firmware version (from get_version info.module)
    dry_time: int = 0  # Minutes remaining (0 = not drying, >0 = drying active)
    dry_status: int = 0  # 0=Off, 1=Checking, 2=Drying, 3=Cooling, 4=Stopping, 5=Error
    dry_sub_status: int = 0  # 0=Off, 1=Heating, 2=Dehumidify
    dry_sf_reason: list[int] = []  # Cannot-dry reasons from firmware (see CannotDryReason)
    module_type: str = ""  # "ams", "n3f", "n3s"


class NozzleInfoResponse(BaseModel):
    nozzle_type: str = ""  # "stainless_steel" or "hardened_steel"
    nozzle_diameter: str = ""  # e.g., "0.4"


class NozzleRackSlot(BaseModel):
    """H2C nozzle rack slot (6-position tool-changer dock)."""

    id: int = 0
    nozzle_type: str = ""
    nozzle_diameter: str = ""
    wear: int | None = None
    stat: int | None = None  # Nozzle status (e.g. mounted/docked)
    max_temp: int = 0  # Max temperature rating °C (0 = not set)
    serial_number: str = ""  # Nozzle serial number
    filament_color: str = ""  # RGBA hex ("00000000" = no filament)
    filament_id: str = ""  # Bambu filament ID
    filament_type: str = ""  # Material type (e.g. "PLA", "PETG")


class AmsLabelBody(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    ams_serial: str = Field(default="", max_length=50)


class FilaSwitchResponse(BaseModel):
    """Filament Track Switch (FTS) state — accessory that mediates AMS-to-extruder routing.

    When installed, the AMS info field reports bits 8-11 = 0xE (uninitialized)
    because slots are dynamically routed via the FTS rather than tied to a
    specific extruder. Frontend uses `installed` to suppress the per-extruder
    slot filter in the print modal. See #1162.
    """

    installed: bool = False
    # in[track] = currently loaded slot for that track (-1 = empty)
    in_slots: list[int] = []
    # out[track] = extruder this track terminates at (0 = right, 1 = left)
    out_extruders: list[int] = []
    stat: int = 0
    info: int = 0


class PrintOptionsResponse(BaseModel):
    """AI detection and print options from xcam data."""

    # Core AI detectors
    spaghetti_detector: bool = False
    print_halt: bool = False
    halt_print_sensitivity: str = "medium"  # Spaghetti sensitivity
    first_layer_inspector: bool = False
    printing_monitor: bool = False
    buildplate_marker_detector: bool = False
    allow_skip_parts: bool = False
    # Additional AI detectors (decoded from cfg bitmask)
    nozzle_clumping_detector: bool = True
    nozzle_clumping_sensitivity: str = "medium"
    pileup_detector: bool = True
    pileup_sensitivity: str = "medium"
    airprint_detector: bool = True
    airprint_sensitivity: str = "medium"
    auto_recovery_step_loss: bool = True
    filament_tangle_detect: bool = False


class PrinterStatus(BaseModel):
    id: int
    name: str
    connected: bool
    state: str | None = None
    current_print: str | None = None
    subtask_name: str | None = None
    gcode_file: str | None = None
    progress: float | None = None
    remaining_time: int | None = None
    layer_num: int | None = None
    total_layers: int | None = None
    temperatures: dict | None = None
    cover_url: str | None = None
    hms_errors: list[HMSErrorResponse] = []
    ams: list[AMSUnit] = []
    ams_exists: bool = False
    vt_tray: list[AMSTray] = []  # Virtual tray / external spool(s)
    sdcard: bool = False  # SD card inserted
    store_to_sdcard: bool = False  # Store sent files on SD card
    timelapse: bool = False  # Timelapse recording active
    ipcam: bool = False  # Live view enabled
    wifi_signal: int | None = None  # WiFi signal strength in dBm
    wired_network: bool = False  # Ethernet connection detected
    door_open: bool = False  # Enclosure door open (X1/P1S/P2S/H2*)
    nozzles: list[NozzleInfoResponse] = []  # Nozzle hardware info (index 0=left/primary, 1=right)
    nozzle_rack: list[NozzleRackSlot] = []  # H2C 6-nozzle tool-changer rack
    print_options: PrintOptionsResponse | None = None  # AI detection and print options
    # Calibration stage tracking
    stg_cur: int = -1  # Current stage number (-1 = not calibrating)
    stg_cur_name: str | None = None  # Human-readable current stage name
    stg: list[int] = []  # List of stage numbers in calibration sequence
    # Air conditioning mode (0=cooling, 1=heating)
    airduct_mode: int = 0
    # Print speed level (1=silent, 2=standard, 3=sport, 4=ludicrous)
    speed_level: int = 2
    # Chamber light on/off
    chamber_light: bool = False
    # Active extruder for dual nozzle (0=right, 1=left)
    active_extruder: int = 0
    # AMS mapping for dual nozzle: which AMS is connected to which nozzle
    ams_mapping: list[int] = []
    # Per-AMS extruder map: {ams_id: extruder_id} where 0=right, 1=left
    ams_extruder_map: dict[str, int] = {}
    # Filament Track Switch (FTS) accessory — when installed, AMS reports
    # bits 8-11 = 0xE (uninitialized) and routing is dynamic via the FTS. See #1162.
    fila_switch: FilaSwitchResponse | None = None
    # Currently loaded tray (global ID): 254 = external spool, 255 = no filament
    tray_now: int = 255
    # AMS status for filament change tracking
    # Main status: 0=idle, 1=filament_change, 2=rfid_identifying, 3=assist, 4=calibration
    ams_status_main: int = 0
    # Sub status: specific step within filament change (when main=1)
    # Known values: 4=retraction, 6=load verification, 7=purge
    ams_status_sub: int = 0
    # mc_print_sub_stage - filament change step indicator used by OrcaSlicer/BambuStudio
    mc_print_sub_stage: int = 0
    # Timestamp of last AMS data update (for RFID refresh detection)
    last_ams_update: float = 0.0
    # Number of printable objects in current print (for skip objects feature)
    printable_objects_count: int = 0
    # Fan speeds (0-100 percentage, None if not available for this model)
    cooling_fan_speed: int | None = None  # Part cooling fan
    big_fan1_speed: int | None = None  # Auxiliary fan
    big_fan2_speed: int | None = None  # Chamber/exhaust fan
    heatbreak_fan_speed: int | None = None  # Hotend heatbreak fan
    # Firmware version (from info.module[name="ota"].sw_ver)
    firmware_version: str | None = None
    # Provider-specific connection/diagnostic details safe for display in the UI.
    connection_details: dict[str, Any] | None = None
    # Developer LAN mode: True = enabled, False = disabled (MQTT encryption), None = unknown
    developer_mode: bool | None = None
    # Queue: printer is awaiting the user to acknowledge the build plate is cleared
    # after a finished/failed print. Persisted across restarts (#961).
    awaiting_plate_clear: bool = False
    # AMS drying support
    supports_drying: bool = False
    # Linked archive for the active print (resolved via subtask_id). Frontend uses
    # this to fetch plate metadata and show the plate name when the source 3MF is
    # multi-plate (#881 follow-up).
    current_archive_id: int | None = None
    # 1-indexed plate number parsed from gcode_file (e.g. /Metadata/plate_2.gcode).
    # Set for every active print regardless of plate count; the frontend decides
    # whether to render it based on current_archive_id's is_multi_plate flag.
    current_plate_id: int | None = None


class DiagnosticCheck(BaseModel):
    """One connection-diagnostic check result.

    ``id`` is a stable key (port_mqtt, port_ftps, port_rtsps, network_mode,
    subnet, mqtt_auth, developer_mode); the frontend renders the localized
    title and fix text from id + status. ``params`` carries interpolation
    values (e.g. network mode, IP addresses) for that text.
    """

    id: str
    status: str  # "pass" | "fail" | "warn" | "skip"
    params: dict = Field(default_factory=dict)


class PrinterDiagnosticResult(BaseModel):
    """Result of a printer connection diagnostic run."""

    printer_id: int | None = None
    ip_address: str
    overall: str  # "ok" | "warnings" | "problems"
    checks: list[DiagnosticCheck]


class DiagnosticRequest(BaseModel):
    """Pre-save (Add Printer) connection diagnostic request.

    serial_number + access_code are optional: when both are present the
    diagnostic also probes MQTT credentials, otherwise only the
    network-level checks run.
    """

    ip_address: str
    serial_number: str | None = None
    access_code: str | None = None
