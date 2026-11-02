"""Validador e Normalizador Temporal de Datas (Strategy Pattern).

Interpreta datas por extenso em português ou em formato numérico,
bloqueia estritamente datas impossíveis no calendário gregoriano e
converte payloads válidos para o padrão ISO-8601 (AAAA-MM-DD).
"""

from __future__ import annotations

import re
from datetime import date, datetime

import dateparser

from backend.domain.models import ErroDiagnosticoItem, ExecutionContext, ResultadoValidacao
from backend.validators.base import BaseValidator


def validar_e_normalizar_data(
    valor: object,
    campo: str = "data_nascimento",
    permitir_futuro: bool = False,
) -> ResultadoValidacao:
    """Valida consistência temporal de calendário e normaliza datas para o padrão ISO-8601."""
    if valor is None:
        return ResultadoValidacao(
            valido=False,
            campo=campo,
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="Data no formato AAAA-MM-DD ou textual em português",
            mensagem_erro=f"O campo '{campo}' é obrigatório.",
        )

    texto = str(valor).strip()

    # Bloqueio estrito de datas impossíveis no calendário gregoriano
    padrao_numerico = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", texto)
    if padrao_numerico:
        d_raw, m_raw, a_raw = (
            int(padrao_numerico.group(1)),
            int(padrao_numerico.group(2)),
            int(padrao_numerico.group(3)),
        )
        if a_raw < 100:
            a_raw += 1900 if a_raw > 30 else 2000

        try:
            date(a_raw, m_raw, d_raw)
        except ValueError as err:
            return ResultadoValidacao(
                valido=False,
                campo=campo,
                regra_violada="DATA_IMPOSSIVEL_CALENDARIO",
                valor_rejeitado=texto,
                formato_esperado="Data existente no calendário gregoriano",
                mensagem_erro=f"A data '{texto}' é impossível no calendário gregoriano: {err}.",
            )

    if re.search(r"\b(fev|fevereiro)\b", texto, re.IGNORECASE) and re.search(r"\b(30|31)\b", texto):
        return ResultadoValidacao(
            valido=False,
            campo=campo,
            regra_violada="DATA_IMPOSSIVEL_CALENDARIO",
            valor_rejeitado=texto,
            formato_esperado="Fevereiro possui no máximo 28 ou 29 dias",
            mensagem_erro=f"A data '{texto}' indica dia impossível para o mês de fevereiro.",
        )

    dt = dateparser.parse(
        texto,
        languages=["pt"],
        settings={
            "DATE_ORDER": "DMY",
            "STRICT_PARSING": False,
            "PREFER_DAY_OF_MONTH": "first",
        },
    )

    if dt is None:
        return ResultadoValidacao(
            valido=False,
            campo=campo,
            regra_violada="FORMATO_DATA_INVALIDO",
            valor_rejeitado=texto,
            formato_esperado="Data válida (ex: '15/03/1985' ou '15 de março de 1985')",
            mensagem_erro=f"Não foi possível interpretar a data '{texto}'. Formato inválido ou irreconhecível.",
        )

    data_objeto = dt.date()
    hoje = datetime.now().date()

    if not permitir_futuro and data_objeto > hoje:
        return ResultadoValidacao(
            valido=False,
            campo=campo,
            regra_violada="DATA_FUTURA_INVALIDA",
            valor_rejeitado=texto,
            formato_esperado="Data anterior ou igual à data atual",
            mensagem_erro=f"A data informada ({data_objeto.isoformat()}) está situada no futuro.",
        )

    if data_objeto.year < 1900:
        return ResultadoValidacao(
            valido=False,
            campo=campo,
            regra_violada="ANO_FORA_DO_LIMITE",
            valor_rejeitado=texto,
            formato_esperado="Ano maior ou igual a 1900",
            mensagem_erro=f"O ano da data ({data_objeto.year}) é anterior ao limiar corporativo de 1900.",
        )

    iso_data = data_objeto.isoformat()
    return ResultadoValidacao(
        valido=True,
        valor_normalizado=iso_data,
        mensagem_transformacao=f"Data '{texto}' normalizada para o formato ISO-8601 '{iso_data}'.",
    )


class DateTimeValidator(BaseValidator):
    """Estratégia de validação e normalização de datas para o pipeline."""

    def __init__(self, permitir_futuro: bool = False) -> None:
        self.permitir_futuro = permitir_futuro

    def validate_and_normalize(
        self,
        field_name: str,
        value: object,
        context: ExecutionContext,
    ) -> tuple[object, list[ErroDiagnosticoItem], list[str]]:
        res = validar_e_normalizar_data(
            value, campo=field_name, permitir_futuro=self.permitir_futuro
        )
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
