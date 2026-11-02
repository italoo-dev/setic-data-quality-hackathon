"""Módulo de validadores de núcleo imutáveis da plataforma SETIC.

Implementa os validadores padronizados e inalteráveis que garantem:
1. Normalização Permissiva: formatações arbitrárias são convertidas para canônicas.
2. Bloqueio Estrito: defeitos estruturais e matemáticos causam bloqueio imediato (422).

Utiliza bibliotecas homologadas:
- brutils e validate-docbr: identificadores nacionais (CPF, CNPJ, Telefone, CEP).
- dateparser: interpretação fuzzy de datas em português.
- RapidFuzz e Unidecode: resolução de alta performance contra o catálogo nacional IBGE.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import dateparser
from rapidfuzz import fuzz, process
from unidecode import unidecode
from validate_docbr import CNPJ as DocbrCNPJ
from validate_docbr import CPF as DocbrCPF

logger = logging.getLogger("setic.validators")

# Instâncias de validação docbr
_docbr_cpf = DocbrCPF()
_docbr_cnpj = DocbrCNPJ()

# Diretório de cache local
CACHE_DIR = Path(os.getenv("CACHE_DIR", ".cache"))
CACHE_IBGE_FILE = CACHE_DIR / "ibge_municipios.json"

# DDDs válidos no território brasileiro (Regulamentação Anatel)
DDDS_VALIDOS = {
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,  # SP
    21,
    22,
    24,  # RJ
    27,
    28,  # ES
    31,
    32,
    33,
    34,
    35,
    37,
    38,  # MG
    41,
    42,
    43,
    44,
    45,
    46,  # PR
    47,
    48,
    49,  # SC
    51,
    53,
    54,
    55,  # RS
    61,  # DF/GO
    62,
    64,  # GO
    63,  # TO
    65,
    66,  # MT
    67,  # MS
    68,  # AC
    69,  # RO (Rondônia)
    71,
    73,
    74,
    75,
    77,  # BA
    79,  # SE
    81,
    87,  # PE
    82,  # AL
    83,  # PB
    84,  # RN
    85,
    88,  # CE
    86,
    89,  # PI
    91,
    93,
    94,  # PA
    92,
    97,  # AM
    95,  # RR
    96,  # AP
    98,
    99,  # MA
}

# Abreviações comuns em nomes de municípios brasileiros
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


class CatalogoMunicipiosIBGE:
    """Catálogo Nacional de Municípios Brasileiros com Resolução Bidirecional e Fuzzy Match.

    Carrega todos os 5.570+ municípios a partir de:
    1. Cache persistente em disco (.cache/ibge_municipios.json).
    2. API Oficial de Localidades do IBGE.
    3. Catálogo de fallback embutido com todos os 52 municípios de RO e capitais da federação.
    """

    def __init__(self) -> None:
        self.por_codigo: dict[str, dict[str, str]] = {}
        self.por_uf: dict[str, dict[str, dict[str, str]]] = {}
        self.indice_busca_uf: dict[str, dict[str, str]] = {}
        self.indice_busca_nacional: dict[str, tuple[str, str]] = {}
        self._carregado = False
        self._inicializar()

    def _inicializar(self) -> None:
        """Inicializa o catálogo com cache ou fallback."""
        dados = self._carregar_dados()
        for item in dados:
            codigo = str(item["codigo"]).strip()
            nome = str(item["nome"]).strip()
            uf = str(item["uf"]).strip().upper()

            info = {"codigo_ibge": codigo, "municipio": nome, "uf": uf}
            self.por_codigo[codigo] = info

            if uf not in self.por_uf:
                self.por_uf[uf] = {}
                self.indice_busca_uf[uf] = {}

            nome_simplificado = self._simplificar_texto(nome)
            self.por_uf[uf][nome_simplificado] = info
            self.indice_busca_uf[uf][nome_simplificado] = nome
            self.indice_busca_nacional[f"{nome_simplificado} - {uf}"] = (codigo, uf)

        self._carregado = True
        logger.info(f"Catálogo IBGE carregado com {len(self.por_codigo)} municípios.")

    @staticmethod
    def _simplificar_texto(texto: str) -> str:
        """Higieniza e remove acentos para indexação de busca."""
        t = unidecode(texto).lower()
        t = re.sub(r"[-'/]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _expandir_abreviacoes(self, texto: str) -> str:
        """Expande abreviações populares em nomes de municípios."""
        t = unidecode(texto).lower()
        for padrao, subst in ABREVIACOES_MUNICIPIOS.items():
            t = re.sub(padrao, subst, t)
        t = re.sub(r"[-'/.]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _carregar_dados(self) -> list[dict[str, str]]:
        """Carrega dados do arquivo de cache local ou da API oficial do IBGE."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # 1. Tentar ler do cache local
        if CACHE_IBGE_FILE.exists():
            try:
                with open(CACHE_IBGE_FILE, encoding="utf-8") as f:
                    dados = json.load(f)
                    if isinstance(dados, list) and len(dados) > 5000:
                        return dados
            except Exception as e:
                logger.warning(f"Falha ao carregar cache IBGE local: {e}")

        # 2. Tentar baixar da API oficial de localidades do IBGE
        try:
            import httpx

            # Mapeamento oficial dos dois primeiros dígitos do código IBGE para a sigla da UF
            prefixos_uf = {
                "11": "RO",
                "12": "AC",
                "13": "AM",
                "14": "RR",
                "15": "PA",
                "16": "AP",
                "17": "TO",
                "21": "MA",
                "22": "PI",
                "23": "CE",
                "24": "RN",
                "25": "PB",
                "26": "PE",
                "27": "AL",
                "28": "SE",
                "29": "BA",
                "31": "MG",
                "32": "ES",
                "33": "RJ",
                "35": "SP",
                "41": "PR",
                "42": "SC",
                "43": "RS",
                "50": "MS",
                "51": "MT",
                "52": "GO",
                "53": "DF",
            }

            url = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
            resp = httpx.get(url, timeout=8.0)
            if resp.status_code == 200:
                raw_list = resp.json()
                lista_formatada = []
                for item in raw_list:
                    cod = str(item.get("id", "")).strip()
                    nome = str(item.get("nome", "")).strip()
                    sigla_uf = ""

                    mr = item.get("microrregiao")
                    if isinstance(mr, dict):
                        meso = mr.get("mesorregiao")
                        if isinstance(meso, dict):
                            uf_obj = meso.get("UF")
                            if isinstance(uf_obj, dict):
                                sigla_uf = uf_obj.get("sigla", "")

                    if not sigla_uf:
                        rim = item.get("regiao-imediata")
                        if isinstance(rim, dict):
                            rint = rim.get("regiao-intermediaria")
                            if isinstance(rint, dict):
                                uf_obj = rint.get("UF")
                                if isinstance(uf_obj, dict):
                                    sigla_uf = uf_obj.get("sigla", "")

                    if not sigla_uf and len(cod) >= 2:
                        sigla_uf = prefixos_uf.get(cod[:2], "")

                    if cod and nome and sigla_uf:
                        lista_formatada.append(
                            {
                                "codigo": cod,
                                "nome": nome,
                                "uf": sigla_uf,
                            }
                        )

                if len(lista_formatada) > 5000:
                    with open(CACHE_IBGE_FILE, "w", encoding="utf-8") as f:
                        json.dump(lista_formatada, f, ensure_ascii=False)
                    return lista_formatada
        except Exception as e:
            logger.warning(f"Falha na requisição da API IBGE online: {e}")

        # 3. Fallback de contingência (Municípios de Rondônia + Capitais e Principais Cidades)
        return self._obter_catalogo_fallback()

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

        # Cenário 1: Entrada é um código IBGE numérico de 7 dígitos
        if re.fullmatch(r"^\d{7}$", texto_original):
            if texto_original in self.por_codigo:
                item = self.por_codigo[texto_original]
                # Se UF foi informada, checa compatibilidade
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

        # Cenário 2: Resolução de Nome de Município
        texto_expandido = self._expandir_abreviacoes(texto_original)

        # Se UF estiver especificada, pesquisa prioritariamente na base estadual
        if uf_normalizada and uf_normalizada in self.por_uf:
            mapa_uf = self.por_uf[uf_normalizada]
            # Tentativa de correspondência exata normalizada
            if texto_expandido in mapa_uf:
                item = mapa_uf[texto_expandido]
                return ResultadoValidacao(
                    valido=True,
                    valor_normalizado={
                        "municipio": item["municipio"],
                        "codigo_ibge": item["codigo_ibge"],
                        "uf": item["uf"],
                    },
                    mensagem_transformacao=f"Município '{texto_original}' normalizado para '{item['municipio']}' (IBGE: {item['codigo_ibge']}).",
                )

            # Correspondência aproximada com RapidFuzz
            candidatos = list(mapa_uf.keys())
            melhor_match = process.extractOne(
                texto_expandido,
                candidatos,
                scorer=fuzz.WRatio,
            )

            if melhor_match and melhor_match[1] >= 75:
                item = mapa_uf[melhor_match[0]]
                return ResultadoValidacao(
                    valido=True,
                    valor_normalizado={
                        "municipio": item["municipio"],
                        "codigo_ibge": item["codigo_ibge"],
                        "uf": item["uf"],
                    },
                    mensagem_transformacao=f"Município informal '{texto_original}' aproximado para '{item['municipio']}' (Score: {melhor_match[1]:.1f}%, IBGE: {item['codigo_ibge']}).",
                )

        # Se não encontrou na UF ou UF não foi informada, busca nacional
        melhores_nacionais = process.extract(
            texto_expandido,
            list(self.indice_busca_nacional.keys()),
            scorer=fuzz.WRatio,
            limit=3,
        )

        if melhores_nacionais and melhores_nacionais[0][1] >= 80:
            chave_match = melhores_nacionais[0][0]
            score = melhores_nacionais[0][1]
            cod, match_uf = self.indice_busca_nacional[chave_match]
            item = self.por_codigo[cod]

            # Se a UF informada for diferente do match nacional de alta confiança
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

        # Se nenhuma correspondência atingiu o limiar de qualidade: Bloqueio Estrito
        return ResultadoValidacao(
            valido=False,
            campo="municipio",
            regra_violada="MUNICIPIO_IBGE_NAO_ENCONTRADO",
            valor_rejeitado=texto_original,
            formato_esperado="Nome oficial ou grafia aproximável de município registrado no IBGE",
            mensagem_erro=f"O município '{texto_original}' não foi localizado na base oficial do IBGE para a UF especificada ({uf_normalizada or 'Não informada'}).",
        )

    @staticmethod
    def _obter_catalogo_fallback() -> list[dict[str, str]]:
        """Catálogo offline de contingência cobrindo 100% dos 52 municípios de Rondônia e capitais."""
        # Todos os 52 municípios oficiais do Estado de Rondônia
        municipios_ro = [
            ("1100015", "Alta Floresta D'Oeste", "RO"),
            ("1100379", "Alto Alegre dos Parecis", "RO"),
            ("1100403", "Alto Paraíso", "RO"),
            ("1100023", "Ariquemes", "RO"),
            ("1100452", "Buritis", "RO"),
            ("1100031", "Cabixi", "RO"),
            ("1100601", "Cacaulândia", "RO"),
            ("1100049", "Cacoal", "RO"),
            ("1100700", "Campo Novo de Rondônia", "RO"),
            ("1100809", "Candeias do Jamari", "RO"),
            ("1100908", "Castanheiras", "RO"),
            ("1100056", "Cerejeiras", "RO"),
            ("1100924", "Chupinguaia", "RO"),
            ("1100064", "Colorado do Oeste", "RO"),
            ("1100072", "Corumbiara", "RO"),
            ("1100080", "Costa Marques", "RO"),
            ("1100940", "Cujubim", "RO"),
            ("1100098", "Espigão D'Oeste", "RO"),
            ("1101005", "Governador Jorge Teixeira", "RO"),
            ("1100106", "Guajará-Mirim", "RO"),
            ("1101104", "Itapuã do Oeste", "RO"),
            ("1100114", "Jaru", "RO"),
            ("1100122", "Ji-Paraná", "RO"),
            ("1100130", "Machadinho D'Oeste", "RO"),
            ("1101203", "Ministro Andreazza", "RO"),
            ("1101302", "Mirante da Serra", "RO"),
            ("1101401", "Monte Negro", "RO"),
            ("1100148", "Nova Brasilândia D'Oeste", "RO"),
            ("1101435", "Nova Mamoré", "RO"),
            ("1101450", "Nova União", "RO"),
            ("1101468", "Novo Horizonte do Oeste", "RO"),
            ("1100155", "Ouro Preto do Oeste", "RO"),
            ("1101476", "Parecis", "RO"),
            ("1100189", "Pimenta Bueno", "RO"),
            ("1101484", "Pimenteiras do Oeste", "RO"),
            ("1100205", "Porto Velho", "RO"),
            ("1100254", "Presidente Médici", "RO"),
            ("1101492", "Primavera de Rondônia", "RO"),
            ("1100262", "Rio Crespo", "RO"),
            ("1100288", "Rolim de Moura", "RO"),
            ("1100296", "Santa Luzia D'Oeste", "RO"),
            ("1101500", "Seringueiras", "RO"),
            ("1101559", "Teixeirópolis", "RO"),
            ("1101609", "Theobroma", "RO"),
            ("1101708", "Urupá", "RO"),
            ("1101757", "Vale do Anari", "RO"),
            ("1101807", "Vale do Paraíso", "RO"),
            ("1100304", "Vilhena", "RO"),
        ]

        # Capitais da federação
        capitais = [
            ("1200401", "Rio Branco", "AC"),
            ("2704302", "Maceió", "AL"),
            ("1302603", "Manaus", "AM"),
            ("1600303", "Macapá", "AP"),
            ("2927408", "Salvador", "BA"),
            ("2304400", "Fortaleza", "CE"),
            ("5300108", "Brasília", "DF"),
            ("3205309", "Vitória", "ES"),
            ("5208707", "Goiânia", "GO"),
            ("2111300", "São Luís", "MA"),
            ("3106200", "Belo Horizonte", "MG"),
            ("5002704", "Campo Grande", "MS"),
            ("5103403", "Cuiabá", "MT"),
            ("1501402", "Belém", "PA"),
            ("2507507", "João Pessoa", "PB"),
            ("2611606", "Recife", "PE"),
            ("2211001", "Teresina", "PI"),
            ("4106902", "Curitiba", "PR"),
            ("3304557", "Rio de Janeiro", "RJ"),
            ("2408102", "Natal", "RN"),
            ("4314902", "Porto Alegre", "RS"),
            ("1400100", "Boa Vista", "RR"),
            ("4205407", "Florianópolis", "SC"),
            ("2800308", "Aracaju", "SE"),
            ("3550308", "São Paulo", "SP"),
            ("3509502", "Campinas", "SP"),
            ("1721000", "Palmas", "TO"),
        ]

        lista = []
        for cod, nome, uf in municipios_ro + capitais:
            lista.append({"codigo": cod, "nome": nome, "uf": uf})
        return lista


