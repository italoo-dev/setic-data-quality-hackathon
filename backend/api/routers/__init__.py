"""Roteadores modulares da API REST FastAPI."""

from backend.api.routers.audit import router as audit_router
from backend.api.routers.metrics import router as metrics_router
from backend.api.routers.rules import router as rules_router
from backend.api.routers.validation import router as validation_router

__all__ = [
    "audit_router",
    "metrics_router",
    "rules_router",
    "validation_router",
]
