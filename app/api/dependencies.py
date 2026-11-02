"""Injeção de Dependências da API FastAPI (Dependency Inversion).

Provedores para sessões do SQLAlchemy, repositórios de dados e pipeline de validação.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.engine.pipeline import ValidationPipeline
from app.repositories.audit import AuditRepository
from app.repositories.rules import RuleRepository


def get_db() -> Generator[Session, None, None]:
    """Generator de sessão de banco de dados para o ciclo de vida da requisição."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_audit_repository(db: Session = Depends(get_db)) -> AuditRepository:
    """Injeta a instância do repositório de auditoria."""
    return AuditRepository(db)


def get_rule_repository(db: Session = Depends(get_db)) -> RuleRepository:
    """Injeta a instância do repositório de regras dinâmicas."""
    return RuleRepository(db)


def get_validation_pipeline(
    rule_repo: RuleRepository = Depends(get_rule_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> ValidationPipeline:
    """Injeta o pipeline orquestrador de validação."""
    return ValidationPipeline(rule_repo=rule_repo, audit_repo=audit_repo)
