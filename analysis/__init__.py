"""Módulo de análise e inteligência de leads para o ProspectAI.

Este módulo agrega:
- Motor heurístico de detecção de sistemas de gestão / PDV / ERP (`POSDetector`).
- Raspador web assíncrono para identificação de sinais operacionais e CNPJ (`WebScraper`).
- Qualificador cognitivo com inteligência artificial GPT-4o-mini (`LLMQualifier`).
"""

from analysis.llm_qualifier import (
    LeadQualification,
    LLMQualifier,
)
from analysis.pos_detector import (
    COMPETITOR_PLATFORMS,
    CompetitorCategory,
    CompetitorPlatform,
    ContactChannel,
    HeuristicEvaluation,
    LikelihoodLevel,
    PixKeyType,
    POSDetector,
    ReviewAnalyzer,
    validate_cnpj,
    validate_cpf,
)
from analysis.web_scraper import (
    ScrapingResult,
    WebScraper,
)

__all__ = [
    "COMPETITOR_PLATFORMS",
    "CompetitorCategory",
    "CompetitorPlatform",
    "ContactChannel",
    "HeuristicEvaluation",
    "LLMQualifier",
    "LeadQualification",
    "LikelihoodLevel",
    "POSDetector",
    "PixKeyType",
    "ReviewAnalyzer",
    "ScrapingResult",
    "WebScraper",
    "validate_cnpj",
    "validate_cpf",
]
