"""Validador e Resoluções Bidirecionais de Municípios IBGE (Strategy Pattern).

Executa a resolução de código de 7 dígitos para município/UF e aproximação
fonética/fuzzy em memória utilizando RapidFuzz e Unidecode (100% offline).
"""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz, process

from app.domain.models import ErroDiagnosticoItem, ExecutionContext, ResultadoValidacao
from app.validators.base import BaseValidator
from app.validators.ibge.catalog import catalogo_ibge


def validar_e_normalizar_municipio(
    municipio_ou_codigo: Any,
    uf: str | None = None,
) -> ResultadoValidacao:
    """Resolve bidirecionalmente municípios brasileiros (Nome <-> Código IBGE de 7 dígitos)."""
    if not municipio_ou_codigo:
        return ResultadoValidacao(
            valido=False,
            campo="municipio",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=municipio_ou_codigo,
            formato_esperado="Nome do município ou código IBGE de 7 dígitos",
            mensagem_erro="O campo município é obrigatório.",
        )

    texto_original = str(municipio_ou_codigo).strip()
    uf_normalizada = catalogo_ibge.normalizar_uf(uf)

    # Cenário 1: Entrada é um código IBGE numérico de 7 dígitos (Resolução Reversa)
    if re.fullmatch(r"^\d{7}$", texto_original):
        if texto_original in catalogo_ibge.por_codigo:
            item = catalogo_ibge.por_codigo[texto_original]
            if uf_normalizada and item["uf"] != uf_normalizada:
                return ResultadoValidacao(
                    valido=False,
                    campo="municipio",
                    regra_violada="UF_INCOMPATIVEL_COM_CODIGO_IBGE",
                    valor_rejeitado=f"Código {texto_original} com UF {uf_normalizada}",
                    formato_esperado=f"Código IBGE correspondente à UF {item['uf']}",
                    mensagem_erro=f"O código IBGE {texto_original} pertence ao município '{item['municipio']}' ({item['uf']}), divergente da UF informada ({uf_normalizada}).",
                )
            return ResultadoValidacao(
                valido=True,
                valor_normalizado={
                    "municipio": item["municipio"],
                    "codigo_ibge": item["codigo_ibge"],
                    "uf": item["uf"],
                },
                mensagem_transformacao=f"Código IBGE '{texto_original}' normalizado para '{item['municipio']}/{item['uf']}'.",
            )
        else:
            return ResultadoValidacao(
                valido=False,
                campo="codigo_ibge",
                regra_violada="CODIGO_IBGE_INEXISTENTE",
                valor_rejeitado=texto_original,
                formato_esperado="Código IBGE válido de 7 dígitos cadastrado na base nacional",
                mensagem_erro=f"O código IBGE '{texto_original}' não foi encontrado na base de dados nacional do IBGE.",
            )

    # Cenário 2: Resolução de Nome de Município via catalogo_ibge + RapidFuzz
    texto_buscado = catalogo_ibge.expandir_e_normalizar(texto_original)

    # 2.1 Busca prioritária no estado especificado
    if uf_normalizada and uf_normalizada in catalogo_ibge.por_uf:
        mapa_uf = catalogo_ibge.por_uf[uf_normalizada]

        if texto_buscado in mapa_uf:
            cod = mapa_uf[texto_buscado]
            item = catalogo_ibge.por_codigo[cod]
            return ResultadoValidacao(
                valido=True,
                valor_normalizado={
                    "municipio": item["municipio"],
                    "codigo_ibge": item["codigo_ibge"],
                    "uf": item["uf"],
                },
                mensagem_transformacao=f"Município '{texto_original}' normalizado para '{item['municipio']}' (IBGE: {item['codigo_ibge']}).",
            )

        melhor_match = process.extractOne(
            texto_buscado,
            list(mapa_uf.keys()),
            scorer=fuzz.WRatio,
        )

        if melhor_match and melhor_match[1] >= 75:
            cod = mapa_uf[melhor_match[0]]
            item = catalogo_ibge.por_codigo[cod]
            return ResultadoValidacao(
                valido=True,
                valor_normalizado={
                    "municipio": item["municipio"],
                    "codigo_ibge": item["codigo_ibge"],
                    "uf": item["uf"],
                },
                mensagem_transformacao=f"Município informal '{texto_original}' aproximado para '{item['municipio']}' (Score: {melhor_match[1]:.1f}%, IBGE: {item['codigo_ibge']}).",
            )

    # 2.2 Busca fuzzy nacional caso não haja UF ou não tenha correspondido no estado
    melhor_nacional = process.extractOne(
        texto_buscado,
        list(catalogo_ibge.indice_nacional.keys()),
        scorer=fuzz.WRatio,
    )

    if melhor_nacional and melhor_nacional[1] >= 80:
        chave_match = melhor_nacional[0]
        score = melhor_nacional[1]
        cod, match_uf, _ = catalogo_ibge.indice_nacional[chave_match]
        item = catalogo_ibge.por_codigo[cod]

        if uf_normalizada and uf_normalizada != match_uf and score >= 90:
            return ResultadoValidacao(
                valido=False,
                campo="municipio",
                regra_violada="MUNICIPIO_NAO_PERTENCE_A_UF",
                valor_rejeitado=f"{texto_original} ({uf_normalizada})",
                formato_esperado=f"Município existente no estado {uf_normalizada}",
                mensagem_erro=f"O município '{item['municipio']}' pertence ao estado {match_uf}, não constando na UF '{uf_normalizada}'.",
            )

        return ResultadoValidacao(
            valido=True,
            valor_normalizado={
                "municipio": item["municipio"],
                "codigo_ibge": item["codigo_ibge"],
                "uf": item["uf"],
            },
            mensagem_transformacao=f"Município '{texto_original}' aproximado nacionalmente para '{item['municipio']}/{item['uf']}' (Score: {score:.1f}%, IBGE: {item['codigo_ibge']}).",
        )

    # Bloqueio Estrito: Município desconhecido
    return ResultadoValidacao(
        valido=False,
        campo="municipio",
        regra_violada="MUNICIPIO_IBGE_NAO_ENCONTRADO",
        valor_rejeitado=texto_original,
        formato_esperado="Nome oficial ou grafia aproximável de município registrado no IBGE",
        mensagem_erro=f"O município '{texto_original}' não foi localizado na base oficial do IBGE para a UF especificada ({uf_normalizada or 'Não informada'}).",
    )


