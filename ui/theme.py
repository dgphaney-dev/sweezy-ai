"""Definicoes de tema, paleta de cores e estilos para a interface do Sweezy AI."""

from __future__ import annotations

import flet as ft

# Paleta de Cores Corporativa (Dark Slate & Emerald/Cyan)
BG_PRIMARY = "#0B132B"
BG_SURFACE = "#1C2541"
BG_CARD = "#141D38"
BG_CARD_HOVER = "#1E2A4A"

ACCENT_CYAN = "#2DD4BF"
ACCENT_BLUE = "#3B82F6"
ACCENT_GREEN = "#10B981"
ACCENT_AMBER = "#F59E0B"
ACCENT_RED = "#EF4444"

TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#94A3B8"
TEXT_MUTED = "#64748B"

BORDER_COLOR = "#2A3756"
BORDER_FOCUS = "#2DD4BF"


def apply_page_theme(page: ft.Page) -> None:
    """Configura o tema escuro e propriedades da janela principal."""
    page.title = "Sweezy AI Enterprise - Prospecção B2B"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG_PRIMARY
    page.padding = 0
    page.window.min_width = 1000
    page.window.min_height = 700
    page.window.width = 1200
    page.window.height = 800


def get_priority_color(priority: str) -> str:
    """Retorna a cor associada ao nivel de prioridade do lead."""
    prio = str(priority).upper().strip()
    if prio in ("HIGH", "ALTA"):
        return ACCENT_RED
    if prio in ("MEDIUM", "MEDIA", "MÉDIA"):
        return ACCENT_AMBER
    return ACCENT_BLUE
