"""Qualificador cognitivo de Leads B2B utilizando OpenAI (GPT-4o-mini).

Este módulo sintetiza o perfil comercial descoberto (Google Places), dados fiscais
(Receita Federal/BrasilAPI), metadados de presença digital (WebScraper) e evidências
de avaliações do Google (ReviewAnalyzer).

Gera como resultado uma qualificação estruturada (`LeadQualification`), determinando a
probabilidade de o lead operar sem PDV/ERP moderno, gancho comercial personalizado para
disparo no WhatsApp e canal de abordagem recomendado. Possui modo fallback heurístico
caso a chave de API não esteja configurada ou ocorra falha de rede.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator
from rich.console import Console

from analysis.pos_detector import (
    ContactChannel,
    HeuristicEvaluation,
    LikelihoodLevel,
    PixKeyType,
    POSDetector,
)

# Carrega variáveis do arquivo .env se presente
load_dotenv()

console = Console()


# ==============================================================================
# Modelos de Dados Pydantic v2
# ==============================================================================

try:
    from core.models import LeadQualification
except ImportError:
    class LeadQualification(BaseModel):
        """Qualificação cognitiva e gancho comercial estruturado gerado pela IA."""
        model_config = ConfigDict(from_attributes=True, use_enum_values=True)

        likelihood_no_pos: LikelihoodLevel = Field(
            ...,
            description="Probabilidade do comércio operar SEM um sistema POS/ERP moderno (HIGH, MEDIUM ou LOW)",
        )
        confidence_score: float = Field(
            ...,
            ge=0.0,
            le=1.0,
            description="Índice de confiança da IA na estimativa (0.0 a 1.0)",
        )
        detected_red_flags: list[str] = Field(
            default_factory=list,
            description="Fatores desqualificadores ou concorrentes encontrados",
        )
        commercial_hook: str = Field(
            ...,
            min_length=10,
            description="Gancho de abordagem persuasivo, consultivo e customizado para WhatsApp em pt-BR",
        )
        recommended_channel: ContactChannel | str = Field(
            default=ContactChannel.WHATSAPP,
            description="Canal prioritário para primeiro contato (WHATSAPP, PHONE, VISIT)",
        )
        reasoning: str = Field(
            ...,
            description="Raciocínio lógico e objetivo que fundamenta a classificação",
        )

        @field_validator("recommended_channel", mode="before")
        @classmethod
        def normalize_channel(cls, v: Any) -> ContactChannel:
            """Normaliza variações de nomes de canais em português para o enum padrão."""
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
# Prompts do Sistema e Especialista em Vendas B2B
# ==============================================================================

SYSTEM_PROMPT = """Você é o consultor sênior líder em prospecção e vendas B2B de automação comercial do ProspectAI no Brasil.
Seu objetivo é analisar estabelecimentos comerciais (restaurantes, bares, padarias, salões, lojas de roupa, pet shops, oficinas)
e qualificar o nível de carência de um sistema moderno de Ponto de Venda (PDV/Frente de Caixa), Cardápio Digital ou ERP.

Critérios operacionais de avaliação:
- ALTA PROBABILIDADE (HIGH):
  * Cardápio ou catálogo apenas em PDF estático ou Google Drive/Canva.
  * Pedidos feitos de forma manual diretamente no chat do WhatsApp sem carrinho.
  * Chave Pix divulgada é CPF ou e-mail pessoal (gestão financeira informal).
  * Clientes reclamando em reviews de 'anotou no papel', 'comanda de papel', 'perderam meu pedido', 'fila no caixa' ou 'demora para fechar a conta'.
  * Agendamento de serviços apenas por mensagem direta (DM/WhatsApp).
- BAIXA PROBABILIDADE (LOW):
  * Já utiliza plataformas consagradas (ex: Linx, Totvs, Bling, Omie, Anota AI, Goomer, Saipos, Trinks, Shopify, Nuvemshop).
  * Possui e-commerce completo ou cardápio interativo com totem na loja.
- MÉDIA PROBABILIDADE (MEDIUM):
  * Sinais mistos ou poucos dados digitais disponíveis.

