"""Roteadores modulares da API REST FastAPI."""

from app.api.routers.audit import router as audit_router
from app.api.routers.metrics import router as metrics_router
from app.api.routers.rules import router as rules_router
from app.api.routers.validation import router as validation_router

__all__ = [
    "audit_router",
    "metrics_router",
    "rules_router",
    "validation_router",
]
