"""Componente de cabecalho superior e navegacao principal."""

from __future__ import annotations

import inspect
from typing import Callable
import flet as ft

from ui.theme import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    BG_CARD,
    BG_SURFACE,
    BORDER_COLOR,
    TEXT_MUTED,
    TEXT_PRIMARY,
)


class Header(ft.Container):
    """Barra superior com branding e navegacao entre modulos."""

    def __init__(self, on_tab_change: Callable[[int], Any]) -> None:
        self.on_tab_change = on_tab_change

        self.tab_bar = ft.TabBar(
            indicator_color=ACCENT_CYAN,
            label_color=ACCENT_CYAN,
            unselected_label_color=TEXT_MUTED,
            tabs=[
                ft.Tab(label="Nova Varredura", icon=ft.Icons.SEARCH),
                ft.Tab(label="Leads Qualificados", icon=ft.Icons.PEOPLE_ALT_OUTLINED),
                ft.Tab(label="Estatísticas", icon=ft.Icons.INSIGHTS),
                ft.Tab(label="Configurações", icon=ft.Icons.SETTINGS_OUTLINED),
            ],
        )

        self.tabs = ft.Tabs(
            length=4,
            selected_index=0,
            animation_duration=200,
            on_change=self._tab_changed,
            content=self.tab_bar,
        )

        super().__init__(
            bgcolor=BG_SURFACE,
            padding=ft.Padding.symmetric(horizontal=24, vertical=12),
            border=ft.Border.only(bottom=ft.BorderSide(1, BORDER_COLOR)),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.RADAR, color=ACCENT_CYAN, size=28),
                            ft.Column(
                                spacing=0,
                                controls=[
                                    ft.Text(
                                        "SWEEZY AI",
                                        size=18,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXT_PRIMARY,
                                    ),
                                    ft.Text(
                                        "INTELLIGENCE B2B",
                                        size=10,
                                        weight=ft.FontWeight.W_600,
                                        color=ACCENT_CYAN,
                                    ),
                                ],
                            ),
                            ft.Container(
                                bgcolor=BG_CARD,
                                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                border_radius=6,
                                border=ft.Border.all(1, BORDER_COLOR),
                                content=ft.Row(
                                    spacing=6,
                                    controls=[
                                        ft.Container(width=7, height=7, border_radius=4, bgcolor=ACCENT_GREEN),
                                        ft.Text("Motor 100% Local (R$ 0,00)", size=11, color=TEXT_PRIMARY),
                                    ],
                                ),
                            ),
                        ],
                    ),
                    self.tabs,
                ],
            ),
        )

    async def _tab_changed(self, e: Any) -> None:
        """Propaga a mudanca de aba para o callback registrado."""
        idx = int(e.control.selected_index)
        res = self.on_tab_change(idx)
        if inspect.isawaitable(res):
            await res