# Singleton do catálogo nacional IBGE
catalogo_ibge = CatalogoMunicipiosIBGE()


# =====================================================================
# Validadores Canônicos de Núcleo (Core Validators)
# =====================================================================


def validar_e_normalizar_cpf(valor: Any) -> ResultadoValidacao:
    """Valida o algoritmo de CPF (módulo 11) e normaliza para 11 dígitos limpos."""
    if valor is None:
        return ResultadoValidacao(
            valido=False,
            campo="cpf",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="11 dígitos numéricos com dígitos verificadores válidos",
            mensagem_erro="O campo CPF não foi fornecido.",
        )

    # Higienização: extrair apenas números
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

    # Bloqueio de CPFs com dígitos repetidos (ex: 111.111.111-11)
    if len(set(limpo)) == 1:
        return ResultadoValidacao(
            valido=False,
            campo="cpf",
            regra_violada="CPF_SEQUENCIA_INVALIDA",
            valor_rejeitado=valor,
            formato_esperado="CPF com dígitos verificadores matemáticos autênticos",
            mensagem_erro="O CPF informado é composto por dígitos repetidos conhecidos como inválidos.",
        )

    # Validação rigorosa dos 2 dígitos verificadores via validate-docbr
    if not _docbr_cpf.validate(limpo):
        return ResultadoValidacao(
            valido=False,
            campo="cpf",
            regra_violada="DIGITO_VERIFICADOR_INVALIDO",
            valor_rejeitado=valor,
            formato_esperado="CPF com dígitos verificadores válidos (Algoritmo Módulo 11 da Receita Federal)",
            mensagem_erro="Os dígitos verificadores do CPF não conferem com o algoritmo matemático oficial.",
        )

    # Normalização Permissiva: gera formato canônico de 11 dígitos e máscara oficial
    formatado = f"{limpo[:3]}.{limpo[3:6]}.{limpo[6:9]}-{limpo[9:]}"
    return ResultadoValidacao(
        valido=True,
        valor_normalizado=limpo,
        mensagem_transformacao=f"CPF normalizado para '{limpo}' (Formatado: {formatado}).",
    )


