"""Módulo de Mascaramento e Anonimização de Dados Sensíveis (LGPD).

Garante que informações de identificação pessoal (PII) como CPF, CNPJ,
telefones, e-mails e PIS/PASEP não sejam expostas em texto puro nem
persistidas sem proteção na trilha de auditoria e no painel gerencial.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from backend.engine.core_tier import CoreTierStep

# Instância canônica do Core Tier para resolução relacional de campos sensíveis e aliases O(1)
_CORE_STEP = CoreTierStep()
_CORE_MAP = _CORE_STEP.map

# Conjunto canônico de campos e aliases classificados como dados pessoais/sensíveis obtidos do BiDict
CAMPOS_SENSIVEIS: frozenset[str] = _CORE_MAP.campos_sensiveis


def mascarar_cpf(valor: str) -> str:
    """Mascara um CPF preservando o formato de entrada (com ou sem pontuação)."""
    digitos = re.sub(r"\D", "", valor)
    tem_pontuacao = "." in valor or "-" in valor

    if len(digitos) == 11:
        if tem_pontuacao:
            return f"{digitos[:3]}.***.***-{digitos[-2:]}"
        return f"{digitos[:3]}******{digitos[-2:]}"

    if len(digitos) <= 4:
        return "***"
    return f"{digitos[:2]}***{digitos[-2:]}"


def mascarar_cnpj(valor: str) -> str:
    """Mascara um CNPJ preservando o formato de entrada (com ou sem pontuação)."""
    digitos = re.sub(r"\D", "", valor)
    tem_pontuacao = "." in valor or "/" in valor or "-" in valor

    if len(digitos) == 14:
        if tem_pontuacao:
            return f"{digitos[:2]}.***.***/{digitos[8:12]}-{digitos[-2:]}"
        return f"{digitos[:2]}******{digitos[8:12]}{digitos[-2:]}"

    if len(digitos) <= 4:
        return "***"
    return f"{digitos[:2]}***{digitos[-2:]}"


def mascarar_pis(valor: str) -> str:
    """Mascara um número PIS/PASEP/NIS preservando o formato de entrada (com ou sem pontuação)."""
    digitos = re.sub(r"\D", "", valor)
    tem_pontuacao = "." in valor or "-" in valor

    if len(digitos) == 11:
        if tem_pontuacao:
            return f"{digitos[:3]}.*****.{digitos[8:10]}-{digitos[-1]}"
        return f"{digitos[:3]}*****{digitos[-3:]}"

    if len(digitos) <= 4:
        return "***"
    return f"{digitos[:2]}***{digitos[-2:]}"


def mascarar_telefone(valor: str) -> str:
    """Mascara um telefone/celular preservando o formato de entrada (com ou sem pontuação)."""
    digitos = re.sub(r"\D", "", valor)
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]

    tem_parentese = "(" in valor

    if len(digitos) == 11:
        ddd = digitos[:2]
        sufixo = digitos[-4:]
        if tem_parentese:
            return f"({ddd}) 9****-{sufixo}"
        return f"{ddd}9****{sufixo}"

    if len(digitos) == 10:
        ddd = digitos[:2]
        sufixo = digitos[-4:]
        if tem_parentese:
            return f"({ddd}) ****-{sufixo}"
        return f"{ddd}****{sufixo}"

    if len(digitos) == 9:
        if "-" in valor:
            return f"9****-{digitos[-4:]}"
        return f"{digitos[0]}****{digitos[-4:]}"

    if len(digitos) == 8:
        if "-" in valor:
            return f"****-{digitos[-4:]}"
        return f"****{digitos[-4:]}"

    if len(digitos) <= 4:
        return "***"

    if tem_parentese and len(digitos) >= 4:
        return f"({digitos[:2]}) ***-{digitos[-2:]}"
    return f"{digitos[:2]}***{digitos[-2:]}"


def mascarar_email(valor: str) -> str:
    """Mascara um endereço de e-mail (ex: c***o@rondonia.gov.br)."""
    if "@" in valor:
        partes = valor.split("@", 1)
        usuario, dominio = partes[0], partes[1]
        if len(usuario) <= 2:
            usuario_mascarado = f"{usuario[0]}***" if usuario else "***"
        else:
            usuario_mascarado = f"{usuario[0]}***{usuario[-1]}"
        return f"{usuario_mascarado}@{dominio}"
    if len(valor) <= 3:
        return "***"
    return f"{valor[0]}***{valor[-1]}"


def mascarar_valor(campo: str, valor: object) -> object:
    """Aplica o mascaramento apropriado conforme a semântica do campo resolvida via BiDict."""
    if valor is None:
        return None
    if not isinstance(valor, (str, int, float)):
        return valor

    texto = str(valor).strip()
    campo_lower = campo.lower()

    grupo = _CORE_MAP.get(campo_lower)
    if grupo is None or not grupo.sensivel:
        return valor

    if grupo.canonical == "cpf":
        if campo_lower == "cpf_cnpj":
            digitos = re.sub(r"\D", "", texto)
            return mascarar_cnpj(texto) if len(digitos) > 11 else mascarar_cpf(texto)
        return mascarar_cpf(texto)
    if grupo.canonical == "cnpj":
        return mascarar_cnpj(texto)
    if grupo.canonical == "telefone":
        return mascarar_telefone(texto)
    if grupo.canonical == "email":
        return mascarar_email(texto)
    if grupo.canonical == "pis":
        return mascarar_pis(texto)

    return valor


def mascarar_dados(dados: Mapping[str, object] | None) -> dict[str, object]:
    """Retorna uma cópia do dicionário de dados com todos os campos sensíveis mascarados."""
    if not dados:
        return {}
    resultado: dict[str, object] = {}
    for chave, valor in dados.items():
        grupo = _CORE_MAP.get(chave.lower())
        if grupo is not None and grupo.sensivel:
            resultado[chave] = mascarar_valor(chave, valor)
        elif isinstance(valor, dict):
            resultado[chave] = mascarar_dados(valor)
        else:
            resultado[chave] = valor
    return resultado


def mascarar_erros(
    erros: Sequence[Mapping[str, object]] | None,
) -> list[dict[str, object]] | None:
    """Mascara os valores rejeitados de erros que correspondam a campos sensíveis."""
    if erros is None:
        return None
    erros_sanitizados: list[dict[str, object]] = []
    for erro in erros:
        erro_copia = dict(erro)
        campo = erro_copia.get("campo")
        if isinstance(campo, str):
            grupo = _CORE_MAP.get(campo.lower())
            if grupo is not None and grupo.sensivel and "valor_rejeitado" in erro_copia:
                erro_copia["valor_rejeitado"] = mascarar_valor(campo, erro_copia["valor_rejeitado"])
        erros_sanitizados.append(erro_copia)
    return erros_sanitizados
