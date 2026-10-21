"""Tela de nova varredura e prospeccao geografica."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable
import flet as ft

from config.settings import get_settings
from core.database import init_db
from discovery.grid_scanner import geocode_location
from pipeline.lead_pipeline import LeadPipeline, PipelineProgress, PipelineStage
from ui.theme import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_RED,
    BG_CARD,
    BG_SURFACE,
    BORDER_COLOR,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class ScanView(ft.Container):
    """View de configuracao e execucao da varredura com telemetria ao vivo."""

    def __init__(self, on_scan_finished: Callable[[], None]) -> None:
        self.on_scan_finished = on_scan_finished

        # Inputs de Busca
        self.cidade_input = ft.TextField(
            label="Cidade",
            hint_text="ex: Belo Horizonte, Curitiba, São Paulo",
            value="Brasília",
            bgcolor=BG_CARD,
            border_color=BORDER_COLOR,
            focused_border_color=ACCENT_CYAN,
            expand=2,
        )

        self.uf_input = ft.Dropdown(
            label="UF / Estado",
            value="DF",
            bgcolor=BG_CARD,
            border_color=BORDER_COLOR,
            focused_border_color=ACCENT_CYAN,
            expand=1,
            options=[
                ft.dropdown.Option("DF"),
                ft.dropdown.Option("MG"),
                ft.dropdown.Option("SP"),
                ft.dropdown.Option("RJ"),
                ft.dropdown.Option("PR"),
                ft.dropdown.Option("RS"),
                ft.dropdown.Option("SC"),
                ft.dropdown.Option("BA"),
                ft.dropdown.Option("GO"),
                ft.dropdown.Option("PE"),
                ft.dropdown.Option("CE"),
            ],
        )

        self.tipo_input = ft.Dropdown(
            label="Segmento / Nicho",
            value="restaurantes",
            bgcolor=BG_CARD,
            border_color=BORDER_COLOR,
            focused_border_color=ACCENT_CYAN,
            expand=2,
            options=[
                ft.dropdown.Option("restaurantes", text="Restaurantes e Alimentação"),
                ft.dropdown.Option("padarias", text="Padarias e Confeitarias"),
                ft.dropdown.Option("mercados", text="Mercados e Mercearias"),
                ft.dropdown.Option("autopecas", text="Auto-peças e Mecânicas"),
                ft.dropdown.Option("farmacias", text="Farmácias e Drogarias"),
                ft.dropdown.Option("vestuario", text="Lojas de Roupas / Vestuário"),
                ft.dropdown.Option("oficinas", text="Oficinas e Funilarias"),
            ],
        )

        self.raio_slider = ft.Slider(
            min=1.0,
            max=10.0,
            divisions=9,
            value=3.0,
            label="{value} km",
            active_color=ACCENT_CYAN,
        )

        # Botao de Inicio
        self.btn_iniciar = ft.FilledButton(
            content="Iniciar Prospecção",
            icon=ft.Icons.ROCKET_LAUNCH,
            style=ft.ButtonStyle(bgcolor=ACCENT_CYAN, color=BG_SURFACE),
            height=48,
            on_click=self._start_scan_clicked,
        )

        # Elementos de Progresso
        self.progress_bar = ft.ProgressBar(value=0.0, color=ACCENT_CYAN, bgcolor=BG_CARD, visible=False)
        self.status_label = ft.Text("Pronto para iniciar varredura.", size=13, color=TEXT_SECONDARY)
        self.counter_label = ft.Text("", size=13, weight=ft.FontWeight.BOLD, color=ACCENT_CYAN)

        # Feed de Eventos / Log
        self.log_list = ft.ListView(
            expand=True,
            spacing=4,
            auto_scroll=True,
        )

        super().__init__(
            expand=True,
            padding=24,
            content=ft.Column(
                expand=True,
                spacing=16,
                controls=[
                    # Titulo do Modulo
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    ft.Text("Varredura Geográfica e Enriquecimento", size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                    ft.Text("Mapeamento automático de estabelecimentos reais e cruzamento com a Receita Federal", size=13, color=TEXT_MUTED),
                                ],
                            ),
                        ],
                    ),
                    # Formulario de Parametros
                    ft.Container(
                        bgcolor=BG_SURFACE,
                        padding=18,
                        border_radius=8,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=ft.Column(
                            spacing=14,
                            controls=[
                                ft.Row(
                                    spacing=12,
                                    controls=[self.cidade_input, self.uf_input, self.tipo_input],
                                ),
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=[
                                        ft.Row(
                                            spacing=8,
                                            controls=[
                                                ft.Text("Raio de Cobertura:", size=13, color=TEXT_SECONDARY),
                                                ft.Container(width=250, content=self.raio_slider),
                                            ],
                                        ),
                                        self.btn_iniciar,
                                    ],
                                ),
                            ],
                        ),
                    ),
                    # Barra de Status e Progresso
                    ft.Container(
                        bgcolor=BG_SURFACE,
                        padding=16,
                        border_radius=8,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=ft.Column(
                            spacing=8,
                            controls=[
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    controls=[self.status_label, self.counter_label],
                                ),
                                self.progress_bar,
                            ],
                        ),
                    ),
                    # Terminal de Eventos ao Vivo
                    ft.Text("Feed de Atividades em Tempo Real:", size=13, weight=ft.FontWeight.W_600, color=TEXT_MUTED),
                    ft.Container(
                        expand=True,
                        bgcolor=BG_CARD,
                        padding=12,
                        border_radius=8,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=self.log_list,
                    ),
                ],
            ),
        )

    def _append_log(self, text: str, is_highlight: bool = False, is_error: bool = False) -> None:
        """Adiciona uma linha no feed de atividades."""
        color = ACCENT_RED if is_error else (ACCENT_GREEN if is_highlight else TEXT_SECONDARY)
        self.log_list.controls.append(
            ft.Row(
                spacing=8,
                controls=[
                    ft.Text(">", size=11, color=ACCENT_CYAN),
                    ft.Text(text, size=12, color=color, selectable=True),
                ],
            )
        )
        if self.page:
            self.page.update()

    def _start_scan_clicked(self, e: Any) -> None:
        """Dispara a rotina de varredura assincrona em thread dedicada."""
        cidade = (self.cidade_input.value or "Brasília").strip()
        uf = (self.uf_input.value or "DF").strip()
        tipo = (self.tipo_input.value or "restaurantes").strip()
        raio = float(self.raio_slider.value or 3.0)

        self.btn_iniciar.disabled = True
        self.progress_bar.visible = True
        self.progress_bar.value = None  # Spinner indeterminado inicial
        self.status_label.value = f"Geocodificando {cidade}, {uf}..."
        self.log_list.controls.clear()
        self._append_log(f"Iniciando varredura para {cidade}, {uf} (Raio: {raio:.1f} km, Segmento: {tipo})...")
        self.page.update()

        threading.Thread(
            target=self._run_scan_thread,
            args=(cidade, uf, tipo, raio),
            daemon=True,
        ).start()

    def _run_scan_thread(self, cidade: str, uf: str, tipo: str, raio: float) -> None:
        """Executa o loop de eventos assincrono na thread de trabalho."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._execute_scan_async(cidade, uf, tipo, raio))
        finally:
            loop.close()

    async def _execute_scan_async(self, cidade: str, uf: str, tipo: str, raio: float) -> None:
        """Rotina assincrona de resolucao de coordenadas e pipeline."""
        target_name = f"{cidade}, {uf}"
        await init_db()

        lat, lng, display_name = await geocode_location(target_name)
        self._append_log(f"Coordenadas identificadas: {lat:.4f}, {lng:.4f} ({display_name})")

        settings = get_settings()
        pipeline = LeadPipeline(settings=settings, concurrency_limit=5)

        def on_progress(p: PipelineProgress) -> None:
            if p.stage == PipelineStage.GRID_GENERATION:
                self.status_label.value = "Calculando malha geográfica de cobertura..."
            elif p.stage == PipelineStage.PLACES_SEARCH:
                self.status_label.value = f"Mapeando comércios no Google Places ({p.places_found} identificados)..."
                self.counter_label.value = f"{p.places_found} locais"
                if p.total_steps > 0:
                    self.progress_bar.value = p.current_step / p.total_steps
            elif p.stage == PipelineStage.DEDUPLICATION:
                self.status_label.value = f"Verificando {p.places_unique} locais únicos na base histórica..."
            elif p.stage == PipelineStage.ENRICHMENT:
                nome_b = f": {p.current_business_name}" if p.current_business_name else ""
                self.status_label.value = f"Enriquecendo dados fiscais (Receita Federal) e PDV ({p.current_step}/{p.total_steps}){nome_b}"
                if p.total_steps > 0:
                    self.progress_bar.value = p.current_step / p.total_steps
                if p.current_business_name:
                    self._append_log(f"Auditado: {p.current_business_name}")
            elif p.stage == PipelineStage.COMPLETED:
                self.status_label.value = "Varredura concluída com sucesso!"
                self.progress_bar.value = 1.0

            if self.page:
                self.page.update()

        try:
            result = await pipeline.run_scan(
                region_name=target_name,
                center_lat=lat,
                center_lng=lng,
                radius_km=raio,
                step_km=1.0,
                business_types=[tipo],
                progress_callback=on_progress,
            )

            self._append_log(
                f"Sucesso! {result.total_places_found} estabelecimentos localizados, {result.total_leads_saved} leads qualificados salvos.",
                is_highlight=True,
            )
            self.status_label.value = f"Varredura finalizada em {result.duration_seconds:.1f}s!"
            self.counter_label.value = f"{result.total_leads_saved} leads salvos"

        except Exception as err:
            self._append_log(f"Erro durante a varredura: {err}", is_error=True)
            self.status_label.value = "Erro na execução da varredura."
        finally:
            self.btn_iniciar.disabled = False
            self.progress_bar.visible = False
            if self.page:
                self.page.update()
            if self.on_scan_finished:
                self.on_scan_finished()
