from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from models.route import Package, Route


@dataclass
class MultiPackageStop:
    street: str
    city: str
    postal_code: str
    package_count: int
    seqs: List[int] = field(default_factory=list)


@dataclass
class DedupResult:
    total_packages: int
    unique_stops: int
    multi_package_stops: List[MultiPackageStop]


def _normalize_key(street: str, postal_code: str) -> Tuple[str, str]:
    norm_street = street.strip().lower()
    norm_street = " ".join(norm_street.split())
    norm_postal = postal_code.strip().upper()
    norm_postal = " ".join(norm_postal.split())
    return (norm_street, norm_postal)


def deduplicate(route: Route) -> DedupResult:
    stop_map: Dict[Tuple[str, str], List[Package]] = {}

    for pkg in route.packages:
        key = _normalize_key(pkg.street, pkg.postal_code)
        if key not in stop_map:
            stop_map[key] = []
        stop_map[key].append(pkg)

    multi_stops: List[MultiPackageStop] = []

    for (norm_street, norm_postal), pkgs in stop_map.items():
        street = pkgs[0].street
        city = pkgs[0].city
        postal = pkgs[0].postal_code
        count = len(pkgs)
        seqs = sorted(p.seq for p in pkgs)

        if count > 1:
            multi_stops.append(MultiPackageStop(
                street=street,
                city=city,
                postal_code=postal,
                package_count=count,
                seqs=seqs,
            ))

    multi_stops.sort(key=lambda m: m.package_count, reverse=True)

    stop_addresses_str = "\n".join(f"{s}" for s, _ in stop_map.keys())
    unique_count = len(stop_map)

    saved = sum(m.package_count - 1 for m in multi_stops)

    return DedupResult(
        total_packages=route.total_packages,
        unique_stops=unique_count,
        multi_package_stops=multi_stops,
    )
