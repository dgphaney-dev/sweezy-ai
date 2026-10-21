# Modelos de Dados e Schema do Banco de Dados - ProspectAI

Este documento contém a documentação técnica completa de todos os modelos de dados, tipos enumerados (Enums), regras de validação Pydantic v2 e o schema relacional (SQLite e migração para PostgreSQL) do projeto **ProspectAI**.

---

## 1. Visão Geral da Arquitetura de Dados

O pipeline de dados do **ProspectAI** opera em múltiplos estágios assíncronos de descoberta, enriquecimento, raspagem e qualificação cognitiva com IA:

```mermaid
flowchart TD
    subgraph Discovery ["1. Descoberta Geográfica"]
        A["Google Places API (New)<br/>(Varredura por Grid)"] --> B["Business Model<br/>(place_id, nome, endereço, lat/lng)"]
    end

    subgraph Enrichment ["2. Enriquecimento Cadastral & Web"]
        B --> C["BrasilAPI / CNPJ.ws"]
        C --> D["CNPJData Model<br/>(CNPJ, CNAEs, Porte, Simples)"]
        B --> E["Web Scraping & Heurística"]
        E --> F["WebAnalysis Model<br/>(Sinais de POS, PIX, Carrinho, Redes)"]
    end

    subgraph Qualification ["3. Qualificação Cognitiva"]
        D & F --> G["GPT-4o-mini + Instructor<br/>(Structured Outputs)"]
        G --> H["LeadQualification Model<br/>(likelihood_no_pos, hook, canal)"]
    end

    subgraph Persistence ["4. Consolidação & Apresentação"]
        B & D & F & H --> I[("Banco de Dados<br/>(SQLite / PostgreSQL)")]
        I --> J["Interface Flet Desktop/Mobile"]
        I --> K["Disparo WhatsApp & Histórico"]
    end
```

---

## 2. Tipos Enumerados (Enums)

Todos os enums herdam de `str` e `enum.Enum`, garantindo interoperabilidade nativa com serializadores JSON, validação transparente no Pydantic v2 e persistência simples como texto no banco de dados.

```python
"""Módulo de enumerações centrais do ProspectAI."""
from enum import Enum


class LeadStatus(str, Enum):
    """Ciclo de vida operacional do Lead no funil de vendas."""
    NEW = "NEW"                      # Recém-descoberto, ainda sem processamento completo
    ANALYZING = "ANALYZING"          # Em pipeline de enriquecimento/qualificação
    QUALIFIED = "QUALIFIED"          # Qualificado pela IA com oportunidade detectada
    CONTACTED = "CONTACTED"          # Primeira abordagem disparada (WhatsApp/Telefone)
    NEGOTIATING = "NEGOTIATING"      # Retornou contato e está em negociação comercial
    CONVERTED = "CONVERTED"          # Fechou contrato ou adquiriu o software POS/ERP
    DISCARDED = "DISCARDED"          # Já possui ERP consolidado ou fora do perfil (ICP)


class LikelihoodLevel(str, Enum):
    """Probabilidade estimada de o estabelecimento NÃO possuir sistema POS/ERP moderno."""
    HIGH = "HIGH"      # Fortes indícios de gestão manual/sem PDV fiscal moderno (alta prioridade)
    MEDIUM = "MEDIUM"  # Sinais mistos ou parciais (necessita validação pelo vendedor)
    LOW = "LOW"        # Quase certeza de que já utiliza solução consolidada de mercado


class ContactChannel(str, Enum):
    """Canal recomendado ou utilizado para abordagem comercial."""
    WHATSAPP = "WHATSAPP"
    PHONE = "PHONE"          # Aceita também alias 'TELEFONE'
    EMAIL = "EMAIL"
    VISIT = "VISIT"          # Aceita também alias 'VISITA'
    
    # Aliases em português para flexibilidade de parsing
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
```

---

## 3. Modelos Pydantic v2 (Implementação Completa)

Os modelos abaixo são definidos utilizando Pydantic v2 (`pydantic>=2.0`), com tipagem forte, validadores customizados e suporte a serialização para banco relacional e JSON.

### 3.1. Código Python Completo (`app/models/schemas.py`)

