"""Web scraper assíncrono para extração de evidências e presenças digitais no ProspectAI.

Este módulo realiza a raspagem de sites de estabelecimentos comerciais utilizando `httpx`
e `BeautifulSoup4`. Extrai informações cadastrais (como CNPJ no rodapé), links sociais
(Instagram, Facebook), botões de pedidos, links de WhatsApp, cardápios em PDF/nuvem e
indícios de plataformas de automação ou e-commerce.
"""

from __future__ import annotations

import asyncio
import random
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console

from analysis.pos_detector import (
    COMPETITOR_PLATFORMS,
    POSDetector,
    PixKeyType,
    REGEX_ONLINE_CART,
    REGEX_PDF_OR_STATIC_MENU,
    REGEX_PIX_CNPJ,
    REGEX_WA_AUTOMATED,
    REGEX_WA_URL,
    validate_cnpj,
)

console = Console()

# ==============================================================================
# Modelos de Dados de Scraping
# ==============================================================================

class ScrapingResult(BaseModel):
    """Resultado estruturado da raspagem de um website de comércio."""
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    url: str | None = Field(default=None, description="URL analisada")
    has_website: bool = Field(default=False, description="Indica se o site respondeu com sucesso")
    status_code: int | None = Field(default=None, description="Código de resposta HTTP")
    title: str | None = Field(default=None, description="Título da página principal")
    cnpj_from_site: str | None = Field(default=None, description="CNPJ válido extraído do rodapé ou texto")
    social_links: dict[str, str | None] = Field(
        default_factory=lambda: {"instagram": None, "facebook": None},
        description="Links identificados de redes sociais",
    )
    whatsapp_urls: list[str] = Field(default_factory=list, description="Links de WhatsApp encontrados")
    has_whatsapp_order: bool = Field(
        default=False,
        description="Pedidos são realizados via link direto para wa.me ou botão de chat",
    )
    has_pdf_menu: bool = Field(
        default=False,
        description="Cardápio ou tabela de preços em PDF/imagem (sinal de ausência de PDV integrado)",
    )
    pdf_menu_urls: list[str] = Field(default_factory=list, description="URLs de cardápios em PDF ou nuvem")
    has_online_cart: bool = Field(
        default=False,
        description="Possui carrinho de compras estruturado de e-commerce",
    )
    detected_pos_systems: list[str] = Field(
        default_factory=list,
        description="Softwares de POS/ERP identificados no código fonte ou rodapé",
    )
    pix_key_type: PixKeyType = Field(
        default=PixKeyType.NONE,
        description="Tipo de chave PIX detectada no conteúdo",
    )
    ordering_buttons: list[str] = Field(
        default_factory=list,
        description="Textos de botões de pedido ou chamada para ação comercial",
    )
    raw_signals: list[str] = Field(
        default_factory=list,
        description="Evidências brutas e tags detectadas durante o scraping",
    )
    raw_html: str | None = Field(default=None, description="HTML bruto da página (truncado para inspeção)")
    error: str | None = Field(default=None, description="Mensagem de erro caso a requisição falhe")

    def to_web_analysis_dict(self) -> dict[str, Any]:
        """Converte o resultado para a estrutura esperada pelo schema WebAnalysis."""
        return {
            "url": self.url,
            "has_website": self.has_website,
            "has_whatsapp_order": self.has_whatsapp_order,
            "has_pdf_menu": self.has_pdf_menu,
            "has_online_cart": self.has_online_cart,
            "detected_pos_systems": self.detected_pos_systems,
            "social_links": self.social_links,
            "cnpj_from_site": self.cnpj_from_site,
            "pix_key_type": (
                self.pix_key_type.value
                if isinstance(self.pix_key_type, PixKeyType)
                else str(self.pix_key_type)
            ),
            "raw_signals": self.raw_signals,
        }

    def to_web_analysis(self) -> Any:
        """Converte o resultado em uma instância do schema WebAnalysis."""
        try:
            from core.models import WebAnalysis
            return WebAnalysis(**self.to_web_analysis_dict())
        except ImportError:
            return self.to_web_analysis_dict()


# ==============================================================================
# Rotação de User-Agents Modernos de Navegadores Desktop
# ==============================================================================

MODERN_USER_AGENTS: list[str] = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4.1 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
    ),
]


