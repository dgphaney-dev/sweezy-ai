"""Modelos de dados Pydantic v2 e enumerações do ProspectAI.

Este módulo implementa os schemas de validação de dados, tipos enumerados
e estruturas de transferência para o pipeline de descoberta, enriquecimento cadastral,
análise de presença digital e qualificação cognitiva com IA.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def _current_utc() -> datetime:
    """Retorna o timestamp atual em UTC (naive para SQLite)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==============================================================================
# Tipos Enumerados (Enums)
# ==============================================================================


class LeadStatus(str, Enum):
    """Ciclo de vida operacional do Lead no funil de vendas comercial."""

    NEW = "NEW"  # Recém-descoberto, ainda sem processamento completo
    ANALYZING = "ANALYZING"  # Em pipeline de enriquecimento ou qualificação
    QUALIFIED = "QUALIFIED"  # Qualificado pela IA com oportunidade detectada
    CONTACTED = "CONTACTED"  # Primeira abordagem disparada (WhatsApp/Telefone)
    NEGOTIATING = "NEGOTIATING"  # Retornou contato e está em negociação comercial
    CONVERTED = "CONVERTED"  # Fechou contrato ou adquiriu o software POS/ERP
    DISCARDED = "DISCARDED"  # Já possui ERP consolidado ou fora do perfil (ICP)


class LikelihoodLevel(str, Enum):
    """Probabilidade estimada de o estabelecimento NÃO possuir sistema POS/ERP moderno."""

    HIGH = "HIGH"  # Fortes indícios de gestão manual/sem PDV fiscal moderno (alta prioridade)
    MEDIUM = "MEDIUM"  # Sinais mistos ou parciais (necessita validação pelo vendedor)
    LOW = "LOW"  # Quase certeza de que já utiliza solução consolidada de mercado


class ContactChannel(str, Enum):
    """Canal recomendado ou utilizado para abordagem comercial."""

    WHATSAPP = "WHATSAPP"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    VISIT = "VISIT"

    # Aliases aceitos para conveniência de parsing em pt-BR
    TELEFONE = "PHONE"
    VISITA = "VISIT"


class BusinessType(str, Enum):
    """Segmentos comerciais do comércio varejista e serviços prioritários."""

    MERCADO = "MERCADO"
    RESTAURANTE = "RESTAURANTE"
    LOJA_ROUPA = "LOJA_ROUPA"
    PADARIA = "PADARIA"
    SALAO = "SALAO"
    PET_SHOP = "PET_SHOP"
    BAR = "BAR"
    CAFE = "CAFE"
    FARMACIA = "FARMACIA"
    OUTROS = "OUTROS"


class CompanyPorte(str, Enum):
    """Porte empresarial segundo classificação oficial da Receita Federal."""

    MEI = "MEI"
    ME = "ME"
    EPP = "EPP"
    DEMAIS = "DEMAIS"


class PixKeyType(str, Enum):
    """Tipo de chave PIX detectada em sites, rodapés ou cardápios digitais."""

    CPF = "CPF"
    CNPJ = "CNPJ"
    NONE = "none"
    TELEFONE = "TELEFONE"
    EMAIL = "EMAIL"
    ALEATORIA = "ALEATORIA"


class ScanSessionStatus(str, Enum):
    """Estado de execução de uma sessão de varredura geográfica."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


# ==============================================================================
# Schemas Base e Modelos Pydantic v2
# ==============================================================================


class BaseSchema(BaseModel):
    """Configuração base comum a todos os schemas Pydantic v2 do projeto."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=True,
    )


class CNAEItem(BaseSchema):
    """Representação de Atividade Econômica (CNAE Principal ou Secundário)."""

    code: int = Field(..., alias="codigo", description="Código numérico do CNAE (ex: 4712100)")
    description: str = Field(
        ...,
        alias="descricao",
        description="Descrição oficial da atividade econômica na Receita Federal",
    )

    @property
    def codigo(self) -> int:
        """Alias para o código do CNAE."""
        return self.code

    @property
    def descricao(self) -> str:
        """Alias para a descrição da atividade do CNAE."""
        return self.description


class Business(BaseSchema):
    """Dados cadastrais e geográficos obtidos via Google Places API (New)."""

    place_id: str = Field(..., description="Identificador único global do Google Places")
    name: str = Field(..., min_length=1, description="Nome comercial ou fantasia do estabelecimento")
    address: str = Field(..., description="Endereço textual formatado retornado pela API")
    phone: str | None = Field(
        default=None,
        description="Telefone formatado nacional ou internacional",
    )
    website: str | None = Field(
        default=None,
        description="URL do site oficial informado no Google Maps",
    )
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude geográfica")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude geográfica")
    rating: float | None = Field(
        default=None,
        ge=1.0,
        le=5.0,
        description="Nota média de avaliações (1 a 5)",
    )
    review_count: int | None = Field(
        default=None,
        ge=0,
        description="Quantidade total de avaliações no Google Maps",
    )
    business_status: str | None = Field(
        default="OPERATIONAL",
        description="Status do local (ex: OPERATIONAL, CLOSED_TEMPORARILY)",
    )
    primary_type: str | None = Field(
        default=None,
        description="Tipo primário de negócio categorizado pelo Google Places",
    )
    google_maps_url: str | None = Field(
        default=None,
        description="Link direto para visualização da ficha no Google Maps",
    )

    @field_validator("phone")
    @classmethod
    def sanitize_phone(cls, v: str | None) -> str | None:
        """Limpa caracteres especiais mantendo dígitos e sinal '+' opcional."""
        if not v:
            return None
        cleaned = re.sub(r"[^\d+]", "", v)
        return cleaned or None


