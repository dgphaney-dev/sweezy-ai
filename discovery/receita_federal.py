"""Módulo de enriquecimento cadastral via Receita Federal (BrasilAPI e CNPJ.ws)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.logging import RichHandler
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger("prospectai.discovery.receita")
if not logger.handlers:
    rich_handler = RichHandler(console=Console(stderr=True), show_time=True, show_path=False, rich_tracebacks=True)
    logger.addHandler(rich_handler)
    logger.setLevel(logging.INFO)


def clean_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def format_cnpj(cnpj: str) -> str:
    digits = clean_cnpj(cnpj)
    if len(digits) != 14:
        return cnpj
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"


def validate_cnpj(cnpj: str) -> bool:
    digits = clean_cnpj(cnpj)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    numbers = [int(d) for d in digits]
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    rem_1 = sum(n * w for n, w in zip(numbers[:12], w1)) % 11
    if numbers[12] != (0 if rem_1 < 2 else 11 - rem_1):
        return False
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    rem_2 = sum(n * w for n, w in zip(numbers[:13], w2)) % 11
    return numbers[13] == (0 if rem_2 < 2 else 11 - rem_2)


def extract_cnpjs_from_text(text: str) -> list[str]:
    if not text:
        return []
    candidates = []
    candidates.extend(re.findall(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", text))
    candidates.extend(re.findall(r"(?i)(?:cnpj|c\.?n\.?p\.?j\.?|mf|inscrição|inscricao)[\s:.\-#]*([0-9]{2}[\.\s]?[0-9]{3}[\.\s]?[0-9]{3}[\/\s]?[0-9]{4}[-\s]?[0-9]{2}|[0-9]{14})", text))
    candidates.extend(re.findall(r"\b\d{14}\b", text))

    valid_cnpjs, seen = [], set()
    for cand in candidates:
        clean = clean_cnpj(cand)
        if clean not in seen and validate_cnpj(clean):
            seen.add(clean)
            valid_cnpjs.append(clean)
    return valid_cnpjs


def extract_first_valid_cnpj(text: str) -> str | None:
    res = extract_cnpjs_from_text(text)
    return res[0] if res else None


class CompanyPartner(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)
    nome_socio: str
    qualificacao_socio: str | None = None
    faixa_etaria: str | None = None
    pais: str | None = None


class CNAEItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)
    code: int
    description: str


class CompanyData(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)
    cnpj: str
    cnpj_formatado: str
    razao_social: str
    nome_fantasia: str | None = None
    situacao_cadastral: str = "ATIVA"
    cnae_fiscal: int = 0
    cnae_fiscal_descricao: str = ""
    cnaes_secundarios: list[CNAEItem] = Field(default_factory=list)
    porte: str = "ME"
    capital_social: float = 0.0
    data_inicio_atividade: str | None = None
    logradouro: str = ""
    numero: str = ""
    complemento: str | None = None
    bairro: str | None = None
    municipio: str = ""
    uf: str = ""
    cep: str | None = None
    ddd_telefone_1: str | None = None
    ddd_telefone_2: str | None = None
    email: str | None = None
    qsa: list[CompanyPartner] = Field(default_factory=list)
    simples_nacional: bool | None = None
    fonte: str = "brasilapi"
    cached_at: str | None = None


class CNPJCache:
    def __init__(self, db_path: str | Path | None = "data/cnpj_cache.db", default_ttl_seconds: float = 86400 * 30) -> None:
        self.default_ttl = default_ttl_seconds
        self.db_path = str(db_path) if db_path else ":memory:"
        self._memory_cache: dict[str, tuple[float, CompanyData]] = {}
        self._lock = asyncio.Lock()
        self._shared_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._init_sqlite()

    def _get_conn(self) -> sqlite3.Connection:
        return self._shared_conn if self._shared_conn is not None else sqlite3.connect(self.db_path)

    def _init_sqlite(self) -> None:
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cnpj_cache (
                    cnpj TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cnpj_expires ON cnpj_cache(expires_at);")
            conn.commit()
        finally:
            if self._shared_conn is None:
                conn.close()

    async def get(self, cnpj: str) -> CompanyData | None:
        clean = clean_cnpj(cnpj)
        now = time.time()
        async with self._lock:
            if clean in self._memory_cache:
                expires_at, data = self._memory_cache[clean]
                if now < expires_at:
                    return data
                del self._memory_cache[clean]

        def _read_sqlite() -> CompanyData | None:
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                cur.execute("SELECT data_json, expires_at FROM cnpj_cache WHERE cnpj = ?", (clean,))
                row = cur.fetchone()
                if not row:
                    return None
                data_json, expires_at = row
                if now > expires_at:
                    cur.execute("DELETE FROM cnpj_cache WHERE cnpj = ?", (clean,))
                    conn.commit()
                    return None
                return CompanyData.model_validate(json.loads(data_json))
            finally:
                if self._shared_conn is None:
                    conn.close()

        data = await asyncio.to_thread(_read_sqlite)
        if data:
            async with self._lock:
                self._memory_cache[clean] = (now + self.default_ttl, data)
        return data

    async def set(self, cnpj: str, data: CompanyData, ttl_seconds: float | None = None) -> None:
        clean = clean_cnpj(cnpj)
        now = time.time()
        ttl = ttl_seconds or self.default_ttl
        expires_at = now + ttl

        async with self._lock:
            self._memory_cache[clean] = (expires_at, data)

        data_json = data.model_dump_json()

        def _write_sqlite() -> None:
            conn = self._get_conn()
            try:
                conn.execute("""
                    INSERT INTO cnpj_cache (cnpj, data_json, updated_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(cnpj) DO UPDATE SET
                        data_json = excluded.data_json,
                        updated_at = excluded.updated_at,
                        expires_at = excluded.expires_at;
                """, (clean, data_json, now, expires_at))
                conn.commit()
            finally:
                if self._shared_conn is None:
                    conn.close()

        await asyncio.to_thread(_write_sqlite)

    async def clear(self) -> None:
        async with self._lock:
            self._memory_cache.clear()

        def _clear_sqlite() -> None:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM cnpj_cache;")
                conn.commit()
            finally:
                if self._shared_conn is None:
                    conn.close()

        await asyncio.to_thread(_clear_sqlite)


class TokenBucketCNPJWS:
    def __init__(self, max_calls_per_minute: int = 3):
        self.interval = 60.0 / max_calls_per_minute
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def wait_turn(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self.interval:
                await asyncio.sleep(self.interval - elapsed)
            self._last_call = time.monotonic()


def _generate_mock_company(cnpj: str) -> CompanyData:
    clean = clean_cnpj(cnpj)
    return CompanyData(
        cnpj=clean,
        cnpj_formatado=format_cnpj(clean),
        razao_social=f"COMERCIO E SERVICOS {clean[-4:]} LTDA",
        nome_fantasia="PONTO COMERCIAL EXEMPLO",
        situacao_cadastral="ATIVA",
        cnae_fiscal=5611201,
        cnae_fiscal_descricao="Restaurantes e similares",
        cnaes_secundarios=[
            CNAEItem(code=5611203, description="Lanchonetes, casas de chá, de sucos e similares"),
            CNAEItem(code=4712100, description="Comércio varejista de mercadorias em geral"),
        ],
        porte="ME",
        capital_social=50000.0,
        data_inicio_atividade="2021-06-15",
        logradouro="Avenida Central",
        numero="500",
        complemento="Sala 01",
        bairro="Centro",
        municipio="São Paulo",
        uf="SP",
        cep="01001-000",
        ddd_telefone_1="1134567890",
        email="contato@pontocomercialexemplo.com.br",
        qsa=[
            CompanyPartner(nome_socio="CARLOS EDUARDO SILVA", qualificacao_socio="49-Sócio-Administrador", faixa_etaria="41 a 50 anos"),
            CompanyPartner(nome_socio="MARIANA ALMEIDA SILVA", qualificacao_socio="22-Sócio", faixa_etaria="31 a 40 anos"),
        ],
        simples_nacional=True,
        fonte="mock",
    )


def normalize_text_for_comparison(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in normalized if not unicodedata.combining(c))
    cleaned = re.sub(r"[^\w\s]", " ", without_accents.lower())
    return " ".join(cleaned.split())


def calculate_string_similarity(str1: str, str2: str) -> float:
    norm1 = normalize_text_for_comparison(str1)
    norm2 = normalize_text_for_comparison(str2)
    if not norm1 or not norm2:
        return 0.0
    if norm1 == norm2:
        return 1.0
    seq_ratio = SequenceMatcher(None, norm1, norm2).ratio()
    tokens1, tokens2 = set(norm1.split()), set(norm2.split())
    jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2) if tokens1 and tokens2 else 0.0
    return max(seq_ratio, (seq_ratio * 0.4) + (jaccard * 0.6))


def correlate_phone(target_phone: str, company: CompanyData) -> bool:
    clean_target = clean_cnpj(target_phone)
    if not clean_target:
        return False
    if clean_target.startswith("55") and len(clean_target) in (12, 13):
        clean_target = clean_target[2:]
    cad_phones = [clean_cnpj(p) for p in (company.ddd_telefone_1, company.ddd_telefone_2) if p]
    for cad in cad_phones:
        if not cad:
            continue
        if clean_target == cad:
            return True
        if len(clean_target) >= 8 and len(cad) >= 8 and clean_target[-8:] == cad[-8:]:
            return True
    return False


def correlate_name_and_address(target_name: str, target_address: str | None, candidate: CompanyData) -> float:
    name_sim_fantasia = calculate_string_similarity(target_name, candidate.nome_fantasia) if candidate.nome_fantasia else 0.0
    name_sim_razao = calculate_string_similarity(target_name, candidate.razao_social)
    name_score = max(name_sim_fantasia, name_sim_razao)

    if target_address:
        cand_address_full = f"{candidate.logradouro} {candidate.numero} {candidate.bairro or ''} {candidate.municipio} {candidate.uf}".strip()
        address_score = calculate_string_similarity(target_address, cand_address_full)
        total_score = (name_score * 0.7) + (address_score * 0.3)
    else:
        total_score = name_score
    return round(total_score, 4)


class ReceitaFederalClient:
    BRASIL_API_URL = "https://brasilapi.com.br/api/cnpj/v1"
    CNPJ_WS_URL = "https://publica.cnpj.ws/cnpj"

    def __init__(self, cache_db_path: str | Path | None = "data/cnpj_cache.db", dry_run: bool = False, timeout: float = 10.0) -> None:
        self.dry_run = dry_run
        self.timeout = timeout
        self.cache = CNPJCache(cache_db_path)
        self.cnpj_ws_limiter = TokenBucketCNPJWS(max_calls_per_minute=3)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": "ProspectAI-LeadAgent/1.0"})
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> ReceitaFederalClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def get_cnpj_data(self, cnpj: str, use_cache: bool = True) -> CompanyData | None:
        clean = clean_cnpj(cnpj)
        if not validate_cnpj(clean):
            return None

        if use_cache:
            cached = await self.cache.get(clean)
            if cached:
                return cached

        if self.dry_run:
            await asyncio.sleep(0.05)
            mock_data = _generate_mock_company(clean)
            if use_cache:
                await self.cache.set(clean, mock_data)
            return mock_data

        brasil_data = await self._fetch_from_brasil_api(clean)
        if brasil_data:
            if use_cache:
                await self.cache.set(clean, brasil_data)
            return brasil_data

        cnpj_ws_data = await self._fetch_from_cnpj_ws(clean)
        if cnpj_ws_data:
            if use_cache:
                await self.cache.set(clean, cnpj_ws_data)
            return cnpj_ws_data
        return None

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1.0, min=1.0, max=4.0), retry=retry_if_exception_type((httpx.ConnectTimeout, httpx.ReadTimeout)), reraise=False)
    async def _fetch_from_brasil_api(self, clean_cnpj_str: str) -> CompanyData | None:
        url = f"{self.BRASIL_API_URL}/{clean_cnpj_str}"
        client = await self._get_client()
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                return self._parse_brasil_api_response(resp.json(), clean_cnpj_str)
            return None
        except Exception:
            return None

    def _parse_brasil_api_response(self, raw: dict[str, Any], clean_cnpj_str: str) -> CompanyData:
        qsa_list = [
            CompanyPartner(
                nome_socio=s.get("nome_socio") or s.get("nome", "SÓCIO"),
                qualificacao_socio=s.get("qualificacao_socio"),
                faixa_etaria=s.get("faixa_etaria"),
                pais=s.get("pais"),
            )
            for s in raw.get("qsa", []) if isinstance(s, dict)
        ]
        secundarios = [
            CNAEItem(code=int(c.get("codigo", 0)), description=c.get("descricao", ""))
            for c in raw.get("cnaes_secundarios", []) if isinstance(c, dict)
        ]
        ddd = raw.get("ddd_telefone_1", "")
        clean_phone = clean_cnpj(ddd) if ddd else None

        return CompanyData(
            cnpj=clean_cnpj_str,
            cnpj_formatado=format_cnpj(clean_cnpj_str),
            razao_social=raw.get("razao_social", ""),
            nome_fantasia=raw.get("nome_fantasia") or None,
            situacao_cadastral=raw.get("situacao_cadastral", "ATIVA"),
            cnae_fiscal=int(raw.get("cnae_fiscal", 0)),
            cnae_fiscal_descricao=raw.get("cnae_fiscal_descricao", ""),
            cnaes_secundarios=secundarios,
            porte=raw.get("porte", "ME"),
            capital_social=float(raw.get("capital_social", 0.0)),
            data_inicio_atividade=raw.get("data_inicio_atividade"),
            logradouro=raw.get("logradouro", ""),
            numero=raw.get("numero", "S/N"),
            complemento=raw.get("complemento"),
            bairro=raw.get("bairro"),
            municipio=raw.get("municipio", ""),
            uf=raw.get("uf", ""),
            cep=raw.get("cep"),
            ddd_telefone_1=clean_phone,
            ddd_telefone_2=raw.get("ddd_telefone_2"),
            email=raw.get("email"),
            qsa=qsa_list,
            simples_nacional=raw.get("opcao_pelo_simples"),
            fonte="brasilapi",
        )

    async def _fetch_from_cnpj_ws(self, clean_cnpj_str: str) -> CompanyData | None:
        await self.cnpj_ws_limiter.wait_turn()
        url = f"{self.CNPJ_WS_URL}/{clean_cnpj_str}"
        client = await self._get_client()
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                return self._parse_cnpj_ws_response(resp.json(), clean_cnpj_str)
            return None
        except Exception:
            return None

    def _parse_cnpj_ws_response(self, raw: dict[str, Any], clean_cnpj_str: str) -> CompanyData:
        est = raw.get("estabelecimento", {})
        atividade_principal = est.get("atividade_principal", {})
        secundarios = [
            CNAEItem(code=int(c.get("id", 0)), description=c.get("descricao", ""))
            for c in est.get("atividades_secundarias", []) if isinstance(c, dict)
        ]
        qsa_list = [
            CompanyPartner(
                nome_socio=s.get("nome", "SÓCIO"),
                qualificacao_socio=s.get("qualificacao_socio", {}).get("descricao") if isinstance(s.get("qualificacao_socio"), dict) else str(s.get("qualificacao_socio", "")),
                faixa_etaria=s.get("faixa_etaria", {}).get("descricao") if isinstance(s.get("faixa_etaria"), dict) else None,
            )
            for s in raw.get("socios", []) if isinstance(s, dict)
        ]
        logr = f"{est.get('tipo_logradouro', '')} {est.get('logradouro', '')}".strip()
        ddd, tel = est.get("ddd1", ""), est.get("telefone1", "")
        clean_phone = clean_cnpj(f"{ddd}{tel}") if (ddd or tel) else None

        return CompanyData(
            cnpj=clean_cnpj_str,
            cnpj_formatado=format_cnpj(clean_cnpj_str),
            razao_social=raw.get("razao_social", ""),
            nome_fantasia=est.get("nome_fantasia") or None,
            situacao_cadastral=est.get("situacao_cadastral", "ATIVA"),
            cnae_fiscal=int(atividade_principal.get("id", 0)),
            cnae_fiscal_descricao=atividade_principal.get("descricao", ""),
            cnaes_secundarios=secundarios,
            porte=raw.get("porte", {}).get("descricao", "ME"),
            capital_social=float(raw.get("capital_social", 0.0)),
            data_inicio_atividade=est.get("data_inicio_atividade"),
            logradouro=logr,
            numero=est.get("numero", "S/N"),
            complemento=est.get("complemento"),
            bairro=est.get("bairro"),
            municipio=est.get("cidade", {}).get("nome", ""),
            uf=est.get("estado", {}).get("sigla", ""),
            cep=est.get("cep"),
            ddd_telefone_1=clean_phone,
            ddd_telefone_2=None,
            email=est.get("email"),
            qsa=qsa_list,
            simples_nacional=raw.get("simples", {}).get("optante") if isinstance(raw.get("simples"), dict) else None,
            fonte="cnpj.ws",
        )

    def match_best_candidate(
        self,
        target_name: str,
        target_phone: str | None,
        target_address: str | None,
        candidates: list[CompanyData],
        min_threshold: float = 0.65,
    ) -> tuple[CompanyData | None, float]:
        if not candidates:
            return None, 0.0
        best_company, best_score = None, 0.0
        for cand in candidates:
            score = correlate_name_and_address(target_name, target_address, cand)
            if target_phone and correlate_phone(target_phone, cand):
                score = max(score, 0.95)
            if score > best_score:
                best_score = score
                best_company = cand
        if best_score >= min_threshold and best_company is not None:
            return best_company, best_score
        return None, best_score