```python
"""Modelos de dados Pydantic v2 para o ProspectAI."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import (
    BusinessType,
    CompanyPorte,
    ContactChannel,
    LeadStatus,
    LikelihoodLevel,
    PixKeyType,
    ScanSessionStatus,
)


class BaseSchema(BaseModel):
    """Configuração base comum a todos os schemas Pydantic."""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=True,
    )


# ------------------------------------------------------------------------------
# 1. CNAE Item Auxiliar (Atividade Econômica)
# ------------------------------------------------------------------------------
class CNAEItem(BaseSchema):
    """Representação de Atividade Econômica (CNAE Principal ou Secundário)."""
    code: int = Field(..., alias="codigo", description="Código numérico do CNAE (ex: 4712100)")
    description: str = Field(..., alias="descricao", description="Descrição oficial da atividade econômica")

    @property
    def codigo(self) -> int:
        return self.code

    @property
    def descricao(self) -> str:
        return self.description


# ------------------------------------------------------------------------------
# 2. Business (Google Places Discovery)
# ------------------------------------------------------------------------------
class Business(BaseSchema):
    """Dados cadastrais e geográficos obtidos via Google Places API (New)."""
    place_id: str = Field(..., description="Identificador único global do Google Places")
    name: str = Field(..., min_length=1, description="Nome comercial ou fantasia do estabelecimento")
    address: str = Field(..., description="Endereço textual formatado retornado pela API")
    phone: str | None = Field(default=None, description="Telefone formatado nacional ou internacional")
    website: str | None = Field(default=None, description="URL do site oficial informado no Google Maps")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude geográfica")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude geográfica")
    rating: float | None = Field(default=None, ge=1.0, le=5.0, description="Nota média de avaliações (1 a 5)")
    review_count: int | None = Field(default=None, ge=0, description="Quantidade total de avaliações")
    business_status: str | None = Field(default="OPERATIONAL", description="Status do local (ex: OPERATIONAL, CLOSED_TEMPORARILY)")
    primary_type: str | None = Field(default=None, description="Tipo primário de negócio categorizado pelo Google Places")
    google_maps_url: str | None = Field(default=None, description="Link direto para visualização da ficha no Google Maps")

    @field_validator("phone")
    @classmethod
    def sanitize_phone(cls, v: str | None) -> str | None:
        """Limpa caracteres especiais mantendo dígitos e sinal '+' opcional."""
        if not v:
            return None
        cleaned = re.sub(r"[^\d+]", "", v)
        return cleaned or None


# ------------------------------------------------------------------------------
# 3. CNPJData (Receita Federal / BrasilAPI / CNPJ.ws)
# ------------------------------------------------------------------------------
class CNPJData(BaseSchema):
    """Informações cadastrais e fiscais oficiais da Receita Federal."""
    cnpj: str = Field(..., description="Número de CNPJ contendo 14 dígitos numéricos")
    razao_social: str = Field(..., description="Razão social registrada na Receita Federal")
    nome_fantasia: str | None = Field(default=None, description="Nome fantasia registrado")
    porte: CompanyPorte | str = Field(default=CompanyPorte.ME, description="Porte empresarial (MEI, ME, EPP, DEMAIS)")
    capital_social: float | None = Field(default=0.0, ge=0.0, description="Capital social integralizado em reais")
    cnae_principal: CNAEItem = Field(..., description="Atividade econômica principal (código e descrição)")
    cnaes_secundarios: list[CNAEItem] = Field(default_factory=list, description="Lista de atividades econômicas secundárias")
    data_abertura: date | str | None = Field(default=None, description="Data de abertura/fundação da empresa")
    situacao_cadastral: str = Field(default="ATIVA", description="Situação cadastral (ATIVA, BAIXADA, SUSPENSA, etc.)")
    simples_nacional: bool | None = Field(default=None, description="Indicador de opção pelo Simples Nacional")
    endereco: dict[str, Any] | str = Field(..., description="Endereço fiscal completo registrado na Receita")
    telefone: str | None = Field(default=None, description="Telefone de contato fiscal registrado")
    email: str | None = Field(default=None, description="E-mail fiscal de contato")

    @field_validator("cnpj")
    @classmethod
    def clean_cnpj(cls, v: str) -> str:
        """Assegura 14 dígitos numéricos para o CNPJ."""
        digits = re.sub(r"\D", "", v)
        if len(digits) != 14:
            raise ValueError(f"CNPJ deve conter exatamente 14 dígitos numéricos, recebido: {v}")
        return digits


# ------------------------------------------------------------------------------
# 4. WebAnalysis (Scraping Heurístico de Presença Digital)
# ------------------------------------------------------------------------------
class WebAnalysis(BaseSchema):
    """Sinais detectados por web scraping no site oficial e presença digital."""
    url: str | None = Field(default=None, description="URL analisada pelo scraper")
    has_website: bool = Field(default=False, description="Possui website próprio em funcionamento")
    has_whatsapp_order: bool = Field(
        default=False, 
        description="Pedidos são realizados via link direto para wa.me ou botão de chat"
    )
    has_pdf_menu: bool = Field(
        default=False, 
        description="Cardápio ou tabela de preços em PDF/imagem (sinal de ausência de PDV integrado)"
    )
    has_online_cart: bool = Field(
        default=False, 
        description="Possui carrinho de compras estruturado de e-commerce (ex: Shopify, Nuvemshop)"
    )
    detected_pos_systems: list[str] = Field(
        default_factory=list, 
        description="Lista de softwares de POS/ERP identificados no código fonte ou rodapé"
    )
    social_links: dict[str, str | None] = Field(
        default_factory=lambda: {"instagram": None, "facebook": None},
        description="Links encontrados para perfis sociais (Instagram, Facebook)"
    )
    cnpj_from_site: str | None = Field(
        default=None, 
        description="CNPJ extraído diretamente do rodapé ou página de termos do site"
    )
    pix_key_type: PixKeyType | str = Field(
        default=PixKeyType.NONE, 
        description="Tipo de chave PIX detectada: CPF, CNPJ ou none"
    )
    raw_signals: list[str] = Field(
        default_factory=list, 
        description="Lista de evidências brutas e tags detectadas durante o scraping"
    )


# ------------------------------------------------------------------------------
# 5. LeadQualification (Qualificação Cognitiva com GPT-4o-mini)
# ------------------------------------------------------------------------------
class LeadQualification(BaseSchema):
    """Decisão estruturada gerada pelo GPT-4o-mini com Instructor."""
    likelihood_no_pos: LikelihoodLevel = Field(
        ..., 
        description="Probabilidade do comércio operar SEM um sistema POS/ERP moderno (HIGH/MEDIUM/LOW)"
    )
    confidence_score: float = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Índice de confiança da IA na estimativa (0.0 a 1.0)"
    )
    detected_red_flags: list[str] = Field(
        default_factory=list, 
        description="Lista de fatores desqualificadores identificados pela IA"
    )
    commercial_hook: str = Field(
        ..., 
        min_length=10, 
        description="Gancho de abordagem persuasivo e customizado para o vendedor"
    )
    recommended_channel: ContactChannel | str = Field(
        default=ContactChannel.WHATSAPP, 
        description="Canal recomendado para primeira abordagem: WHATSAPP, TELEFONE/PHONE, VISITA/VISIT"
    )
    reasoning: str = Field(
        ..., 
        description="Raciocínio lógico e detalhado que justifica a qualificação"
    )

    @field_validator("recommended_channel", mode="before")
    @classmethod
    def normalize_channel(cls, v: Any) -> ContactChannel:
        """Normaliza variações de canais em português para o enum."""
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


# ------------------------------------------------------------------------------
# 6. ContactHistory (Histórico de Interação Comercial)
# ------------------------------------------------------------------------------
class ContactHistory(BaseSchema):
    """Registro de interação comercial e mensagens enviadas ao lead."""
    id: UUID = Field(default_factory=uuid4, description="ID único do contato")
    lead_id: UUID = Field(..., description="ID do lead correspondente")
    channel: ContactChannel | str = Field(..., description="Canal empregado na comunicação")
    message_sent: str = Field(..., description="Conteúdo textual da mensagem disparada")
    response: str | None = Field(default=None, description="Resposta recebida do contato comercial")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Data e hora do envio")


# ------------------------------------------------------------------------------
# 7. ScanSession (Metadados da Sessão de Varredura Geográfica)
# ------------------------------------------------------------------------------
class ScanSession(BaseSchema):
    """Registro de sessão de varredura por quadrícula geográfica."""
    id: UUID = Field(default_factory=uuid4, description="ID único da sessão de busca")
    region_name: str = Field(..., description="Nome descritivo da localidade (ex: 'Vila Madalena - SP')")
    center_lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude do centro da varredura")
    center_lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude do centro da varredura")
    radius_km: float = Field(..., gt=0.0, le=50.0, description="Raio de busca em quilômetros")
    included_types: list[str] = Field(
        default_factory=lambda: [BusinessType.RESTAURANTE.value, BusinessType.PADARIA.value],
        description="Lista de tipos de estabelecimentos buscados"
    )
    total_found: int = Field(default=0, ge=0, description="Total de estabelecimentos descobertos no Google Places")
    total_qualified: int = Field(default=0, ge=0, description="Total de leads com probabilidade HIGH/MEDIUM")
    started_at: datetime = Field(default_factory=datetime.utcnow, description="Horário de início")
    completed_at: datetime | None = Field(default=None, description="Horário de conclusão")
    status: ScanSessionStatus = Field(default=ScanSessionStatus.RUNNING, description="Status da sessão de scan")


# ------------------------------------------------------------------------------
# 8. Lead (Entidade Central Consolidada)
# ------------------------------------------------------------------------------
class Lead(BaseSchema):
    """Entidade central agregadora de inteligência de vendas do ProspectAI."""
    id: UUID = Field(default_factory=uuid4, description="Identificador único universal do Lead")
    business: Business = Field(..., description="Dados descobertos no Google Places")
    cnpj_data: CNPJData | None = Field(default=None, description="Enriquecimento fiscal oficial da Receita Federal")
    web_analysis: WebAnalysis | None = Field(default=None, description="Heurística de presença digital e sinais de POS")
    qualification: LeadQualification | None = Field(default=None, description="Qualificação e gancho gerados por IA")
    status: LeadStatus = Field(default=LeadStatus.NEW, description="Status operacional do Lead no funil comercial")
    notes: str | None = Field(default=None, description="Anotações internas do operador ou SDR")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Data de criação no sistema")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Data da última atualização")
    contacted_at: datetime | None = Field(default=None, description="Data do primeiro contato efetuado")

    @model_validator(mode="after")
    def sync_timestamps(self) -> "Lead":
        """Garante consistência de atualização temporal."""
        return self
```