class CNPJData(BaseSchema):
    """Informações cadastrais e fiscais oficiais da Receita Federal (via BrasilAPI / CNPJ.ws)."""

    cnpj: str = Field(..., description="Número de CNPJ contendo exatamente 14 dígitos numéricos")
    razao_social: str = Field(..., description="Razão social registrada na Receita Federal")
    nome_fantasia: str | None = Field(default=None, description="Nome fantasia registrado")
    porte: CompanyPorte | str = Field(
        default=CompanyPorte.ME,
        description="Porte empresarial (MEI, ME, EPP, DEMAIS)",
    )
    capital_social: float | None = Field(
        default=0.0,
        ge=0.0,
        description="Capital social integralizado em reais",
    )
    cnae_principal: CNAEItem = Field(
        ...,
        description="Atividade econômica principal (código e descrição)",
    )
    cnaes_secundarios: list[CNAEItem] = Field(
        default_factory=list,
        description="Lista de atividades econômicas secundárias",
    )
    data_abertura: date | str | None = Field(
        default=None,
        description="Data de abertura ou fundação da empresa",
    )
    situacao_cadastral: str = Field(
        default="ATIVA",
        description="Situação cadastral (ATIVA, BAIXADA, SUSPENSA, etc.)",
    )
    simples_nacional: bool | None = Field(
        default=None,
        description="Indicador de opção pelo Simples Nacional",
    )
    endereco: dict[str, Any] | str = Field(
        ...,
        description="Endereço fiscal completo registrado na Receita Federal",
    )
    telefone: str | None = Field(
        default=None,
        description="Telefone de contato fiscal registrado",
    )
    email: str | None = Field(
        default=None,
        description="E-mail fiscal de contato",
    )

    @field_validator("cnpj")
    @classmethod
    def clean_cnpj(cls, v: str) -> str:
        """Assegura exatamente 14 dígitos numéricos para o CNPJ."""
        digits = re.sub(r"\D", "", v)
        if len(digits) != 14:
            raise ValueError(
                f"CNPJ deve conter exatamente 14 dígitos numéricos, recebido: '{v}'"
            )
        return digits


class WebAnalysis(BaseSchema):
    """Sinais detectados por web scraping no site oficial e presença digital."""

    url: str | None = Field(default=None, description="URL analisada pelo scraper")
    has_website: bool = Field(
        default=False,
        description="Possui website próprio em funcionamento",
    )
    has_whatsapp_order: bool = Field(
        default=False,
        description="Pedidos são realizados via link direto para wa.me ou botão de chat",
    )
    has_pdf_menu: bool = Field(
        default=False,
        description="Cardápio ou tabela de preços em PDF/imagem (sinal de ausência de PDV integrado)",
    )
    has_online_cart: bool = Field(
        default=False,
        description="Possui carrinho de compras estruturado de e-commerce (ex: Shopify, Nuvemshop)",
    )
    detected_pos_systems: list[str] = Field(
        default_factory=list,
        description="Lista de softwares de POS/ERP identificados no código fonte ou rodapé",
    )
    social_links: dict[str, str | None] = Field(
        default_factory=lambda: {"instagram": None, "facebook": None},
        description="Links encontrados para perfis sociais (Instagram, Facebook)",
    )
    cnpj_from_site: str | None = Field(
        default=None,
        description="CNPJ extraído diretamente do rodapé ou página de termos do site",
    )
    pix_key_type: PixKeyType | str = Field(
        default=PixKeyType.NONE,
        description="Tipo de chave PIX detectada: CPF, CNPJ, none, TELEFONE, EMAIL, ALEATORIA",
    )
    raw_signals: list[str] = Field(
        default_factory=list,
        description="Lista de evidências brutas e tags detectadas durante o scraping",
    )


