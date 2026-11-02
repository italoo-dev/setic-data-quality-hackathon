"""Validadores Canônicos de Documentos: PIS/PASEP (Strategy Pattern).

Valida a integridade do cadastro no PIS/PASEP através da biblioteca brutils.
"""

from __future__ import annotations

import brutils

from backend.domain.models import ErroDiagnosticoItem, ExecutionContext, ResultadoValidacao
from backend.validators.base import BaseValidator


def validar_e_normalizar_pis(valor: object) -> ResultadoValidacao:
    """Valida e normaliza PIS/PASEP utilizando brutils."""
    if not valor:
        return ResultadoValidacao(
            valido=False,
            campo="pis",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="Número de PIS com 11 dígitos numéricos",
            mensagem_erro="O campo PIS é obrigatório.",
        )

    texto = str(valor).strip().replace(" ", "")
    limpo = brutils.remove_symbols_pis(texto)

    if not brutils.is_valid_pis(limpo):
        return ResultadoValidacao(
            valido=False,
            campo="pis",
            regra_violada="PIS_INVALIDO",
            valor_rejeitado=valor,
            formato_esperado="PIS/PASEP autêntico de 11 dígitos numéricos",
            mensagem_erro="O número de PIS informado é inválido.",
        )

    formatado = brutils.format_pis(limpo)
    return ResultadoValidacao(
        valido=True,
        valor_normalizado=limpo,
        mensagem_transformacao=f"PIS normalizado para '{limpo}' (Formatado: {formatado}).",
    )


class PISValidator(BaseValidator):
    """Estratégia de validação e normalização de PIS/PASEP para o pipeline."""

    def validate_and_normalize(
        self,
        field_name: str,
        value: object,
        context: ExecutionContext,
    ) -> tuple[object, list[ErroDiagnosticoItem], list[str]]:
        res = validar_e_normalizar_pis(value)
        if not res.valido:
            erro = self.build_diagnostic_error(
                campo=field_name,
                regra_violada=res.regra_violada,
                valor_rejeitado=res.valor_rejeitado,
                formato_esperado=res.formato_esperado,
                mensagem=res.mensagem_erro,
            )
            return value, [erro], []

        transformacoes = [res.mensagem_transformacao] if res.mensagem_transformacao else []
        return res.valor_normalizado, [], transformacoes