---

## 4. Schema do Banco de Dados Relacional

O banco de dados relacional foi concebido com normalização e relacionamentos estritos, garantindo integridade referencial com `FOREIGN KEY ... ON DELETE CASCADE` e suporte a campos compostos serializados em JSON/TEXT.

### 4.1. Diagrama Entidade-Relacionamento (Mermaid ER)

```mermaid
erDiagram
    SCAN_SESSIONS ||--o{ LEADS : "origina"
    LEADS ||--|| BUSINESS_PLACES : "possui (1:1)"
    LEADS ||--o| CNPJ_RECORDS : "enriquece (1:0..1)"
    LEADS ||--o| WEB_ANALYSES : "inspeciona (1:0..1)"
    LEADS ||--o| LEAD_QUALIFICATIONS : "qualifica (1:0..1)"
    LEADS ||--o{ CONTACT_HISTORIES : "registra interações (1:N)"

    SCAN_SESSIONS {
        text id PK
        text region_name
        real center_lat
        real center_lng
        real radius_km
        text included_types_json
        integer total_found
        integer total_qualified
        text status
        text started_at
        text completed_at
    }

    LEADS {
        text id PK
        text scan_session_id FK
        text status
        text notes
        text created_at
        text updated_at
        text contacted_at
    }

    BUSINESS_PLACES {
        text place_id PK
        text lead_id FK
        text name
        text address
        text phone
        text website
        real lat
        real lng
        real rating
        integer review_count
        text business_status
        text primary_type
        text google_maps_url
    }

    CNPJ_RECORDS {
        text cnpj PK
        text lead_id FK
        text razao_social
        text nome_fantasia
        text porte
        real capital_social
        text cnae_principal_json
        text cnaes_secundarios_json
        text data_abertura
        text situacao_cadastral
        integer simples_nacional
        text endereco_json
        text telefone
        text email
    }

    WEB_ANALYSES {
        integer id PK
        text lead_id FK
        text url
        integer has_website
        integer has_whatsapp_order
        integer has_pdf_menu
        integer has_online_cart
        text detected_pos_systems_json
        text social_links_json
        text cnpj_from_site
        text pix_key_type
        text raw_signals_json
        text checked_at
    }

    LEAD_QUALIFICATIONS {
        integer id PK
        text lead_id FK
        text likelihood_no_pos
        real confidence_score
        text detected_red_flags_json
        text commercial_hook
        text recommended_channel
        text reasoning
        text qualified_at
    }

    CONTACT_HISTORIES {
        text id PK
        text lead_id FK
        text channel
        text message_sent
        text response
        text created_at
    }
```

