"""Módulo de configurações e variáveis de ambiente do ProspectAI.

Carrega configurações do arquivo .env e variáveis de ambiente do sistema operacional
utilizando Pydantic Settings (Pydantic v2).
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações globais da aplicação ProspectAI."""

    # --------------------------------------------------------------------------
    # Google Places API (New)
    # --------------------------------------------------------------------------
    google_api_key: str = Field(
        default="",
        alias="GOOGLE_API_KEY",
        description="Chave da Google Cloud restrita à Places API (New) para descoberta.",
    )
    places_provider: str = Field(
        default="osm",
        alias="PLACES_PROVIDER",
        description="Provedor de descoberta geográfica ('osm' para OpenStreetMap gratuito, 'google' para Google Places).",
    )

    # --------------------------------------------------------------------------
    # OpenAI API & LLM
    # --------------------------------------------------------------------------
    openai_api_key: str = Field(
        default="",
        alias="OPENAI_API_KEY",
        description="Chave secreta da OpenAI para qualificação e raciocínio com IA.",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        alias="OPENAI_MODEL",
        description="Modelo de LLM utilizado para qualificação estruturada de leads.",
    )
    llm_max_concurrent: int = Field(
        default=10,
        alias="LLM_MAX_CONCURRENT",
        description="Semáforo de concorrência máxima de requisições ao LLM.",
    )
    llm_temperature: float = Field(
        default=0.3,
        alias="LLM_TEMPERATURE",
        description="Temperatura de amostragem do modelo LLM (valores baixos favorecem precisão).",
    )

    # --------------------------------------------------------------------------
    # Banco de Dados
    # --------------------------------------------------------------------------
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/prospect_ai.db",
        alias="DATABASE_URL",
        description="URI de conexão assíncrona do SQLAlchemy (padrão SQLite com aiosqlite).",
    )

    # --------------------------------------------------------------------------
    # Varredura Geográfica e Grid Scanner
    # --------------------------------------------------------------------------
    default_scan_radius_km: float = Field(
        default=5.0,
        alias="DEFAULT_SCAN_RADIUS_KM",
        description="Raio padrão de varredura geográfica em quilômetros.",
    )
    default_grid_step_km: float = Field(
        default=1.5,
        alias="DEFAULT_GRID_STEP_KM",
        description="Espaçamento entre vértices da grade geográfica em quilômetros.",
    )
    max_results_per_search: int = Field(
        default=20,
        alias="MAX_RESULTS_PER_SEARCH",
        description="Quantidade máxima de estabelecimentos por quadrícula de busca.",
    )

    # --------------------------------------------------------------------------
    # Taxas Limite de Requisições (Rate Limits)
    # --------------------------------------------------------------------------
    google_requests_per_second: int = Field(
        default=5,
        alias="GOOGLE_REQUESTS_PER_SECOND",
        description="Limite de requisições por segundo na Places API do Google.",
    )
    brasilapi_requests_per_second: int = Field(
        default=2,
        alias="BRASILAPI_REQUESTS_PER_SECOND",
        description="Limite de requisições por segundo na BrasilAPI para evitar 429.",
    )
    cnpjws_requests_per_minute: int = Field(
        default=3,
        alias="CNPJWS_REQUESTS_PER_MINUTE",
        description="Limite de requisições por minuto no plano gratuito da CNPJ.ws.",
    )
    http_timeout_seconds: float = Field(
        default=10.0,
        alias="HTTP_TIMEOUT_SECONDS",
        description="Tempo limite padrão (timeout) em segundos para requisições HTTP.",
    )

    # --------------------------------------------------------------------------
    # Aplicação e Interface de Usuário
    # --------------------------------------------------------------------------
    app_title: str = Field(
        default="Sweezy AI",
        alias="APP_TITLE",
        description="Título exibido na barra superior da aplicação.",
    )
    app_theme: str = Field(
        default="dark",
        alias="APP_THEME",
        description="Tema visual da aplicação ('dark' ou 'light').",
    )
    app_port: int = Field(
        default=8550,
        alias="APP_PORT",
        description="Porta local utilizada caso a interface seja executada no navegador.",
    )
    log_level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
        description="Nível de detalhamento do logger (DEBUG, INFO, WARNING, ERROR).",
    )

    # --------------------------------------------------------------------------
    # Configuração Pydantic Settings
    # --------------------------------------------------------------------------
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: Any) -> str:
        """Normaliza a URL do banco para garantir compatibilidade assíncrona.

        Converte `sqlite:///` para `sqlite+aiosqlite:///` quando aplicável.
        """
        if not v or not isinstance(v, str):
            return "sqlite+aiosqlite:///./data/prospect_ai.db"
        url = v.strip()
        if url.startswith("sqlite:///") and not url.startswith("sqlite+aiosqlite:///"):
            return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        if url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
            return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url

    def ensure_data_directory(self) -> Path:
        """Garante a existência do diretório para arquivos locais de banco de dados.

        Returns:
            Path: Diretório onde o banco de dados e arquivos locais são armazenados.
        """
        if "sqlite" in self.database_url:
            raw_path = self.database_url.split("///")[-1]
            db_path = Path(raw_path)
            db_dir = db_path.parent
            if db_dir and not db_dir.exists():
                db_dir.mkdir(parents=True, exist_ok=True)
            return db_dir
        data_dir = Path("./data")
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir


@lru_cache
def get_settings() -> Settings:
    """Retorna uma instância única em cache das configurações da aplicação.

    Returns:
        Settings: Configurações carregadas do ambiente ou arquivo .env.
    """
    return Settings()


# Instância global para importação direta e rápida
settings: Settings = get_settings()
