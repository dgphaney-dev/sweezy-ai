"""Tela de configuracoes gerais e diagnosticos do sistema."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import flet as ft

from config.settings import get_settings
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


class SettingsView(ft.Container):
    """View de configuracoes de API, persistencia e diagnostico operacional."""

    def __init__(self) -> None:
        settings = get_settings()
        env_key = os.getenv("GOOGLE_API_KEY", getattr(settings, "google_api_key", ""))
        masked_key = f"{env_key[:6]}...{env_key[-4:]}" if len(env_key) > 10 else "Não configurada"

        self.key_input = ft.TextField(
            label="Chave da Google Places API (New)",
            value=env_key,
            password=True,
            can_reveal_password=True,
            bgcolor=BG_CARD,
            border_color=BORDER_COLOR,
            expand=True,
        )

        db_path = Path("data/sweezy.db").resolve()
        db_exists = db_path.exists()
        db_size_kb = db_path.stat().st_size / 1024 if db_exists else 0.0

        super().__init__(
            expand=True,
            padding=24,
            content=ft.Column(
                expand=True,
                spacing=20,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    # Titulo
                    ft.Column(
                        spacing=2,
                        controls=[
                            ft.Text("Configurações do Sistema", size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ft.Text("Credenciais de busca, integridade de banco de dados e parametros operacionais", size=13, color=TEXT_MUTED),
                        ],
                    ),
                    # Secao: Provedor Geografico
                    ft.Container(
                        bgcolor=BG_SURFACE,
                        padding=20,
                        border_radius=8,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    controls=[
                                        ft.Text("Provedor Geográfico: OpenStreetMap (OSM)", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                        ft.Container(
                                            bgcolor=BG_CARD,
                                            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                            border_radius=4,
                                            content=ft.Row(
                                                spacing=6,
                                                controls=[
                                                    ft.Container(width=7, height=7, border_radius=4, bgcolor=ACCENT_GREEN),
                                                    ft.Text("Ativo (100% Gratuito - R$ 0,00)", size=11, color=TEXT_PRIMARY),
                                                ],
                                            ),
                                        ),
                                    ],
                                ),
                                ft.Text(
                                    "O motor OpenStreetMap / Nominatim busca estabelecimentos reais de rua, padarias, oficinas, farmácias e mercados de qualquer cidade brasileira sem consumir cotas, sem chave e sem cartão de crédito.",
                                    size=12,
                                    color=TEXT_SECONDARY,
                                ),
                                ft.Divider(color=BORDER_COLOR, height=1),
                                ft.Text("Chave Opcional: Google Cloud Places API (New)", size=13, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                                ft.Row(
                                    spacing=10,
                                    controls=[
                                        self.key_input,
                                        ft.FilledButton(
                                            content="Salvar Chave",
                                            icon=ft.Icons.SAVE,
                                            style=ft.ButtonStyle(bgcolor=ACCENT_CYAN, color=BG_SURFACE),
                                            on_click=self._save_key_clicked,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ),
                    # Secao: Banco de Dados Local
                    ft.Container(
                        bgcolor=BG_SURFACE,
                        padding=20,
                        border_radius=8,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Text("Persistência Local (SQLite WAL)", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                ft.Row(
                                    spacing=24,
                                    controls=[
                                        ft.Column(
                                            spacing=4,
                                            controls=[
                                                ft.Text("Caminho do Banco:", size=12, color=TEXT_MUTED),
                                                ft.Text(str(db_path), size=12, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                                            ],
                                        ),
                                        ft.Column(
                                            spacing=4,
                                            controls=[
                                                ft.Text("Tamanho Atual:", size=12, color=TEXT_MUTED),
                                                ft.Text(f"{db_size_kb:.1f} KB", size=12, weight=ft.FontWeight.W_600, color=ACCENT_CYAN),
                                            ],
                                        ),
                                        ft.Column(
                                            spacing=4,
                                            controls=[
                                                ft.Text("Modo Concorrente:", size=12, color=TEXT_MUTED),
                                                ft.Text("PRAGMA journal_mode=WAL", size=12, weight=ft.FontWeight.W_600, color=ACCENT_GREEN),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ),
                    # Secao: Motor Cognitivo
                    ft.Container(
                        bgcolor=BG_SURFACE,
                        padding=20,
                        border_radius=8,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=ft.Column(
                            spacing=10,
                            controls=[
                                ft.Text("Motor de Qualificação B2B", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                ft.Text(
                                    "O qualificador opera de forma 100% determinística local em Python. Não requer OpenAI e gera diagnósticos de vendas com custo zero.",
                                    size=12,
                                    color=TEXT_SECONDARY,
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        )

    def _save_key_clicked(self, e: Any) -> None:
        """Salva a chave no arquivo .env se informada."""
        new_key = (self.key_input.value or "").strip()
        if not new_key:
            return

        env_path = Path(".env")
        lines = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()

        updated = False
        new_lines = []
        for line in lines:
            if line.startswith("GOOGLE_API_KEY=") or line.startswith("GOOGLE_PLACES_API_KEY="):
                new_lines.append(f"GOOGLE_API_KEY={new_key}")
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f"GOOGLE_API_KEY={new_key}")

        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        os.environ["GOOGLE_API_KEY"] = new_key

        try:
            e.page.show_dialog(
                ft.SnackBar(
                    content=ft.Text("Chave da Google Places API salva com sucesso no .env!"),
                    bgcolor=BG_SURFACE,
                    duration=3000,
                )
            )
        except Exception:
            pass
