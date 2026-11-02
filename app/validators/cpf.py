"""Validador e Normalizador Canônico de CPF (Strategy Pattern).

Utiliza a biblioteca homologada brutils para higienização e validação dos dígitos
verificadores oficiais pelo algoritmo módulo 11 da Receita Federal.
"""

from __future__ import annotations

import brutils

from app.domain.models import ErroDiagnosticoItem, ExecutionContext, ResultadoValidacao
from app.validators.base import BaseValidator


def validar_e_normalizar_cpf(valor: object) -> ResultadoValidacao:
    """Valida e normaliza CPF utilizando a biblioteca oficial brutils."""
    if valor is None:
        return ResultadoValidacao(
            valido=False,
            campo="cpf",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="11 dígitos numéricos com dígitos verificadores válidos",
            mensagem_erro="O campo CPF não foi fornecido.",
        )

    texto = str(valor).strip().replace(" ", "")
    limpo = brutils.remove_symbols_cpf(texto)

    if len(limpo) != 11:
        return ResultadoValidacao(
            valido=False,
            campo="cpf",
            regra_violada="QUANTIDADE_DIGITOS_INVALIDA",
            valor_rejeitado=valor,
            formato_esperado="Exatamente 11 dígitos numéricos",
            mensagem_erro=f"O CPF informado possui {len(limpo)} dígitos. Esperado: exatamente 11 dígitos.",
        )

    if len(set(limpo)) == 1:
        return ResultadoValidacao(
            valido=False,
            campo="cpf",
            regra_violada="CPF_SEQUENCIA_INVALIDA",
            valor_rejeitado=valor,
            formato_esperado="CPF com dígitos variados e não apenas números repetidos",
            mensagem_erro="CPF composto por números idênticos repetidos é inválido perante a Receita Federal.",
        )

    if not brutils.is_valid_cpf(limpo):
        return ResultadoValidacao(
            valido=False,
            campo="cpf",
            regra_violada="DIGITO_VERIFICADOR_INVALIDO",
            valor_rejeitado=valor,
            formato_esperado="CPF com 11 dígitos e verificadores válidos segundo a Receita Federal",
            mensagem_erro="Os dígitos verificadores do CPF não conferem com o algoritmo matemático oficial.",
        )

    formatado = brutils.format_cpf(limpo)
    return ResultadoValidacao(
        valido=True,
        valor_normalizado=limpo,
        mensagem_transformacao=f"CPF normalizado para '{limpo}' (Formatado: {formatado}).",
    )


class CPFValidator(BaseValidator):
    """Estratégia de validação e normalização de CPF para o pipeline."""

    def validate_and_normalize(
        self,
        field_name: str,
        value: object,
        context: ExecutionContext,
    ) -> tuple[object, list[ErroDiagnosticoItem], list[str]]:
        res = validar_e_normalizar_cpf(value)
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
