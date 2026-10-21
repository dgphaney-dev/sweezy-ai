"""Camada de persistência assíncrona SQLAlchemy 2.0 para o Sweezy AI."""

from __future__ import annotations

import csv
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    selectinload,
)

from config.settings import get_settings, settings
from core.models import (
    Business,
    CNAEItem,
    CNPJData,
    CompanyPorte,
    ContactChannel,
    ContactHistory,
    Lead,
    LeadQualification,
    LeadStatus,
    LikelihoodLevel,
    ScanSession,
    ScanSessionStatus,
    WebAnalysis,
)

logger = logging.getLogger("prospectai.core.database")


def _current_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _enum_str(val: Any) -> str | None:
    if val is None:
        return None
    return str(val.value) if hasattr(val, "value") else str(val)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: SQLITE_JSON, list[Any]: SQLITE_JSON}


class ScanSessionModel(Base):
    __tablename__ = "scan_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    region_name: Mapped[str] = mapped_column(String(255), nullable=False)
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False)
    radius_km: Mapped[float] = mapped_column(Float, nullable=False)
    included_types_json: Mapped[list[Any]] = mapped_column(SQLITE_JSON, default=list)
    total_found: Mapped[int] = mapped_column(Integer, default=0)
    total_qualified: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default=ScanSessionStatus.RUNNING.value)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_current_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    businesses: Mapped[list[BusinessModel]] = relationship("BusinessModel", back_populates="scan_session")
    leads: Mapped[list[LeadModel]] = relationship("LeadModel", back_populates="scan_session")

    def to_pydantic(self) -> ScanSession:
        status_val = (
            ScanSessionStatus(self.status)
            if self.status in ScanSessionStatus.__members__.values()
            else ScanSessionStatus.RUNNING
        )
        return ScanSession(
            id=UUID(self.id),
            region_name=self.region_name,
            center_lat=self.center_lat,
            center_lng=self.center_lng,
            radius_km=self.radius_km,
            included_types=list(self.included_types_json or []),
            total_found=self.total_found,
            total_qualified=self.total_qualified,
            started_at=self.started_at,
            completed_at=self.completed_at,
            status=status_val,
        )


