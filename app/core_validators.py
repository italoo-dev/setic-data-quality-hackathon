"""Módulo de validadores de núcleo imutáveis da plataforma SETIC.

Implementa os validadores padronizados e inalteráveis que garantem:
1. Normalização Permissiva: formatações arbitrárias são convertidas para canônicas.
2. Bloqueio Estrito: defeitos estruturais e matemáticos causam bloqueio imediato (422).

Utiliza bibliotecas homologadas de mercado sem reinventar a roda:
- brutils: base de dados oficial com todos os 5.570 municípios brasileiros (brutils/data/cities_code.json).
- phonenumbers (Google libphonenumber): validação oficial de DDD, nono dígito e padrões Anatel.
- validate-docbr: validação algorítmica de CPF e CNPJ (módulo 11 da Receita Federal).
- dateparser: interpretação fuzzy de datas em português e validação temporal.
- RapidFuzz e Unidecode: correspondência fonética de alta performance sem requisições externas.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from importlib.resources import files
from typing import Any

import dateparser
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat
from rapidfuzz import fuzz, process
from unidecode import unidecode
from validate_docbr import CNPJ as DocbrCNPJ
from validate_docbr import CPF as DocbrCPF

logger = logging.getLogger("setic.validators")

# Instâncias de validação algorítmica homologadas
_docbr_cpf = DocbrCPF()
_docbr_cnpj = DocbrCNPJ()

# Expansões canônicas de abreviações populares em nomes de municípios brasileiros
ABREVIACOES_MUNICIPIOS = {
    r"\bp\.\b": "porto",
    r"\bsto\.\b": "santo",
    r"\bsta\.\b": "santa",
    r"\bs\.\b": "sao",
    r"\bpres\.\b": "presidente",
    r"\bgov\.\b": "governador",
    r"\bcel\.\b": "coronel",
    r"\bdr\.\b": "doutor",
    r"\bprof\.\b": "professor",
    r"\bmal\.\b": "marechal",
    r"\bgal\.\b": "general",
}


@dataclass
class ResultadoValidacao:
    """Resultado detalhado de validação e normalização de um campo."""

    valido: bool
    valor_normalizado: Any = None
    mensagem_transformacao: str | None = None
    campo: str = ""
    regra_violada: str = ""
    valor_rejeitado: Any = None
    formato_esperado: str = ""
    mensagem_erro: str = ""


def formatar_nome_municipio(nome_chave: str) -> str:
    """Formata nomes de municípios preservando partículas da língua portuguesa."""
    partes = nome_chave.split(" ")
    minusculas = {"de", "da", "do", "dos", "das", "e"}
    resultado = []
    for i, p in enumerate(partes):
        if "'" in p:
            sub = p.split("'")
            p_fmt = sub[0].lower() + "'" + sub[1].capitalize()
        elif "-" in p:
            sub = p.split("-")
            p_fmt = "-".join(s.capitalize() for s in sub)
        elif i > 0 and p in minusculas:
            p_fmt = p
        else:
            p_fmt = p.capitalize()
        resultado.append(p_fmt)
    return " ".join(resultado)


class CatalogoMunicipiosIBGE:
    """Catálogo Nacional de Municípios Brasileiros alimentado diretamente pelo pacote brutils.

    Carrega todos os 5.570 municípios a partir do arquivo canônico 'data/cities_code.json'
    do pacote brutils, operando de forma 100% autônoma, offline e determinística.
    """

    def __init__(self) -> None:
        self.por_codigo: dict[str, dict[str, str]] = {}
        self.por_uf: dict[str, dict[str, str]] = {}
        self.indice_nacional: dict[str, tuple[str, str, str]] = {}
        self._inicializar()

    def _inicializar(self) -> None:
        """Carrega os dados diretamente de brutils/data/cities_code.json."""
        try:
            arquivo_recurso = files("brutils").joinpath("data", "cities_code.json")
            with arquivo_recurso.open("r", encoding="utf-8") as f:
                dados_raw: dict[str, dict[str, str]] = json.load(f)
        except Exception as e:
            logger.error(f"Erro crítico ao ler 'cities_code.json' do brutils: {e}")
            dados_raw = {}

        for uf, cidades in dados_raw.items():
            uf_upper = uf.upper()
            self.por_uf[uf_upper] = {}

            for nome_chave, codigo_str in cidades.items():
                codigo = str(codigo_str).strip()
                nome_formatado = formatar_nome_municipio(nome_chave)

                self.por_codigo[codigo] = {
                    "codigo_ibge": codigo,
                    "municipio": nome_formatado,
                    "uf": uf_upper,
                }
                self.por_uf[uf_upper][nome_chave] = codigo
                self.indice_nacional[f"{nome_chave} ({uf_upper})"] = (
                    codigo,
                    uf_upper,
                    nome_formatado,
                )

        logger.info(
            f"Catálogo IBGE inicializado com {len(self.por_codigo)} municípios a partir de brutils."
        )

    @staticmethod
    def _expandir_e_normalizar(texto: str) -> str:
        """Normaliza texto expandindo abreviações e removendo pontuações."""
        t = unidecode(texto).lower()
        for padrao, subst in ABREVIACOES_MUNICIPIOS.items():
            t = re.sub(padrao, subst, t)
        t = re.sub(r"[-'/.]", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    def resolver(
        self,
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
        uf_normalizada = uf.strip().upper() if uf else None

        # Cenário 1: Entrada é um código IBGE numérico de 7 dígitos (Resolução Reversa)
        if re.fullmatch(r"^\d{7}$", texto_original):
            if texto_original in self.por_codigo:
                item = self.por_codigo[texto_original]
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

        # Cenário 2: Resolução de Nome de Município via brutils + RapidFuzz
        texto_buscado = self._expandir_e_normalizar(texto_original)

        # Busca prioritária no estado especificado
        if uf_normalizada and uf_normalizada in self.por_uf:
            mapa_uf = self.por_uf[uf_normalizada]

            # 2.1 Tentativa de correspondência exata
            if texto_buscado in mapa_uf:
                cod = mapa_uf[texto_buscado]
                item = self.por_codigo[cod]
                return ResultadoValidacao(
                    valido=True,
                    valor_normalizado={
                        "municipio": item["municipio"],
                        "codigo_ibge": item["codigo_ibge"],
                        "uf": item["uf"],
                    },
                    mensagem_transformacao=f"Município '{texto_original}' normalizado para '{item['municipio']}' (IBGE: {item['codigo_ibge']}).",
                )

            # 2.2 Aproximação fuzzy no estado
            melhor_match = process.extractOne(
                texto_buscado,
                list(mapa_uf.keys()),
                scorer=fuzz.WRatio,
            )

            if melhor_match and melhor_match[1] >= 75:
                cod = mapa_uf[melhor_match[0]]
                item = self.por_codigo[cod]
                return ResultadoValidacao(
                    valido=True,
                    valor_normalizado={
                        "municipio": item["municipio"],
                        "codigo_ibge": item["codigo_ibge"],
                        "uf": item["uf"],
                    },
                    mensagem_transformacao=f"Município informal '{texto_original}' aproximado para '{item['municipio']}' (Score: {melhor_match[1]:.1f}%, IBGE: {item['codigo_ibge']}).",
                )

        # 2.3 Busca fuzzy nacional se não houver UF ou não encontrou no estado
        melhor_nacional = process.extractOne(
            texto_buscado,
            list(self.indice_nacional.keys()),
            scorer=fuzz.WRatio,
        )

        if melhor_nacional and melhor_nacional[1] >= 80:
            chave_match = melhor_nacional[0]
            score = melhor_nacional[1]
            cod, match_uf, _ = self.indice_nacional[chave_match]
            item = self.por_codigo[cod]

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


# Instância única do catálogo nacional (carregado diretamente do brutils)
catalogo_ibge = CatalogoMunicipiosIBGE()


# =====================================================================
# Validadores Canônicos de Núcleo (Core Validators)
# =====================================================================


def validar_e_normalizar_cpf(valor: Any) -> ResultadoValidacao:
    """Valida o algoritmo de CPF (módulo 11 da Receita Federal via validate-docbr)."""
    if valor is None:
        return ResultadoValidacao(
            valido=False,
            campo="cpf",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="11 dígitos numéricos com dígitos verificadores válidos",
            mensagem_erro="O campo CPF não foi fornecido.",
        )

    limpo = re.sub(r"\D", "", str(valor))

    if len(limpo) != 11:
        return ResultadoValidacao(
            valido=False,
            campo="cpf",
            regra_violada="QUANTIDADE_DIGITOS_INVALIDA",
            valor_rejeitado=valor,
            formato_esperado="Exatamente 11 dígitos numéricos",
            mensagem_erro=f"O CPF informado contém {len(limpo)} dígitos. Esperado: 11 dígitos.",
        )

    if len(set(limpo)) == 1:
        return ResultadoValidacao(
            valido=False,
            campo="cpf",
            regra_violada="CPF_SEQUENCIA_INVALIDA",
            valor_rejeitado=valor,
            formato_esperado="CPF com dígitos verificadores matemáticos autênticos",
            mensagem_erro="O CPF informado é composto por dígitos repetidos conhecidos como inválidos.",
        )

    if not _docbr_cpf.validate(limpo):
        return ResultadoValidacao(
            valido=False,
            campo="cpf",
            regra_violada="DIGITO_VERIFICADOR_INVALIDO",
            valor_rejeitado=valor,
            formato_esperado="CPF com dígitos verificadores válidos (Algoritmo Módulo 11 da Receita Federal)",
            mensagem_erro="Os dígitos verificadores do CPF não conferem com o algoritmo matemático oficial.",
        )

    formatado = f"{limpo[:3]}.{limpo[3:6]}.{limpo[6:9]}-{limpo[9:]}"
    return ResultadoValidacao(
        valido=True,
        valor_normalizado=limpo,
        mensagem_transformacao=f"CPF normalizado para '{limpo}' (Formatado: {formatado}).",
    )


def validar_e_normalizar_cnpj(valor: Any) -> ResultadoValidacao:
    """Valida o algoritmo de CNPJ via validate-docbr e normaliza para 14 dígitos limpos."""
    if valor is None:
        return ResultadoValidacao(
            valido=False,
            campo="cnpj",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="14 dígitos numéricos",
            mensagem_erro="O campo CNPJ não foi fornecido.",
        )

    limpo = re.sub(r"\D", "", str(valor))

    if len(limpo) != 14:
        return ResultadoValidacao(
            valido=False,
            campo="cnpj",
            regra_violada="QUANTIDADE_DIGITOS_INVALIDA",
            valor_rejeitado=valor,
            formato_esperado="Exatamente 14 dígitos numéricos",
            mensagem_erro=f"O CNPJ informado contém {len(limpo)} dígitos. Esperado: 14 dígitos.",
        )

    if not _docbr_cnpj.validate(limpo):
        return ResultadoValidacao(
            valido=False,
            campo="cnpj",
            regra_violada="DIGITO_VERIFICADOR_INVALIDO",
            valor_rejeitado=valor,
            formato_esperado="CNPJ com dígitos verificadores válidos (Algoritmo Oficial)",
            mensagem_erro="Os dígitos verificadores do CNPJ são matematicamente inconsistentes.",
        )

    return ResultadoValidacao(
        valido=True,
        valor_normalizado=limpo,
        mensagem_transformacao=f"CNPJ normalizado para {limpo}.",
    )


def validar_e_normalizar_data(
    valor: Any,
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


def validar_e_normalizar_telefone(valor: Any) -> ResultadoValidacao:
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

    # Validação oficial de região e DDD via libphonenumber
    if not phonenumbers.is_valid_number_for_region(numero_analisado, "BR"):
        return ResultadoValidacao(
            valido=False,
            campo="telefone",
            regra_violada="TELEFONE_INVALIDO_ANATEL",
            valor_rejeitado=valor,
            formato_esperado="Número com DDD e formato regulatório válido na Anatel",
            mensagem_erro=f"O telefone '{texto}' não é um número brasileiro válido de acordo com a base regulatória da Anatel.",
        )

    # Normalização Permissiva: formato nacional e dígitos canônicos
    formato_nacional = phonenumbers.format_number(numero_analisado, PhoneNumberFormat.NATIONAL)
    digitos_limpos = f"{numero_analisado.national_number}"

    return ResultadoValidacao(
        valido=True,
        valor_normalizado=digitos_limpos,
        mensagem_transformacao=f"Telefone normalizado para '{digitos_limpos}' (Formatado: {formato_nacional}).",
    )


def validar_e_normalizar_cep(valor: Any) -> ResultadoValidacao:
    """Valida formato de 8 dígitos de Código de Endereçamento Postal (CEP)."""
    if valor is None:
        return ResultadoValidacao(
            valido=False,
            campo="cep",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="CEP com 8 dígitos numéricos",
            mensagem_erro="O campo CEP é obrigatório.",
        )

    limpo = re.sub(r"\D", "", str(valor))
    if len(limpo) != 8:
        return ResultadoValidacao(
            valido=False,
            campo="cep",
            regra_violada="FORMATO_CEP_INVALIDO",
            valor_rejeitado=valor,
            formato_esperado="8 dígitos numéricos (ex: 76801000 ou 76801-000)",
            mensagem_erro=f"O CEP informado contém {len(limpo)} dígitos. Esperado: exatamente 8 dígitos.",
        )

    formatado = f"{limpo[:5]}-{limpo[5:]}"
    return ResultadoValidacao(
        valido=True,
        valor_normalizado=limpo,
        mensagem_transformacao=f"CEP normalizado para '{limpo}' (Formatado: {formatado}).",
    )


def validar_e_normalizar_municipio(
    municipio: Any,
    uf: str | None = None,
) -> ResultadoValidacao:
    """Invoca a resolução do Catálogo Nacional de Municípios IBGE alimentado por brutils."""
    return catalogo_ibge.resolver(municipio, uf)
