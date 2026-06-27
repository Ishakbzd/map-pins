from typing import Dict, List, Tuple

import folium
from folium.plugins import Fullscreen, MarkerCluster

from core.deduplicator import _normalize_key, deduplicate
from models.route import Route

STOP_COLORS = [
    "red",
    "blue",
    "green",
    "purple",
    "orange",
    "darkred",
    "darkblue",
    "darkgreen",
]


def generate_map_html(
    routes: List[Route],
    coords_map: Dict[str, Tuple[float, float]],
) -> str:
    if not coords_map:
        return (
            "<p style='color:#666;font-family:sans-serif;padding:20px;'>"
            "No coordinates available for map preview.</p>"
        )

    lats = [c[0] for c in coords_map.values()]
    lons = [c[1] for c in coords_map.values()]
    center = [sum(lats) / len(lats), sum(lons) / len(lons)]

    m = folium.Map(
        location=center,
        zoom_start=12,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    Fullscreen(
        position="topright",
        title_collapse="Exit fullscreen",
        title_expand="Fullscreen",
    ).add_to(m)

    for route_idx, route in enumerate(routes):
        color = STOP_COLORS[route_idx % len(STOP_COLORS)]
        seen_keys = set()
        ordered_stops: List[Tuple[str, str, str, str, Tuple[float, float]]] = []

        for pkg in route.packages:
            key = _normalize_key(pkg.street, pkg.postal_code)
            coords = coords_map.get(pkg.full_address)
            if not coords or key in seen_keys:
                continue
            seen_keys.add(key)
            ordered_stops.append((
                pkg.street, pkg.city, pkg.postal_code, pkg.code, coords,
            ))

        cluster = MarkerCluster(
            name=f"{route.code} ({len(ordered_stops)} stops)",
            options={"maxClusterRadius": 50},
        ).add_to(m)

        for i, (street, city, postal, code, coords) in enumerate(ordered_stops, 1):
            popup_html = (
                f"<div style='font-family:sans-serif;font-size:13px;min-width:180px;'>"
                f"<b style='font-size:14px;color:#2c3e50;'>{street}</b><br>"
                f"{city}, QC {postal}<br>"
                f"<span style='color:#888;font-size:11px;'>{code}</span>"
                f"</div>"
            )

            folium.CircleMarker(
                location=coords,
                radius=6,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                weight=2,
                popup=folium.Popup(popup_html, max_width=280),
                tooltip=f"#{i} {street}",
            ).add_to(cluster)

    folium.LayerControl(collapsed=True).add_to(m)

    return m._repr_html_()


def save_map_html_file(html: str, path: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
