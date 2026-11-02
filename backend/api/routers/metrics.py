"""Roteador da API para Indicadores e Métricas Operacionais da CAGD."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_audit_repository
from backend.repositories.audit import AuditRepository
from backend.schemas import MetricasOperacionaisCAGD

router = APIRouter(prefix="/api/v1", tags=["Gestão e Telemetria"])


@router.get(
    "/metricas",
    response_model=MetricasOperacionaisCAGD,
    summary="Métricas Operacionais Consolidadas para a CAGD",
)
def obter_metricas_cagd(
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> MetricasOperacionaisCAGD:
    """Calcula estatísticas agregadas de qualidade, rejeição e latência para a gestão."""
    return audit_repo.obter_metricas_cagd()
