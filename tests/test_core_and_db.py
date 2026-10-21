"""Testes automatizados dos modelos centrais e banco de dados assíncrono do ProspectAI."""

import asyncio
import os
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from core.models import (
    Business,
    BusinessType,
    CNAEItem,
    CNPJData,
    CompanyPorte,
    ContactChannel,
    ContactHistory,
    Lead,
    LeadQualification,
    LeadStatus,
    LikelihoodLevel,
    PixKeyType,
    ScanSession,
    ScanSessionStatus,
    WebAnalysis,
)
from core.database import (
    add_contact_history,
    get_cached_cnpj,
    get_contact_history,
    get_db_session,
    get_engine,
    get_lead_by_id,
    get_leads,
    get_scan_session,
    init_db,
    list_scan_sessions,
    save_cnpj_cache,
    save_lead,
    save_scan_session,
    update_lead_status,
)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_full_database_lifecycle():
    """Testa todo o ciclo de vida do banco SQLite assíncrono com modo WAL."""
    test_db = f"test_prospect_{uuid4().hex[:8]}.db"
    test_url = f"sqlite+aiosqlite:///{test_db}"

    engine = get_engine(test_url)
    try:
        # 1. Inicializa o banco de dados
        await init_db(engine)

        # 2. Testa ScanSession
        session = ScanSession(
            region_name="Vila Madalena, São Paulo - SP",
            center_lat=-23.5505,
            center_lng=-46.6833,
            radius_km=2.5,
            included_types=[BusinessType.RESTAURANTE.value, BusinessType.PADARIA.value],
            status=ScanSessionStatus.RUNNING,
        )
        saved_session = await save_scan_session(session)
        assert saved_session.id == session.id
        assert saved_session.region_name == "Vila Madalena, São Paulo - SP"

        retrieved_session = await get_scan_session(session.id)
        assert retrieved_session is not None
        assert retrieved_session.radius_km == 2.5

        sessions_list = await list_scan_sessions()
        assert len(sessions_list) >= 1

        # 3. Testa Criação e Validação de Lead completo
        business = Business(
            place_id="ChIJ_test_place_001",
            name="Padaria & Confeitaria Bela Vista",
            address="Rua Harmonia, 123 - Vila Madalena, São Paulo - SP",
            phone="(11) 99887-7665",
            website="http://www.padariabelavista.com.br",
            lat=-23.5510,
            lng=-46.6840,
            rating=4.6,
            review_count=120,
            primary_type="bakery",
        )
        assert business.phone == "11998877665"

        cnae_p = CNAEItem(codigo=1091102, descricao="Fabricação de produtos de padaria e confeitaria")
        cnae_s = CNAEItem(codigo=4721102, descricao="Padaria e confeitaria com predominância de revenda")
        cnpj_data = CNPJData(
            cnpj="12.345.678/0001-95",
            razao_social="Bela Vista Panificadora Ltda",
            nome_fantasia="Padaria Bela Vista",
            porte=CompanyPorte.ME,
            cnae_principal=cnae_p,
            cnaes_secundarios=[cnae_s],
            endereco={"logradouro": "Rua Harmonia", "numero": "123", "bairro": "Vila Madalena"},
            telefone="1138123456",
        )
        assert cnpj_data.cnpj == "12345678000195"

        web_analysis = WebAnalysis(
            url="http://www.padariabelavista.com.br",
            has_website=True,
            has_whatsapp_order=True,
            has_pdf_menu=True,
            has_online_cart=False,
            detected_pos_systems=[],
            pix_key_type=PixKeyType.CNPJ,
            raw_signals=["wa.me link", "cardapio.pdf"],
        )

        qualification = LeadQualification(
            likelihood_no_pos=LikelihoodLevel.HIGH,
            confidence_score=0.92,
            detected_red_flags=["usa_whatsapp_sem_catalogo"],
            commercial_hook="Automatize o fechamento de caixa e os pedidos de balcão da Padaria Bela Vista",
            recommended_channel="whatsapp",
            reasoning="A padaria recebe pedidos via WhatsApp com cardápio em PDF sem sistema de PDV integrado.",
        )
        assert qualification.recommended_channel == ContactChannel.WHATSAPP

        lead = Lead(
            business=business,
            cnpj_data=cnpj_data,
            web_analysis=web_analysis,
            qualification=qualification,
            status=LeadStatus.QUALIFIED,
        )

        saved_lead = await save_lead(lead)
        assert saved_lead.id == lead.id
        assert saved_lead.business.name == "Padaria & Confeitaria Bela Vista"
        assert saved_lead.cnpj_data is not None
        assert saved_lead.cnpj_data.cnpj == "12345678000195"
        assert saved_lead.qualification is not None
        assert saved_lead.qualification.likelihood_no_pos == LikelihoodLevel.HIGH

        # 4. Busca do lead por ID
        fetched_lead = await get_lead_by_id(lead.id)
        assert fetched_lead is not None
        assert fetched_lead.business.place_id == "ChIJ_test_place_001"
        assert fetched_lead.web_analysis is not None
        assert fetched_lead.web_analysis.has_pdf_menu is True

        # 5. Listagem com filtros
        leads_high = await get_leads(likelihood=LikelihoodLevel.HIGH)
        assert len(leads_high) >= 1
        assert any(l.id == lead.id for l in leads_high)

        leads_search = await get_leads(search_query="Bela Vista")
        assert len(leads_search) >= 1

        # 6. Atualização de status
        updated = await update_lead_status(lead.id, LeadStatus.NEGOTIATING, notes="Cliente demonstrou interesse.")
        assert updated is not None
        assert updated.status == LeadStatus.NEGOTIATING
        assert updated.notes == "Cliente demonstrou interesse."

        # 7. Verificação do cache de CNPJ com TTL
        cached_cnpj = await get_cached_cnpj("12.345.678/0001-95")
        assert cached_cnpj is not None
        assert cached_cnpj.razao_social == "Bela Vista Panificadora Ltda"

        # 8. Histórico de contato e atualização automática para CONTACTED
        contact = ContactHistory(
            lead_id=lead.id,
            channel=ContactChannel.WHATSAPP,
            message_sent="Olá, gostaríamos de apresentar uma solução para automatizar os pedidos da padaria.",
        )
        saved_contact = await add_contact_history(contact)
        assert saved_contact.id == contact.id

        history = await get_contact_history(lead.id)
        assert len(history) == 1
        assert history[0].channel == ContactChannel.WHATSAPP

        lead_after_contact = await get_lead_by_id(lead.id)
        assert lead_after_contact is not None
        assert lead_after_contact.contacted_at is not None

    finally:
        await engine.dispose()
        for f in [test_db, f"{test_db}-shm", f"{test_db}-wal"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
