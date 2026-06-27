import json
import os
import time
from typing import Callable, Dict, List, Optional, Tuple

from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim

from core.deduplicator import _normalize_key
from models.route import Route

USER_AGENT = "GATIRouteManager/1.0"

_in_memory: Dict[str, Tuple[float, float]] = {}
_cache_path: Optional[str] = None


def _get_cache_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    cache_dir = os.path.join(base, "GATIRouteManager")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _get_cache_path() -> str:
    global _cache_path
    if _cache_path is None:
        _cache_path = os.path.join(_get_cache_dir(), "geocode_cache.json")
    return _cache_path


def _load_cache() -> Dict[str, Tuple[float, float]]:
    path = _get_cache_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return {k: tuple(v) for k, v in raw.items()}
    except Exception:
        return {}


def _save_cache(cache: Dict[str, Tuple[float, float]]) -> None:
    path = _get_cache_path()
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass


def get_geolocator() -> Nominatim:
    return Nominatim(user_agent=USER_AGENT)


def geocode_address(
    geolocator: Nominatim,
    address: str,
    max_retries: int = 2,
) -> Optional[Tuple[float, float]]:
    cached = _in_memory.get(address)
    if cached:
        return cached

    for attempt in range(max_retries):
        try:
            location = geolocator.geocode(address, timeout=10)
            if location:
                _in_memory[address] = (location.latitude, location.longitude)
                return (location.latitude, location.longitude)
            return None
        except (GeocoderTimedOut, GeocoderUnavailable):
            if attempt < max_retries - 1:
                time.sleep(1.0)
                continue
            return None
    return None


def geocode_routes(
    routes: List[Route],
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Tuple[float, float]]:
    disk_cache = _load_cache()
    _in_memory.update(disk_cache)

    geolocator = get_geolocator()
    result: Dict[str, Tuple[float, float]] = {}

    all_stops: List[str] = []
    seen_keys = set()
    for route in routes:
        for pkg in route.packages:
            key = _normalize_key(pkg.street, pkg.postal_code)
            if key not in seen_keys:
                seen_keys.add(key)
                all_stops.append(pkg.full_address)

    total = len(all_stops)
    for i, full_address in enumerate(all_stops):
        cached = _in_memory.get(full_address)
        if cached:
            result[full_address] = cached
            if on_progress:
                short = full_address.split(",")[0]
                on_progress(i + 1, total, f"{short} (cached)")
            continue

        if on_progress:
            short = full_address.split(",")[0]
            on_progress(i + 1, total, short)

        coords = geocode_address(geolocator, full_address)
        if coords:
            result[full_address] = coords
        if i < total - 1:
            time.sleep(1.1)

    if _in_memory:
        _save_cache(_in_memory)

    return result
