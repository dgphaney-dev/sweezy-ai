"""Qualificador de Leads B2B local e deterministico de alta performance.

Sintetiza o perfil comercial descoberto (Google Places), dados fiscais
(Receita Federal/BrasilAPI) e metadados de presenca digital (WebScraper).

Gera como resultado uma qualificacao estruturada (LeadQualification) com custo ZERO
(R$ 0,00), determinando a probabilidade de o lead operar sem PDV/ERP moderno,
gancho comercial personalizado pronto para WhatsApp e canal de abordagem recomendado.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from analysis.pos_detector import (
    ContactChannel,
    HeuristicEvaluation,
    LikelihoodLevel,
    PixKeyType,
    POSDetector,
)

# ==============================================================================
# Modelos de Dados Pydantic v2
# ==============================================================================

try:
    from core.models import LeadQualification
except ImportError:
    class LeadQualification(BaseModel):
        """Qualificacao estruturada e gancho comercial gerado pelo motor de regras."""
        model_config = ConfigDict(from_attributes=True, use_enum_values=True)

        likelihood_no_pos: LikelihoodLevel = Field(
            ...,
            description="Probabilidade do comercio operar SEM um sistema POS/ERP moderno (HIGH, MEDIUM ou LOW)",
        )
        confidence_score: float = Field(
            ...,
            ge=0.0,
            le=1.0,
            description="Indice de confianca da estimativa (0.0 a 1.0)",
        )
        detected_red_flags: list[str] = Field(
            default_factory=list,
            description="Fatores desqualificadores ou concorrentes encontrados",
        )
        commercial_hook: str = Field(
            ...,
            min_length=10,
            description="Gancho de abordagem persuasivo e customizado para WhatsApp em pt-BR",
        )
        recommended_channel: ContactChannel | str = Field(
            default=ContactChannel.WHATSAPP,
            description="Canal prioritario para primeiro contato (WHATSAPP, PHONE, VISIT)",
        )
        reasoning: str = Field(
            ...,
            description="Raciocinio logico que fundamenta a classificacao",
        )

        @field_validator("recommended_channel", mode="before")
        @classmethod
        def normalize_channel(cls, v: Any) -> ContactChannel:
            """Normaliza variacoes de nomes de canais para o enum padrao."""
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


# ==============================================================================
# Classe do Qualificador Local (Zero Custo)
# ==============================================================================

class LLMQualifier:
    """Qualificador de leads deterministico de alto desempenho sem custos de API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        mock_mode: bool = True,
    ) -> None:
        """Inicializa o qualificador local.
        
        Opera com custo R$ 0,00 sem depender de servicos externos de LLM.
        """
        self.api_key = api_key or ""
        self.model = model or "rule-based-v1"
        self.mock_mode = True
        self.pos_detector = POSDetector()

    def _extract_partner_name(self, cnpj_info: dict[str, Any] | None) -> str | None:
        """Extrai o primeiro nome de um socio administrador se disponivel no QSA."""
        if not cnpj_info:
            return None
        qsa = cnpj_info.get("qsa") or cnpj_info.get("socios") or []
        if isinstance(qsa, list) and len(qsa) > 0:
            first = qsa[0]
            raw_name = ""
            if isinstance(first, dict):
                raw_name = first.get("nome_socio") or first.get("nome") or ""
            elif isinstance(first, str):
                raw_name = first
            if raw_name:
                parts = raw_name.strip().title().split()
                if parts:
                    return parts[0]
        return None

    def _generate_qualification(
        self,
        business_name: str,
        niche: str,
        evaluation: HeuristicEvaluation,
        has_phone: bool,
        cnpj_info: dict[str, Any] | None = None,
    ) -> LeadQualification:
        """Gera a qualificacao e pitch de abordagem utilizando regras heuristicas locais."""
        likelihood = evaluation.likelihood
        score = evaluation.heuristic_score

        # Determinar indice de confianca
        confidence = 0.75
        if evaluation.pain_points:
            confidence += 0.10
        if evaluation.competitors_found:
            confidence += 0.10
        if cnpj_info and cnpj_info.get("porte"):
            confidence += 0.05
        confidence = min(0.95, confidence)

        # Canal recomendado
        recommended_channel = ContactChannel.WHATSAPP if has_phone else ContactChannel.VISIT

        # Identificacao de socio
        partner_name = self._extract_partner_name(cnpj_info)
        greeting = f"Olá {partner_name}" if partner_name else "Olá"

        # Construcao dinamica do Gancho Comercial (Pitch) personalizado em pt-BR
        hook: str
        if evaluation.has_pdf_menu:
            hook = (
                f"{greeting}, tudo bem? Vi o cardápio do {business_name} e percebi que vocês utilizam "
                "cardápio em formato PDF ou imagem. Vocês sabiam que com um cardápio digital interativo "
                "vocês conseguem atualizar preços e itens esgotados em segundos no celular, "
                "sem custo de reimpressão, além de aumentar o ticket médio dos pedidos em até 20%? "
                "Posso te mandar uma demonstração rápida de 3 minutos de como ficaria o cardápio de vocês?"
            )
        elif evaluation.pain_points:
            hook = (
                f"{greeting}! Acompanho o trabalho do {business_name} na região. Reparei que os clientes "
                "elogiam muito os produtos de vocês, mas às vezes surgem comentários sobre fila no caixa "
                "ou demora no fechamento de contas. Temos uma solução de frente de caixa ultrarrápida "
                "que fecha comandas em segundos e elimina filas. "
                "Teria 5 minutos nesta semana para eu te apresentar como funciona?"
            )
        elif evaluation.has_whatsapp_order:
            hook = (
                f"{greeting}! Tudo bem? Vi que vocês recebem pedidos diretamente pelo WhatsApp do {business_name}. "
                "Sabemos que anotar pedidos manualmente no chat toma um tempo enorme e gera erros de comanda. "
                "Temos um sistema onde o cliente monta o pedido sozinho e vocês só clicam em aprovar "
                "para imprimir direto na produção. Faz sentido agendarmos uma apresentação rápida de 5 minutos?"
            )
        elif evaluation.pix_key_type in (PixKeyType.CPF, PixKeyType.EMAIL):
            hook = (
                f"{greeting}! Tudo bem? Identifiquei o perfil do {business_name} e vi que vocês trabalham com chave Pix "
                "pessoal. Sabia que hoje você pode ter um PDV com Pix integrado direto na tela ou maquininha, "
                "que dá baixa automática sem você precisar conferir comprovante na mão no celular do proprietário? "
                "Gostaria de ver como funciona em uma rápida demonstração?"
            )
        elif evaluation.competitors_found:
            comps = ", ".join(evaluation.competitors_found)
            hook = (
                f"{greeting}! Tudo bem? Vi que o {business_name} já utiliza soluções do mercado ({comps}). "
                "Estamos apresentando uma solução complementar com taxas mais acessíveis, integração fiscal direta "
                "e suporte local imediato. Vocês estariam abertos a conhecer novas condições para reduzir custos mensais?"
            )
        else:
            hook = (
                f"{greeting}! Tudo bem? Estive analisando o {business_name} e vejo um potencial excelente no "
                f"segmento de {niche}. Gostaria de entender como vocês controlam hoje o estoque e a frente de caixa "
                "do estabelecimento. Se tiver 5 minutos, adoraria compartilhar como comércios parecidos na sua região "
                "reduziram custos e agilizaram o atendimento com nosso sistema. Que tal conversarmos?"
            )

        # Raciocinio analitico objetivo
        reasons: list[str] = [
            f"Avaliação heurística concluiu score de {score}/100 ({likelihood.value if hasattr(likelihood, 'value') else likelihood}).",
        ]
        if evaluation.competitors_found:
            reasons.append(f"Concorrentes identificados: {', '.join(evaluation.competitors_found)}.")
        if evaluation.positive_signals:
            reasons.append(f"Sinais de operação manual: {'; '.join(evaluation.positive_signals[:3])}.")
        if evaluation.pain_points:
            reasons.append(f"Dores identificadas em reviews: {len(evaluation.pain_points)} menção(ões).")
        if partner_name:
            reasons.append(f"Sócio administrador mapeado no QSA: {partner_name}.")

        return LeadQualification(
            likelihood_no_pos=likelihood,
            confidence_score=confidence,
            detected_red_flags=evaluation.red_flags,
            commercial_hook=hook,
            recommended_channel=recommended_channel,
            reasoning=" | ".join(reasons),
        )

    async def qualify(
        self,
        business_name: str,
        niche: str,
        heuristic_evaluation: HeuristicEvaluation | None = None,
        scraping_data: dict[str, Any] | None = None,
        cnpj_info: dict[str, Any] | None = None,
        reviews_summary: list[str] | None = None,
        phone: str | None = None,
        website_url: str | None = None,
    ) -> LeadQualification:
        """Sintetiza os dados do lead e produz a qualificacao estruturada com custo R$ 0,00."""
        eval_result = heuristic_evaluation
        if eval_result is None:
            raw_html = scraping_data.get("raw_html", "") if scraping_data else ""
            wa_urls = scraping_data.get("whatsapp_urls", []) if scraping_data else []
            rev_dicts = [{"text": r} for r in (reviews_summary or [])]
            eval_result = self.pos_detector.evaluate(
                name=business_name,
                website_url=website_url,
                html_content=raw_html,
                whatsapp_urls=wa_urls,
                reviews=rev_dicts,
                cnpj_data=cnpj_info,
            )

        return self._generate_qualification(
            business_name=business_name,
            niche=niche,
            evaluation=eval_result,
            has_phone=bool(phone),
            cnpj_info=cnpj_info,
        )


# Alias para clareza conceitual
LeadQualifier = LLMQualifier