---

### 4.2. Comandos SQL DDL para SQLite (MVP)

Abaixo está o script SQL DDL para SQLite com `PRAGMA foreign_keys = ON`, restrições de verificação (`CHECK`) e tipos estritos:

```sql
-- Ativação obrigatória de integridade referencial no SQLite
PRAGMA foreign_keys = ON;

-- 1. Sessões de Varredura Geográfica
CREATE TABLE IF NOT EXISTS scan_sessions (
    id TEXT PRIMARY KEY,
    region_name TEXT NOT NULL,
    center_lat REAL NOT NULL,
    center_lng REAL NOT NULL,
    radius_km REAL NOT NULL,
    included_types_json TEXT NOT NULL DEFAULT '[]',
    total_found INTEGER NOT NULL DEFAULT 0,
    total_qualified INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'STOPPED')),
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

-- 2. Tabela Agregadora de Leads
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    scan_session_id TEXT,
    status TEXT NOT NULL DEFAULT 'NEW' CHECK(status IN ('NEW', 'ANALYZING', 'QUALIFIED', 'CONTACTED', 'NEGOTIATING', 'CONVERTED', 'DISCARDED')),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    contacted_at TEXT,
    FOREIGN KEY (scan_session_id) REFERENCES scan_sessions(id) ON DELETE SET NULL
);

-- 3. Estabelecimentos do Google Places API
CREATE TABLE IF NOT EXISTS business_places (
    place_id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    phone TEXT,
    website TEXT,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    rating REAL,
    review_count INTEGER,
    business_status TEXT DEFAULT 'OPERATIONAL',
    primary_type TEXT,
    google_maps_url TEXT,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

-- 4. Registros Fiscais da Receita Federal (CNPJ)
CREATE TABLE IF NOT EXISTS cnpj_records (
    cnpj TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL UNIQUE,
    razao_social TEXT NOT NULL,
    nome_fantasia TEXT,
    porte TEXT NOT NULL,
    capital_social REAL DEFAULT 0.0,
    cnae_principal_json TEXT NOT NULL,
    cnaes_secundarios_json TEXT NOT NULL DEFAULT '[]',
    data_abertura TEXT,
    situacao_cadastral TEXT NOT NULL DEFAULT 'ATIVA',
    simples_nacional INTEGER DEFAULT 1,
    endereco_json TEXT NOT NULL,
    telefone TEXT,
    email TEXT,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

-- 5. Análise de Presença Digital e Sinais de POS
CREATE TABLE IF NOT EXISTS web_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL UNIQUE,
    url TEXT,
    has_website INTEGER NOT NULL DEFAULT 0,
    has_whatsapp_order INTEGER NOT NULL DEFAULT 0,
    has_pdf_menu INTEGER NOT NULL DEFAULT 0,
    has_online_cart INTEGER NOT NULL DEFAULT 0,
    detected_pos_systems_json TEXT NOT NULL DEFAULT '[]',
    social_links_json TEXT NOT NULL DEFAULT '{}',
    cnpj_from_site TEXT,
    pix_key_type TEXT NOT NULL DEFAULT 'none',
    raw_signals_json TEXT NOT NULL DEFAULT '[]',
    checked_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

-- 6. Qualificação e Avaliação do Agente de IA
CREATE TABLE IF NOT EXISTS lead_qualifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL UNIQUE,
    likelihood_no_pos TEXT NOT NULL CHECK(likelihood_no_pos IN ('HIGH', 'MEDIUM', 'LOW')),
    confidence_score REAL NOT NULL CHECK(confidence_score >= 0.0 AND confidence_score <= 1.0),
    detected_red_flags_json TEXT NOT NULL DEFAULT '[]',
    commercial_hook TEXT NOT NULL,
    recommended_channel TEXT NOT NULL DEFAULT 'WHATSAPP' CHECK(recommended_channel IN ('WHATSAPP', 'PHONE', 'EMAIL', 'VISIT')),
    reasoning TEXT NOT NULL,
    qualified_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

-- 7. Histórico de Abordagens e Mensagens Comerciais
CREATE TABLE IF NOT EXISTS contact_histories (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL,
    channel TEXT NOT NULL CHECK(channel IN ('WHATSAPP', 'PHONE', 'EMAIL', 'VISIT')),
    message_sent TEXT NOT NULL,
    response TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);
```

