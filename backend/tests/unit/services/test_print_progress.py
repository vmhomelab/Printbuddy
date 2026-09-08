"""Tests for effective print-progress calculation."""

from types import SimpleNamespace

from backend.app.services.print_progress import effective_print_progress, is_pre_print_stage


def test_raw_bambu_pre_print_payload_reports_zero_actual_progress():
    state = {"raw_data": {"mc_percent": 25, "stg_cur": 2, "layer_num": 0, "total_layer_num": 120}}

    assert is_pre_print_stage(state) is True
    assert effective_print_progress(state) == 0


def test_raw_bambu_layer_payload_uses_layer_progress():
    state = {"raw_data": {"mc_percent": 64, "stg_cur": 0, "layer_num": 32, "total_layer_num": 100}}

    assert effective_print_progress(state) == 32


def test_pre_print_stage_with_no_layers_reports_zero_actual_progress():
    state = SimpleNamespace(progress=25, layer_num=0, total_layers=120, stg_cur=2)

    assert is_pre_print_stage(state) is True
    assert effective_print_progress(state) == 0


def test_layer_progress_overrides_firmware_progress_after_printing_starts():
    state = SimpleNamespace(progress=30, layer_num=1, total_layers=100, stg_cur=0)

    assert effective_print_progress(state) == 1


def test_layer_progress_drives_real_milestone_progress():
    state = SimpleNamespace(progress=50, layer_num=25, total_layers=100, stg_cur=0)

    assert effective_print_progress(state) == 25


def test_raw_progress_is_preserved_when_layers_are_unknown_and_not_pre_print():
    state = SimpleNamespace(progress=42, layer_num=0, total_layers=0, stg_cur=0)

    assert effective_print_progress(state) == 42
