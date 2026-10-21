"""Tela de gestao, filtragem e abordagem de Leads qualificados."""

from __future__ import annotations

import asyncio
import os
from typing import Any
import flet as ft

from core.database import export_leads_to_csv, get_db_session, init_db, list_leads
from core.models import LikelihoodLevel
from ui.components.lead_card import LeadCard
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


class LeadsView(ft.Container):
    """View de listagem, busca e acao sobre os leads armazenados no SQLite."""

    def __init__(self) -> None:
        self.search_input = ft.TextField(
            hint_text="Buscar por nome, bairro, telefone ou CNPJ...",
            prefix_icon=ft.Icons.SEARCH,
            bgcolor=BG_CARD,
            border_color=BORDER_COLOR,
            expand=True,
            on_change=self._on_search_changed,
        )

        self.current_filter = "ALL"
        self.btn_export = ft.OutlinedButton(
            content="Exportar CSV",
            icon=ft.Icons.DOWNLOAD,
            style=ft.ButtonStyle(color=ACCENT_CYAN),
            on_click=self._export_csv_clicked,
        )

        self.btn_refresh = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Atualizar Leads",
            icon_color=TEXT_SECONDARY,
            on_click=self._on_refresh_clicked,
        )

        # Chips / Segmentos de filtro de prioridade
        self.filter_buttons = ft.Row(
            spacing=8,
            controls=[
                self._build_filter_chip("Todos", "ALL", ACCENT_CYAN, is_active=True),
                self._build_filter_chip("Alta Prioridade (Sem PDV)", "HIGH", ACCENT_RED),
                self._build_filter_chip("Média Prioridade", "MEDIUM", ACCENT_AMBER),
                self._build_filter_chip("Baixa Prioridade", "LOW", ACCENT_BLUE),
            ],
        )

        self.counter_text = ft.Text("Carregando leads...", size=13, color=TEXT_MUTED)

        # Lista de Cards
        self.leads_list = ft.ListView(
            expand=True,
            spacing=12,
            padding=ft.Padding.only(right=10),
        )

        super().__init__(
            expand=True,
            padding=24,
            content=ft.Column(
                expand=True,
                spacing=16,
                controls=[
                    # Cabecalho da Tela
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    ft.Text("Leads Qualificados para Abordagem", size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                    self.counter_text,
                                ],
                            ),
                            ft.Row(
                                spacing=8,
                                controls=[self.btn_export, self.btn_refresh],
                            ),
                        ],
                    ),
                    # Barra de Busca e Filtros
                    ft.Container(
                        bgcolor=BG_SURFACE,
                        padding=12,
                        border_radius=8,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=ft.Column(
                            spacing=10,
                            controls=[
                                self.search_input,
                                self.filter_buttons,
                            ],
                        ),
                    ),
                    # Lista de Cards dos Leads
                    ft.Container(
                        expand=True,
                        content=self.leads_list,
                    ),
                ],
            ),
        )

    async def _on_refresh_clicked(self, e: Any) -> None:
        """Atualiza a lista de leads."""
        await self.load_leads()

    def _build_filter_chip(self, label: str, value: str, color: str, is_active: bool = False) -> ft.Container:
        """Cria um botao de filtro estilisado."""
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border_radius=6,
            bgcolor=BG_CARD if not is_active else BG_SURFACE,
            border=ft.Border.all(1, color if is_active else BORDER_COLOR),
            ink=True,
            on_click=lambda e: self._on_filter_clicked(value),
            content=ft.Text(label, size=12, weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.NORMAL, color=color if is_active else TEXT_SECONDARY),
        )

    async def _on_filter_clicked(self, filter_value: str) -> None:
        """Atualiza o filtro de prioridade selecionado."""
        self.current_filter = filter_value
        for chip in self.filter_buttons.controls:
            chip_label = chip.content.value
            is_active = (
                (filter_value == "ALL" and "Todos" in chip_label)
                or (filter_value == "HIGH" and "Alta" in chip_label)
                or (filter_value == "MEDIUM" and "Média" in chip_label)
                or (filter_value == "LOW" and "Baixa" in chip_label)
            )
            chip.border = ft.Border.all(1, ACCENT_CYAN if is_active else BORDER_COLOR)
            chip.content.color = ACCENT_CYAN if is_active else TEXT_SECONDARY
            chip.content.weight = ft.FontWeight.W_600 if is_active else ft.FontWeight.NORMAL

        await self.load_leads()

    async def _on_search_changed(self, e: Any) -> None:
        """Dispara busca ao digitar com debounce implicito."""
        await self.load_leads()

    async def load_leads(self) -> None:
        """Busca leads do banco de dados assincrono e popula a lista."""
        query_text = (self.search_input.value or "").strip()
        prio = None if self.current_filter == "ALL" else self.current_filter

        await init_db()
        async with get_db_session() as session:
            leads = await list_leads(
                likelihood=prio,
                search_query=query_text or None,
                limit=100,
                session=session,
            )

        self.leads_list.controls.clear()
        if not leads:
            self.counter_text.value = "Nenhum lead encontrado com os filtros aplicados."
            self.leads_list.controls.append(
                ft.Container(
                    padding=40,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.SEARCH_OFF, size=48, color=TEXT_MUTED),
                            ft.Text("Nenhum lead localizado.", size=16, weight=ft.FontWeight.BOLD, color=TEXT_SECONDARY),
                            ft.Text("Realize uma nova varredura ou ajuste os termos de pesquisa.", size=13, color=TEXT_MUTED),
                        ],
                    ),
                )
            )
        else:
            self.counter_text.value = f"Exibindo {len(leads)} estabelecimentos prospectados:"
            for lead in leads:
                self.leads_list.controls.append(LeadCard(lead))

        try:
            self.update()
        except Exception:
            pass

    async def _export_csv_clicked(self, e: Any) -> None:
        """Exporta os leads para arquivo CSV e notifica o usuario."""
        prio = None if self.current_filter == "ALL" else self.current_filter
        out_name = "leads_exportados.csv"

        await init_db()
        async with get_db_session() as session:
            total = await export_leads_to_csv(output_path=out_name, likelihood=prio, session=session)

        full_path = os.path.abspath(out_name)
        try:
            e.page.show_dialog(
                ft.SnackBar(
                    content=ft.Text(f"{total} leads exportados com sucesso para: {out_name}"),
                    bgcolor=BG_SURFACE,
                    duration=3500,
                )
            )
        except Exception:
            pass
