"""Testes unitários e de integração para o módulo discovery do ProspectAI."""

import asyncio
import pytest
from discovery import (
    GooglePlacesClient,
    PlaceResult,
    PlaceReview,
    GridScanner,
    GridPoint,
    generate_circular_grid,
    generate_bbox_grid,
    get_bounding_box,
    haversine_distance,
    yield_grid_coordinates,
    ReceitaFederalClient,
    CompanyData,
    CNPJCache,
    validate_cnpj,
    format_cnpj,
    clean_cnpj,
    extract_cnpjs_from_text,
    extract_first_valid_cnpj,
    correlate_phone,
    correlate_name_and_address,
)


# ==============================================================================
# 1. Testes de Validação e Extração de CNPJ (Módulo 11)
# ==============================================================================


def test_cnpj_cleaning_and_formatting():
    """Valida funções utilitárias de limpeza e formatação de máscara."""
    raw = "06.990.590/0001-23"
    cleaned = clean_cnpj(raw)
    assert cleaned == "06990590000123"
    assert format_cnpj(cleaned) == "06.990.590/0001-23"


def test_cnpj_validation_modulo11():
    """Testa algoritmo Módulo 11 com CNPJs reais válidos e inválidos."""
    # CNPJs reais válidos (Google Brasil, Petrobras, Magazine Luiza)
    valid_cnpjs = [
        "06.990.590/0001-23",  # Google Brasil
        "33.000.167/0001-01",  # Petrobras
        "47.960.950/0001-21",  # Magazine Luiza
        "06990590000123",
    ]
    for cnpj in valid_cnpjs:
        assert validate_cnpj(cnpj) is True, f"Deveria ser válido: {cnpj}"

    # CNPJs inválidos
    invalid_cnpjs = [
        "00.000.000/0000-00",  # Dígitos repetidos
        "11.111.111/1111-11",
        "06.990.590/0001-24",  # Dígito verificador incorreto
        "12345",               # Tamanho incorreto
        "",
        "abc",
    ]
    for cnpj in invalid_cnpjs:
        assert validate_cnpj(cnpj) is False, f"Deveria ser inválido: {cnpj}"


def test_extract_cnpjs_from_text():
    """Testa varredura por regex em texto simulado de rodapé."""
    html_footer = """
    <footer>
        <p>Restaurante Bom Sabor Ltda - Todos os direitos reservados.</p>
        <p>Atendimento ao Consumidor | SAC: (11) 3456-7890</p>
        <p>CNPJ: 06.990.590/0001-23 - Inscrição Estadual: 123.456.789.000</p>
        <p>Filial: 33.000.167/0001-01 | CNPJ Inválido: 11.111.111/1111-11</p>
    </footer>
    """
    extracted = extract_cnpjs_from_text(html_footer)
    assert len(extracted) == 2
    assert "06990590000123" in extracted
    assert "33000167000101" in extracted
    assert "11111111111111" not in extracted

    first = extract_first_valid_cnpj(html_footer)
    assert first == "06990590000123"


# ==============================================================================
# 2. Testes de Geometria e Grid Scanner
# ==============================================================================


def test_haversine_distance():
    """Testa cálculo de distância entre coordenadas conhecidas."""
    # Distância entre Praça da Sé (SP) e MASP (Av Paulista) ~ 2.6 km
    se_lat, se_lng = -23.55052, -46.63330
    masp_lat, masp_lng = -23.56141, -46.65588

    dist = haversine_distance(se_lat, se_lng, masp_lat, masp_lng)
    assert 2.0 <= dist <= 3.2

    # Distância ponto a si mesmo = 0
    assert haversine_distance(se_lat, se_lng, se_lat, se_lng) == 0.0


def test_bounding_box():
    """Testa cálculo de Bounding Box em torno de um ponto."""
    lat, lng = -23.55052, -46.63330
    radius_km = 5.0
    min_lat, min_lng, max_lat, max_lng = get_bounding_box(lat, lng, radius_km)

    assert min_lat < lat < max_lat
    assert min_lng < lng < max_lng

    # Verifica distância das extremidades
    assert haversine_distance(lat, lng, min_lat, lng) <= 5.1
    assert haversine_distance(lat, lng, max_lat, lng) <= 5.1


def test_generate_circular_grid():
    """Testa geração de grade com empacotamento hexagonal."""
    lat, lng = -23.55052, -46.63330
    points = generate_circular_grid(center_lat=lat, center_lng=lng, radius_km=3.0, step_km=1.5)

    assert len(points) >= 5
    # Primeiro ponto deve ser o centro
    assert points[0].lat == lat
    assert points[0].lng == lng
    assert points[0].distance_from_center_km == 0.0

    # Todos os pontos devem estar a no máximo 3.0 km do centro
    for pt in points:
        assert pt.distance_from_center_km <= 3.01
        assert pt.radius_meters > 0.0

    # Teste do gerador de tuplas
    tuples = list(yield_grid_coordinates(center_lat=lat, center_lng=lng, radius_km=3.0, step_km=1.5))
    assert len(tuples) == len(points)
    assert isinstance(tuples[0], tuple)
    assert len(tuples[0]) == 3


def test_generate_bbox_grid():
    """Testa geração de grade regular retangular."""
    points = generate_bbox_grid(
        min_lat=-23.56,
        min_lng=-46.66,
        max_lat=-23.54,
        max_lng=-46.64,
        step_km=1.5,
    )
    assert len(points) >= 4
    for pt in points:
        assert -23.57 <= pt.lat <= -23.53
        assert -46.67 <= pt.lng <= -46.63


