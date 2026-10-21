"""Módulo de Descoberta (Discovery) do ProspectAI.

Responsável pela varredura territorial sistemática, localização de estabelecimentos
comerciais via Google Places API (New) v1 e enriquecimento cadastral oficial
por meio da Receita Federal (BrasilAPI e CNPJ.ws).

Exporta os principais clientes, modelos de dados e utilitários:
- Google Places: GooglePlacesClient, PlaceResult, PlaceReview
- Grid Scanner: GridScanner, GridPoint, ScanStats, generate_circular_grid, generate_bbox_grid, haversine_distance, yield_grid_coordinates
- Receita Federal: ReceitaFederalClient, CompanyData, CompanyPartner, CNAEItem, CNPJCache, validate_cnpj, format_cnpj, clean_cnpj, extract_cnpjs_from_text, extract_first_valid_cnpj
"""

from discovery.google_places import (
    GooglePlacesClient,
    PlaceResult,
    PlaceReview,
)
from discovery.grid_scanner import (
    EARTH_RADIUS_KM,
    GridPoint,
    GridScanner,
    ScanStats,
    generate_bbox_grid,
    generate_circular_grid,
    get_bounding_box,
    haversine_distance,
    yield_grid_coordinates,
)
from discovery.receita_federal import (
    CNAEItem,
    CNPJCache,
    CompanyData,
    CompanyPartner,
    ReceitaFederalClient,
    calculate_string_similarity,
    clean_cnpj,
    correlate_name_and_address,
    correlate_phone,
    extract_cnpjs_from_text,
    extract_first_valid_cnpj,
    format_cnpj,
    normalize_text_for_comparison,
    validate_cnpj,
)

__all__ = [
    # Google Places API (New)
    "GooglePlacesClient",
    "PlaceResult",
    "PlaceReview",
    # Grid Scanner & Geometria
    "GridScanner",
    "GridPoint",
    "ScanStats",
    "EARTH_RADIUS_KM",
    "generate_circular_grid",
    "generate_bbox_grid",
    "get_bounding_box",
    "haversine_distance",
    "yield_grid_coordinates",
    # Receita Federal & CNPJ
    "ReceitaFederalClient",
    "CompanyData",
    "CompanyPartner",
    "CNAEItem",
    "CNPJCache",
    "clean_cnpj",
    "format_cnpj",
    "validate_cnpj",
    "extract_cnpjs_from_text",
    "extract_first_valid_cnpj",
    "correlate_phone",
    "correlate_name_and_address",
    "calculate_string_similarity",
    "normalize_text_for_comparison",
]
