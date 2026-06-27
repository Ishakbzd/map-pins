import csv
import os
from typing import List

from models.route import Route
from core.deduplicator import deduplicate


def export_route_csv(route: Route, output_dir: str) -> str:
    city_label = route.city if route.city else "Route"
    filename = f"{city_label}_{route.code}_Route.csv"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Stop", "Full Address", "Street", "City", "Province",
            "Postal Code", "Tracking ID", "Package Code", "Dimensions",
        ])

        for i, pkg in enumerate(route.packages, start=1):
            writer.writerow([
                i,
                pkg.full_address,
                pkg.street,
                pkg.city,
                pkg.province,
                pkg.postal_code,
                pkg.tracking_id,
                pkg.code,
                pkg.dimensions,
            ])

    return filepath


def export_route_summary(route: Route, output_dir: str) -> str:
    city_label = route.city if route.city else "Route"
    filename = f"{city_label}_{route.code}_Summary.txt"
    filepath = os.path.join(output_dir, filename)

    result = deduplicate(route)

    lines = [
        f"Route: {route.code}",
        f"Date: {route.date}",
        f"Total packages: {result.total_packages}",
        f"Unique stops: {result.unique_stops}",
        f"Multi-package stops: {result.total_packages - result.unique_stops} packages saved",
        "",
    ]

    if result.multi_package_stops:
        lines.append("Multi-package stop detail:")
        for stop in result.multi_package_stops:
            seqs_str = ", ".join(str(s) for s in stop.seqs)
            lines.append(
                f"  [{stop.package_count} pkgs] {stop.street}, {stop.city} "
                f"QC {stop.postal_code} -- seq {seqs_str}"
            )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))

    return filepath


def export_routes(routes: List[Route], output_dir: str) -> List[str]:
    exported = []
    for route in routes:
        csv_path = export_route_csv(route, output_dir)
        summary_path = export_route_summary(route, output_dir)
        exported.append(csv_path)
        exported.append(summary_path)
    return exported