def test_grid_scanner_deduplication():
    """Testa o rastreador de deduplicação do GridScanner."""
    scanner = GridScanner()

    place_a = PlaceResult(
        place_id="place_1",
        name="Padaria Alfa",
        address="Rua A, 100",
        lat=-23.55,
        lng=-46.63,
    )
    place_b = PlaceResult(
        place_id="place_2",
        name="Bar Beta",
        address="Rua B, 200",
        lat=-23.56,
        lng=-46.64,
    )
    place_a_dup = PlaceResult(
        place_id="place_1",
        name="Padaria Alfa",
        address="Rua A, 100",
        lat=-23.55,
        lng=-46.63,
    )

    batch1 = scanner.filter_new_places([place_a, place_b])
    assert len(batch1) == 2
    assert scanner.stats.unique_places_found == 2
    assert scanner.stats.duplicate_places_skipped == 0

    # Segundo lote com duplicata
    batch2 = scanner.filter_new_places([place_a_dup])
    assert len(batch2) == 0
    assert scanner.stats.unique_places_found == 2
    assert scanner.stats.duplicate_places_skipped == 1


# ==============================================================================
# 3. Testes Assíncronos do Google Places Client (Mock / Dry-Run)
# ==============================================================================


@pytest.mark.asyncio
async def test_google_places_dry_run_nearby():
    """Testa busca nearby no GooglePlacesClient em modo dry-run."""
    client = GooglePlacesClient(dry_run=True)
    async with client:
        results = await client.search_nearby(
            lat=-23.5615,
            lng=-46.6917,
            radius_meters=1500.0,
            max_results=5,
        )
        assert len(results) > 0
        first = results[0]
        assert isinstance(first, PlaceResult)
        assert first.place_id
        assert first.name
        assert first.address
        assert first.lat != 0.0
        assert first.lng != 0.0


@pytest.mark.asyncio
async def test_google_places_dry_run_text_and_details():
    """Testa Text Search e Place Details em modo dry-run."""
    client = GooglePlacesClient(dry_run=True)
    async with client:
        # Text Search
        text_results = await client.search_text(
            query="restaurante em pinheiros",
            lat=-23.5615,
            lng=-46.6917,
            radius_meters=2000.0,
            max_results=3,
        )
        assert len(text_results) > 0

        # Place Details com reviews
        details = await client.get_place_details("mock_places_12345")
        assert details is not None
        assert details.place_id == "mock_places_12345"
        assert len(details.reviews) > 0
        assert isinstance(details.reviews[0], PlaceReview)
        assert details.reviews[0].text != ""


# ==============================================================================
# 4. Testes Assíncronos do Receita Federal Client e Cache
# ==============================================================================


@pytest.mark.asyncio
async def test_receita_federal_cache_and_mock():
    """Testa cache em memória/sqlite e modo simulado do ReceitaFederalClient."""
    cache = CNPJCache(db_path=":memory:")
    client = ReceitaFederalClient(cache_db_path=":memory:", dry_run=True)

    test_cnpj = "06990590000123"
    company = await client.get_cnpj_data(test_cnpj)

    assert company is not None
    assert isinstance(company, CompanyData)
    assert company.cnpj == test_cnpj
    assert company.situacao_cadastral == "ATIVA"
    assert len(company.qsa) > 0
    assert company.cnae_fiscal > 0

    # Segunda chamada deve atingir o cache
    cached_company = await client.get_cnpj_data(test_cnpj, use_cache=True)
    assert cached_company is not None
    assert cached_company.razao_social == company.razao_social

    await client.close()


def test_phone_and_name_correlation():
    """Testa correlação heurística de telefone e nome/endereço."""
    client = ReceitaFederalClient(dry_run=True)

    company = CompanyData(
        cnpj="06990590000123",
        cnpj_formatado="06.990.590/0001-23",
        razao_social="PADARIA E CONFEITARIA ESTRELA DO SUL LTDA",
        nome_fantasia="PADARIA ESTRELA",
        situacao_cadastral="ATIVA",
        cnae_fiscal=1091102,
        cnae_fiscal_descricao="Padaria e confeitaria com predominância de revenda",
        porte="ME",
        capital_social=30000.0,
        logradouro="Rua das Acácias",
        numero="150",
        municipio="Campinas",
        uf="SP",
        ddd_telefone_1="1932345678",
    )

    # 1. Match de telefone
    assert correlate_phone("(19) 3234-5678", company) is True
    assert correlate_phone("+55 19 3234-5678", company) is True
    assert correlate_phone("(11) 99999-9999", company) is False

    # 2. Match de nome
    score_similar = correlate_name_and_address(
        target_name="Padaria Estrela Campinas",
        target_address="Rua das Acácias, 150 - Campinas",
        candidate=company,
    )
    assert score_similar >= 0.70

    score_different = correlate_name_and_address(
        target_name="Oficina Mecânica São Jorge",
        target_address="Av Brasil, 1000 - Santos",
        candidate=company,
    )
    assert score_different < 0.40

    # 3. Match eleito
    best, conf = client.match_best_candidate(
        target_name="Padaria Estrela",
        target_phone="(19) 3234-5678",
        target_address="Rua das Acácias",
        candidates=[company],
    )
    assert best is not None
    assert conf >= 0.90
