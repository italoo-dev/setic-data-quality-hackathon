"""Roteador da API para Consulta da Trilha de Auditoria e Telemetria."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_audit_repository
from app.repositories.audit import AuditRepository

router = APIRouter(prefix="/api/v1", tags=["Gestão e Telemetria"])


@router.get(
    "/auditoria",
    summary="Consultar Trilha de Auditoria e Telemetria",
)
def consultar_auditoria(
    sistema_origem: str | None = None,
    sucesso: bool | None = None,
    limite: int = Query(default=50, ge=1, le=500),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> list[dict[str, object]]:
    """Consulta os registros mais recentes da trilha de auditoria operacional."""
    registros = audit_repo.listar_registros(
        sistema_origem=sistema_origem,
        sucesso=sucesso,
        limite=limite,
    )
    return [r.to_dict() for r in registros]