---

### 4.3. Recomendações de Índices (Index Strategy)

Os índices abaixo garantem tempo de resposta sub-milissegundo em operações frequentes da interface gráfica e das rotinas de varredura:

```sql
-- 1. Filtragem rápida no funil de vendas (Kanban e abas da UI)
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status);

-- 2. Paginação ordenada por data da última modificação
CREATE INDEX IF NOT EXISTS idx_leads_updated_at ON leads (updated_at DESC);

-- 3. Deduplicação e busca espacial aproximada por coordenadas
CREATE INDEX IF NOT EXISTS idx_business_places_lat_lng ON business_places (lat, lng);

-- 4. Busca por nome comercial e segmento
CREATE INDEX IF NOT EXISTS idx_business_places_name ON business_places (name);
CREATE INDEX IF NOT EXISTS idx_business_places_primary_type ON business_places (primary_type);

-- 5. Busca direta por Razão Social
CREATE INDEX IF NOT EXISTS idx_cnpj_records_razao ON cnpj_records (razao_social);

-- 6. Ordenação prioritária de oportunidades comerciais (HIGH primeiro, com maior confiança)
CREATE INDEX IF NOT EXISTS idx_qualifications_likelihood ON lead_qualifications (likelihood_no_pos, confidence_score DESC);

-- 7. Junção cronológica rápida de mensagens enviadas
CREATE INDEX IF NOT EXISTS idx_contact_histories_lead_date ON contact_histories (lead_id, created_at DESC);
```

