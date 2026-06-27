import pytest
from models.route import Route, Package
from core.deduplicator import deduplicate, _normalize_key


def make_package(seq: int, street: str, postal: str, city: str = "Gatineau") -> Package:
    return Package(
        code="D123456789012",
        tracking_id="INTLCMI123456789",
        seq=seq,
        street=street,
        city=city,
        province="QC",
        postal_code=postal,
        dimensions="10x10x10 cm",
        full_address=f"{street}, {city}, QC {postal}, Canada",
    )


class TestNormalizeKey:
    def test_normalizes_street(self):
        assert _normalize_key("  rue   St-Louis ", "J8T 4H6") == ("rue st-louis", "J8T 4H6")

    def test_differs_by_postal(self):
        k1 = _normalize_key("27 rue du Lacaune", "J8V3R9")
        k2 = _normalize_key("27 rue du Lacaune", "J8V3R8")
        assert k1 != k2


class TestDeduplicate:
    def test_single_stop(self):
        route = Route(code="GATI9275", date="2026-06-27")
        route.packages = [make_package(1, "27 rue du Lacaune", "J8V3R9")]
        result = deduplicate(route)
        assert result.total_packages == 1
        assert result.unique_stops == 1
        assert result.multi_package_stops == []

    def test_multi_package_same_stop(self):
        route = Route(code="GATI9275", date="2026-06-27")
        route.packages = [
            make_package(5, "27 rue du Lacaune", "J8V3R9"),
            make_package(6, "27 rue du Lacaune", "J8V3R9"),
            make_package(7, "27 rue du Lacaune", "J8V3R9"),
            make_package(8, "27 rue du Lacaune", "J8V3R9"),
            make_package(9, "27 rue du Lacaune", "J8V3R9"),
        ]
        result = deduplicate(route)
        assert result.total_packages == 5
        assert result.unique_stops == 1
        assert len(result.multi_package_stops) == 1
        assert result.multi_package_stops[0].package_count == 5
        assert result.multi_package_stops[0].seqs == [5, 6, 7, 8, 9]

    def test_multiple_distinct_stops(self):
        route = Route(code="GATI9275", date="2026-06-27")
        route.packages = [
            make_package(1, "27 rue du Lacaune", "J8V3R9"),
            make_package(2, "2015 rue Saint-Louis", "J8T4H6"),
            make_package(3, "73 rue Stephane", "J8V1T8"),
        ]
        result = deduplicate(route)
        assert result.total_packages == 3
        assert result.unique_stops == 3
        assert result.multi_package_stops == []

    def test_mixed_stops(self):
        route = Route(code="GATI9275", date="2026-06-27")
        route.packages = [
            make_package(1, "27 rue du Lacaune", "J8V3R9"),
            make_package(2, "27 rue du Lacaune", "J8V3R9"),
            make_package(3, "2015 rue Saint-Louis", "J8T4H6"),
        ]
        result = deduplicate(route)
        assert result.total_packages == 3
        assert result.unique_stops == 2
        assert len(result.multi_package_stops) == 1
        assert result.multi_package_stops[0].street == "27 rue du Lacaune"

    def test_normalized_deduplication(self):
        route = Route(code="GATI9275", date="2026-06-27")
        route.packages = [
            make_package(1, "27 rue du Lacaune", "J8V3R9"),
            make_package(2, "27  rue  du  Lacaune", "J8V3R9"),
        ]
        result = deduplicate(route)
        assert result.unique_stops == 1
