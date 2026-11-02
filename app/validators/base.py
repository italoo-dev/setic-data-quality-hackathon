"""Classe Base para Validadores Canônicos (Strategy Pattern).

Fornece a interface abstrata e utilitários compartilhados para construção
de erros diagnósticos e normalização padronizada segundo o contrato de domínio.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import ErroDiagnosticoItem, ExecutionContext


class BaseValidator(ABC):
    """Classe base abstrata para estratégias de validação e normalização de campos."""

    @abstractmethod
    def validate_and_normalize(
        self,
        field_name: str,
        value: object,
        context: ExecutionContext,
    ) -> tuple[object, list[ErroDiagnosticoItem], list[str]]:
        """Executa a validação e higienização do valor fornecido.

        Retorna:
            tuple[object, list[ErroDiagnosticoItem], list[str]]:
                (valor_normalizado, lista_de_erros, lista_de_transformacoes)
        """
        ...

    @staticmethod
    def build_diagnostic_error(
        campo: str,
        regra_violada: str,
        valor_rejeitado: object,
        formato_esperado: str,
        mensagem: str,
    ) -> ErroDiagnosticoItem:
        """Fábrica utilitária DRY para construção uniforme de ErroDiagnosticoItem."""
        return ErroDiagnosticoItem(
            campo=campo,
            regra_violada=regra_violada,
            valor_rejeitado=valor_rejeitado,
            formato_esperado=formato_esperado,
            mensagem=mensagem,
        )