# ==============================================================================
# Regex Específicas de Raspagem
# ==============================================================================

# Botões de ação de pedido / compra
REGEX_ORDER_BUTTON_TEXT = re.compile(
    r"(pe[çc]a\s+on-?line|pe[çc]a\s+pelo\s+whatsapp|fazer\s+pedido|pedir\s+agora|card[áa]pio|"
    r"fazer\s+reserva|comprar\s+agora|adicionar\s+ao\s+carrinho|ver\s+card[áa]pio|pedir\s+pelo\s+zap)",
    re.IGNORECASE,
)

# CNPJ em texto solto (com ou sem máscara)
REGEX_CNPJ_RAW = re.compile(
    r"(?:cnpj|mf|inscri[çc][ãa]o)[\s:.]*([0-9]{2}[\.\s]?[0-9]{3}[\.\s]?[0-9]{3}[\/\s]?[0-9]{4}[-\s]?[0-9]{2}|[0-9]{14})",
    re.IGNORECASE,
)


# ==============================================================================
# Classe do Raspador Web Assíncrono
# ==============================================================================

class WebScraper:
    """Raspador web assíncrono para análise de presença e sinais operacionais de estabelecimentos."""

    def __init__(
        self,
        timeout: float = 8.0,
        max_redirects: int = 5,
        verify_ssl: bool = True,
        pos_detector: POSDetector | None = None,
    ) -> None:
        """Inicializa o WebScraper com parâmetros de resiliência e detecção.

        Args:
            timeout: Tempo limite em segundos por requisição HTTP (padrão: 8s).
            max_redirects: Limite máximo de redirecionamentos seguidos.
            verify_ssl: Se True, verifica certificados SSL. Se falhar por SSL, faz retry sem verificação.
            pos_detector: Instância opcional de POSDetector reutilizável.
        """
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.verify_ssl = verify_ssl
        self.pos_detector = pos_detector or POSDetector()

    def _get_random_headers(self) -> dict[str, str]:
        """Gera cabeçalhos HTTP realistas simulando navegadores modernos em pt-BR."""
        return {
            "User-Agent": random.choice(MODERN_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    @staticmethod
    def normalize_url(url: str | None) -> str | None:
        """Adiciona protocolo https:// caso o usuário ou Maps forneça domínio sem esquema."""
        if not url:
            return None
        cleaned = url.strip()
        if not cleaned:
            return None
        if not cleaned.startswith(("http://", "https://")):
            cleaned = f"https://{cleaned}"
        return cleaned

    def extract_cnpj(self, soup: BeautifulSoup, full_text: str) -> str | None:
        """Procura e valida número de CNPJ no rodapé e corpo do HTML."""
        # 1. Busca prioritária em rodapés (<footer>, classes e IDs relacionados)
        footer_elements = soup.find_all(
            ["footer", "div", "section"],
            attrs={"class": re.compile(r"footer|rodape|bottom|info", re.I)},
        )
        for el in footer_elements:
            footer_text = el.get_text(separator=" ", strip=True)
            cnpj_candidates = REGEX_PIX_CNPJ.findall(footer_text)
            for cand in cnpj_candidates:
                clean = re.sub(r"\D", "", cand)
                if validate_cnpj(clean):
                    return clean

        # 2. Busca com máscara padrão no documento inteiro
        body_matches = REGEX_PIX_CNPJ.findall(full_text)
        for cand in body_matches:
            clean = re.sub(r"\D", "", cand)
            if validate_cnpj(clean):
                return clean

        # 3. Busca contextual com termos fiscais (CNPJ: 12345678000195)
        raw_matches = REGEX_CNPJ_RAW.findall(full_text)
        for cand in raw_matches:
            clean = re.sub(r"\D", "", cand)
            if len(clean) == 14 and validate_cnpj(clean):
                return clean

        return None

    def extract_social_links(self, soup: BeautifulSoup, base_url: str) -> dict[str, str | None]:
        """Extrai links para redes sociais (Instagram e Facebook)."""
        social_links: dict[str, str | None] = {"instagram": None, "facebook": None}

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            full_href = urljoin(base_url, href)
            lower_href = full_href.lower()

            if "instagram.com" in lower_href and not social_links["instagram"]:
                # Filtrar links genéricos de compartilhamento
                if "/p/" not in lower_href and "sharer" not in lower_href:
                    social_links["instagram"] = full_href

            elif "facebook.com" in lower_href and not social_links["facebook"]:
                if "sharer" not in lower_href and "/share" not in lower_href:
                    social_links["facebook"] = full_href

        return social_links

    def extract_whatsapp_links(self, soup: BeautifulSoup, full_html: str, base_url: str) -> list[str]:
        """Extrai todos os links de WhatsApp presentes em tags <a> e scripts inline."""
        wa_urls: set[str] = set()

        # 1. Tags <a> com href
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            full_href = urljoin(base_url, href)
            if "wa.me" in full_href.lower() or "api.whatsapp.com" in full_href.lower():
                wa_urls.add(full_href)

        # 2. Varredura via Regex no código HTML bruto (para capturar links em onclick/scripts)
        matches = REGEX_WA_URL.findall(full_html)
        for match in matches:
            wa_urls.add(match)

        return sorted(list(wa_urls))

    def extract_pdf_menus(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Identifica links para arquivos de cardápio em PDF, Google Drive, Canva, etc."""
        pdf_urls: set[str] = set()

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            full_href = urljoin(base_url, href)
            lower_href = full_href.lower()
            anchor_text = a_tag.get_text(strip=True).lower()

            # Extensão direta ou nuvem
            is_static_doc = any(
                ext in lower_href
                for ext in [
                    ".pdf",
                    "drive.google.com",
                    "dropbox.com",
                    "onedrive.live.com",
                    "canva.com/design",
                    "canva.site",
                    "issuu.com",
                    "heyzine.com",
                ]
            )

            # Relevância com contexto de cardápio/preços
            is_menu_context = any(
                term in anchor_text or term in lower_href
                for term in ["cardapio", "menu", "tabela", "precos", "valores", "catalogo"]
            )

            if is_static_doc or (is_menu_context and (".jpg" in lower_href or ".png" in lower_href)):
                pdf_urls.add(full_href)

        return sorted(list(pdf_urls))

    def extract_ordering_buttons(self, soup: BeautifulSoup) -> list[str]:
        """Identifica textos de botões de pedido ou chamada comercial de conversão."""
        buttons_found: list[str] = []

        # Botões e links com classe de botão
        action_elements = soup.find_all(["button", "a"])
        for el in action_elements:
            text = el.get_text(separator=" ", strip=True)
            if text and len(text) <= 50 and REGEX_ORDER_BUTTON_TEXT.search(text):
                buttons_found.append(text)
                if len(buttons_found) >= 10:
                    break

        return buttons_found

    async def scrape(self, target_url: str | None) -> ScrapingResult:
        """Executa a raspagem assíncrona da página inicial do estabelecimento.

        Args:
            target_url: URL do site oficial do estabelecimento.

        Returns:
            ScrapingResult com metadados, links, evidências e flags de automação.
        """
        normalized_url = self.normalize_url(target_url)
        if not normalized_url:
            return ScrapingResult(
                url=None,
                has_website=False,
                error="Nenhuma URL informada para scraping",
                raw_signals=["SEM_URL"],
            )

        headers = self._get_random_headers()
        response_text: str = ""
        status_code: int | None = None

        # Tentativa de requisição com httpx e fallback para SSL se necessário
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                max_redirects=self.max_redirects,
                verify=self.verify_ssl,
                headers=headers,
            ) as client:
                resp = await client.get(normalized_url)
                status_code = resp.status_code
                response_text = resp.text

        except (httpx.ConnectError, httpx.ConnectTimeout) as conn_err:
            return ScrapingResult(
                url=normalized_url,
                has_website=False,
                error=f"Falha de conexão / Timeout: {conn_err}",
                raw_signals=["FALHA_CONEXAO_TIMEOUT"],
            )
        except httpx.HTTPError as http_err:
            # Caso seja erro de verificação SSL (muito comum em pequenas empresas no Brasil),
            # tenta uma vez sem verificação estrita de certificado
            if "certificate" in str(http_err).lower() or "ssl" in str(http_err).lower():
                try:
                    async with httpx.AsyncClient(
                        timeout=self.timeout,
                        follow_redirects=True,
                        max_redirects=self.max_redirects,
                        verify=False,
                        headers=headers,
                    ) as client_insecure:
                        resp = await client_insecure.get(normalized_url)
                        status_code = resp.status_code
                        response_text = resp.text
                except Exception as retry_err:
                    return ScrapingResult(
                        url=normalized_url,
                        has_website=False,
                        error=f"Falha de certificado SSL e fallback: {retry_err}",
                        raw_signals=["ERRO_SSL"],
                    )
            else:
                return ScrapingResult(
                    url=normalized_url,
                    has_website=False,
                    error=f"Erro HTTP ao acessar website: {http_err}",
                    raw_signals=["ERRO_HTTP"],
                )
        except Exception as generic_err:
            return ScrapingResult(
                url=normalized_url,
                has_website=False,
                error=f"Erro inesperado no scraping: {generic_err}",
                raw_signals=["ERRO_DESCONHECIDO"],
            )

        if not response_text:
            return ScrapingResult(
                url=normalized_url,
                has_website=True,
                status_code=status_code,
                error="Resposta HTML vazia",
                raw_signals=["HTML_VAZIO"],
            )

        # Parsing com BeautifulSoup
        try:
            soup = BeautifulSoup(response_text, "html.parser")
        except Exception:
            soup = BeautifulSoup(response_text, "html5lib")

        # Título da página
        title = soup.title.string.strip() if soup.title and soup.title.string else None
        body_text = soup.get_text(separator=" ", strip=True)

        # 1. Extração de CNPJ
        cnpj = self.extract_cnpj(soup, body_text)

        # 2. Links Sociais
        social_links = self.extract_social_links(soup, normalized_url)

        # 3. Links e Pedidos via WhatsApp
        wa_links = self.extract_whatsapp_links(soup, response_text, normalized_url)
        has_wa_order = False
        for wa in wa_links:
            if not REGEX_WA_AUTOMATED.search(wa):
                has_wa_order = True
                break

        # 4. Cardápio em PDF ou Nuvem Estática
        pdf_menus = self.extract_pdf_menus(soup, normalized_url)
        has_pdf_menu = len(pdf_menus) > 0 or bool(REGEX_PDF_OR_STATIC_MENU.search(response_text))

        # 5. Carrinho e Checkouts
        has_online_cart = bool(REGEX_ONLINE_CART.search(body_text))

        # 6. Botões de Pedido
        ordering_buttons = self.extract_ordering_buttons(soup)

        # 7. Detecção de Sistemas de POS/ERP/Concorrentes
        detected_pos: list[str] = []
        for platform in self.pos_detector.detect_competitors(response_text, normalized_url):
            detected_pos.append(platform.name)

        # 8. Detecção de Chave Pix
        pix_type, _ = self.pos_detector.detect_pix_key(body_text)

        # Sinais brutos para rastreabilidade
        raw_signals: list[str] = []
        if cnpj:
            raw_signals.append(f"CNPJ_ENCONTRADO:{cnpj}")
        if social_links["instagram"]:
            raw_signals.append("INSTAGRAM_DETECTADO")
        if social_links["facebook"]:
            raw_signals.append("FACEBOOK_DETECTADO")
        if has_wa_order:
            raw_signals.append("WHATSAPP_CRU_DETECTADO")
        if has_pdf_menu:
            raw_signals.append("CARDAPIO_PDF_OU_NUVEM_DETECTADO")
        if has_online_cart:
            raw_signals.append("CARRINHO_ONLINE_DETECTADO")
        if detected_pos:
            raw_signals.append(f"CONCORRENTES_DETECTADOS:{','.join(set(detected_pos))}")
        if pix_type != PixKeyType.NONE:
            raw_signals.append(f"PIX_TIPO:{pix_type.value}")

        return ScrapingResult(
            url=normalized_url,
            has_website=True,
            status_code=status_code,
            title=title,
            cnpj_from_site=cnpj,
            social_links=social_links,
            whatsapp_urls=wa_links,
            has_whatsapp_order=has_wa_order,
            has_pdf_menu=has_pdf_menu,
            pdf_menu_urls=pdf_menus,
            has_online_cart=has_online_cart,
            detected_pos_systems=list(set(detected_pos)),
            pix_key_type=pix_type,
            ordering_buttons=ordering_buttons,
            raw_signals=raw_signals,
            raw_html=response_text[:5000],  # Primeiros 5k chars para depuração
            error=None,
        )
