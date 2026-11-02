"""Camada de Domínio - Modelos e Contratos da Plataforma de Qualidade de Dados."""

from backend.domain.masking import (
    CAMPOS_SENSIVEIS,
    mascarar_cnpj,
    mascarar_cpf,
    mascarar_dados,
    mascarar_email,
    mascarar_erros,
    mascarar_pis,
    mascarar_telefone,
    mascarar_valor,
)
from backend.domain.models import (
    ErroDiagnosticoItem,
    ExecutionContext,
    ResultadoMotor,
    ResultadoValidacao,
)

__all__ = [
    "CAMPOS_SENSIVEIS",
    "ErroDiagnosticoItem",
    "ExecutionContext",
    "ResultadoMotor",
    "ResultadoValidacao",
    "mascarar_cnpj",
    "mascarar_cpf",
    "mascarar_dados",
    "mascarar_email",
    "mascarar_erros",
    "mascarar_pis",
    "mascarar_telefone",
    "mascarar_valor",
]
