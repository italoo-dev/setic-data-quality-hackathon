"""Validador e Normalizador Canônico de CEP (Strategy Pattern).

Utiliza a biblioteca brutils para sanitização, validação de formato e
normalização canônica do Código de Endereçamento Postal brasileiro.
"""

from __future__ import annotations

import brutils

from backend.domain.models import ErroDiagnosticoItem, ExecutionContext, ResultadoValidacao
from backend.validators.base import BaseValidator


def validar_e_normalizar_cep(valor: object) -> ResultadoValidacao:
    """Valida e normaliza CEP utilizando a biblioteca oficial brutils."""
    if valor is None:
        return ResultadoValidacao(
            valido=False,
            campo="cep",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="CEP com 8 dígitos numéricos (ex: 76801-000)",
            mensagem_erro="O campo CEP é obrigatório.",
        )

    texto = str(valor).strip().replace(" ", "")
    limpo = brutils.remove_symbols_cep(texto)

    if not brutils.is_valid_cep(limpo):
        return ResultadoValidacao(
            valido=False,
            campo="cep",
            regra_violada="FORMATO_CEP_INVALIDO",
            valor_rejeitado=valor,
            formato_esperado="CEP válido contendo exatamente 8 dígitos numéricos",
            mensagem_erro=f"O CEP '{texto}' é inválido perante o padrão postal brasileiro.",
        )

    formatado = brutils.format_cep(limpo)
    return ResultadoValidacao(
        valido=True,
        valor_normalizado=limpo,
        mensagem_transformacao=f"CEP normalizado para '{limpo}' (Formatado: {formatado}).",
    )


class CEPValidator(BaseValidator):
    """Estratégia de validação e normalização de CEP para o pipeline."""

    def validate_and_normalize(
        self,
        field_name: str,
        value: object,
        context: ExecutionContext,
    ) -> tuple[object, list[ErroDiagnosticoItem], list[str]]:
        res = validar_e_normalizar_cep(value)
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
