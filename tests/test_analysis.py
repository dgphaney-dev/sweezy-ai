"""Testes unitários e de integração para o módulo analysis do ProspectAI."""

import pytest
from analysis import (
    COMPETITOR_PLATFORMS,
    CompetitorCategory,
    CompetitorPlatform,
    ContactChannel,
    HeuristicEvaluation,
    LeadQualification,
    LikelihoodLevel,
    LLMQualifier,
    PixKeyType,
    POSDetector,
    ReviewAnalyzer,
    ScrapingResult,
    WebScraper,
    validate_cnpj,
    validate_cpf,
)


# ==============================================================================
# 1. Testes do Catálogo de Concorrentes (50+ Plataformas Brasileiras)
# ==============================================================================

def test_competitor_catalog_size_and_diversity():
    """Valida se o catálogo possui pelo menos 50 plataformas brasileiras e múltiplas categorias."""
    assert len(COMPETITOR_PLATFORMS) >= 50, "O catálogo deve conter ao menos 50 plataformas"

    # Verificar se as principais categorias do mercado brasileiro estão presentes
    categories = {p.category for p in COMPETITOR_PLATFORMS}
    assert CompetitorCategory.ERP_PDV in categories
    assert CompetitorCategory.FOOD_DELIVERY in categories
    assert CompetitorCategory.AGENDAMENTO in categories
    assert CompetitorCategory.ECOMMERCE in categories
    assert CompetitorCategory.SMART_POS in categories

    # Verificar líderes de mercado listados na especificação
    names = {p.name for p in COMPETITOR_PLATFORMS}
    expected_leaders = [
        "Linx", "Totvs", "Bling!", "Omie", "Tiny ERP", "Anota AI",
        "Goomer", "Saipos", "Trinks", "Avec (BelezaSoft)", "Nuvemshop", "Shopify"
    ]
    for leader in expected_leaders:
        assert leader in names, f"Plataforma líder '{leader}' deve estar no catálogo"


# ==============================================================================
# 2. Testes de Detecção de Plataformas e Concorrentes no DOM
# ==============================================================================

def test_detect_competitors_in_html_and_url():
    """Testa a identificação precisa de softwares consolidados no HTML ou domínio."""
    detector = POSDetector()

    # Match de Linx e Totvs via scripts e links
    html_sample = """
        <html>
            <head>
                <script src="https://cdn.linxcommerce.com.br/checkout.js"></script>
            </head>
            <body>
                <a href="https://totvs.com.br/cliente">Portal Totvs</a>
            </body>
        </html>
    """
    detected = detector.detect_competitors(html_sample, "https://lojaexemplo.com.br")
    detected_names = [p.name for p in detected]
    assert "Linx" in detected_names
    assert "Totvs" in detected_names

    # Match de plataforma de delivery (Anota AI e Goomer)
    html_food = """
        <div>
            <a href="https://pedido.anota.ai/loja/hamburgueria">Peça pelo Anota AI</a>
            <a href="https://cardapio.goomer.com.br/restaurante">Ver no Goomer</a>
        </div>
    """
    detected_food = detector.detect_competitors(html_food, None)
    food_names = [p.name for p in detected_food]
    assert "Anota AI" in food_names
    assert "Goomer" in food_names


# ==============================================================================
# 3. Testes de Detecção de Chave Pix (CPF vs CNPJ vs E-mail vs Telefone)
# ==============================================================================

def test_detect_pix_key_types():
    """Testa a identificação e validação de diferentes tipos de chave Pix."""
    detector = POSDetector()

    # CPF válido
    cpf_text = "Pague com Pix. Nossa chave CPF: 111.444.777-35 (titular João da Silva)"
    pix_type, key = detector.detect_pix_key(cpf_text)
    assert pix_type == PixKeyType.CPF
    assert key == "111.444.777-35"

    # CNPJ válido (Google Brasil)
    cnpj_text = "Chave Pix CNPJ: 06.990.590/0001-23"
    pix_type_cnpj, key_cnpj = detector.detect_pix_key(cnpj_text)
    assert pix_type_cnpj == PixKeyType.CNPJ
    assert key_cnpj == "06.990.590/0001-23"

    # E-mail pessoal (Gmail)
    email_text = "Aceitamos Pix: contato.joao@gmail.com"
    pix_type_email, key_email = detector.detect_pix_key(email_text)
    assert pix_type_email == PixKeyType.EMAIL
    assert key_email == "contato.joao@gmail.com"

    # Telefone celular como chave Pix
    phone_text = "Faça seu Pix no telefone: 11987654321"
    pix_type_phone, _ = detector.detect_pix_key(phone_text)
    assert pix_type_phone == PixKeyType.TELEFONE

    # Ausência de Pix
    no_pix_text = "Aceitamos apenas cartões de crédito e débito no balcão."
    pix_type_none, _ = detector.detect_pix_key(no_pix_text)
    assert pix_type_none == PixKeyType.NONE


