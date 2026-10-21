"""Módulo de Orquestração de Pipelines (Pipeline) do ProspectAI.

Responsável por orquestrar o fluxo ponta a ponta de descoberta territorial,
enriquecimento web e cadastral, detecção heurística de PDV/ERP,
qualificação cognitiva com IA e persistência transacional de leads.

Exporta:
- LeadPipeline: Classe principal orquestradora
- PipelineProgress: Estrutura de dados para acompanhamento em tempo real
- PipelineResult: Resultado consolidado com métricas de execução
- PipelineStage: Enum com os estágios do ciclo de vida
- ProgressCallback: Tipo de assinatura para funções observadoras de progresso
"""

from pipeline.lead_pipeline import (
    LeadPipeline,
    PipelineProgress,
    PipelineResult,
    PipelineStage,
    ProgressCallback,
)

__all__ = [
    "LeadPipeline",
    "PipelineProgress",
    "PipelineResult",
    "PipelineStage",
    "ProgressCallback",
]
