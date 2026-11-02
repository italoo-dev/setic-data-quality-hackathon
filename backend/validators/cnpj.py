"""Validador e Normalizador Canônico de CNPJ (Strategy Pattern).

Utiliza a biblioteca homologada brutils para conferência estrita dos dígitos
verificadores e higienização alfanumérica/numérica do cadastro nacional.
"""

from __future__ import annotations

import brutils

from backend.domain.models import ErroDiagnosticoItem, ExecutionContext, ResultadoValidacao
from backend.validators.base import BaseValidator


def validar_e_normalizar_cnpj(valor: object) -> ResultadoValidacao:
    """Valida e normaliza CNPJ utilizando a biblioteca oficial brutils."""
    if valor is None:
        return ResultadoValidacao(
            valido=False,
            campo="cnpj",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="14 dígitos numéricos",
            mensagem_erro="O campo CNPJ não foi fornecido.",
        )

    texto = str(valor).strip().replace(" ", "")
    limpo = brutils.remove_symbols_cnpj(texto)

    if len(limpo) != 14:
        return ResultadoValidacao(
            valido=False,
            campo="cnpj",
            regra_violada="QUANTIDADE_DIGITOS_INVALIDA",
            valor_rejeitado=valor,
            formato_esperado="Exatamente 14 dígitos numéricos",
            mensagem_erro=f"O CNPJ informado possui {len(limpo)} dígitos. Esperado: exatamente 14 dígitos.",
        )

    if len(set(limpo)) == 1:
        return ResultadoValidacao(
            valido=False,
            campo="cnpj",
            regra_violada="CNPJ_SEQUENCIA_INVALIDA",
            valor_rejeitado=valor,
            formato_esperado="CNPJ com dígitos variados e não apenas números repetidos",
            mensagem_erro="CNPJ composto por números idênticos repetidos é inválido perante a Receita Federal.",
        )

    if not brutils.is_valid_cnpj(limpo):
        return ResultadoValidacao(
            valido=False,
            campo="cnpj",
            regra_violada="DIGITO_VERIFICADOR_INVALIDO",
            valor_rejeitado=valor,
            formato_esperado="CNPJ com 14 dígitos e verificadores válidos segundo a Receita Federal",
            mensagem_erro="Os dígitos verificadores do CNPJ são matematicamente inconsistentes.",
        )

    formatado = brutils.format_cnpj(limpo)
    return ResultadoValidacao(
        valido=True,
        valor_normalizado=limpo,
        mensagem_transformacao=f"CNPJ normalizado para '{limpo}' (Formatado: {formatado}).",
    )


class CNPJValidator(BaseValidator):
    """Estratégia de validação e normalização de CNPJ para o pipeline."""

    def validate_and_normalize(
        self,
        field_name: str,
        value: object,
        context: ExecutionContext,
    ) -> tuple[object, list[ErroDiagnosticoItem], list[str]]:
        res = validar_e_normalizar_cnpj(value)
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