Regras do commercial_hook:
1. Deve ser escrito em português do Brasil informal e profissional, pronto para ser enviado via WhatsApp.
2. Deve citar pelo menos um detalhe real e específico do estabelecimento (nome, nicho ou dor encontrada).
3. Seja empático e focado em lucro, agilidade ou redução de erros operacionais.
4. Finalize sempre com uma pergunta aberta simples, convidando para uma demonstração rápida de 5 minutos."""


# ==============================================================================
# Classe do Qualificador Cognitivo
# ==============================================================================

class LLMQualifier:
    """Qualificador de leads com inteligência artificial GPT-4o-mini e fallback heurístico."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        mock_mode: bool = False,
    ) -> None:
        """Inicializa o qualificador.

        Args:
            api_key: Chave de API da OpenAI (padrão obtido via settings ou env OPENAI_API_KEY).
            model: Nome do modelo OpenAI (padrão: gpt-4o-mini).
            mock_mode: Se True, opera em modo simulado sem efetuar chamadas à API da OpenAI.
        """
        # Tenta obter configurações do módulo config.settings se existir
        config_key = None
        config_model = None
        try:
            from config.settings import settings  # type: ignore
            config_key = getattr(settings, "OPENAI_API_KEY", None)
            config_model = getattr(settings, "OPENAI_MODEL", None)
        except ImportError:
            pass

        self.api_key = api_key or config_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or config_model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.mock_mode = mock_mode or self._is_mock_key(self.api_key)
        self.pos_detector = POSDetector()

    @staticmethod
    def _is_mock_key(key: str | None) -> bool:
        """Verifica se a chave informada é nula, mock ou placeholder de exemplo."""
        if not key or not key.strip():
            return True
        cleaned = key.strip().lower()
        if any(token in cleaned for token in ("mock", "test", "placeholder", "fake", "exemplo")):
            return True
        if cleaned.startswith("your_openai_api_key") or cleaned in ("none", "null", "false"):
            return True
        if not cleaned.startswith("sk-"):
            return True
        return False

    def _generate_heuristic_fallback(
        self,
        business_name: str,
        niche: str,
        evaluation: HeuristicEvaluation,
        has_phone: bool,
    ) -> LeadQualification:
        """Gera a qualificação e pitch de abordagem utilizando regras heurísticas locais."""
        likelihood = evaluation.likelihood
        score = evaluation.heuristic_score

        # Determinar índice de confiança
        confidence = 0.70
        if evaluation.pain_points:
            confidence += 0.15
        if evaluation.competitors_found:
            confidence += 0.15
        confidence = min(0.95, confidence)

        # Canal recomendado
        recommended_channel = ContactChannel.WHATSAPP if has_phone else ContactChannel.VISIT

        # Construção dinâmica do Gancho Comercial (Pitch) personalizado em pt-BR
        hook: str
        if evaluation.has_pdf_menu:
            hook = (
                f"Olá, tudo bem? Vi o cardápio do {business_name} e percebi que vocês utilizam "
                "cardápio em formato PDF/imagem. Vocês sabiam que com um cardápio digital interativo "
                "vocês conseguem atualizar preços e itens esgotados em 1 segundo no celular, "
                "sem precisar de designer, além de aumentar o ticket médio dos pedidos em até 22%? "
                "Posso te mandar uma demonstração rápida de 3 minutos de como ficaria o cardápio de vocês?"
            )
        elif evaluation.pain_points:
            primeira_dor = evaluation.pain_points[0]
            hook = (
                f"Olá! Acompanho o sucesso do {business_name} na região. Reparei que alguns clientes "
                "elogiam muito o atendimento de vocês, mas às vezes comentam sobre o tempo de espera no caixa "
                "ou fechamento de contas. Desenvolvemos uma solução simples de frente de caixa que agiliza a cobrança "
                "e fecha comandas em segundos, eliminando filas. "
                "Teria 5 minutos nesta semana para eu te apresentar como funciona?"
            )
        elif evaluation.has_whatsapp_order:
            hook = (
                f"Olá! Tudo bem? Vi que vocês recebem pedidos diretamente pelo WhatsApp do {business_name}. "
                "Sabemos que anotar pedidos manualmente no chat toma um tempo enorme do atendente e gera "
                "erros de cálculo e entregas trocadas. Temos um sistema onde o cliente monta o pedido sozinho "
                "e você só clica em aprovar para imprimir a comanda direto na cozinha. "
                "Faz sentido agendarmos uma apresentação rápida de 5 minutos?"
            )
        elif evaluation.pix_key_type in (PixKeyType.CPF, PixKeyType.EMAIL):
            hook = (
                f"Olá! Tudo bem? Identifiquei o perfil do {business_name} e vi que vocês trabalham com chave Pix "
                "individual. Sabia que hoje você pode ter um PDV com Pix integrado direto na tela ou maquininha, "
                "que dá baixa automática sem você precisar conferir comprovante na mão no celular do dono? "
                "Gostaria de ver como funciona em uma rápida demonstração?"
            )
        elif evaluation.competitors_found:
            comps = ", ".join(evaluation.competitors_found)
            hook = (
                f"Olá! Tudo bem? Vi que o {business_name} já utiliza ferramentas como {comps}. "
                "Estamos apresentando uma solução complementar com taxas mais acessíveis e suporte local 24h. "
                "Vocês estariam abertos a conhecer novas condições comerciais para reduzir seus custos mensais?"
            )
        else:
            hook = (
                f"Olá! Tudo bem? Estive analisando o {business_name} no Google e vejo um potencial excelente no "
                f"segmento de {niche}. Gostaria de entender como vocês controlam hoje o estoque e a frente de caixa "
                "do estabelecimento. Se tiver 5 minutos, adoraria compartilhar como estabelecimentos parecidos na "
                "sua região reduziram custos e agilizaram o atendimento com nosso sistema. Que tal conversarmos?"
            )

        # Raciocínio heurístico detalhado
        reasons: list[str] = [
            f"Avaliação heurística concluiu score de {score}/100.",
        ]
        if evaluation.competitors_found:
            reasons.append(f"Concorrentes mapeados: {', '.join(evaluation.competitors_found)}.")
        if evaluation.positive_signals:
            reasons.append(f"Sinais de processos manuais: {'; '.join(evaluation.positive_signals[:3])}.")
        if evaluation.pain_points:
            reasons.append(f"Dores identificadas em reviews: {len(evaluation.pain_points)} ocorrência(s).")

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
        """Sintetiza todos os dados de um lead e produz a qualificação cognitiva estruturada.

        Args:
            business_name: Nome do comércio.
            niche: Segmento comercial (ex: Restaurante, Padaria, Barbearia, Varejo).
            heuristic_evaluation: Resultado prévio da avaliação do POSDetector.
            scraping_data: Metadados retornados pelo WebScraper.
            cnpj_info: Dados enriquecidos da Receita Federal.
            reviews_summary: Lista de trechos ou resumos de avaliações do Google.
            phone: Telefone de contato do estabelecimento.
            website_url: URL do website oficial.

        Returns:
            LeadQualification com probabilidade, confiança, pitch e canal.
        """
        # Se não foi fornecida avaliação heurística prévia, calcula agora
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

        # Fallback imediato se estiver em mock mode ou sem chave da OpenAI
        if self.mock_mode or not self.api_key:
            return self._generate_heuristic_fallback(
                business_name=business_name,
                niche=niche,
                evaluation=eval_result,
                has_phone=bool(phone),
            )

        likelihood_str = getattr(eval_result.likelihood, "value", str(eval_result.likelihood))
        pix_str = getattr(eval_result.pix_key_type, "value", str(eval_result.pix_key_type))

        # Montagem do prompt para GPT-4o-mini
        user_prompt = f"""
INFORMAÇÕES DO ESTABELECIMENTO:
- Nome Comercial: {business_name}
- Nicho / Segmento: {niche}
- Telefone / WhatsApp: {phone or 'Não informado'}
- Website: {website_url or 'Nenhum'}

PONTUAÇÃO HEURÍSTICA & EVIDÊNCIAS:
- Score Heurístico: {eval_result.heuristic_score}/100 ({likelihood_str})
- Presença de Cardápio em PDF / Nuvem: {eval_result.has_pdf_menu}
- Pedido via WhatsApp Cru: {eval_result.has_whatsapp_order}
- Presença de Carrinho de Compras: {eval_result.has_online_cart}
- Chave Pix Detectada: {pix_str}
- Concorrentes / Plataformas Encontradas: {', '.join(eval_result.competitors_found) or 'Nenhum'}
- Sinais Positivos (Dores): {'; '.join(eval_result.positive_signals) or 'Nenhum'}
- Fatores Desqualificadores: {'; '.join(eval_result.red_flags) or 'Nenhum'}
- Citações de Dores em Reviews: {'; '.join(eval_result.pain_points) or 'Nenhuma review crítica'}

DADOS FISCAIS RECEITA FEDERAL:
- Porte Empresarial: {cnpj_info.get('porte', 'Não informado') if cnpj_info else 'Não disponível'}
- Situação Cadastral: {cnpj_info.get('situacao_cadastral', 'Desconhecida') if cnpj_info else 'Desconhecida'}

TAREFA:
Classifique o nível de propensão (likelihood_no_pos), defina o índice de confiança (confidence_score de 0.0 a 1.0),
liste os fatores desqualificadores, elabore um comercial_hook persuasivo e natural para WhatsApp em português do Brasil
e informe o reasoning detalhado da sua decisão.
"""

        try:
            from openai import AsyncOpenAI
            import instructor

            client = AsyncOpenAI(api_key=self.api_key)
            instructor_client = instructor.from_openai(client)

            qualification: LeadQualification = await instructor_client.chat.completions.create(
                model=self.model,
                response_model=LeadQualification,
                max_retries=2,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            return qualification

        except Exception as err:
            console.print(
                f"[yellow]Aviso: Falha ao consultar OpenAI ({err}). "
                "Ativando fallback heurístico seguro.[/yellow]"
            )
            return self._generate_heuristic_fallback(
                business_name=business_name,
                niche=niche,
                evaluation=eval_result,
                has_phone=bool(phone),
            )