class LeadQualification(BaseSchema):
    """Decisão estruturada gerada pelo GPT-4o-mini com Instructor."""

    likelihood_no_pos: LikelihoodLevel = Field(
        ...,
        description="Probabilidade do comércio operar SEM um sistema POS/ERP moderno (HIGH/MEDIUM/LOW)",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Índice de confiança da IA na estimativa (0.0 a 1.0)",
    )
    detected_red_flags: list[str] = Field(
        default_factory=list,
        description="Lista de fatores desqualificadores identificados pela IA",
    )
    commercial_hook: str = Field(
        ...,
        min_length=10,
        description="Gancho de abordagem persuasivo e customizado para o vendedor",
    )
    recommended_channel: ContactChannel | str = Field(
        default=ContactChannel.WHATSAPP,
        description="Canal recomendado para primeira abordagem: WHATSAPP, PHONE, VISIT, EMAIL",
    )
    reasoning: str = Field(
        ...,
        description="Raciocínio lógico e detalhado que justifica a qualificação",
    )

    @field_validator("recommended_channel", mode="before")
    @classmethod
    def normalize_channel(cls, v: Any) -> ContactChannel:
        """Normaliza variações de canais em português para o enum correspondente."""
        if isinstance(v, ContactChannel):
            return v
        val = str(v).upper().strip()
        if val in ("TELEFONE", "PHONE"):
            return ContactChannel.PHONE
        if val in ("VISITA", "VISIT"):
            return ContactChannel.VISIT
        if val in ("EMAIL", "E-MAIL"):
            return ContactChannel.EMAIL
        return ContactChannel.WHATSAPP


class ContactHistory(BaseSchema):
    """Registro de interação comercial e mensagens enviadas ao lead."""

    id: UUID = Field(default_factory=uuid4, description="ID único do contato")
    lead_id: UUID = Field(..., description="ID do lead correspondente")
    channel: ContactChannel | str = Field(..., description="Canal empregado na comunicação")
    message_sent: str = Field(..., description="Conteúdo textual da mensagem disparada")
    response: str | None = Field(
        default=None,
        description="Resposta recebida do contato comercial",
    )
    created_at: datetime = Field(
        default_factory=_current_utc,
        description="Data e hora do envio",
    )


class ScanSession(BaseSchema):
    """Registro de sessão de varredura por quadrícula geográfica."""

    id: UUID = Field(default_factory=uuid4, description="ID único da sessão de busca")
    region_name: str = Field(
        ...,
        description="Nome descritivo da localidade (ex: 'Vila Madalena - SP')",
    )
    center_lat: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Latitude do centro da varredura",
    )
    center_lng: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Longitude do centro da varredura",
    )
    radius_km: float = Field(
        ...,
        gt=0.0,
        le=50.0,
        description="Raio de busca em quilômetros",
    )
    included_types: list[str] = Field(
        default_factory=lambda: [BusinessType.RESTAURANTE.value, BusinessType.PADARIA.value],
        description="Lista de tipos de estabelecimentos buscados",
    )
    total_found: int = Field(
        default=0,
        ge=0,
        description="Total de estabelecimentos descobertos no Google Places",
    )
    total_qualified: int = Field(
        default=0,
        ge=0,
        description="Total de leads com probabilidade HIGH ou MEDIUM",
    )
    started_at: datetime = Field(
        default_factory=_current_utc,
        description="Horário de início da sessão",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Horário de conclusão da sessão",
    )
    status: ScanSessionStatus = Field(
        default=ScanSessionStatus.RUNNING,
        description="Status operacional da sessão de varredura",
    )


class Lead(BaseSchema):
    """Entidade central agregadora de inteligência de vendas do ProspectAI."""

    id: UUID = Field(default_factory=uuid4, description="Identificador único universal do Lead")
    business: Business = Field(..., description="Dados descobertos no Google Places")
    cnpj_data: CNPJData | None = Field(
        default=None,
        description="Enriquecimento fiscal oficial da Receita Federal",
    )
    web_analysis: WebAnalysis | None = Field(
        default=None,
        description="Heurística de presença digital e sinais de POS/ERP",
    )
    qualification: LeadQualification | None = Field(
        default=None,
        description="Qualificação e gancho gerados por Inteligência Artificial",
    )
    status: LeadStatus = Field(
        default=LeadStatus.NEW,
        description="Status operacional do Lead no funil comercial",
    )
    notes: str | None = Field(
        default=None,
        description="Anotações internas do operador ou vendedor (SDR)",
    )
    created_at: datetime = Field(
        default_factory=_current_utc,
        description="Data de criação no sistema",
    )
    updated_at: datetime = Field(
        default_factory=_current_utc,
        description="Data da última atualização",
    )
    contacted_at: datetime | None = Field(
        default=None,
        description="Data do primeiro contato comercial efetuado",
    )

    @model_validator(mode="after")
    def sync_timestamps(self) -> Lead:
        """Garante consistência de atualização temporal."""
        if self.updated_at and self.created_at:
            t_updated = self.updated_at.replace(tzinfo=None) if self.updated_at.tzinfo else self.updated_at
            t_created = self.created_at.replace(tzinfo=None) if self.created_at.tzinfo else self.created_at
            if t_updated < t_created:
                self.updated_at = self.created_at
        return self


class CNPJCache(BaseSchema):
    """Registro de cache de consulta CNPJ com expiração temporal (TTL de 60 dias)."""

    cnpj: str = Field(..., description="CNPJ com 14 dígitos numéricos")
    data: CNPJData = Field(..., description="Dados completos da empresa retornados pela API fiscal")
    cached_at: datetime = Field(
        default_factory=_current_utc,
        description="Data e hora de gravação no cache",
    )
    expires_at: datetime = Field(
        ...,
        description="Data de expiração do registro em cache",
    )