# ==============================================================================
# 4. Testes de Análise Semântica de Avaliações (ReviewAnalyzer)
# ==============================================================================

def test_review_analyzer_friction_and_modernity():
    """Testa a detecção de termos de atrito operacional (papel, fila) e modernidade."""
    analyzer = ReviewAnalyzer()

    # Comentários com evidências de processos manuais e fila
    manual_reviews = [
        {"text": "Comida boa, mas o garçom anotou no papel e perderam o pedido."},
        {"text": "Fila enorme no caixa para pagar e não tinham troco."},
        {"text": "Ambiente agradável, mas muita demora para trazer a conta."},
    ]
    res_manual = analyzer.analyze(manual_reviews)
    assert res_manual["score_delta"] > 0
    assert len(res_manual["positive_evidences"]) >= 2
    assert len(res_manual["negative_evidences"]) == 0

    # Comentários com indícios de sistemas modernos
    modern_reviews = [
        {"text": "Adorei o cardápio digital no tablet na mesa e o totem de autoatendimento."},
        {"text": "Sistema muito rápido, pedi pelo ifood e retirei sem fila."},
    ]
    res_modern = analyzer.analyze(modern_reviews)
    assert res_modern["score_delta"] < 0
    assert len(res_modern["negative_evidences"]) >= 2


# ==============================================================================
# 5. Testes do Algoritmo de Pontuação Heurística (0 a 100)
# ==============================================================================

def test_heuristic_evaluation_scoring_high_likelihood():
    """Valida um lead com processos analógicos obtendo HIGH likelihood e score >= 70."""
    detector = POSDetector()

    html_content = """
        <html>
            <body>
                <h1>Restaurante Sabor Caseiro</h1>
                <p>Veja nosso cardápio completo:</p>
                <a href="https://drive.google.com/file/d/12345/view">Cardápio em PDF no Drive</a>
                <p>Chave Pix: 111.444.777-35</p>
                <a href="https://wa.me/5511999998888">Peça pelo WhatsApp</a>
            </body>
        </html>
    """
    reviews = [
        {"text": "Anotaram no papel e demorou uma eternidade, comanda de papel arcaica."}
    ]

    eval_result = detector.evaluate(
        name="Restaurante Sabor Caseiro",
        website_url="https://saborcaseiro.wixsite.com/home",
        html_content=html_content,
        whatsapp_urls=["https://wa.me/5511999998888"],
        reviews=reviews,
        cnpj_data={"porte": "MEI", "data_abertura": "2023-01-01"},
    )

    assert eval_result.heuristic_score >= 70
    assert eval_result.likelihood == LikelihoodLevel.HIGH
    assert eval_result.has_pdf_menu is True
    assert eval_result.has_whatsapp_order is True
    assert len(eval_result.positive_signals) >= 3
    assert len(eval_result.pain_points) > 0


def test_heuristic_evaluation_scoring_low_likelihood():
    """Valida um lead informatizado com Linx/Shopify recebendo LOW likelihood e score < 40."""
    detector = POSDetector()

    html_content = """
        <html>
            <head><script src="https://cdn.shopify.com/s/files/script.js"></script></head>
            <body>
                <h1>Boutique Elegance</h1>
                <a href="https://linx.com.br">Parceiro Linx</a>
                <button>Adicionar ao Carrinho</button>
            </body>
        </html>
    """
    reviews = [
        {"text": "Loja excelente, sistema muito rápido e aplicativo próprio ótimo."}
    ]

    eval_result = detector.evaluate(
        name="Boutique Elegance",
        website_url="https://boutiqueelegance.com.br",
        html_content=html_content,
        whatsapp_urls=["https://wa.me/5511999997777?text=pedido_token_1234"],
        reviews=reviews,
    )

    assert eval_result.heuristic_score < 40
    assert eval_result.likelihood == LikelihoodLevel.LOW
    assert len(eval_result.red_flags) > 0
    assert "Shopify" in eval_result.competitors_found or "Linx" in eval_result.competitors_found


# ==============================================================================
# 6. Testes do WebScraper (Parsing, CNPJ, Links Sociais e PDF)
# ==============================================================================

