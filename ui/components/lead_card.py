"""Componente de exibicao detalhada de Lead com acoes comerciais."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any
import flet as ft

from ui.theme import (
    ACCENT_AMBER,
    ACCENT_BLUE,
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_RED,
    BG_CARD,
    BG_CARD_HOVER,
    BG_SURFACE,
    BORDER_COLOR,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    get_priority_color,
)


class LeadCard(ft.Container):
    """Card estruturado com informacoes de enriquecimento, PDV e acao de vendas."""

    def __init__(self, lead_data: Any, on_copy: Any = None) -> None:
        self.lead = lead_data
        self.on_copy = on_copy

        b = getattr(lead_data, "business", None)
        q = getattr(lead_data, "qualification", None)
        w = getattr(lead_data, "web_analysis", None)
        c = getattr(lead_data, "cnpj_data", None)

        nome = b.name if b else "Comércio sem Nome"
        endereco = b.address if b else "Endereço não disponível"
        telefone = b.phone if (b and b.phone) else ""
        maps_url = b.google_maps_url if b else None

        cnpj = c.cnpj if c else (w.cnpj_from_site if (w and w.cnpj_from_site) else "Não informado")
        porte = str(c.porte) if (c and c.porte) else "ME"
        razao = c.razao_social if c else nome

        prio_val = q.likelihood_no_pos if q else "MEDIUM"
        if hasattr(prio_val, "value"):
            prio_val = prio_val.value
        prio_str = str(prio_val).upper()

        score_val = int(q.confidence_score * 100) if q else 70
        commercial_hook = q.commercial_hook if q else "Olá, temos soluções de automação comercial para o seu negócio."

        # Identificacao de socios
        socios_nomes = []
        if c and hasattr(c, "socios") and c.socios:
            for s in c.socios:
                if isinstance(s, dict):
                    socios_nomes.append(s.get("nome", ""))
                elif isinstance(s, str):
                    socios_nomes.append(s)
        socios_display = ", ".join([s.strip().title() for s in socios_nomes if s][:2]) or "Consultar QSA"

        # Detecao de PDV
        pos_detected = w.detected_pos_systems if (w and w.detected_pos_systems) else []
        if pos_detected:
            pdv_status_text = f"Sistemas Identificados: {', '.join(pos_detected)}"
            pdv_color = ACCENT_BLUE
            pdv_badge = "COM SISTEMA"
        elif w and (w.has_pdf_menu or w.has_whatsapp_order):
            pdv_status_text = "Nenhum PDV/ERP detectado (Operação manual identificada)"
            pdv_color = ACCENT_RED
            pdv_badge = "SEM PDV (ALTA DOR)"
        else:
            pdv_status_text = "Nenhum PDV moderno detectado no site oficial"
            pdv_color = ACCENT_AMBER
            pdv_badge = "SEM PDV MODERNO"

        # Telefone limpo para o WhatsApp
        clean_phone = re.sub(r"[^\d]", "", telefone)
        if clean_phone.startswith("55"):
            clean_phone = clean_phone[2:]
        wa_url = f"https://wa.me/55{clean_phone}?text={urllib.parse.quote(commercial_hook)}" if clean_phone else None

        prio_color = get_priority_color(prio_str)

        super().__init__(
            bgcolor=BG_CARD,
            padding=16,
            border_radius=8,
            border=ft.Border.all(1, BORDER_COLOR),
            content=ft.Column(
                spacing=12,
                controls=[
                    # Linha 1: Titulo, Badges de Prioridade e Score
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Row(
                                spacing=10,
                                controls=[
                                    ft.Text(
                                        nome,
                                        size=16,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXT_PRIMARY,
                                    ),
                                    ft.Container(
                                        bgcolor=BG_SURFACE,
                                        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                        border_radius=4,
                                        border=ft.Border.all(1, prio_color),
                                        content=ft.Text(prio_str, size=10, weight=ft.FontWeight.BOLD, color=prio_color),
                                    ),
                                    ft.Container(
                                        bgcolor=BG_SURFACE,
                                        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                        border_radius=4,
                                        border=ft.Border.all(1, pdv_color),
                                        content=ft.Text(pdv_badge, size=10, weight=ft.FontWeight.W_600, color=pdv_color),
                                    ),
                                ],
                            ),
                            ft.Row(
                                spacing=6,
                                controls=[
                                    ft.Text("Score:", size=12, color=TEXT_MUTED),
                                    ft.Text(f"{score_val}%", size=14, weight=ft.FontWeight.BOLD, color=ACCENT_CYAN),
                                ],
                            ),
                        ],
                    ),
                    # Linha 2: Informacoes Cadastrais (CNPJ, Porte, Socios, Telefone)
                    ft.Row(
                        alignment=ft.MainAxisAlignment.START,
                        spacing=24,
                        wrap=True,
                        controls=[
                            ft.Row(
                                spacing=4,
                                controls=[
                                    ft.Icon(ft.Icons.BADGE_OUTLINED, size=14, color=TEXT_MUTED),
                                    ft.Text(f"CNPJ: {cnpj}", size=12, color=TEXT_SECONDARY),
                                    ft.Text(f"({porte})", size=11, color=TEXT_MUTED),
                                ],
                            ),
                            ft.Row(
                                spacing=4,
                                controls=[
                                    ft.Icon(ft.Icons.PERSON_OUTLINE, size=14, color=TEXT_MUTED),
                                    ft.Text(f"Sócios: {socios_display}", size=12, color=TEXT_SECONDARY),
                                ],
                            ),
                            ft.Row(
                                spacing=4,
                                controls=[
                                    ft.Icon(ft.Icons.PHONE_OUTLINED, size=14, color=ACCENT_GREEN),
                                    ft.Text(telefone or "Sem telefone", size=12, color=ACCENT_GREEN if telefone else TEXT_MUTED),
                                ],
                            ),
                        ],
                    ),
                    # Linha 3: Endereco e Status de PDV
                    ft.Column(
                        spacing=4,
                        controls=[
                            ft.Row(
                                spacing=4,
                                controls=[
                                    ft.Icon(ft.Icons.LOCATION_ON_OUTLINED, size=14, color=TEXT_MUTED),
                                    ft.Text(endereco, size=12, color=TEXT_MUTED),
                                ],
                            ),
                            ft.Row(
                                spacing=4,
                                controls=[
                                    ft.Icon(ft.Icons.TERMINAL_OUTLINED, size=14, color=pdv_color),
                                    ft.Text(pdv_status_text, size=12, color=pdv_color),
                                ],
                            ),
                        ],
                    ),
                    # Linha 4: Bloco do Roteiro / Pitch de Abordagem
                    ft.Container(
                        bgcolor=BG_SURFACE,
                        padding=12,
                        border_radius=6,
                        border=ft.Border.all(1, BORDER_COLOR),
                        content=ft.Column(
                            spacing=4,
                            controls=[
                                ft.Text("Roteiro Consultivo de Abordagem:", size=11, weight=ft.FontWeight.W_600, color=ACCENT_CYAN),
                                ft.Text(f'"{commercial_hook}"', size=12, italic=True, color=TEXT_SECONDARY),
                            ],
                        ),
                    ),
                    # Linha 5: Botoes de Acao
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        spacing=10,
                        controls=[
                            ft.OutlinedButton(
                                content="Copiar Pitch",
                                icon=ft.Icons.COPY_ALL,
                                style=ft.ButtonStyle(color=TEXT_PRIMARY),
                                on_click=lambda e: self._copy_pitch_clicked(e, commercial_hook),
                            ),
                            ft.OutlinedButton(
                                content="Ver no Maps",
                                icon=ft.Icons.MAP_OUTLINED,
                                style=ft.ButtonStyle(color=TEXT_SECONDARY),
                                url=maps_url,
                                visible=bool(maps_url),
                            ),
                            ft.FilledButton(
                                content="Abrir WhatsApp",
                                icon=ft.Icons.CHAT,
                                style=ft.ButtonStyle(bgcolor=ACCENT_GREEN, color=TEXT_PRIMARY),
                                url=wa_url,
                                visible=bool(wa_url),
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _copy_pitch_clicked(self, e: Any, text: str) -> None:
        """Copia o pitch para a area de transferencia e emite notificacao."""
        import subprocess
        import sys

        try:
            if sys.platform == "win32":
                subprocess.run(["clip"], input=text.encode("utf-16"), check=True)
            elif sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True)
        except Exception:
            pass

        try:
            e.page.show_dialog(
                ft.SnackBar(
                    content=ft.Text("Pitch de abordagem copiado para a área de transferência!"),
                    bgcolor=BG_SURFACE,
                    duration=2500,
                )
            )
        except Exception:
            pass
