"""Utility functions for converting between filament_id and setting_id formats, and shared filament constants.

Bambu printers use two ID formats for filament presets:
  - **filament_id** (aka tray_info_idx): e.g. "GFL05", "GFG02", "GFA00"
    Reported by printer firmware (RFID tags, AMS status).
  - **setting_id**: e.g. "GFSL05", "GFSG02", "GFSA00"
    Used by BambuStudio / Bambu Cloud API to resolve presets.

The only difference for official Bambu filaments is an "S" inserted after "GF".
User presets (starting with "P") use the same ID in both contexts.
"""

MATERIAL_TEMPS: dict[str, tuple[int, int]] = {
    "PLA": (190, 230),
    "PETG": (220, 260),
    "ABS": (240, 270),
    "ASA": (240, 270),
    "TPU": (200, 240),
    "PA": (260, 290),
    "PC": (250, 280),
    "PVA": (190, 210),
    "PLA-CF": (210, 240),
    "PETG-CF": (240, 270),
    "PA-CF": (270, 300),
}

GENERIC_FILAMENT_IDS: dict[str, str] = {
    "PLA": "GFL99",
    "PETG": "GFG99",
    "ABS": "GFB99",
    "ASA": "GFB98",
    "PC": "GFC99",
    "PA": "GFN99",
    "NYLON": "GFN99",
    "TPU": "GFU99",
    "PVA": "GFS99",
    "HIPS": "GFS98",
    "PLA-CF": "GFL98",
    "PETG-CF": "GFG98",
    "PA-CF": "GFN98",
    "PETG HF": "GFG96",
}

_COMPOSITE_VARIANT_ALIASES: dict[str, tuple[str, ...]] = {
    "CF": ("CF", "CARBON FIBER", "CARBON FIBRE"),
}


def _contains_variant_alias(value: str, variant: str) -> bool:
    normalized = value.upper().replace("_", " ").replace("-", " ")
    tokens = set(normalized.split())
    if variant in tokens:
        return True
    return any(alias in normalized for alias in _COMPOSITE_VARIANT_ALIASES.get(variant, ()))


def _candidate_with_variant(material: str, variant: str) -> str:
    for suffix in (f"-{variant}", f" {variant}", f"_{variant}"):
        if material.endswith(suffix):
            return f"{material[: -len(suffix)].strip(' -_')}-{variant}"
    return f"{material}-{variant}"


def effective_bambu_material(material: str | None, subtype: str | None = None) -> str:
    """Return the Bambu-facing material type for AMS configuration.

    Printbuddy and Spoolman can store composite materials either as a real
    material (``PLA-CF``) or as base material + variant (``PLA`` + ``CF``).
    The Bambu AMS command must use the composite material in ``tray_type``;
    otherwise the printer reports plain ``PLA`` and 3MF AMS mapping for
    ``PLA-CF`` cannot match it.
    """
    mat = (material or "").strip().upper()
    sub = (subtype or "").strip().upper()
    if not mat:
        return ""

    if mat in GENERIC_FILAMENT_IDS and "-" in mat:
        return mat

    for variant in _COMPOSITE_VARIANT_ALIASES:
        if _contains_variant_alias(mat, variant):
            candidate = _candidate_with_variant(mat, variant)
            if candidate in GENERIC_FILAMENT_IDS:
                return candidate
        if sub and _contains_variant_alias(sub, variant):
            candidate = f"{mat}-{variant}"
            if candidate in GENERIC_FILAMENT_IDS:
                return candidate

    return mat


def generic_bambu_filament_id(material: str | None, subtype: str | None = None) -> str:
    """Return the generic Bambu filament_id for a material, if known."""
    effective = effective_bambu_material(material, subtype)
    return GENERIC_FILAMENT_IDS.get(effective) or GENERIC_FILAMENT_IDS.get(effective.split("-")[0].split(" ")[0]) or ""


def filament_id_to_setting_id(filament_id: str) -> str:
    """Convert filament_id → setting_id (e.g. "GFL05" → "GFSL05").

    - Already a setting_id ("GFS…") → returned unchanged.
    - User presets ("P…") → returned unchanged.
    - Empty / unknown → returned unchanged.
    """
    if not filament_id:
        return filament_id

    # User presets start with "P" - leave unchanged
    if filament_id.startswith("P"):
        return filament_id

    # Official Bambu presets: GFx## -> GFSx##
    if filament_id.startswith("GF") and len(filament_id) >= 4:
        # Already a setting_id (has S after GF)
        if filament_id[2] == "S":
            return filament_id
        return f"GFS{filament_id[2:]}"

    return filament_id


def setting_id_to_filament_id(setting_id: str) -> str:
    """Convert setting_id → filament_id (e.g. "GFSL05" → "GFL05").

    - Already a filament_id ("GF" without "S") → returned unchanged.
    - User presets ("P…") → returned unchanged.
    - Empty / unknown → returned unchanged.
    """
    if not setting_id:
        return setting_id

    # User presets start with "P" - leave unchanged
    if setting_id.startswith("P"):
        return setting_id

    # Setting_id format: GFSx## -> GFx##  (remove the "S")
    if setting_id.startswith("GFS") and len(setting_id) >= 5:
        return f"GF{setting_id[3:]}"

    return setting_id


def normalize_slicer_filament(slicer_filament: str | None) -> tuple[str, str]:
    """Normalize a slicer_filament value into (tray_info_idx, setting_id).

    The slicer_filament field on a spool can be stored in either format:
      - filament_id: "GFL05"  (from RFID tag scan)
      - setting_id:  "GFSL05" or "GFSL05_07"  (from cloud preset picker)

    Returns (tray_info_idx, setting_id) with version suffixes stripped.
    """
    raw = slicer_filament or ""
    if not raw:
        return ("", "")

    # Strip version suffix (e.g. "GFSL05_07" → "GFSL05")
    base = raw.split("_")[0] if "_" in raw else raw

    tray_info_idx = setting_id_to_filament_id(base)
    sid = filament_id_to_setting_id(base)

    return (tray_info_idx, sid)