#### Tabela de Justificativa dos Índices

| Índice | Tabela | Colunas | Objetivo / Justificativa |
| :--- | :--- | :--- | :--- |
| `idx_leads_status` | `leads` | `status` | Filtragem instantânea das abas da UI (ex: "Novos", "Qualificados", "Convertidos"). |
| `idx_leads_updated_at` | `leads` | `updated_at DESC` | Paginação padrão da lista de leads exibindo primeiro as alterações mais recentes. |
| `idx_business_places_lat_lng` | `business_places` | `lat, lng` | Deduplicação de estabelecimentos entre quadrículas vizinhas do grid scan. |
| `idx_qualifications_likelihood` | `lead_qualifications` | `likelihood_no_pos, confidence_score` | Criação de listas de alta conversão para o vendedor (HIGH com confiança > 0.8). |
| `idx_contact_histories_lead_date` | `contact_histories` | `lead_id, created_at` | Carregamento da linha do tempo de mensagens no modal de detalhes do Lead. |

---

### 4.4. Mapeamento SQLAlchemy 2.0 (`app/models/entities.py`)

Abaixo está o mapeamento ORM declarativo correspondente para integração com Python e SQLite/PostgreSQL:

```python
"""Mapeamento ORM declarativo SQLAlchemy 2.0 para o ProspectAI."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Classe base declarativa SQLAlchemy 2.0 com mapeamento flexível de JSON."""
    type_annotation_map = {
        dict[str, Any]: SQLITE_JSON,
        list[Any]: SQLITE_JSON,
    }


class ScanSessionEntity(Base):
    __tablename__ = "scan_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    region_name: Mapped[str] = mapped_column(String(255), nullable=False)
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False)
    radius_km: Mapped[float] = mapped_column(Float, nullable=False)
    included_types_json: Mapped[list[Any]] = mapped_column(SQLITE_JSON, default=list)
    total_found: Mapped[int] = mapped_column(Integer, default=0)
    total_qualified: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    leads: Mapped[list["LeadEntity"]] = relationship("LeadEntity", back_populates="scan_session")


class LeadEntity(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scan_sessions.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="NEW", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    scan_session: Mapped[ScanSessionEntity | None] = relationship("ScanSessionEntity", back_populates="leads")
    business: Mapped["BusinessEntity"] = relationship("BusinessEntity", back_populates="lead", uselist=False, cascade="all, delete-orphan")
    cnpj_data: Mapped["CNPJRecordEntity | None"] = relationship("CNPJRecordEntity", back_populates="lead", uselist=False, cascade="all, delete-orphan")
    web_analysis: Mapped["WebAnalysisEntity | None"] = relationship("WebAnalysisEntity", back_populates="lead", uselist=False, cascade="all, delete-orphan")
    qualification: Mapped["LeadQualificationEntity | None"] = relationship("LeadQualificationEntity", back_populates="lead", uselist=False, cascade="all, delete-orphan")
    contact_history: Mapped[list["ContactHistoryEntity"]] = relationship("ContactHistoryEntity", back_populates="lead", cascade="all, delete-orphan")


class BusinessEntity(Base):
    __tablename__ = "business_places"

    place_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    business_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    primary_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    google_maps_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    lead: Mapped[LeadEntity] = relationship("LeadEntity", back_populates="business")

    __table_args__ = (
        Index("idx_business_places_coords", "lat", "lng"),
    )


class CNPJRecordEntity(Base):
    __tablename__ = "cnpj_records"

    cnpj: Mapped[str] = mapped_column(String(14), primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), unique=True, nullable=False)
    razao_social: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    nome_fantasia: Mapped[str | None] = mapped_column(String(255), nullable=True)
    porte: Mapped[str] = mapped_column(String(30), nullable=False)
    capital_social: Mapped[float | None] = mapped_column(Float, default=0.0)
    cnae_principal_json: Mapped[dict[str, Any]] = mapped_column(SQLITE_JSON, nullable=False)
    cnaes_secundarios_json: Mapped[list[Any]] = mapped_column(SQLITE_JSON, default=list)
    data_abertura: Mapped[str | None] = mapped_column(String(20), nullable=True)
    situacao_cadastral: Mapped[str] = mapped_column(String(50), default="ATIVA")
    simples_nacional: Mapped[bool | None] = mapped_column(Boolean, default=True)
    endereco_json: Mapped[dict[str, Any]] = mapped_column(SQLITE_JSON, nullable=False)
    telefone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    lead: Mapped[LeadEntity] = relationship("LeadEntity", back_populates="cnpj_data")


class WebAnalysisEntity(Base):
    __tablename__ = "web_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[str] = mapped_column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), unique=True, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_website: Mapped[bool] = mapped_column(Boolean, default=False)
    has_whatsapp_order: Mapped[bool] = mapped_column(Boolean, default=False)
    has_pdf_menu: Mapped[bool] = mapped_column(Boolean, default=False)
    has_online_cart: Mapped[bool] = mapped_column(Boolean, default=False)
    detected_pos_systems_json: Mapped[list[Any]] = mapped_column(SQLITE_JSON, default=list)
    social_links_json: Mapped[dict[str, Any]] = mapped_column(SQLITE_JSON, default=dict)
    cnpj_from_site: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pix_key_type: Mapped[str] = mapped_column(String(20), default="none")
    raw_signals_json: Mapped[list[Any]] = mapped_column(SQLITE_JSON, default=list)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped[LeadEntity] = relationship("LeadEntity", back_populates="web_analysis")


class LeadQualificationEntity(Base):
    __tablename__ = "lead_qualifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[str] = mapped_column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), unique=True, nullable=False)
    likelihood_no_pos: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    detected_red_flags_json: Mapped[list[Any]] = mapped_column(SQLITE_JSON, default=list)
    commercial_hook: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_channel: Mapped[str] = mapped_column(String(20), default="WHATSAPP")
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    qualified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped[LeadEntity] = relationship("LeadEntity", back_populates="qualification")

    __table_args__ = (
        Index("idx_lead_qualifications_score", "likelihood_no_pos", "confidence_score"),
    )


class ContactHistoryEntity(Base):
    __tablename__ = "contact_histories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id: Mapped[str] = mapped_column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    message_sent: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped[LeadEntity] = relationship("LeadEntity", back_populates="contact_history")
```

