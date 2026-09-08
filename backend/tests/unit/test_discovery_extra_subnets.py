"""Unit tests for DISCOVERY_EXTRA_SUBNETS parsing and merge."""

from unittest.mock import patch

from backend.app.services.network_utils import get_discovery_subnets, parse_extra_subnets


class TestParseExtraSubnets:
    def test_empty(self):
        assert parse_extra_subnets("") == []
        assert parse_extra_subnets("   ") == []
        assert parse_extra_subnets(None) == []

    def test_single_cidr(self):
        assert parse_extra_subnets("10.0.0.0/24") == ["10.0.0.0/24"]

    def test_multiple_and_normalize(self):
        assert parse_extra_subnets("10.0.0.0/24, 192.168.1.5/24") == [
            "10.0.0.0/24",
            "192.168.1.0/24",
        ]

    def test_skips_invalid(self):
        assert parse_extra_subnets("not-a-cidr, 10.0.0.0/24, 999.1.1.1/24") == ["10.0.0.0/24"]

    def test_dedupes(self):
        assert parse_extra_subnets("10.0.0.0/24,10.0.0.0/24") == ["10.0.0.0/24"]


class TestGetDiscoverySubnets:
    def test_merges_extra_after_local(self):
        local = [{"subnet": "10.2.0.0/24"}]
        with (
            patch(
                "backend.app.services.network_utils.get_network_interfaces",
                return_value=local,
            ),
            patch(
                "backend.app.services.network_utils.parse_extra_subnets",
                return_value=["10.0.0.0/24"],
            ),
        ):
            assert get_discovery_subnets() == ["10.2.0.0/24", "10.0.0.0/24"]

    def test_does_not_duplicate_local(self):
        local = [{"subnet": "10.0.0.0/24"}]
        with (
            patch(
                "backend.app.services.network_utils.get_network_interfaces",
                return_value=local,
            ),
            patch(
                "backend.app.services.network_utils.parse_extra_subnets",
                return_value=["10.0.0.0/24"],
            ),
        ):
            assert get_discovery_subnets() == ["10.0.0.0/24"]
