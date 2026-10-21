"""Módulo de varredura geográfica em grade (Grid Scanner) para o ProspectAI / Sweezy AI."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.logging import RichHandler

if TYPE_CHECKING:
    from discovery.google_places import GooglePlacesClient, PlaceResult

logger = logging.getLogger("prospectai.discovery.grid")
if not logger.handlers:
    rich_handler = RichHandler(console=Console(stderr=True), show_time=True, show_path=False, rich_tracebacks=True)
    logger.addHandler(rich_handler)
    logger.setLevel(logging.INFO)

EARTH_RADIUS_KM = 6371.0


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi, delta_lambda = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    return EARTH_RADIUS_KM * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def get_bounding_box(center_lat: float, center_lng: float, radius_km: float) -> tuple[float, float, float, float]:
    delta_lat = radius_km / 111.32
    cos_lat = max(0.0001, abs(math.cos(math.radians(center_lat))))
    delta_lng = radius_km / (111.32 * cos_lat)
    return (
        round(max(-90.0, center_lat - delta_lat), 6),
        round(max(-180.0, center_lng - delta_lng), 6),
        round(min(90.0, center_lat + delta_lat), 6),
        round(min(180.0, center_lng + delta_lng), 6),
    )


class GridPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)
    radius_meters: float = Field(..., gt=0.0)
    index: int = 0
    distance_from_center_km: float = 0.0

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.lat, self.lng, self.radius_meters)

    def as_dict(self) -> dict[str, Any]:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "radius_meters": self.radius_meters,
            "index": self.index,
            "distance_from_center_km": self.distance_from_center_km,
        }


class ScanStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    total_cells: int = 0
    scanned_cells: int = 0
    total_places_found: int = 0
    unique_places_found: int = 0
    duplicate_places_skipped: int = 0
    start_time: float = Field(default_factory=time.time)
    end_time: float | None = None

    @property
    def elapsed_seconds(self) -> float:
        return max(0.001, (self.end_time or time.time()) - self.start_time)

    @property
    def scan_rate_per_sec(self) -> float:
        return round(self.scanned_cells / self.elapsed_seconds, 2)

    @property
    def duplicate_ratio(self) -> float:
        return round((self.duplicate_places_skipped / self.total_places_found) * 100, 1) if self.total_places_found else 0.0


def generate_circular_grid(
    center_lat: float,
    center_lng: float,
    radius_km: float,
    step_km: float = 1.5,
    sub_radius_meters: float | None = None,
) -> list[GridPoint]:
    step_km = max(0.2, step_km)
    radius_km = max(step_km / 2.0, radius_km)
    cell_radius = (step_km / math.sqrt(3.0)) * 1.15 * 1000.0 if sub_radius_meters is None else float(sub_radius_meters)

    dy_km = step_km * (math.sqrt(3.0) / 2.0)
    dx_km = step_km
    deg_lat_per_km = 1.0 / 111.32
    cos_lat = max(0.0001, abs(math.cos(math.radians(center_lat))))
    deg_lng_per_km = 1.0 / (111.32 * cos_lat)

    max_steps_y = int(math.ceil(radius_km / dy_km)) + 1
    max_steps_x = int(math.ceil(radius_km / dx_km)) + 1

    points_with_dist: list[tuple[float, float, float]] = [(center_lat, center_lng, 0.0)]

    for row in range(-max_steps_y, max_steps_y + 1):
        y_offset_km = row * dy_km
        x_shift_km = (dx_km / 2.0) if (row % 2 != 0) else 0.0

        for col in range(-max_steps_x, max_steps_x + 1):
            if row == 0 and col == 0:
                continue
            x_offset_km = (col * dx_km) + x_shift_km
            pt_lat = center_lat + (y_offset_km * deg_lat_per_km)
            pt_lng = center_lng + (x_offset_km * deg_lng_per_km)
            dist_km = haversine_distance(center_lat, center_lng, pt_lat, pt_lng)
            if dist_km <= radius_km:
                points_with_dist.append((round(pt_lat, 6), round(pt_lng, 6), round(dist_km, 3)))

    points_with_dist.sort(key=lambda item: item[2])
    return [
        GridPoint(lat=p[0], lng=p[1], radius_meters=round(cell_radius, 1), index=i, distance_from_center_km=p[2])
        for i, p in enumerate(points_with_dist)
    ]


def generate_bbox_grid(
    min_lat: float, min_lng: float, max_lat: float, max_lng: float, step_km: float = 1.5, sub_radius_meters: float | None = None
) -> list[GridPoint]:
    step_km = max(0.2, step_km)
    center_lat, center_lng = (min_lat + max_lat) / 2.0, (min_lng + max_lng) / 2.0
    cell_radius = (step_km / math.sqrt(2.0)) * 1.10 * 1000.0 if sub_radius_meters is None else float(sub_radius_meters)

    deg_lat_per_km = 1.0 / 111.32
    cos_lat = max(0.0001, abs(math.cos(math.radians(center_lat))))
    deg_lng_per_km = 1.0 / (111.32 * cos_lat)
    step_lat, step_lng = step_km * deg_lat_per_km, step_km * deg_lng_per_km

    points, idx = [], 0
    curr_lat = min_lat
    while curr_lat <= max_lat + (step_lat * 0.1):
        curr_lng = min_lng
        while curr_lng <= max_lng + (step_lng * 0.1):
            dist = haversine_distance(center_lat, center_lng, curr_lat, curr_lng)
            points.append(
                GridPoint(lat=round(curr_lat, 6), lng=round(curr_lng, 6), radius_meters=round(cell_radius, 1), index=idx, distance_from_center_km=round(dist, 3))
            )
            idx += 1
            curr_lng += step_lng
        curr_lat += step_lat
    return points


def yield_grid_coordinates(center_lat: float, center_lng: float, radius_km: float, step_km: float = 1.5) -> Iterator[tuple[float, float, float]]:
    for pt in generate_circular_grid(center_lat, center_lng, radius_km, step_km):
        yield pt.as_tuple()


class GridScanner:
    def __init__(self) -> None:
        self.seen_place_ids: set[str] = set()
        self.stats = ScanStats()

    def is_seen(self, place_id: str) -> bool:
        return place_id in self.seen_place_ids

    def mark_seen(self, place_id: str) -> None:
        if place_id:
            self.seen_place_ids.add(place_id)

    def filter_new_places(self, places: list[PlaceResult]) -> list[PlaceResult]:
        unique_list: list[PlaceResult] = []
        for p in places:
            self.stats.total_places_found += 1
            if p.place_id and p.place_id not in self.seen_place_ids:
                self.seen_place_ids.add(p.place_id)
                self.stats.unique_places_found += 1
                unique_list.append(p)
            else:
                self.stats.duplicate_places_skipped += 1
        return unique_list

    def reset(self) -> None:
        self.seen_place_ids.clear()
        self.stats = ScanStats()

    async def scan_stream(
        self,
        places_client: GooglePlacesClient,
        center_lat: float,
        center_lng: float,
        radius_km: float,
        step_km: float = 1.5,
        included_types: list[str] | None = None,
        max_results_per_cell: int = 20,
    ) -> AsyncIterator[tuple[GridPoint, list[PlaceResult]]]:
        grid_points = generate_circular_grid(center_lat, center_lng, radius_km, step_km)
        self.stats.total_cells = len(grid_points)
        self.stats.start_time = time.time()

        for cell in grid_points:
            try:
                raw_places = await places_client.search_nearby(
                    lat=cell.lat, lng=cell.lng, radius_meters=cell.radius_meters, included_types=included_types, max_results=max_results_per_cell
                )
                new_places = self.filter_new_places(raw_places)
                self.stats.scanned_cells += 1
                yield cell, new_places
            except Exception as e:
                logger.error(f"Erro ao varrer célula {cell.index} ({cell.lat}, {cell.lng}): {e}")
                self.stats.scanned_cells += 1
                yield cell, []

        self.stats.end_time = time.time()

    async def scan_region(
        self,
        places_client: GooglePlacesClient,
        center_lat: float,
        center_lng: float,
        radius_km: float,
        step_km: float = 1.5,
        included_types: list[str] | None = None,
        max_results_per_cell: int = 20,
        on_progress: Callable[[int, int, int], None] | None = None,
    ) -> list[PlaceResult]:
        all_unique: list[PlaceResult] = []
        async for cell, new_places in self.scan_stream(
            places_client=places_client,
            center_lat=center_lat,
            center_lng=center_lng,
            radius_km=radius_km,
            step_km=step_km,
            included_types=included_types,
            max_results_per_cell=max_results_per_cell,
        ):
            all_unique.extend(new_places)
            if on_progress:
                on_progress(self.stats.scanned_cells, self.stats.total_cells, self.stats.unique_places_found)
        return all_unique


KNOWN_BRAZILIAN_LOCATIONS: dict[str, tuple[float, float, str]] = {
    "brasilia": (-15.7938, -47.8828, "Brasília, DF, Brasil"),
    "brasília": (-15.7938, -47.8828, "Brasília, DF, Brasil"),
    "distrito federal": (-15.7938, -47.8828, "Brasília, DF, Brasil"),
    "df": (-15.7938, -47.8828, "Brasília, DF, Brasil"),
    "asa sul": (-15.8150, -47.9050, "Asa Sul, Brasília - DF, Brasil"),
    "asa norte": (-15.7650, -47.8850, "Asa Norte, Brasília - DF, Brasil"),
    "taguatinga": (-15.8330, -48.0560, "Taguatinga, Brasília - DF, Brasil"),
    "águas claras": (-15.8390, -48.0280, "Águas Claras, Brasília - DF, Brasil"),
    "aguas claras": (-15.8390, -48.0280, "Águas Claras, Brasília - DF, Brasil"),
    "guara": (-15.8240, -47.9800, "Guará, Brasília - DF, Brasil"),
    "guará": (-15.8240, -47.9800, "Guará, Brasília - DF, Brasil"),
    "sudoeste": (-15.7980, -47.9250, "Sudoeste, Brasília - DF, Brasil"),
    "sao paulo": (-23.5505, -46.6333, "São Paulo, SP, Brasil"),
    "são paulo": (-23.5505, -46.6333, "São Paulo, SP, Brasil"),
    "sp": (-23.5505, -46.6333, "São Paulo, SP, Brasil"),
    "rio de janeiro": (-22.9068, -43.1729, "Rio de Janeiro, RJ, Brasil"),
    "rj": (-22.9068, -43.1729, "Rio de Janeiro, RJ, Brasil"),
    "belo horizonte": (-19.9227, -43.9451, "Belo Horizonte, MG, Brasil"),
    "bh": (-19.9227, -43.9451, "Belo Horizonte, MG, Brasil"),
    "mg": (-19.9227, -43.9451, "Belo Horizonte, MG, Brasil"),
    "goiania": (-16.6809, -49.2533, "Goiânia, GO, Brasil"),
    "goiânia": (-16.6809, -49.2533, "Goiânia, GO, Brasil"),
    "go": (-16.6809, -49.2533, "Goiânia, GO, Brasil"),
    "curitiba": (-25.4284, -49.2733, "Curitiba, PR, Brasil"),
    "pr": (-25.4284, -49.2733, "Curitiba, PR, Brasil"),
    "porto alegre": (-30.0346, -51.2177, "Porto Alegre, RS, Brasil"),
    "rs": (-30.0346, -51.2177, "Porto Alegre, RS, Brasil"),
    "salvador": (-12.9777, -38.5016, "Salvador, BA, Brasil"),
    "ba": (-12.9777, -38.5016, "Salvador, BA, Brasil"),
    "fortaleza": (-3.7172, -38.5433, "Fortaleza, CE, Brasil"),
    "recife": (-8.0476, -34.8770, "Recife, PE, Brasil"),
    "campinas": (-22.9056, -47.0596, "Campinas, SP, Brasil"),
    "florianopolis": (-27.5954, -48.5480, "Florianópolis, SC, Brasil"),
    "florianópolis": (-27.5954, -48.5480, "Florianópolis, SC, Brasil"),
    "vitoria": (-20.3155, -40.3128, "Vitória, ES, Brasil"),
    "vitória": (-20.3155, -40.3128, "Vitória, ES, Brasil"),
    "manaus": (-3.1190, -60.0217, "Manaus, AM, Brasil"),
    "belem": (-1.4558, -48.4902, "Belém, PA, Brasil"),
    "belém": (-1.4558, -48.4902, "Belém, PA, Brasil"),
}


async def geocode_location(query: str) -> tuple[float, float, str]:
    clean_q = query.strip()
    if not clean_q:
        return -15.7938, -47.8828, "Brasília, DF, Brasil"

    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "SweezyAI/1.0 (contato@sweezy.ai)"}
    search_term = clean_q if "brasil" in clean_q.lower() else f"{clean_q}, Brasil"
    params = {"q": search_term, "format": "json", "addressdetails": 1, "limit": 1, "countrycodes": "br"}

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    first = data[0]
                    return float(first["lat"]), float(first["lon"]), first.get("display_name", clean_q)
    except Exception as e:
        logger.warning(f"Nominatim geocode falhou para '{clean_q}': {e}")

    q_lower = clean_q.lower()
    for key, val in KNOWN_BRAZILIAN_LOCATIONS.items():
        if key in q_lower or q_lower in key:
            return val

    return -15.7938, -47.8828, "Brasília, DF, Brasil"
