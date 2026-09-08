"""Integration coverage for virtual-printer print-queue ingestion."""

import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.config import settings
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.virtual_printer.manager import VirtualPrinterInstance


def _write_multi_plate_3mf(path: Path) -> None:
    """Create a minimal sliced 3MF containing three printable plates."""

    slice_info = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="prediction" value="600"/>
    <filament id="1" type="PLA" color="#ff0000" used_g="10.5" used_m="1.0"/>
  </plate>
  <plate>
    <metadata key="index" value="2"/>
    <metadata key="prediction" value="900"/>
    <filament id="2" type="PETG" color="#00ff00" used_g="20.0" used_m="2.0"/>
  </plate>
  <plate>
    <metadata key="index" value="3"/>
    <metadata key="prediction" value="1200"/>
    <filament id="3" type="ASA" color="#0000ff" used_g="30.0" used_m="3.0"/>
  </plate>
</config>
"""

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Metadata/slice_info.config", slice_info)
        zf.writestr("Metadata/plate_1.gcode", "; plate 1\n")
        zf.writestr("Metadata/plate_2.gcode", "; plate 2\n")
        zf.writestr("Metadata/plate_3.gcode", "; plate 3\n")
        zf.writestr("Metadata/project_settings.config", json.dumps({"print": {}}))


@pytest.mark.asyncio
@pytest.mark.integration
async def test_virtual_printer_print_queue_send_all_enqueues_each_plate(
    test_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """A VP print_queue upload with multiple plates creates one queue row per plate."""

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archives")
    settings.archive_dir.mkdir(parents=True, exist_ok=True)

    # Existing pending row proves the VP path appends instead of hard-coding position=1.
    existing = PrintQueueItem(archive_id=None, library_file_id=1, position=5, status="pending")
    db_session.add(existing)
    await db_session.commit()

    upload_path = tmp_path / "MultiPlate.gcode.3mf"
    _write_multi_plate_3mf(upload_path)

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    instance = VirtualPrinterInstance(
        vp_id=1,
        name="Queue VP",
        mode="print_queue",
        model="BL-P001",
        access_code="12345678",
        serial_suffix="391800001",
        auto_dispatch=False,
        queue_force_color_match=True,
        base_dir=tmp_path,
        session_factory=session_factory,
    )

    await instance._add_to_print_queue(upload_path, "192.0.2.10")

    result = await db_session.execute(
        select(PrintQueueItem).where(PrintQueueItem.archive_id.isnot(None)).order_by(PrintQueueItem.position)
    )
    queued = result.scalars().all()

    assert [item.plate_id for item in queued] == [1, 2, 3]
    assert [item.position for item in queued] == [6, 7, 8]
    assert [json.loads(item.required_filament_types) for item in queued] == [["PLA"], ["PETG"], ["ASA"]]
    assert all(item.manual_start is True for item in queued)
    assert all(item.filament_overrides for item in queued)