@pytest.mark.asyncio
async def test_web_scraper_html_extraction():
    """Testa extração de elementos sem necessidade de requisição HTTP externa."""
    scraper = WebScraper()

    html_mock = """
        <!DOCTYPE html>
        <html>
            <head><title>Pizzaria Bella Massa</title></head>
            <body>
                <h1>Bem-vindo à Bella Massa</h1>
                <a href="https://instagram.com/pizzariabellamassa">Siga no Instagram</a>
                <a href="https://facebook.com/pizzariabellamassa">Curta no Facebook</a>
                <a href="/downloads/cardapio_pizzas.pdf">Baixar Cardápio PDF</a>
                <a href="https://wa.me/5511988887777?text=Quero%20uma%20pizza">Pedir pelo WhatsApp</a>
                <button>Peça Online</button>

                <footer>
                    <p>Bella Massa Pizzaria Ltda</p>
                    <p>CNPJ: 06.990.590/0001-23 - Todos os direitos reservados</p>
                </footer>
            </body>
        </html>
    """

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_mock, "html.parser")
    base_url = "https://bellamassa.com.br"

    # CNPJ extraído do footer
    cnpj = scraper.extract_cnpj(soup, soup.get_text())
    assert cnpj == "06990590000123"

    # Links sociais
    socials = scraper.extract_social_links(soup, base_url)
    assert socials["instagram"] == "https://instagram.com/pizzariabellamassa"
    assert socials["facebook"] == "https://facebook.com/pizzariabellamassa"

    # WhatsApp e PDF menus
    wa_links = scraper.extract_whatsapp_links(soup, html_mock, base_url)
    assert len(wa_links) > 0
    assert "wa.me" in wa_links[0]

    pdf_menus = scraper.extract_pdf_menus(soup, base_url)
    assert len(pdf_menus) > 0
    assert "cardapio_pizzas.pdf" in pdf_menus[0]

    buttons = scraper.extract_ordering_buttons(soup)
    assert any("Peça Online" in b for b in buttons)

    # Conversão para WebAnalysis de core.models
    scraping_res = ScrapingResult(
        url=base_url,
        has_website=True,
        cnpj_from_site=cnpj,
        social_links=socials,
        whatsapp_urls=wa_links,
        has_whatsapp_order=True,
        has_pdf_menu=True,
        pdf_menu_urls=pdf_menus,
        has_online_cart=False,
        ordering_buttons=buttons,
        raw_signals=["TEST_SIGNAL"],
    )
    web_analysis = scraping_res.to_web_analysis()
    assert getattr(web_analysis, "has_website", False) is True
    assert getattr(web_analysis, "cnpj_from_site", None) == "06990590000123"
    assert getattr(web_analysis, "has_pdf_menu", False) is True


# ==============================================================================
# 7. Testes do LLMQualifier (Modo Heurístico Fallback)
# ==============================================================================

@pytest.mark.asyncio
async def test_llm_qualifier_mock_fallback():
    """Testa a geração estruturada de LeadQualification em modo fallback heurístico."""
    qualifier = LLMQualifier(mock_mode=True)

    # Lead simulado de Restaurante com Cardápio PDF e dor no caixa
    detector = POSDetector()
    eval_result = detector.evaluate(
        name="Churrascaria Gaúcha",
        website_url="https://gauchachurrasco.canva.site",
        html_content="<a href='cardapio.pdf'>Cardápio em PDF</a>",
        whatsapp_urls=["https://wa.me/5511999991111"],
        reviews=[{"text": "A carne é espetacular, mas anotou no papel e houve fila enorme no caixa."}],
        cnpj_data={"porte": "ME"},
    )

    qualification = await qualifier.qualify(
        business_name="Churrascaria Gaúcha",
        niche="Restaurante / Churrascaria",
        heuristic_evaluation=eval_result,
        phone="11999991111",
        website_url="https://gauchachurrasco.canva.site",
    )

    assert isinstance(qualification, LeadQualification)
    assert qualification.likelihood_no_pos == LikelihoodLevel.HIGH
    assert 0.0 <= qualification.confidence_score <= 1.0
    assert qualification.recommended_channel == ContactChannel.WHATSAPP
    assert "Churrascaria Gaúcha" in qualification.commercial_hook
    assert len(qualification.commercial_hook) >= 30
    assert "cardápio" in qualification.commercial_hook.lower() or "caixa" in qualification.commercial_hook.lower()
    assert len(qualification.reasoning) > 0