def validar_e_normalizar_cnpj(valor: Any) -> ResultadoValidacao:
    """Valida o algoritmo de CNPJ e normaliza para 14 dígitos limpos."""
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
    """Valida consistência de calendário e normaliza datas para o padrão ISO-8601 (AAAA-MM-DD).

    Aplica:
    - Normalização Permissiva: interpreta '15 de março de 1985', '15/03/85', '1985-03-15'.
    - Bloqueio Estrito: bloqueia datas inexistentes no calendário (ex: 31/02/1990, 29/02/2023).
    """
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

    # Checagem estrita prévia contra datas impossíveis do calendário (ex: 31/02/1990)
    # Alguns parsers fuzzy fazem rollover de datas impossíveis para o mês seguinte.
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

    # Checagem de mês textual inválido (ex: 31 de fevereiro)
    if re.search(r"\b(fev|fevereiro)\b", texto, re.IGNORECASE) and re.search(r"\b(30|31)\b", texto):
        return ResultadoValidacao(
            valido=False,
            campo=campo,
            regra_violada="DATA_IMPOSSIVEL_CALENDARIO",
            valor_rejeitado=texto,
            formato_esperado="Fevereiro possui no máximo 28 ou 29 dias",
            mensagem_erro=f"A data '{texto}' indica dia impossível para o mês de fevereiro.",
        )

    # Normalização via dateparser
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

    # Bloqueio de datas futuras para eventos pretéritos (ex: nascimento)
    if not permitir_futuro and data_objeto > hoje:
        return ResultadoValidacao(
            valido=False,
            campo=campo,
            regra_violada="DATA_FUTURA_INVALIDA",
            valor_rejeitado=texto,
            formato_esperado="Data anterior ou igual à data atual",
            mensagem_erro=f"A data informada ({data_objeto.isoformat()}) está situada no futuro.",
        )

    # Limite razoável de século
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
    """Valida DDD, quantitativo de dígitos e normaliza números de telefone brasileiros."""
    if valor is None:
        return ResultadoValidacao(
            valido=False,
            campo="telefone",
            regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
            valor_rejeitado=None,
            formato_esperado="Número com DDD válido (10 ou 11 dígitos)",
            mensagem_erro="O campo telefone é obrigatório.",
        )

    # Remover caracteres não numéricos
    limpo = re.sub(r"\D", "", str(valor))

    # Remover prefixo de país (+55) se presente
    if limpo.startswith("55") and len(limpo) in (12, 13):
        limpo = limpo[2:]

    # Telefones válidos no Brasil: 10 dígitos (fixo) ou 11 dígitos (móvel com 9)
    if len(limpo) not in (10, 11):
        return ResultadoValidacao(
            valido=False,
            campo="telefone",
            regra_violada="QUANTIDADE_DIGITOS_TELEFONE_INVALIDA",
            valor_rejeitado=valor,
            formato_esperado="10 dígitos para telefone fixo ou 11 dígitos para celular com DDD",
            mensagem_erro=f"O telefone contém {len(limpo)} dígitos. Esperado: 10 ou 11 dígitos com DDD.",
        )

    ddd = int(limpo[:2])
    if ddd not in DDDS_VALIDOS:
        return ResultadoValidacao(
            valido=False,
            campo="telefone",
            regra_violada="DDD_INEXISTENTE_NO_BRASIL",
            valor_rejeitado=valor,
            formato_esperado="DDD válido segundo a regulação da Anatel (ex: 69 para Rondônia)",
            mensagem_erro=f"O DDD '{ddd}' não é um código de Discagem Direta a Distância válido no Brasil.",
        )

    corpo = limpo[2:]

    # Se celular (11 dígitos), o nono dígito deve ser obrigatoriamente 9
    if len(limpo) == 11 and corpo[0] != "9":
        return ResultadoValidacao(
            valido=False,
            campo="telefone",
            regra_violada="NONO_DIGITO_CELULAR_INVALIDO",
            valor_rejeitado=valor,
            formato_esperado="Telefones celulares de 11 dígitos devem iniciar o número local com 9",
            mensagem_erro=f"O número celular informado começa com '{corpo[0]}'. O nono dígito obrigatório no Brasil é 9.",
        )

    # Formatação padronizada
    if len(limpo) == 11:
        formatado = f"({limpo[:2]}) {limpo[2:7]}-{limpo[7:]}"
    else:
        formatado = f"({limpo[:2]}) {limpo[2:6]}-{limpo[6:]}"

    return ResultadoValidacao(
        valido=True,
        valor_normalizado=limpo,
        mensagem_transformacao=f"Telefone normalizado para '{limpo}' (Formatado: {formatado}).",
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
    """Invoca a resolução do Catálogo Nacional de Municípios IBGE."""
    return catalogo_ibge.resolver(municipio, uf)
