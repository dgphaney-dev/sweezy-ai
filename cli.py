"""Interface de Linha de Comando (CLI Runner) para o Sweezy AI."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from config.settings import get_settings
from core.database import close_db, export_leads_to_csv, get_db_session, get_lead_stats, init_db, list_leads
from core.models import LeadStatus, LikelihoodLevel
from discovery.grid_scanner import geocode_location
from pipeline.lead_pipeline import LeadPipeline, PipelineProgress, PipelineResult, PipelineStage

app = typer.Typer(name="Sweezy AI CLI", help="Sweezy AI - Prospecção B2B de Leads sem PDV/ERP no Brasil.", add_completion=False)
console = Console(legacy_windows=False)


@app.command("scan")
def scan_command(
    location: str | None = typer.Argument(None, help="Localização (ex: 'Brasília, DF')"),
    region: str | None = typer.Option(None, "--region", "-r"),
    city: str | None = typer.Option(None, "--city", "--cidade"),
    state: str | None = typer.Option(None, "--state", "--estado"),
    lat: float | None = typer.Option(None, "--lat"),
    lng: float | None = typer.Option(None, "--lng"),
    radius: float = typer.Option(2.0, "--radius"),
    business_type: str = typer.Option("all", "--type", "-t"),
    step: float = typer.Option(1.0, "--step"),
    concurrency: int = typer.Option(5, "--concurrency", "-c"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Executa o pipeline completo de varredura, enriquecimento e qualificação."""
    target_region = location or region or (f"{city}, {state}" if (city and state) else (city or state or "Brasília, DF"))
    actual_lat, actual_lng = lat, lng

    if actual_lat is None or actual_lng is None:
        console.print(f"[bold cyan]Identificando coordenadas de:[/bold cyan] [green]{target_region}[/green]...")
        geo_lat, geo_lng, display_name = asyncio.run(geocode_location(target_region))
        actual_lat = actual_lat or geo_lat
        actual_lng = actual_lng or geo_lng
        console.print(f"[dim]Localidade: {display_name} ({actual_lat:.4f}, {actual_lng:.4f})[/dim]")

    console.print(
        Panel.fit(
            f"[bold cyan]Sweezy AI - Varredura Geográfica e Qualificação[/bold cyan]\n"
            f"[bold white]Região:[/bold white] [green]{target_region}[/green] | "
            f"[bold white]Coordenadas:[/bold white] ({actual_lat:.4f}, {actual_lng:.4f}) | "
            f"[bold white]Raio:[/bold white] {radius:.1f} km | "
            f"[bold white]Segmento:[/bold white] {business_type}",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    async def _execute_scan() -> PipelineResult:
        settings = get_settings()
        pipeline = LeadPipeline(settings=settings, concurrency_limit=concurrency)
        if dry_run:
            pipeline.places_client.dry_run = True
            pipeline.receita_client.dry_run = True

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40, style="grey37", complete_style="cyan"),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress_bar:
            task_id = progress_bar.add_task(description="Preparando busca...", total=100)

            def on_progress(p: PipelineProgress) -> None:
                if p.stage == PipelineStage.GRID_GENERATION:
                    progress_bar.update(task_id, description="Calculando malha...", completed=p.current_step, total=p.total_steps)
                elif p.stage == PipelineStage.PLACES_SEARCH:
                    progress_bar.update(task_id, description=f"Buscando no Places ({p.places_found} encontrados)...", completed=p.current_step, total=p.total_steps)
                elif p.stage == PipelineStage.DEDUPLICATION:
                    progress_bar.update(task_id, description=f"Deduplicando ({p.places_unique} únicos)...")
                elif p.stage == PipelineStage.ENRICHMENT:
                    nome = f" - {p.current_business_name[:25]}" if p.current_business_name else ""
                    progress_bar.update(task_id, description=f"Qualificando ({p.current_step}/{p.total_steps}){nome}", completed=p.current_step, total=p.total_steps)
                elif p.stage == PipelineStage.COMPLETED:
                    progress_bar.update(task_id, description="[bold green]Varredura Concluída!", completed=p.total_steps, total=p.total_steps)

            parsed_types = [t.strip() for t in business_type.split(",") if t.strip()]
            return await pipeline.run_scan(
                region_name=target_region,
                center_lat=actual_lat,
                center_lng=actual_lng,
                radius_km=radius,
                step_km=step,
                business_types=parsed_types,
                progress_callback=on_progress,
            )

    try:
        result = asyncio.run(_execute_scan())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Operacao cancelada pelo usuario.[/bold yellow]")
        raise typer.Exit(code=1)
    finally:
        asyncio.run(close_db())

    console.print("\n")
    console.print(
        Panel(
            f"[bold green]Varredura finalizada com sucesso em {result.duration_seconds:.1f} segundos![/bold green]\n\n"
            f"- [bold white]Pontos na Grade:[/bold white] {result.total_grid_points}\n"
            f"- [bold white]Locais Descobertos:[/bold white] {result.total_places_found}\n"
            f"- [bold white]Locais Unicos:[/bold white] {result.total_places_unique}\n"
            f"- [bold white]Leads Gravados:[/bold white] {result.total_leads_saved}\n"
            f"  * [bold red]Alta Prioridade (Sem PDV/ERP):[/bold red] {result.high_priority_leads}\n"
            f"  * [bold yellow]Media Prioridade (Mistos):[/bold yellow] {result.medium_priority_leads}\n"
            f"  * [bold blue]Baixa Prioridade (Com Sistema):[/bold blue] {result.low_priority_leads}",
            title=f"[bold]Metricas ({result.region_name})[/bold]",
            border_style="green",
            box=box.ROUNDED,
        )
    )

    if result.leads:
        table = Table(title="Principais Leads Identificados", box=box.MINIMAL_DOUBLE_HEAD, header_style="bold magenta")
        table.add_column("Nome Fantasia", style="bold white", max_width=28)
        table.add_column("Prioridade", justify="center")
        table.add_column("Score", justify="center")
        table.add_column("Telefone", style="cyan")
        table.add_column("CNPJ", style="dim")
        table.add_column("Cardapio PDF", justify="center")
        table.add_column("Zap Cru", justify="center")
        table.add_column("Gancho Comercial / Abordagem WhatsApp", max_width=50)

        for lead in result.leads[:15]:
            b, q, w, c = lead.business, lead.qualification, lead.web_analysis, lead.cnpj_data
            prio = getattr(q.likelihood_no_pos, "value", str(q.likelihood_no_pos)) if q else "N/A"
            if prio == "HIGH":
                prio_styled = "[bold white on red] ALTA [/]"
            elif prio == "MEDIUM":
                prio_styled = "[bold black on yellow] MEDIA [/]"
            else:
                prio_styled = "[bold white on blue] BAIXA [/]"

            table.add_row(
                b.name,
                prio_styled,
                f"{q.confidence_score * 100:.0f}%" if q else "-",
                b.phone or "-",
                c.cnpj if c else (w.cnpj_from_site if (w and w.cnpj_from_site) else "-"),
                "Sim" if (w and w.has_pdf_menu) else "-",
                "Sim" if (w and w.has_whatsapp_order) else "-",
                q.commercial_hook if q else "-",
            )

        console.print(table)
        console.print(f"[italic dim]Exibindo {min(15, len(result.leads))} de {len(result.leads)} leads. Use 'python cli.py list-leads' para ver todos.[/italic dim]\n")


@app.command("list-leads")
def list_leads_command(
    status: str | None = typer.Option(None, "--status", "-s", help="HIGH, MEDIUM, LOW ou NEW, QUALIFIED, CONTACTED"),
    limit: int = typer.Option(20, "--limit", "-l"),
    search: str | None = typer.Option(None, "--search", "-q"),
) -> None:
    """Lista leads armazenados no banco de dados com filtros."""
    async def _fetch_leads() -> list[Any]:
        await init_db()
        likelihood_filter, status_filter = None, None
        if status:
            val = status.strip().upper()
            if val in (LikelihoodLevel.HIGH.value, LikelihoodLevel.MEDIUM.value, LikelihoodLevel.LOW.value):
                likelihood_filter = val
            else:
                status_filter = val

        async with get_db_session() as session:
            return await list_leads(status=status_filter, likelihood=likelihood_filter, search_query=search, limit=limit, session=session)

    try:
        leads = asyncio.run(_fetch_leads())
    finally:
        asyncio.run(close_db())

    if not leads:
        console.print(f"[bold yellow]Nenhum lead localizado (filtro: '{status or "todos"}', busca: '{search or "nenhuma"}').[/bold yellow]")
        return

    table = Table(title=f"Leads Prospectados no Sweezy AI (Total Exibido: {len(leads)})", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Nome Comercial", style="bold white", max_width=25)
    table.add_column("Endereço", style="dim", max_width=30)
    table.add_column("Telefone", style="green")
    table.add_column("Prioridade", justify="center")
    table.add_column("Score", justify="center")
    table.add_column("CNPJ", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Canal", justify="center")

    for lead in leads:
        b, q, c = lead.business, lead.qualification, lead.cnpj_data
        prio = q.likelihood_no_pos if q else "N/A"
        if prio == "HIGH":
            prio_badge = "[bold red]HIGH[/bold red]"
        elif prio == "MEDIUM":
            prio_badge = "[bold yellow]MEDIUM[/bold yellow]"
        else:
            prio_badge = "[bold blue]LOW[/bold blue]"

        table.add_row(
            str(lead.id)[:8],
            b.name if b else "-",
            b.address if b else "-",
            b.phone if (b and b.phone) else "-",
            prio_badge,
            f"{q.confidence_score * 100:.0f}%" if q else "-",
            c.cnpj if c else "-",
            lead.status,
            q.recommended_channel if q else "WHATSAPP",
        )

    console.print(table)


@app.command("export")
def export_command(
    format: str = typer.Option("csv", "--format", "-f"),
    output: str = typer.Option("leads.csv", "--output", "-o"),
    status: str | None = typer.Option(None, "--status", "-s"),
) -> None:
    """Exporta todos os leads qualificados para CSV estruturado."""
    if format.lower() != "csv":
        console.print(f"[bold red]Formato '{format}' não suportado. Utilize '--format csv'.[/bold red]")
        raise typer.Exit(code=1)

    async def _do_export() -> int:
        await init_db()
        likelihood_filter, status_filter = None, None
        if status:
            val = status.strip().upper()
            if val in ("HIGH", "MEDIUM", "LOW"):
                likelihood_filter = val
            else:
                status_filter = val

        async with get_db_session() as session:
            return await export_leads_to_csv(output_path=output, status=status_filter, likelihood=likelihood_filter, session=session)

    try:
        total = asyncio.run(_do_export())
    finally:
        asyncio.run(close_db())

    out_path = Path(output)
    if total > 0 and out_path.exists():
        console.print(
            Panel(
                f"[bold green]Exportacao concluida com sucesso![/bold green]\n\n"
                f"- [bold white]Arquivo:[/bold white] [cyan]{out_path.resolve()}[/cyan]\n"
                f"- [bold white]Total Exportados:[/bold white] {total}\n"
                f"- [bold white]Tamanho:[/bold white] {out_path.stat().st_size / 1024:.2f} KB",
                border_style="green",
                box=box.ROUNDED,
            )
        )
    else:
        console.print(f"[bold yellow]Nenhum lead encontrado para exportar com o filtro '{status or "todos"}'.[/bold yellow]")


@app.command("stats")
def stats_command() -> None:
    """Apresenta métricas consolidadas do funil comercial."""
    async def _fetch_stats() -> dict[str, Any]:
        await init_db()
        async with get_db_session() as session:
            return await get_lead_stats(session=session)

    try:
        stats = asyncio.run(_fetch_stats())
    finally:
        asyncio.run(close_db())

    total = stats.get("total_leads", 0)
    high = stats.get("high_priority", 0)
    med = stats.get("medium_priority", 0)
    low = stats.get("low_priority", 0)
    cnpj = stats.get("enriched_cnpj", 0)
    sess = stats.get("total_scan_sessions", 0)

    table = Table(title="Estatisticas de Qualificacao e Funil Comercial", box=box.ROUNDED, header_style="bold green")
    table.add_column("Métrica", style="bold white")
    table.add_column("Valor Absoluto", justify="right", style="cyan")
    table.add_column("Proporção", justify="right", style="yellow")

    table.add_row("Total de Leads Cadastrados", str(total), "100.0%")
    table.add_row("Alta Prioridade (Sem POS/ERP)", str(high), f"{(high / total * 100 if total else 0):.1f}%")
    table.add_row("Média Prioridade (Mistos)", str(med), f"{(med / total * 100 if total else 0):.1f}%")
    table.add_row("Baixa Prioridade (Com Sistema)", str(low), f"{(low / total * 100 if total else 0):.1f}%")
    table.add_row("Enriquecidos com CNPJ", str(cnpj), f"{(cnpj / total * 100 if total else 0):.1f}%")
    table.add_row("Total de Sessões de Varredura", str(sess), "Sessões salvas")

    console.print(table)


if __name__ == "__main__":
    app()