class BusinessModel(Base):
    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    place_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    scan_session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scan_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    commercial_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    business_status: Mapped[str | None] = mapped_column(String(50), default="OPERATIONAL")
    primary_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    google_maps_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_current_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_current_utc, onupdate=_current_utc)

    scan_session: Mapped[ScanSessionModel | None] = relationship("ScanSessionModel", back_populates="businesses")
    lead: Mapped[LeadModel | None] = relationship("LeadModel", back_populates="business", uselist=False, cascade="all, delete-orphan")
    contact_history: Mapped[list[ContactHistoryModel]] = relationship("ContactHistoryModel", back_populates="business", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_businesses_coords", "lat", "lng"),)

    def to_pydantic(self) -> Business:
        return Business(
            place_id=self.place_id,
            name=self.name,
            address=self.address,
            phone=self.phone,
            website=self.website,
            lat=self.lat,
            lng=self.lng,
            rating=self.rating,
            review_count=self.review_count,
            business_status=self.business_status or "OPERATIONAL",
            primary_type=self.primary_type,
            google_maps_url=self.google_maps_url,
        )


class LeadModel(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    business_id: Mapped[str] = mapped_column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    scan_session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scan_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default=LeadStatus.NEW.value, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True, index=True)

    likelihood_no_pos: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    commercial_hook: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_channel: Mapped[str | None] = mapped_column(String(20), default="WHATSAPP")
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_red_flags_json: Mapped[list[Any]] = mapped_column(SQLITE_JSON, default=list)

    cnpj_data_json: Mapped[dict[str, Any] | None] = mapped_column(SQLITE_JSON, nullable=True)
    web_analysis_json: Mapped[dict[str, Any] | None] = mapped_column(SQLITE_JSON, nullable=True)
    qualification_json: Mapped[dict[str, Any] | None] = mapped_column(SQLITE_JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_current_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_current_utc, onupdate=_current_utc, index=True)
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    business: Mapped[BusinessModel] = relationship("BusinessModel", back_populates="lead")
    scan_session: Mapped[ScanSessionModel | None] = relationship("ScanSessionModel", back_populates="leads")
    contact_history: Mapped[list[ContactHistoryModel]] = relationship("ContactHistoryModel", back_populates="lead", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_leads_likelihood_score", "likelihood_no_pos", "confidence_score"),)

    def to_pydantic(self) -> Lead:
        cnpj_obj: CNPJData | None = None
        if self.cnpj_data_json:
            try:
                cnpj_obj = CNPJData.model_validate(self.cnpj_data_json)
            except Exception as e:
                logger.warning(f"Erro ao validar cnpj_data_json: {e}")

        web_obj: WebAnalysis | None = None
        if self.web_analysis_json:
            try:
                web_obj = WebAnalysis.model_validate(self.web_analysis_json)
            except Exception as e:
                logger.warning(f"Erro ao validar web_analysis_json: {e}")

        qual_obj: LeadQualification | None = None
        if self.qualification_json:
            try:
                qual_obj = LeadQualification.model_validate(self.qualification_json)
            except Exception as e:
                logger.warning(f"Erro ao validar qualification_json: {e}")
        elif self.likelihood_no_pos:
            qual_obj = LeadQualification(
                likelihood_no_pos=LikelihoodLevel(self.likelihood_no_pos),
                confidence_score=self.confidence_score or 0.0,
                commercial_hook=self.commercial_hook or "Oportunidade detectada para automacao comercial.",
                recommended_channel=ContactChannel(self.recommended_channel or "WHATSAPP"),
                reasoning=self.reasoning or "Qualificacao gerada via pipeline de analise.",
                detected_red_flags=list(self.detected_red_flags_json or []),
            )

        status_val = (
            LeadStatus(self.status)
            if self.status in LeadStatus.__members__.values()
            else LeadStatus.NEW
        )

        return Lead(
            id=UUID(self.id),
            business=self.business.to_pydantic(),
            cnpj_data=cnpj_obj,
            web_analysis=web_obj,
            qualification=qual_obj,
            status=status_val,
            notes=self.notes,
            created_at=self.created_at,
            updated_at=self.updated_at,
            contacted_at=self.contacted_at,
        )


class CNPJCacheModel(Base):
    __tablename__ = "cnpj_cache"

    cnpj: Mapped[str] = mapped_column(String(14), primary_key=True)
    razao_social: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    nome_fantasia: Mapped[str | None] = mapped_column(String(255), nullable=True)
    porte: Mapped[str | None] = mapped_column(String(30), nullable=True)
    situacao_cadastral: Mapped[str] = mapped_column(String(50), default="ATIVA")
    data_abertura: Mapped[str | None] = mapped_column(String(20), nullable=True)
    capital_social: Mapped[float | None] = mapped_column(Float, default=0.0)
    simples_nacional: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cnae_principal_codigo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cnae_principal_descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cnae_principal_json: Mapped[dict[str, Any] | None] = mapped_column(SQLITE_JSON, nullable=True)
    cnaes_secundarios_json: Mapped[list[Any]] = mapped_column(SQLITE_JSON, default=list)
    qsa_json: Mapped[list[Any]] = mapped_column(SQLITE_JSON, default=list)
    endereco_json: Mapped[dict[str, Any] | None] = mapped_column(SQLITE_JSON, nullable=True)
    endereco_completo: Mapped[str | None] = mapped_column(Text, nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_data_json: Mapped[dict[str, Any] | None] = mapped_column(SQLITE_JSON, nullable=True)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_current_utc)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_pydantic(self) -> CNPJData:
        if self.raw_data_json:
            try:
                return CNPJData.model_validate(self.raw_data_json)
            except Exception:
                pass

        cnae_p = CNAEItem(
            codigo=self.cnae_principal_codigo or 0,
            descricao=self.cnae_principal_descricao or "Não informado",
        )
        cnaes_s: list[CNAEItem] = []
        for c in self.cnaes_secundarios_json or []:
            try:
                cnaes_s.append(CNAEItem.model_validate(c))
            except Exception:
                continue

        return CNPJData(
            cnpj=self.cnpj,
            razao_social=self.razao_social,
            nome_fantasia=self.nome_fantasia,
            porte=self.porte or CompanyPorte.ME.value,
            capital_social=self.capital_social or 0.0,
            cnae_principal=cnae_p,
            cnaes_secundarios=cnaes_s,
            data_abertura=self.data_abertura,
            situacao_cadastral=self.situacao_cadastral,
            simples_nacional=self.simples_nacional,
            endereco=self.endereco_json or self.endereco_completo or {},
            telefone=self.telefone,
            email=self.email,
        )


class ContactHistoryModel(Base):
    __tablename__ = "contact_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    lead_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)
    business_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    message_sent: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_current_utc)

    lead: Mapped[LeadModel | None] = relationship("LeadModel", back_populates="contact_history")
    business: Mapped[BusinessModel | None] = relationship("BusinessModel", back_populates="contact_history")

    def to_pydantic(self) -> ContactHistory:
        channel_val = (
            ContactChannel(self.channel)
            if self.channel in ContactChannel.__members__.values()
            else ContactChannel.WHATSAPP
        )
        return ContactHistory(
            id=UUID(self.id),
            lead_id=UUID(self.lead_id) if self.lead_id else uuid4(),
            channel=channel_val,
            message_sent=self.message_sent,
            response=self.response,
            created_at=self.created_at,
        )


ScanSessionEntity = ScanSessionModel
BusinessEntity = BusinessModel
LeadEntity = LeadModel
CNPJRecordEntity = CNPJCacheModel
ContactHistoryEntity = ContactHistoryModel

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(db_url: str | None = None) -> AsyncEngine:
    global _engine
    if _engine is None or db_url is not None:
        raw_url = db_url or get_settings().database_url
        if raw_url.startswith("sqlite:///") and not raw_url.startswith("sqlite+aiosqlite:///"):
            normalized_url = raw_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        elif raw_url.startswith("sqlite://") and not raw_url.startswith("sqlite+aiosqlite://"):
            normalized_url = raw_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        else:
            normalized_url = raw_url

        settings.ensure_data_directory()
        is_sqlite = "sqlite" in normalized_url
        connect_args: dict[str, Any] = {"check_same_thread": False} if is_sqlite else {}

        engine = create_async_engine(normalized_url, echo=False, future=True, connect_args=connect_args)

        if is_sqlite:
            @event.listens_for(engine.sync_engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection: Any, connection_record: Any) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA synchronous = NORMAL")
                cursor.execute("PRAGMA busy_timeout = 10000")
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute("PRAGMA cache_size = -64000")
                cursor.execute("PRAGMA temp_store = MEMORY")
                cursor.close()

        _engine = engine
    return _engine


def get_session_factory(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    eng = engine or get_engine()
    if _session_factory is None or engine is not None:
        _session_factory = async_sessionmaker(
            bind=eng,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


get_sessionmaker = get_session_factory


@asynccontextmanager
async def get_db_session(engine: AsyncEngine | None = None) -> AsyncIterator[AsyncSession]:
    factory = get_session_factory(engine)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db(engine: AsyncEngine | None = None) -> None:
    eng = engine or get_engine()
    settings.ensure_data_directory()
    async with eng.begin() as conn:
        logger.info("Criando tabelas relacionais do Sweezy AI...")
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def save_lead(
    lead: Lead | dict[str, Any],
    scan_session_id: str | None = None,
    session: AsyncSession | None = None,
) -> Lead:
    lead_data = Lead.model_validate(lead) if isinstance(lead, dict) else lead
    if session is None:
        async with get_db_session() as s:
            return await _save_lead_internal(lead_data, scan_session_id, s)
    return await _save_lead_internal(lead_data, scan_session_id, session)


async def _save_lead_internal(lead: Lead, scan_session_id: str | None, session: AsyncSession) -> Lead:
    b_data = lead.business
    stmt_b = select(BusinessModel).where(BusinessModel.place_id == b_data.place_id)
    biz = (await session.execute(stmt_b)).scalar_one_or_none()
    now = _current_utc()

    if biz is None:
        biz = BusinessModel(
            id=str(uuid4()),
            place_id=b_data.place_id,
            scan_session_id=scan_session_id,
            name=b_data.name,
            commercial_name=b_data.name,
            address=b_data.address,
            phone=b_data.phone,
            website=b_data.website,
            lat=b_data.lat,
            lng=b_data.lng,
            rating=b_data.rating,
            review_count=b_data.review_count,
            business_status=b_data.business_status or "OPERATIONAL",
            primary_type=b_data.primary_type,
            google_maps_url=b_data.google_maps_url,
            cnpj=lead.cnpj_data.cnpj if lead.cnpj_data else None,
            created_at=now,
            updated_at=now,
        )
        session.add(biz)
        await session.flush()
    else:
        biz.name = b_data.name
        biz.address = b_data.address
        biz.phone = b_data.phone
        biz.website = b_data.website
        biz.lat = b_data.lat
        biz.lng = b_data.lng
        biz.rating = b_data.rating
        biz.review_count = b_data.review_count
        biz.business_status = b_data.business_status
        biz.primary_type = b_data.primary_type
        biz.google_maps_url = b_data.google_maps_url
        if lead.cnpj_data:
            biz.cnpj = lead.cnpj_data.cnpj
        if scan_session_id:
            biz.scan_session_id = scan_session_id
        biz.updated_at = now
        await session.flush()

    stmt_l = (
        select(LeadModel)
        .options(selectinload(LeadModel.business))
        .where(or_(LeadModel.id == str(lead.id), LeadModel.business_id == biz.id))
    )
    lead_model = (await session.execute(stmt_l)).scalar_one_or_none()

    status_str = _enum_str(lead.status) or LeadStatus.NEW.value
    likelihood_str = _enum_str(lead.qualification.likelihood_no_pos) if lead.qualification else None
    confidence_val = lead.qualification.confidence_score if lead.qualification else None
    hook_val = lead.qualification.commercial_hook if lead.qualification else None
    channel_str = _enum_str(lead.qualification.recommended_channel) if lead.qualification else "WHATSAPP"
    reasoning_val = lead.qualification.reasoning if lead.qualification else None
    red_flags_list = list(lead.qualification.detected_red_flags) if lead.qualification else []

    cnpj_json = lead.cnpj_data.model_dump(mode="json") if lead.cnpj_data else None
    web_json = lead.web_analysis.model_dump(mode="json") if lead.web_analysis else None
    qual_json = lead.qualification.model_dump(mode="json") if lead.qualification else None
    cnpj_str = lead.cnpj_data.cnpj if lead.cnpj_data else None

    if lead_model is None:
        lead_model = LeadModel(
            id=str(lead.id),
            business_id=biz.id,
            scan_session_id=scan_session_id,
            status=status_str,
            notes=lead.notes,
            cnpj=cnpj_str,
            likelihood_no_pos=likelihood_str,
            confidence_score=confidence_val,
            commercial_hook=hook_val,
            recommended_channel=channel_str,
            reasoning=reasoning_val,
            detected_red_flags_json=red_flags_list,
            cnpj_data_json=cnpj_json,
            web_analysis_json=web_json,
            qualification_json=qual_json,
            created_at=lead.created_at or now,
            updated_at=now,
            contacted_at=lead.contacted_at,
        )
        session.add(lead_model)
    else:
        lead_model.status = status_str
        lead_model.notes = lead.notes or lead_model.notes
        if cnpj_str:
            lead_model.cnpj = cnpj_str
        if scan_session_id:
            lead_model.scan_session_id = scan_session_id
        if lead.qualification:
            lead_model.likelihood_no_pos = likelihood_str
            lead_model.confidence_score = confidence_val
            lead_model.commercial_hook = hook_val
            lead_model.recommended_channel = channel_str
            lead_model.reasoning = reasoning_val
            lead_model.detected_red_flags_json = red_flags_list
            lead_model.qualification_json = qual_json
        if lead.web_analysis:
            lead_model.web_analysis_json = web_json
        if lead.cnpj_data:
            lead_model.cnpj_data_json = cnpj_json
        lead_model.updated_at = now
        if lead.contacted_at:
            lead_model.contacted_at = lead.contacted_at

    await session.flush()
    if lead.cnpj_data:
        await _save_cnpj_cache_internal(lead.cnpj_data, session)

    stmt_reload = select(LeadModel).options(selectinload(LeadModel.business)).where(LeadModel.id == lead_model.id)
    reloaded = (await session.execute(stmt_reload)).scalar_one()
    return reloaded.to_pydantic()


async def get_lead_by_id(lead_id: str | UUID, session: AsyncSession | None = None) -> Lead | None:
    str_id = str(lead_id)
    async def _query(s: AsyncSession) -> Lead | None:
        stmt = select(LeadModel).options(selectinload(LeadModel.business)).where(LeadModel.id == str_id)
        model = (await s.execute(stmt)).scalar_one_or_none()
        return model.to_pydantic() if model else None

    if session is None:
        async with get_db_session() as s:
            return await _query(s)
    return await _query(session)


async def get_lead_by_place_id(place_id: str, session: AsyncSession | None = None) -> Lead | None:
    async def _query(s: AsyncSession) -> Lead | None:
        stmt = (
            select(LeadModel)
            .join(BusinessModel, LeadModel.business_id == BusinessModel.id)
            .options(selectinload(LeadModel.business))
            .where(BusinessModel.place_id == place_id)
        )
        model = (await s.execute(stmt)).scalar_one_or_none()
        return model.to_pydantic() if model else None

    if session is None:
        async with get_db_session() as s:
            return await _query(s)
    return await _query(session)


async def get_leads(
    status: LeadStatus | str | None = None,
    likelihood: LikelihoodLevel | str | None = None,
    session_id: str | None = None,
    search_query: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession | None = None,
) -> list[Lead]:
    async def _query(s: AsyncSession) -> list[Lead]:
        stmt = select(LeadModel).options(selectinload(LeadModel.business)).order_by(LeadModel.updated_at.desc())
        if status:
            stmt = stmt.where(LeadModel.status == _enum_str(status))
        if likelihood:
            stmt = stmt.where(LeadModel.likelihood_no_pos == _enum_str(likelihood))
        if session_id:
            stmt = stmt.where(LeadModel.scan_session_id == session_id)
        if search_query:
            term = f"%{search_query.strip()}%"
            stmt = stmt.join(LeadModel.business).where(
                or_(
                    BusinessModel.name.ilike(term),
                    BusinessModel.address.ilike(term),
                    LeadModel.commercial_hook.ilike(term),
                )
            )
        stmt = stmt.limit(limit).offset(offset)
        models = (await s.execute(stmt)).scalars().all()
        return [m.to_pydantic() for m in models]

    if session is None:
        async with get_db_session() as s:
            return await _query(s)
    return await _query(session)


list_leads = get_leads


async def update_lead_status(
    lead_id: str | UUID,
    status: LeadStatus | str,
    notes: str | None = None,
    session: AsyncSession | None = None,
) -> Lead | None:
    str_id = str(lead_id)
    status_str = _enum_str(status) or LeadStatus.NEW.value

    async def _update(s: AsyncSession) -> Lead | None:
        stmt = select(LeadModel).options(selectinload(LeadModel.business)).where(LeadModel.id == str_id)
        lead_model = (await s.execute(stmt)).scalar_one_or_none()
        if not lead_model:
            return None
        lead_model.status = status_str
        lead_model.updated_at = _current_utc()
        if notes is not None:
            lead_model.notes = notes
        if status_str == LeadStatus.CONTACTED.value and not lead_model.contacted_at:
            lead_model.contacted_at = _current_utc()
        await s.flush()
        return lead_model.to_pydantic()

    if session is None:
        async with get_db_session() as s:
            return await _update(s)
    return await _update(session)


async def count_leads(
    status: LeadStatus | str | None = None,
    likelihood: LikelihoodLevel | str | None = None,
    session: AsyncSession | None = None,
) -> int:
    async def _count(s: AsyncSession) -> int:
        stmt = select(func.count(LeadModel.id))
        if status:
            stmt = stmt.where(LeadModel.status == _enum_str(status))
        if likelihood:
            stmt = stmt.where(LeadModel.likelihood_no_pos == _enum_str(likelihood))
        return int((await s.execute(stmt)).scalar() or 0)

    if session is None:
        async with get_db_session() as s:
            return await _count(s)
    return await _count(session)


async def get_lead_stats(session: AsyncSession | None = None) -> dict[str, Any]:
    async def _stats(s: AsyncSession) -> dict[str, Any]:
        total_leads = await s.scalar(select(func.count(LeadModel.id))) or 0
        high_count = await s.scalar(select(func.count(LeadModel.id)).where(LeadModel.likelihood_no_pos == "HIGH")) or 0
        med_count = await s.scalar(select(func.count(LeadModel.id)).where(LeadModel.likelihood_no_pos == "MEDIUM")) or 0
        low_count = await s.scalar(select(func.count(LeadModel.id)).where(LeadModel.likelihood_no_pos == "LOW")) or 0
        with_cnpj = await s.scalar(select(func.count(LeadModel.id)).where(LeadModel.cnpj.isnot(None))) or 0
        total_sessions = await s.scalar(select(func.count(ScanSessionModel.id))) or 0

        return {
            "total_leads": total_leads,
            "high_priority": high_count,
            "medium_priority": med_count,
            "low_priority": low_count,
            "enriched_cnpj": with_cnpj,
            "total_scan_sessions": total_sessions,
        }

    if session is None:
        async with get_db_session() as s:
            return await _stats(s)
    return await _stats(session)


async def save_cnpj_cache(
    cnpj_data: CNPJData | dict[str, Any],
    session: AsyncSession | None = None,
    ttl_days: int = 60,
) -> CNPJCacheModel:
    c_data = CNPJData.model_validate(cnpj_data) if isinstance(cnpj_data, dict) else cnpj_data
    if session is None:
        async with get_db_session() as s:
            return await _save_cnpj_cache_internal(c_data, s, ttl_days=ttl_days)
    return await _save_cnpj_cache_internal(c_data, session, ttl_days=ttl_days)


async def _save_cnpj_cache_internal(
    c_data: CNPJData,
    session: AsyncSession,
    ttl_days: int = 60,
) -> CNPJCacheModel:
    clean_cnpj = re.sub(r"\D", "", c_data.cnpj)
    stmt = select(CNPJCacheModel).where(CNPJCacheModel.cnpj == clean_cnpj)
    entry = (await session.execute(stmt)).scalar_one_or_none()

    now = _current_utc()
    expires = now + timedelta(days=ttl_days)
    cnae_p_json = c_data.cnae_principal.model_dump(mode="json")
    cnaes_s_json = [item.model_dump(mode="json") for item in c_data.cnaes_secundarios]
    raw_payload = c_data.model_dump(mode="json")
    endereco_str = c_data.endereco if isinstance(c_data.endereco, str) else str(c_data.endereco)

    if entry is None:
        entry = CNPJCacheModel(
            cnpj=clean_cnpj,
            razao_social=c_data.razao_social,
            nome_fantasia=c_data.nome_fantasia,
            porte=_enum_str(c_data.porte),
            situacao_cadastral=c_data.situacao_cadastral,
            data_abertura=str(c_data.data_abertura) if c_data.data_abertura else None,
            capital_social=c_data.capital_social or 0.0,
            simples_nacional=c_data.simples_nacional,
            cnae_principal_codigo=c_data.cnae_principal.code,
            cnae_principal_descricao=c_data.cnae_principal.description,
            cnae_principal_json=cnae_p_json,
            cnaes_secundarios_json=cnaes_s_json,
            endereco_json=c_data.endereco if isinstance(c_data.endereco, dict) else {},
            endereco_completo=endereco_str,
            telefone=c_data.telefone,
            email=c_data.email,
            raw_data_json=raw_payload,
            cached_at=now,
            expires_at=expires,
        )
        session.add(entry)
    else:
        entry.razao_social = c_data.razao_social
        entry.nome_fantasia = c_data.nome_fantasia
        entry.porte = _enum_str(c_data.porte)
        entry.situacao_cadastral = c_data.situacao_cadastral
        entry.data_abertura = str(c_data.data_abertura) if c_data.data_abertura else None
        entry.capital_social = c_data.capital_social or 0.0
        entry.simples_nacional = c_data.simples_nacional
        entry.cnae_principal_codigo = c_data.cnae_principal.code
        entry.cnae_principal_descricao = c_data.cnae_principal.description
        entry.cnae_principal_json = cnae_p_json
        entry.cnaes_secundarios_json = cnaes_s_json
        entry.endereco_json = c_data.endereco if isinstance(c_data.endereco, dict) else {}
        entry.endereco_completo = endereco_str
        entry.telefone = c_data.telefone
        entry.email = c_data.email
        entry.raw_data_json = raw_payload
        entry.cached_at = now
        entry.expires_at = expires

    await session.flush()
    return entry


async def get_cached_cnpj(cnpj: str, session: AsyncSession | None = None) -> CNPJData | None:
    clean_cnpj = re.sub(r"\D", "", cnpj)
    if len(clean_cnpj) != 14:
        return None

    async def _query(s: AsyncSession) -> CNPJData | None:
        stmt = select(CNPJCacheModel).where(CNPJCacheModel.cnpj == clean_cnpj)
        entry = (await s.execute(stmt)).scalar_one_or_none()
        if not entry:
            return None

        now = _current_utc()
        exp = entry.expires_at.replace(tzinfo=None) if (entry.expires_at and entry.expires_at.tzinfo) else entry.expires_at
        if exp and exp < now:
            return None
        return entry.to_pydantic()

    if session is None:
        async with get_db_session() as s:
            return await _query(s)
    return await _query(session)


async def save_scan_session(
    scan_session: ScanSession | dict[str, Any],
    session: AsyncSession | None = None,
) -> ScanSession:
    s_data = ScanSession.model_validate(scan_session) if isinstance(scan_session, dict) else scan_session

    async def _save(s: AsyncSession) -> ScanSession:
        stmt = select(ScanSessionModel).where(ScanSessionModel.id == str(s_data.id))
        model = (await s.execute(stmt)).scalar_one_or_none()
        status_str = _enum_str(s_data.status) or ScanSessionStatus.RUNNING.value

        if model is None:
            model = ScanSessionModel(
                id=str(s_data.id),
                region_name=s_data.region_name,
                center_lat=s_data.center_lat,
                center_lng=s_data.center_lng,
                radius_km=s_data.radius_km,
                included_types_json=s_data.included_types,
                total_found=s_data.total_found,
                total_qualified=s_data.total_qualified,
                status=status_str,
                started_at=s_data.started_at,
                completed_at=s_data.completed_at,
            )
            s.add(model)
        else:
            model.region_name = s_data.region_name
            model.total_found = s_data.total_found
            model.total_qualified = s_data.total_qualified
            model.status = status_str
            model.completed_at = s_data.completed_at

        await s.flush()
        return model.to_pydantic()

    if session is None:
        async with get_db_session() as s:
            return await _save(s)
    return await _save(session)


async def get_scan_session(session_id: str | UUID, session: AsyncSession | None = None) -> ScanSession | None:
    str_id = str(session_id)
    async def _query(s: AsyncSession) -> ScanSession | None:
        stmt = select(ScanSessionModel).where(ScanSessionModel.id == str_id)
        model = (await s.execute(stmt)).scalar_one_or_none()
        return model.to_pydantic() if model else None

    if session is None:
        async with get_db_session() as s:
            return await _query(s)
    return await _query(session)


async def list_scan_sessions(limit: int = 20, offset: int = 0, session: AsyncSession | None = None) -> list[ScanSession]:
    async def _query(s: AsyncSession) -> list[ScanSession]:
        stmt = select(ScanSessionModel).order_by(ScanSessionModel.started_at.desc()).limit(limit).offset(offset)
        models = (await s.execute(stmt)).scalars().all()
        return [m.to_pydantic() for m in models]

    if session is None:
        async with get_db_session() as s:
            return await _query(s)
    return await _query(session)


async def add_contact_history(
    contact: ContactHistory | dict[str, Any],
    session: AsyncSession | None = None,
) -> ContactHistory:
    c_data = ContactHistory.model_validate(contact) if isinstance(contact, dict) else contact

    async def _insert(s: AsyncSession) -> ContactHistory:
        channel_str = _enum_str(c_data.channel) or ContactChannel.WHATSAPP.value
        model = ContactHistoryModel(
            id=str(c_data.id),
            lead_id=str(c_data.lead_id),
            channel=channel_str,
            message_sent=c_data.message_sent,
            response=c_data.response,
            created_at=c_data.created_at,
        )
        s.add(model)

        stmt_l = select(LeadModel).where(LeadModel.id == str(c_data.lead_id))
        lead_model = (await s.execute(stmt_l)).scalar_one_or_none()
        if lead_model:
            lead_model.contacted_at = c_data.created_at
            if lead_model.status in (LeadStatus.NEW.value, LeadStatus.QUALIFIED.value):
                lead_model.status = LeadStatus.CONTACTED.value
            lead_model.updated_at = _current_utc()

        await s.flush()
        return model.to_pydantic()

    if session is None:
        async with get_db_session() as s:
            return await _insert(s)
    return await _insert(session)


async def get_contact_history(lead_id: str | UUID, session: AsyncSession | None = None) -> list[ContactHistory]:
    str_id = str(lead_id)
    async def _query(s: AsyncSession) -> list[ContactHistory]:
        stmt = select(ContactHistoryModel).where(ContactHistoryModel.lead_id == str_id).order_by(ContactHistoryModel.created_at.desc())
        models = (await s.execute(stmt)).scalars().all()
        return [m.to_pydantic() for m in models]

    if session is None:
        async with get_db_session() as s:
            return await _query(s)
    return await _query(session)


async def export_leads_to_csv(
    output_path: str | Path,
    status: LeadStatus | str | None = None,
    likelihood: LikelihoodLevel | str | None = None,
    session: AsyncSession | None = None,
) -> int:
    leads = await get_leads(status=status, likelihood=likelihood, limit=10000, session=session)
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "lead_id", "nome_fantasia", "razao_social", "cnpj", "telefone", "endereco",
        "website", "segmento", "score_ia", "prioridade_sem_pos", "gancho_comercial_whatsapp",
        "canal_recomendado", "status_funil", "data_criacao",
    ]

    count = 0
    with open(out_file, mode="w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()

        for lead in leads:
            b, c, q = lead.business, lead.cnpj_data, lead.qualification
            row = {
                "lead_id": str(lead.id),
                "nome_fantasia": b.name if b else "",
                "razao_social": c.razao_social if c else "",
                "cnpj": c.cnpj if c else "",
                "telefone": b.phone if (b and b.phone) else "",
                "endereco": b.address if b else "",
                "website": b.website if (b and b.website) else "",
                "segmento": b.primary_type if b else "",
                "score_ia": f"{q.confidence_score * 100:.0f}%" if q else "N/A",
                "prioridade_sem_pos": q.likelihood_no_pos if q else "N/A",
                "gancho_comercial_whatsapp": q.commercial_hook if q else "",
                "canal_recomendado": q.recommended_channel if q else "WHATSAPP",
                "status_funil": lead.status,
                "data_criacao": lead.created_at.strftime("%Y-%m-%d %H:%M:%S") if lead.created_at else "",
            }
            writer.writerow(row)
            count += 1

    logger.info(f"Exportados {count} leads para {output_path}")
    return count
