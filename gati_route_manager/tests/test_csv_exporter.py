import csv
import os
import tempfile

import pytest
from models.route import Route, Package
from core.csv_exporter import export_route_csv, export_route_summary


def make_route() -> Route:
    route = Route(code="GATI9275", date="2026-06-27")
    route.packages = [
        Package(
            code="D123456789012",
            tracking_id="INTLCMI123456789",
            seq=1,
            street="27 rue du Lacaune",
            city="Gatineau",
            province="QC",
            postal_code="J8V3R9",
            dimensions="10x10x10 cm",
            full_address="27 rue du Lacaune, Gatineau, QC J8V3R9, Canada",
        ),
        Package(
            code="D987654321098",
            tracking_id="INTLCMI987654321",
            seq=2,
            street="2015 rue Saint-Louis",
            city="Gatineau",
            province="QC",
            postal_code="J8T4H6",
            dimensions="20x15x10 cm",
            full_address="2015 rue Saint-Louis, Gatineau, QC J8T4H6, Canada",
        ),
    ]
    return route


class TestExportRouteCsv:
    def test_csv_header(self):
        route = make_route()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_route_csv(route, tmpdir)
            with open(path, encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                header = next(reader)
                assert header == [
                    "Stop", "Full Address", "Street", "City", "Province",
                    "Postal Code", "Tracking ID", "Package Code", "Dimensions",
                ]

    def test_csv_data_rows(self):
        route = make_route()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_route_csv(route, tmpdir)
            with open(path, encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                next(reader)
                rows = list(reader)
                assert len(rows) == 2
                assert rows[0][1] == "27 rue du Lacaune, Gatineau, QC J8V3R9, Canada"
                assert rows[0][2] == "27 rue du Lacaune"
                assert rows[1][1] == "2015 rue Saint-Louis, Gatineau, QC J8T4H6, Canada"

    def test_utf8_bom(self):
        route = make_route()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_route_csv(route, tmpdir)
            with open(path, "rb") as f:
                bom = f.read(3)
                assert bom == b"\xef\xbb\xbf"

    def test_filename_format(self):
        route = make_route()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_route_csv(route, tmpdir)
            assert os.path.basename(path) == "Gatineau_GATI9275_Route.csv"


class TestExportRouteSummary:
    def test_summary_content(self):
        route = make_route()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_route_summary(route, tmpdir)
            with open(path, encoding="utf-8") as f:
                content = f.read()
                assert "Route: GATI9275" in content
                assert "Date: 2026-06-27" in content
                assert "Total packages: 2" in content
                assert "Unique stops: 2" in content

    def test_filename_format(self):
        route = make_route()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_route_summary(route, tmpdir)
            assert os.path.basename(path) == "Gatineau_GATI9275_Summary.txt"
