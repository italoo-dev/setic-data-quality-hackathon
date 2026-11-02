"""Validadores Canônicos de Contato: Telefone e E-mail (Strategy Pattern).

- Telefone: Validação estrita de DDDs e formato regulatório Anatel via Google libphonenumber.
- E-mail: Validação sintática e de estrutura segundo RFC via biblioteca brutils.
"""

from __future__ import annotations

import brutils
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

from app.domain.models import ErroDiagnosticoItem, ExecutionContext, ResultadoValidacao
from app.validators.base import BaseValidator


def validar_e_normalizar_telefone(valor: object) -> ResultadoValidacao:
    """Valida telefone utilizando Google libphonenumber (phonenumbers) para padrões nacionais e DDD."""
    if not valor:
        return ResultadoValidacao(
            valido=False,
            campo="telefone",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="Número com DDD válido segundo a regulação da Anatel",
            mensagem_erro="O campo telefone é obrigatório.",
        )

    texto = str(valor).strip()

    try:
        numero_analisado = phonenumbers.parse(texto, "BR")
    except NumberParseException as err:
        return ResultadoValidacao(
            valido=False,
            campo="telefone",
            regra_violada="FORMATO_TELEFONE_INVALIDO",
            valor_rejeitado=valor,
            formato_esperado="Número com DDD brasileiro válido (ex: (69) 99234-5678 ou (69) 3216-5400)",
            mensagem_erro=f"Não foi possível interpretar a estrutura do número telefônico: {err}.",
        )

    if not phonenumbers.is_valid_number_for_region(numero_analisado, "BR"):
        return ResultadoValidacao(
            valido=False,
            campo="telefone",
            regra_violada="TELEFONE_INVALIDO_ANATEL",
            valor_rejeitado=valor,
            formato_esperado="Número com DDD e formato regulatório válido na Anatel",
            mensagem_erro=f"O telefone '{texto}' não é um número brasileiro válido de acordo com a base regulatória da Anatel.",
        )

    formato_nacional = phonenumbers.format_number(numero_analisado, PhoneNumberFormat.NATIONAL)
    digitos_limpos = f"{numero_analisado.national_number}"

    return ResultadoValidacao(
        valido=True,
        valor_normalizado=digitos_limpos,
        mensagem_transformacao=f"Telefone normalizado para '{digitos_limpos}' (Formatado: {formato_nacional}).",
    )


def validar_e_normalizar_email(valor: object) -> ResultadoValidacao:
    """Valida endereço de e-mail utilizando brutils."""
    if not valor:
        return ResultadoValidacao(
            valido=False,
            campo="email",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="Endereço de e-mail válido (ex: usuario@dominio.com)",
            mensagem_erro="O campo e-mail é obrigatório.",
        )

    texto = str(valor).strip()
    if not brutils.is_valid_email(texto):
        return ResultadoValidacao(
            valido=False,
            campo="email",
            regra_violada="FORMATO_EMAIL_INVALIDO",
            valor_rejeitado=valor,
            formato_esperado="Endereço de e-mail em formato válido segundo RFC",
            mensagem_erro=f"O endereço de e-mail '{texto}' é inválido.",
        )

    return ResultadoValidacao(
        valido=True,
        valor_normalizado=texto.lower(),
        mensagem_transformacao=f"E-mail normalizado para '{texto.lower()}'.",
    )


class PhoneValidator(BaseValidator):
    """Estratégia de validação e normalização de telefones para o pipeline."""

    def validate_and_normalize(
        self,
        field_name: str,
        value: object,
        context: ExecutionContext,
    ) -> tuple[object, list[ErroDiagnosticoItem], list[str]]:
        res = validar_e_normalizar_telefone(value)
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


class EmailValidator(BaseValidator):
    """Estratégia de validação e normalização de e-mails para o pipeline."""

    def validate_and_normalize(
        self,
        field_name: str,
        value: object,
        context: ExecutionContext,
    ) -> tuple[object, list[ErroDiagnosticoItem], list[str]]:
        res = validar_e_normalizar_email(value)
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
