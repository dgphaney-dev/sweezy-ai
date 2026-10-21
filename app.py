"""Ponto de entrada da Aplicacao Desktop do Sweezy AI (Flet Desktop)."""

from __future__ import annotations

import sys
from pathlib import Path

# Garante inclusao do diretorio raiz no PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import flet as ft

from ui.components.header import Header
from ui.theme import apply_page_theme
from ui.views.analytics_view import AnalyticsView
from ui.views.leads_view import LeadsView
from ui.views.scan_view import ScanView
from ui.views.settings_view import SettingsView


def main(page: ft.Page) -> None:
    """Inicializacao da aplicacao Desktop."""
    apply_page_theme(page)

    def on_scan_finished() -> None:
        """Callback executado ao finalizar uma varredura."""
        pass

    def on_tab_change(tab_index: int) -> None:
        """Alterna a exibicao dos modulos conforme a aba selecionada."""
        if tab_index == 0:
            content_area.content = scan_view
        elif tab_index == 1:
            content_area.content = leads_view
            leads_view.load_leads()
        elif tab_index == 2:
            content_area.content = analytics_view
            analytics_view.load_stats()
        elif tab_index == 3:
            content_area.content = settings_view
        page.update()

    header = Header(on_tab_change=on_tab_change)
    scan_view = ScanView(on_scan_finished=on_scan_finished)
    leads_view = LeadsView()
    analytics_view = AnalyticsView()
    settings_view = SettingsView()

    content_area = ft.Container(
        expand=True,
        content=scan_view,
    )

    page.add(
        ft.Column(
            expand=True,
            spacing=0,
            controls=[
                header,
                content_area,
            ],
        )
    )

    # Carrega contadores iniciais de fundo
    leads_view.load_leads()
    page.update()


if __name__ == "__main__":
    ft.run(main)
