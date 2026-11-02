"""Camada de Apresentação e Entrega REST (FastAPI)."""

from app.api.dependencies import (
    get_audit_repository,
    get_db,
    get_rule_repository,
    get_validation_pipeline,
)

__all__ = [
    "get_audit_repository",
    "get_db",
    "get_rule_repository",
    "get_validation_pipeline",
]