class IBGEMunicipioValidator(BaseValidator):
    """Estratégia de resolução e validação de Municípios IBGE para o pipeline."""

    def validate_and_normalize(
        self,
        field_name: str,
        value: Any,
        context: ExecutionContext,
    ) -> tuple[Any, list[ErroDiagnosticoItem], list[str]]:
        uf = context.dados_brutos.get("uf")
        res = validar_e_normalizar_municipio(value, uf=uf)
        if not res.valido:
            erro = self.build_diagnostic_error(
                campo=res.campo or field_name,
                regra_violada=res.regra_violada,
                valor_rejeitado=res.valor_rejeitado,
                formato_esperado=res.formato_esperado,
                mensagem=res.mensagem_erro,
            )
            return value, [erro], []

        # Se for dicionário com município, código_ibge e uf, atualiza context diretamente
        if isinstance(res.valor_normalizado, dict):
            context.dados_normalizados["municipio"] = res.valor_normalizado["municipio"]
            context.dados_normalizados["codigo_ibge"] = res.valor_normalizado["codigo_ibge"]
            context.dados_normalizados["uf"] = res.valor_normalizado["uf"]

        transformacoes = [res.mensagem_transformacao] if res.mensagem_transformacao else []
        return res.valor_normalizado, [], transformacoes
