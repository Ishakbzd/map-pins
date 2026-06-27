import re
from typing import List, Optional

import pdfplumber

from models.route import Package, Route


ROUTE_PATTERN = re.compile(r"^(?:Route\s*[-:]?\s*)?(GATI\d{4})$", re.IGNORECASE)
PACKAGE_CODE_PATTERN = re.compile(r"D\d{12}")
TRACKING_ID_PATTERN = re.compile(r"INTLCMI\d{9}")
POSTAL_CODE_PATTERN = re.compile(r"J[0-9][A-Z]\s*[0-9][A-Z][0-9]")
SEQ_PATTERN = re.compile(r"\b(\d{1,3})\b")
DATE_PATTERN = re.compile(r"From (\d{4}-\d{2}-\d{2})")
TOTAL_PACKAGES_PATTERN = re.compile(r"Total number of packages\s*:\s*(\d+)", re.IGNORECASE)
DIMENSIONS_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:cm\s*)?x\s*\d+(?:\.\d+)?\s*(?:cm\s*)?x\s*\d+(?:\.\d+)?\s*(?:cm|in|mm)?",
    re.IGNORECASE,
)


CITIES = {
    "gatineau": "Gatineau",
    "l'ange-gardien": "L'Ange-Gardien",
    "cantley": "Cantley",
    "chelsea": "Chelsea",
}

PROVINCE = "QC"


def _normalize_city(city: str) -> str:
    city_lower = city.strip().lower()
    for key, val in CITIES.items():
        if key in city_lower:
            return val
    return city.strip().title()


def _normalize_street(street: str) -> str:
    return re.sub(r"\s+", " ", street.strip())


def _clean_address_artifacts(address: str) -> str:
    address = re.sub(r"\s+", " ", address.strip())
    address = re.sub(r"\bCA\b$", "", address).strip()
    address = re.sub(r"\s+", " ", address).strip()
    return address


def _extract_date(text: str) -> str:
    match = DATE_PATTERN.search(text)
    return match.group(1) if match else ""


def _extract_postal_code(text: str) -> Optional[str]:
    match = POSTAL_CODE_PATTERN.search(text)
    if match:
        return re.sub(r"\s+", "", match.group(0))
    return None


def _parse_single_route(route_code: str, date: str, lines: List[str]) -> Route:
    route = Route(code=route_code, date=date)
    current_buffer = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        has_tracking = bool(TRACKING_ID_PATTERN.search(stripped))
        has_package_code = bool(PACKAGE_CODE_PATTERN.search(stripped))
        has_seq = bool(SEQ_PATTERN.search(stripped) if re.match(r"^\d{1,3}\b", stripped) else False)

        if has_tracking and has_package_code:
            if current_buffer:
                _try_extract_package(route, current_buffer, date)
            current_buffer = stripped
        else:
            if current_buffer:
                current_buffer += " " + stripped
            elif has_package_code or has_tracking:
                current_buffer = stripped

    if current_buffer:
        _try_extract_package(route, current_buffer, date)

    route.packages.sort(key=lambda p: p.seq)
    return route


def _try_extract_package(route: Route, text: str, date: str) -> None:
    try:
        package = _extract_package(text, route.code, date)
        if package:
            route.packages.append(package)
    except Exception:
        pass


def _extract_package(text: str, route_code: str, date: str) -> Optional[Package]:
    code_match = PACKAGE_CODE_PATTERN.search(text)
    tracking_match = TRACKING_ID_PATTERN.search(text)
    postal_match = POSTAL_CODE_PATTERN.search(text)

    if not code_match or not tracking_match:
        return None

    code = code_match.group(0)
    tracking_id = tracking_match.group(0)

    tracking_end = tracking_match.end()

    remaining_after_id = text[tracking_end:].strip()

    seq = 0
    seq_match = re.search(r"^\s*(\d{1,3})\b", remaining_after_id)
    if seq_match:
        seq = int(seq_match.group(1))
        address_part = remaining_after_id[seq_match.end():].strip()
    else:
        address_part = remaining_after_id

    address_part = _clean_address_artifacts(address_part)

    postal_code = ""
    if postal_match:
        postal_code = re.sub(r"\s+", "", postal_match.group(0))

    dimensions = ""
    dim_match = DIMENSIONS_PATTERN.search(address_part)
    if dim_match:
        dimensions = dim_match.group(0).strip()
        address_part = address_part[:dim_match.start()].strip()

    address_part = re.sub(r"\s+", " ", address_part).strip()

    if address_part.endswith("CA"):
        address_part = address_part[:-2].strip()
    address_part = address_part.strip()

    province = PROVINCE
    known_city = ""
    street = address_part

    qc_idx = address_part.lower().find(" qc ")
    if qc_idx == -1:
        qc_idx = address_part.lower().find("qc ")

    if qc_idx >= 0:
        before_qc = address_part[:qc_idx].strip()
    else:
        before_qc = address_part

    for city_key in sorted(CITIES.keys(), key=len, reverse=True):
        if city_key in before_qc.lower():
            city_found = _normalize_city(city_key)
            city_idx = before_qc.lower().rindex(city_key)
            street = before_qc[:city_idx].strip()
            known_city = city_found
            break

    if known_city:
        street = _normalize_street(street.rstrip(",").rstrip())
        full_address = f"{street}, {known_city}, QC {postal_code}, Canada" if postal_code else f"{street}, {known_city}, QC, Canada"
        return Package(
            code=code,
            tracking_id=tracking_id,
            seq=seq,
            street=street,
            city=known_city,
            province=province,
            postal_code=postal_code,
            dimensions=dimensions,
            full_address=full_address,
        )

    full_addr = f"{address_part}, QC {postal_code}, Canada" if postal_code else f"{address_part}, QC, Canada"
    return Package(
        code=code,
        tracking_id=tracking_id,
        seq=seq,
        street=address_part,
        city="",
        province=province,
        postal_code=postal_code,
        dimensions=dimensions,
        full_address=full_addr,
    )


SKIP_LINE_PATTERNS = [
    re.compile(r"^Intelcom Courrier", re.IGNORECASE),
    re.compile(r"^From \d{4}-\d{2}-\d{2}"),
    re.compile(r"^To \d{4}-\d{2}-\d{2}"),
    re.compile(r"^Code\s+Tracking", re.IGNORECASE),
    re.compile(r"^Route\s*[-:]\s*GATI\d{4}\s+Total", re.IGNORECASE),
]


def _is_skip_line(line: str) -> bool:
    return any(p.match(line) for p in SKIP_LINE_PATTERNS)


def parse_pdf(file_path: str) -> List[Route]:
    routes: List[Route] = []
    current_route_code: Optional[str] = None
    current_route_lines: List[str] = []
    global_date = ""

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            if not global_date:
                global_date = _extract_date(text)

            lines = text.split("\n")

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue

                if not global_date:
                    global_date = _extract_date(stripped)

                if _is_skip_line(stripped):
                    continue

                route_match = ROUTE_PATTERN.search(stripped)
                if route_match:
                    new_code = route_match.group(1).upper()
                    if new_code != current_route_code:
                        if current_route_code and current_route_lines:
                            route = _parse_single_route(current_route_code, global_date, current_route_lines)
                            if route.packages:
                                routes.append(route)
                        current_route_code = new_code
                        current_route_lines = []
                elif current_route_code:
                    current_route_lines.append(stripped)

    if current_route_code and current_route_lines:
        route = _parse_single_route(current_route_code, global_date, current_route_lines)
        if route.packages:
            routes.append(route)

    return routes
