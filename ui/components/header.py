"""Componente de cabecalho superior e navegacao principal."""

from __future__ import annotations

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

    def __init__(self, on_tab_change: Callable[[int], None]) -> None:
        self.on_tab_change = on_tab_change

        self.tabs = ft.Tabs(
            selected_index=0,
            animation_duration=200,
            indicator_color=ACCENT_CYAN,
            label_color=ACCENT_CYAN,
            unselected_label_color=TEXT_MUTED,
            on_change=lambda e: self.on_tab_change(int(e.control.selected_index)),
            tabs=[
                ft.Tab(text="Nova Varredura", icon=ft.Icons.SEARCH),
                ft.Tab(text="Leads Qualificados", icon=ft.Icons.PEOPLE_ALT_OUTLINED),
                ft.Tab(text="Estatísticas", icon=ft.Icons.INSIGHTS),
                ft.Tab(text="Configurações", icon=ft.Icons.SETTINGS_OUTLINED),
            ],
        )

        super().__init__(
            bgcolor=BG_SURFACE,
            padding=ft.padding.symmetric(horizontal=24, vertical=12),
            border=ft.border.only(bottom=ft.BorderSide(1, BORDER_COLOR)),
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
                                padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                border_radius=6,
                                border=ft.border.all(1, BORDER_COLOR),
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
