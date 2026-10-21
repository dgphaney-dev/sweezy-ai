"""Testes unitários e de integração para o pipeline e CLI runner do ProspectAI."""

import asyncio
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import app
from core.database import close_db, get_db_session, init_db, list_leads
from pipeline.lead_pipeline import (
    LeadPipeline,
    PipelineProgress,
    PipelineResult,
    PipelineStage,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path, monkeypatch):
    """Configura banco de dados SQLite temporário e modo simulado para testes."""
    db_file = tmp_path / "test_pipeline.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("GOOGLE_API_KEY", "mock_key")
    monkeypatch.setenv("OPENAI_API_KEY", "mock_key")

    from config.settings import get_settings
    get_settings.cache_clear()
    asyncio.run(close_db())

    yield

    asyncio.run(close_db())
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_lead_pipeline_dry_run():
    """Testa execução completa do LeadPipeline em modo simulado."""
    pipeline = LeadPipeline(concurrency_limit=2)
    pipeline.places_client.dry_run = True
    pipeline.receita_client.dry_run = True

    progress_events: list[PipelineProgress] = []

    def on_progress(p: PipelineProgress):
        progress_events.append(p)

    result = await pipeline.run_scan(
        region_name="Moema, SP",
        center_lat=-23.604,
        center_lng=-46.666,
        radius_km=1.5,
        step_km=1.0,
        business_types=["restaurant"],
        max_places=4,
        progress_callback=on_progress,
    )

    assert isinstance(result, PipelineResult)
    assert result.region_name == "Moema, SP"
    assert result.total_grid_points > 0
    assert result.total_places_found > 0
    assert result.total_leads_saved > 0
    assert len(result.leads) == result.total_leads_saved
    assert result.duration_seconds > 0

    # Verifica se os eventos de progresso passaram pelos estágios chave
    stages = [p.stage for p in progress_events]
    assert PipelineStage.STARTING in stages
    assert PipelineStage.GRID_GENERATION in stages
    assert PipelineStage.PLACES_SEARCH in stages
    assert PipelineStage.ENRICHMENT in stages
    assert PipelineStage.COMPLETED in stages

    # Verifica persistência no SQLite
    async with get_db_session() as session:
        leads_in_db = await list_leads(session_id=result.session_id, session=session)
        assert len(leads_in_db) == result.total_leads_saved


def test_cli_scan_command(tmp_path):
    """Testa execução do comando 'scan' da CLI."""
    result = runner.invoke(
        app,
        [
            "scan",
            "--region",
            "Moema, SP",
            "--lat",
            "-23.604",
            "--lng",
            "-46.666",
            "--radius",
            "1.5",
            "--type",
            "restaurant",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "Moema, SP" in result.stdout
    assert "Varredura finalizada com sucesso" in result.stdout


def test_cli_list_leads_and_stats():
    """Testa comandos 'list-leads' e 'stats' após inserção de dados."""
    # 1. Executa scan para povoar o banco
    runner.invoke(
        app,
        [
            "scan",
            "--region",
            "Pinheiros, SP",
            "--lat",
            "-23.561",
            "--lng",
            "-46.691",
            "--radius",
            "1.0",
            "--type",
            "bakery",
            "--dry-run",
        ],
    )

    # 2. Executa list-leads sem filtro
    list_res = runner.invoke(app, ["list-leads", "--limit", "10"])
    assert list_res.exit_code == 0
    assert "Leads Prospectados no Sweezy AI" in list_res.stdout

    # 3. Executa list-leads com filtro de status / prioridade
    list_high = runner.invoke(app, ["list-leads", "--status", "HIGH"])
    assert list_high.exit_code == 0

    # 4. Executa comando stats
    stats_res = runner.invoke(app, ["stats"])
    assert stats_res.exit_code == 0
    assert "Estatisticas de Qualificacao e Funil Comercial" in stats_res.stdout
    assert "Total de Leads Cadastrados" in stats_res.stdout


def test_cli_export_command(tmp_path):
    """Testa comando 'export' para arquivo CSV."""
    # 1. Scan prévio
    runner.invoke(
        app,
        [
            "scan",
            "--region",
            "Vila Mariana, SP",
            "--lat",
            "-23.589",
            "--lng",
            "-46.634",
            "--radius",
            "1.0",
            "--type",
            "restaurant",
            "--dry-run",
        ],
    )

    output_csv = tmp_path / "leads_exported.csv"
    export_res = runner.invoke(
        app,
        ["export", "--format", "csv", "--output", str(output_csv)],
    )

    assert export_res.exit_code == 0
    assert "Exportacao concluida com sucesso" in export_res.stdout
    assert output_csv.exists()
    content = output_csv.read_text(encoding="utf-8-sig")
    assert "nome_fantasia;razao_social;cnpj" in content
