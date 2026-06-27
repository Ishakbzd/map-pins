import pytest
from models.route import Route, Package
from core.pdf_parser import _clean_address_artifacts, _normalize_city, _normalize_street


class TestCleanAddressArtifacts:
    def test_removes_trailing_ca(self):
        assert _clean_address_artifacts("123 rue Test CA") == "123 rue Test"

    def test_collapses_whitespace(self):
        assert _clean_address_artifacts("123  rue   Test") == "123 rue Test"

    def test_strips_whitespace(self):
        assert _clean_address_artifacts("  123 rue Test  ") == "123 rue Test"


class TestNormalizeCity:
    def test_gatineau_variants(self):
        assert _normalize_city("gatineau") == "Gatineau"
        assert _normalize_city("GATINEAU") == "Gatineau"

    def test_l_ange_gardien(self):
        assert _normalize_city("l'ange-gardien") == "L'Ange-Gardien"

    def test_unknown_city(self):
        assert _normalize_city("montreal") == "Montreal"


class TestNormalizeStreet:
    def test_collapses_spaces(self):
        assert _normalize_street("123  rue   Test") == "123 rue Test"