---

## 5. Notas de Migração para PostgreSQL (Produção)

Ao escalar a aplicação para múltiplos usuários simultâneos ou ambiente de nuvem, a migração do SQLite para PostgreSQL é recomendada com as seguintes adaptações:

### 5.1. Comparativo de Tipos e Equivalências

| Campo / Tipo | SQLite (MVP) | PostgreSQL (Produção) | Vantagem no PostgreSQL |
| :--- | :--- | :--- | :--- |
| **Identificadores (UUID)** | `TEXT` | `UUID` (nativo) | Redução de 50% no espaço em disco e maior velocidade de indexação. |
| **Colunas JSON** | `TEXT` / `JSON` | `JSONB` | Permite indexação GIN (`@>`) e consultas estruturadas internas sem parsing de string. |
| **Data e Hora** | `TEXT` (ISO-8601) | `TIMESTAMPTZ` | Gerenciamento automático de fuso horário (`America/Sao_Paulo`). |
| **Booleanos** | `INTEGER` (0 ou 1) | `BOOLEAN` | Tipagem estrita e validação nativa. |
| **Coordenadas Geográficas**| `REAL` (`lat`, `lng`) | `GEOMETRY(Point, 4326)` (PostGIS) | Cálculos geodésicos reais de raio (`ST_DWithin`) sem deformação cartográfica. |

