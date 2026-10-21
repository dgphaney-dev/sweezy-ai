"""Tela de analise de metricas e funil comercial do Sweezy AI."""

from __future__ import annotations

import asyncio
from typing import Any
import flet as ft

from core.database import get_db_session, get_lead_stats, init_db
from ui.theme import (
    ACCENT_AMBER,
    ACCENT_BLUE,
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


class AnalyticsView(ft.Container):
    """View executiva com indicadores de desempenho e qualificacao de leads."""

    def __init__(self) -> None:
        self.cards_row = ft.Row(spacing=16, wrap=True)
        self.progress_column = ft.Column(spacing=14)

        super().__init__(
            expand=True,
            padding=24,
            content=ft.Column(
                expand=True,
                spacing=20,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    # Cabecalho
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    ft.Text("Métricas Comerciais e Funil de Qualificação", size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                    ft.Text("Visão consolidada da carência tecnológica e maturidade dos estabelecimentos prospectados", size=13, color=TEXT_MUTED),
                                ],
                            ),
                            ft.IconButton(
                                icon=ft.Icons.REFRESH,
                                tooltip="Atualizar Métricas",
                                on_click=lambda e: self.load_stats(),
                            ),
                        ],
                    ),
                    # Fileira de Cards de Metricas Principais
                    self.cards_row,
                    # Painel de Distribuicao e Gargalos
                    ft.Container(
                        bgcolor=BG_SURFACE,
                        padding=20,
                        border_radius=8,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=ft.Column(
                            spacing=14,
                            controls=[
                                ft.Text("Distribuição de Potencial por Nível de Prioridade", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                self.progress_column,
                            ],
                        ),
                    ),
                ],
            ),
        )

    def _build_kpi_card(self, title: str, value: str, subtitle: str, color: str, icon: Any) -> ft.Container:
        """Constroi um card indicador com borda e cor customizada."""
        return ft.Container(
            width=260,
            bgcolor=BG_CARD,
            padding=18,
            border_radius=8,
            border=ft.Border.all(1, BORDER_COLOR),
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(title, size=12, color=TEXT_MUTED, weight=ft.FontWeight.W_600),
                            ft.Icon(icon, size=20, color=color),
                        ],
                    ),
                    ft.Text(value, size=28, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ft.Text(subtitle, size=11, color=color),
                ],
            ),
        )

    def _build_distribution_bar(self, label: str, count: int, total: int, color: str) -> ft.Column:
        """Constroi uma barra de progresso proporcional para um segmento."""
        pct = (count / total) if total > 0 else 0.0
        return ft.Column(
            spacing=4,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(label, size=12, color=TEXT_SECONDARY),
                        ft.Text(f"{count} ({pct * 100:.1f}%)", size=12, weight=ft.FontWeight.BOLD, color=color),
                    ],
                ),
                ft.ProgressBar(value=pct, color=color, bgcolor=BG_CARD, height=8),
            ],
        )

    def load_stats(self) -> None:
        """Carrega dados estatisticos do SQLite e atualiza os graficos."""
        async def _fetch() -> dict[str, Any]:
            await init_db()
            async with get_db_session() as session:
                return await get_lead_stats(session=session)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            stats = loop.run_until_complete(_fetch())
        finally:
            loop.close()

        total = stats.get("total_leads", 0)
        high = stats.get("high_priority", 0)
        med = stats.get("medium_priority", 0)
        low = stats.get("low_priority", 0)
        cnpj = stats.get("enriched_cnpj", 0)
        sessions = stats.get("total_scan_sessions", 0)

        self.cards_row.controls.clear()
        self.cards_row.controls.extend([
            self._build_kpi_card("TOTAL DE LEADS", str(total), "Estabelecimentos no banco", ACCENT_CYAN, ft.Icons.STORE),
            self._build_kpi_card("ALTA PRIORIDADE", str(high), "Sem PDV / Alta carência", ACCENT_RED, ft.Icons.WARNING_AMBER),
            self._build_kpi_card("MÉDIA PRIORIDADE", str(med), "Sistemas mistos ou legados", ACCENT_AMBER, ft.Icons.TIMELAPSE),
            self._build_kpi_card("ENRIQUECIDOS CNPJ", str(cnpj), f"{(cnpj/total*100 if total else 0):.1f}% com dados fiscais", ACCENT_GREEN, ft.Icons.VERIFIED_OUTLINED),
        ])

        self.progress_column.controls.clear()
        self.progress_column.controls.extend([
            self._build_distribution_bar("Alta Prioridade (Sem Sistema / Operação Manual)", high, total, ACCENT_RED),
            self._build_distribution_bar("Média Prioridade (Sistemas Legados ou Incompletos)", med, total, ACCENT_AMBER),
            self._build_distribution_bar("Baixa Prioridade (Já utilizam ERP Consolidado)", low, total, ACCENT_BLUE),
        ])

        if self.page:
            self.page.update()
