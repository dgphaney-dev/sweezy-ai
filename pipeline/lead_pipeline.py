"""Orquestrador do Pipeline de Descoberta e Qualificação de Leads (ProspectAI / Sweezy AI)."""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from rich.console import Console
from rich.logging import RichHandler

from analysis.llm_qualifier import LLMQualifier
from analysis.pos_detector import (
    ContactChannel as POSContactChannel,
    HeuristicEvaluation,
    LikelihoodLevel as POSLikelihoodLevel,
    PixKeyType as POSPixKeyType,
    POSDetector,
)
from analysis.web_scraper import ScrapingResult, WebScraper
from config.settings import Settings, get_settings
from core.database import (
    get_db_session,
    get_lead_by_place_id,
    init_db,
    save_lead,
    save_scan_session,
)
from core.models import (
    Business,
    CNAEItem as CoreCNAEItem,
    CNPJData as CoreCNPJData,
    ContactChannel,
    Lead,
    LeadQualification as CoreLeadQualification,
    LeadStatus,
    LikelihoodLevel,
    PixKeyType,
    ScanSession,
    ScanSessionStatus,
    WebAnalysis,
)
from discovery.google_places import GooglePlacesClient, PlaceResult
from discovery.grid_scanner import GridPoint, GridScanner, generate_circular_grid
from discovery.receita_federal import (
    CompanyData,
    ReceitaFederalClient,
    extract_cnpjs_from_text,
)

logger = logging.getLogger("prospectai.pipeline")
if not logger.handlers:
    rich_handler = RichHandler(console=Console(stderr=True), show_time=True, show_path=False, rich_tracebacks=True)
    logger.addHandler(rich_handler)
    logger.setLevel(logging.INFO)


def _current_utc() -> datetime:
    return datetime.now(timezone.utc)


class PipelineStage(str, Enum):
    STARTING = "STARTING"
    GRID_GENERATION = "GRID_GENERATION"
    PLACES_SEARCH = "PLACES_SEARCH"
    DEDUPLICATION = "DEDUPLICATION"
    ENRICHMENT = "ENRICHMENT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class PipelineProgress:
    stage: PipelineStage
    current_step: int
    total_steps: int
    places_found: int = 0
    places_unique: int = 0
    places_scraped: int = 0
    cnpj_enriched: int = 0
    leads_qualified: int = 0
    high_priority_count: int = 0
    medium_priority_count: int = 0
    low_priority_count: int = 0
    current_business_name: str | None = None
    message: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def percentage(self) -> float:
        if self.total_steps <= 0:
            return 0.0
        return min(100.0, round((self.current_step / self.total_steps) * 100, 1))


@dataclass
class PipelineResult:
    session_id: str
    region_name: str
    center_lat: float
    center_lng: float
    radius_km: float
    business_types: list[str]
    total_grid_points: int
    total_places_found: int
    total_places_unique: int
    total_leads_saved: int
    high_priority_leads: int
    medium_priority_leads: int
    low_priority_leads: int
    duration_seconds: float
    leads: list[Lead] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


ProgressCallback = Callable[[PipelineProgress], None]


class LeadPipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        places_client: GooglePlacesClient | None = None,
        receita_client: ReceitaFederalClient | None = None,
        scraper: WebScraper | None = None,
        pos_detector: POSDetector | None = None,
        llm_qualifier: LLMQualifier | None = None,
        grid_scanner: GridScanner | None = None,
        concurrency_limit: int = 5,
    ) -> None:
        self.settings = settings or get_settings()
        use_osm = (
            getattr(self.settings, "places_provider", "").lower() == "osm"
            or not self.settings.google_api_key
        )
        self.places_client = places_client or GooglePlacesClient(
            api_key="" if use_osm else self.settings.google_api_key,
            dry_run=use_osm,
            requests_per_second=float(self.settings.google_requests_per_second),
            timeout=self.settings.http_timeout_seconds,
        )
        self.receita_client = receita_client or ReceitaFederalClient(timeout=self.settings.http_timeout_seconds)
        self.pos_detector = pos_detector or POSDetector()
        self.scraper = scraper or WebScraper(timeout=self.settings.http_timeout_seconds, pos_detector=self.pos_detector)
        self.llm_qualifier = llm_qualifier or LLMQualifier(api_key=self.settings.openai_api_key, model=self.settings.openai_model)
        self.grid_scanner = grid_scanner or GridScanner()
        self.concurrency_limit = max(1, concurrency_limit)
        self._semaphore = asyncio.Semaphore(self.concurrency_limit)
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True
        logger.warning("Pipeline recebeu sinal de cancelamento.")

    async def _emit_progress(self, callback: ProgressCallback | None, progress: PipelineProgress) -> None:
        if callback is None:
            return
        try:
            snapshot = copy.copy(progress)
            res = callback(snapshot)
            if asyncio.iscoroutine(res):
                await res
        except Exception as e:
            logger.warning(f"Erro no callback de progresso: {e}", exc_info=True)

    async def _process_single_business(self, place: PlaceResult, niche: str, session_id: str) -> Lead | None:
        if self._is_cancelled:
            return None

        async with self._semaphore:
            if self._is_cancelled:
                return None

            try:
                scraping_result: ScrapingResult
                if self.places_client.dry_run:
                    has_site = bool(place.website)
                    scraping_result = ScrapingResult(
                        url=place.website,
                        has_website=has_site,
                        has_whatsapp_order=True,
                        has_pdf_menu=bool(has_site),
                        cnpj_from_site="06990590000123" if has_site else None,
                        pix_key_type=POSPixKeyType.CPF,
                        raw_signals=["MOCK_DRY_RUN"],
                    )
                elif place.website:
                    scraping_result = await self.scraper.scrape(place.website)
                else:
                    scraping_result = ScrapingResult(url=None, has_website=False, error="Sem website", raw_signals=["SEM_WEBSITE_GMB"])

                cnpj_data_core: CoreCNPJData | None = None
                target_cnpj: str | None = scraping_result.cnpj_from_site

                if not target_cnpj and scraping_result.raw_html:
                    cnpjs_found = extract_cnpjs_from_text(scraping_result.raw_html)
                    if cnpjs_found:
                        target_cnpj = cnpjs_found[0]

                if not target_cnpj and self.places_client.dry_run:
                    target_cnpj = "06990590000123"

                company_fiscal: CompanyData | None = None
                if target_cnpj:
                    company_fiscal = await self.receita_client.get_cnpj_data(target_cnpj)
                    if company_fiscal:
                        cnaes_sec = [CoreCNAEItem(code=c.code, description=c.description) for c in company_fiscal.cnaes_secundarios]
                        cnpj_data_core = CoreCNPJData(
                            cnpj=company_fiscal.cnpj,
                            razao_social=company_fiscal.razao_social,
                            nome_fantasia=company_fiscal.nome_fantasia,
                            porte=company_fiscal.porte,
                            capital_social=company_fiscal.capital_social,
                            cnae_principal=CoreCNAEItem(code=company_fiscal.cnae_fiscal, description=company_fiscal.cnae_fiscal_descricao),
                            cnaes_secundarios=cnaes_sec,
                            data_abertura=company_fiscal.data_inicio_atividade,
                            situacao_cadastral=company_fiscal.situacao_cadastral,
                            simples_nacional=company_fiscal.simples_nacional,
                            endereco={
                                "logradouro": company_fiscal.logradouro,
                                "numero": company_fiscal.numero,
                                "complemento": company_fiscal.complemento,
                                "bairro": company_fiscal.bairro,
                                "municipio": company_fiscal.municipio,
                                "uf": company_fiscal.uf,
                                "cep": company_fiscal.cep,
                            },
                            telefone=company_fiscal.ddd_telefone_1,
                            email=company_fiscal.email,
                        )

                reviews_list = [{"author": r.author_name, "text": r.text, "rating": r.rating} for r in place.reviews]
                cnpj_dict = company_fiscal.model_dump() if company_fiscal else None

                heuristics_eval: HeuristicEvaluation = self.pos_detector.evaluate(
                    name=place.name,
                    website_url=place.website,
                    html_content=scraping_result.raw_html,
                    whatsapp_urls=scraping_result.whatsapp_urls,
                    reviews=reviews_list,
                    cnpj_data=cnpj_dict,
                )

                reviews_summary = [r.text for r in place.reviews if r.text]
                qual_result = await self.llm_qualifier.qualify(
                    business_name=place.name,
                    niche=place.primary_type or niche,
                    heuristic_evaluation=heuristics_eval,
                    scraping_data=scraping_result.to_web_analysis_dict(),
                    cnpj_info=cnpj_dict,
                    reviews_summary=reviews_summary,
                    phone=place.phone,
                    website_url=place.website,
                )

                lh_str = qual_result.likelihood_no_pos.value if hasattr(qual_result.likelihood_no_pos, "value") else str(qual_result.likelihood_no_pos)
                ch_str = qual_result.recommended_channel.value if hasattr(qual_result.recommended_channel, "value") else str(qual_result.recommended_channel)

                try:
                    lh_enum = LikelihoodLevel(lh_str)
                except (ValueError, KeyError):
                    lh_enum = LikelihoodLevel.MEDIUM

                try:
                    ch_enum = ContactChannel(ch_str)
                except (ValueError, KeyError):
                    ch_enum = ContactChannel.WHATSAPP

                domain_qualification = CoreLeadQualification(
                    likelihood_no_pos=lh_enum,
                    confidence_score=qual_result.confidence_score,
                    detected_red_flags=qual_result.detected_red_flags,
                    commercial_hook=qual_result.commercial_hook,
                    recommended_channel=ch_enum,
                    reasoning=qual_result.reasoning,
                )

                domain_business = Business(
                    place_id=place.place_id,
                    name=place.name,
                    address=place.address,
                    phone=place.phone,
                    website=place.website,
                    lat=place.lat,
                    lng=place.lng,
                    rating=place.rating,
                    review_count=place.review_count,
                    business_status=place.business_status or "OPERATIONAL",
                    primary_type=place.primary_type or niche,
                    google_maps_url=place.google_maps_url,
                )

                pix_str = scraping_result.pix_key_type.value if hasattr(scraping_result.pix_key_type, "value") else str(scraping_result.pix_key_type)
                try:
                    pix_enum = PixKeyType(pix_str)
                except (ValueError, KeyError):
                    pix_enum = PixKeyType.NONE

                domain_web_analysis = WebAnalysis(
                    url=scraping_result.url,
                    has_website=scraping_result.has_website,
                    has_whatsapp_order=scraping_result.has_whatsapp_order,
                    has_pdf_menu=scraping_result.has_pdf_menu,
                    has_online_cart=scraping_result.has_online_cart,
                    detected_pos_systems=scraping_result.detected_pos_systems,
                    social_links=scraping_result.social_links,
                    cnpj_from_site=scraping_result.cnpj_from_site,
                    pix_key_type=pix_enum,
                    raw_signals=scraping_result.raw_signals,
                )

                lead_status = LeadStatus.QUALIFIED if domain_qualification.likelihood_no_pos in (LikelihoodLevel.HIGH, LikelihoodLevel.MEDIUM) else LeadStatus.NEW

                lead = Lead(
                    id=uuid4(),
                    business=domain_business,
                    cnpj_data=cnpj_data_core,
                    web_analysis=domain_web_analysis,
                    qualification=domain_qualification,
                    status=lead_status,
                )

                await save_lead(lead, scan_session_id=session_id)
                return lead

            except Exception as e:
                logger.error(f"Erro durante enriquecimento do estabelecimento '{place.name}': {e}", exc_info=True)
                return None

    async def run_scan(
        self,
        region_name: str,
        center_lat: float,
        center_lng: float,
        radius_km: float = 2.0,
        step_km: float = 1.0,
        business_types: list[str] | None = None,
        max_places: int | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> PipelineResult:
        start_time = time.time()
        self._is_cancelled = False
        types = business_types or ["restaurant"]
        primary_niche = types[0] if types else "restaurant"

        await init_db()

        session_id = str(uuid4())
        scan_session = ScanSession(
            id=UUID(session_id),
            region_name=region_name,
            center_lat=center_lat,
            center_lng=center_lng,
            radius_km=radius_km,
            included_types=types,
            status=ScanSessionStatus.RUNNING,
            started_at=_current_utc(),
        )
        await save_scan_session(scan_session)

        progress = PipelineProgress(
            stage=PipelineStage.STARTING,
            current_step=0,
            total_steps=100,
            message=f"Iniciando varredura para '{region_name}'...",
        )
        await self._emit_progress(progress_callback, progress)
        errors: list[str] = []

        try:
            progress.stage = PipelineStage.GRID_GENERATION
            progress.message = "Calculando malha geodésica hexagonal..."
            await self._emit_progress(progress_callback, progress)

            grid_points: list[GridPoint] = generate_circular_grid(
                center_lat=center_lat,
                center_lng=center_lng,
                radius_km=radius_km,
                step_km=step_km,
            )
            total_cells = len(grid_points)
            progress.total_steps = total_cells
            progress.message = f"Grade gerada com {total_cells} pontos de busca."
            await self._emit_progress(progress_callback, progress)

            progress.stage = PipelineStage.PLACES_SEARCH
            raw_places_collected: list[PlaceResult] = []
            seen_place_ids: set[str] = set()

            for idx, pt in enumerate(grid_points, start=1):
                if self._is_cancelled:
                    break

                progress.current_step = idx
                progress.message = f"Consultando Google Places na célula {idx}/{total_cells}..."
                await self._emit_progress(progress_callback, progress)

                try:
                    cell_results = await self.places_client.search_nearby(
                        lat=pt.lat,
                        lng=pt.lng,
                        radius_meters=pt.radius_meters,
                        included_types=types,
                        max_results=self.settings.max_results_per_search,
                        region_hint=region_name,
                    )
                    progress.places_found += len(cell_results)

                    reg_lower = region_name.lower()
                    for p in cell_results:
                        if p.place_id and p.place_id not in seen_place_ids:
                            if ("brasilia" in reg_lower or "brasília" in reg_lower or "df" in reg_lower):
                                addr = p.address.lower()
                                if any(outra_uf in addr for outra_uf in [" - sp", " - rj", " - mg", " - pr", " - rs", " - ba", " - sc"]):
                                    continue
                            seen_place_ids.add(p.place_id)
                            raw_places_collected.append(p)
                            progress.places_unique += 1

                except Exception as err:
                    err_msg = f"Erro ao buscar Places na célula ({pt.lat}, {pt.lng}): {err}"
                    logger.warning(err_msg)
                    errors.append(err_msg)

                # Intervalo preventivo contra limites de taxa da API (QPS)
                await asyncio.sleep(0.35)

                if max_places and len(raw_places_collected) >= max_places:
                    raw_places_collected = raw_places_collected[:max_places]
                    break

            total_unique = len(raw_places_collected)
            progress.stage = PipelineStage.DEDUPLICATION
            progress.message = "Verificando unicidade contra base histórica..."
            await self._emit_progress(progress_callback, progress)

            places_to_process: list[PlaceResult] = []
            already_cataloged: list[Lead] = []
            for p in raw_places_collected:
                existing_lead = await get_lead_by_place_id(p.place_id)
                if not existing_lead:
                    places_to_process.append(p)
                else:
                    already_cataloged.append(existing_lead)

            progress.stage = PipelineStage.ENRICHMENT
            progress.total_steps = len(places_to_process) if places_to_process else len(already_cataloged)
            progress.current_step = 0
            if places_to_process:
                progress.message = f"Iniciando enriquecimento de {len(places_to_process)} novos locais..."
            else:
                progress.message = f"Todos os {len(already_cataloged)} locais já se encontram catalogados no banco."
            await self._emit_progress(progress_callback, progress)

            persisted_leads: list[Lead] = []
            enriched_counter = 0

            async def run_and_track(p: PlaceResult) -> Lead | None:
                nonlocal enriched_counter
                lead_res = await self._process_single_business(place=p, niche=primary_niche, session_id=session_id)
                enriched_counter += 1
                progress.current_step = enriched_counter
                progress.current_business_name = p.name

                if lead_res:
                    if lead_res.web_analysis and lead_res.web_analysis.has_website:
                        progress.places_scraped += 1
                    if lead_res.cnpj_data:
                        progress.cnpj_enriched += 1
                    if lead_res.qualification:
                        progress.leads_qualified += 1
                        lh = lead_res.qualification.likelihood_no_pos
                        if lh == LikelihoodLevel.HIGH:
                            progress.high_priority_count += 1
                        elif lh == LikelihoodLevel.MEDIUM:
                            progress.medium_priority_count += 1
                        else:
                            progress.low_priority_count += 1

                progress.message = f"Processado: {p.name} ({enriched_counter}/{len(places_to_process)})"
                await self._emit_progress(progress_callback, progress)
                return lead_res

            tasks = [run_and_track(p) for p in places_to_process]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if isinstance(res, Lead):
                    persisted_leads.append(res)
                elif isinstance(res, Exception):
                    errors.append(f"Erro em tarefa concorrente: {res}")

            if not persisted_leads and already_cataloged:
                persisted_leads = already_cataloged

            duration = round(time.time() - start_time, 2)
            high_count = sum(1 for l in persisted_leads if l.qualification and l.qualification.likelihood_no_pos == LikelihoodLevel.HIGH)
            med_count = sum(1 for l in persisted_leads if l.qualification and l.qualification.likelihood_no_pos == LikelihoodLevel.MEDIUM)
            low_count = sum(1 for l in persisted_leads if l.qualification and l.qualification.likelihood_no_pos == LikelihoodLevel.LOW)

            scan_session.total_found = progress.places_found
            scan_session.total_qualified = high_count + med_count
            scan_session.status = ScanSessionStatus.COMPLETED if not self._is_cancelled else ScanSessionStatus.STOPPED
            scan_session.completed_at = _current_utc()
            await save_scan_session(scan_session)

            progress.stage = PipelineStage.COMPLETED if not self._is_cancelled else PipelineStage.CANCELLED
            progress.current_step = progress.total_steps
            progress.message = f"Varredura concluída em {duration}s! {len(persisted_leads)} leads salvos."
            await self._emit_progress(progress_callback, progress)

            return PipelineResult(
                session_id=session_id,
                region_name=region_name,
                center_lat=center_lat,
                center_lng=center_lng,
                radius_km=radius_km,
                business_types=types,
                total_grid_points=total_cells,
                total_places_found=progress.places_found,
                total_places_unique=total_unique,
                total_leads_saved=len(persisted_leads),
                high_priority_leads=high_count,
                medium_priority_leads=med_count,
                low_priority_leads=low_count,
                duration_seconds=duration,
                leads=persisted_leads,
                errors=errors,
            )

        except Exception as e:
            logger.error(f"Falha catastrófica no pipeline: {e}", exc_info=True)
            scan_session.status = ScanSessionStatus.FAILED
            scan_session.completed_at = _current_utc()
            await save_scan_session(scan_session)

            progress.stage = PipelineStage.FAILED
            progress.message = f"Erro no pipeline: {e}"
            await self._emit_progress(progress_callback, progress)

            return PipelineResult(
                session_id=session_id,
                region_name=region_name,
                center_lat=center_lat,
                center_lng=center_lng,
                radius_km=radius_km,
                business_types=types,
                total_grid_points=0,
                total_places_found=0,
                total_places_unique=0,
                total_leads_saved=0,
                high_priority_leads=0,
                medium_priority_leads=0,
                low_priority_leads=0,
                duration_seconds=round(time.time() - start_time, 2),
                leads=[],
                errors=[str(e)],
            )