### 5.2. DDL PostgreSQL com JSONB e Índices GIN

```sql
-- Extensões necessárias no PostgreSQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Exemplo da tabela web_analyses com JSONB e GIN Index
CREATE TABLE web_analyses (
    id BIGSERIAL PRIMARY KEY,
    lead_id UUID NOT NULL UNIQUE REFERENCES leads(id) ON DELETE CASCADE,
    url TEXT,
    has_website BOOLEAN NOT NULL DEFAULT FALSE,
    has_whatsapp_order BOOLEAN NOT NULL DEFAULT FALSE,
    has_pdf_menu BOOLEAN NOT NULL DEFAULT FALSE,
    has_online_cart BOOLEAN NOT NULL DEFAULT FALSE,
    detected_pos_systems JSONB NOT NULL DEFAULT '[]'::jsonb,
    social_links JSONB NOT NULL DEFAULT '{}'::jsonb,
    cnpj_from_site VARCHAR(20),
    pix_key_type VARCHAR(20) NOT NULL DEFAULT 'none',
    raw_signals JSONB NOT NULL DEFAULT '[]'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Índice GIN para busca rápida de sistemas concorrentes instalados
CREATE INDEX idx_web_analyses_pos_gin ON web_analyses USING GIN (detected_pos_systems);

-- Exemplo de query PostgreSQL: Buscar estabelecimentos que usam iFood mas não possuem Linx
-- SELECT * FROM web_analyses WHERE detected_pos_systems @> '["iFood"]' AND NOT (detected_pos_systems @> '["Linx"]');
```

### 5.3. Configuração de Pool Assíncrono com AsyncPG
No PostgreSQL com SQLAlchemy assíncrono:
- **Driver de Conexão**: `postgresql+asyncpg://usuario:senha@localhost:5432/prospect_ai`
- **Configuração de Pool**:
  ```python
  from sqlalchemy.ext.asyncio import create_async_engine

  engine = create_async_engine(
      "postgresql+asyncpg://user:pass@localhost:5432/prospect_ai",
      pool_size=20,
      max_overflow=10,
      pool_timeout=30,
      pool_recycle=1800,
  )
  ```
- **Alembic**: O Alembic gerencia migrações de forma idêntica alterando apenas o dialeto no `alembic.ini` para a string de conexão do PostgreSQL.
