"""Catálogo Nacional de Municípios Brasileiros (IBGE).

Carrega e indexa em memória todos os 5.570 municípios brasileiros a partir do
arquivo canônico empacotado 'data/cities_code.json' da biblioteca brutils.
Garante operação 100% autônoma, offline, determinística e de alta performance.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from importlib.resources import files

import brutils

logger = logging.getLogger("setic.validators.ibge")

_MAPA_ABREVIACOES = {
    "p": "porto",
    "sto": "santo",
    "sta": "santa",
    "s": "sao",
    "pres": "presidente",
    "gov": "governador",
    "cel": "coronel",
    "dr": "doutor",
    "prof": "professor",
    "mal": "marechal",
    "gal": "general",
}
_RE_ABREVIACOES = re.compile(
    r"\b(p|sto|sta|s|pres|gov|cel|dr|prof|mal|gal)\.",
    re.IGNORECASE,
)


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
    """Índice em memória de todos os municípios do Brasil alimentado por brutils."""

    def __init__(self) -> None:
        self.por_codigo: dict[str, dict[str, str]] = {}
        self.por_uf: dict[str, dict[str, str]] = {}
        self.indice_nacional: dict[str, tuple[str, str, str]] = {}
        self._inicializar()

    def _inicializar(self) -> None:
        """Carrega os dados diretamente do arquivo cities_code.json em brutils."""
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
    def expandir_e_normalizar(texto: str) -> str:
        """Normaliza texto expandindo abreviações populares e removendo pontuações."""
        sem_acento = "".join(
            c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
        ).lower()
        expandido = _RE_ABREVIACOES.sub(lambda m: _MAPA_ABREVIACOES[m.group(1).lower()], sem_acento)
        limpo = re.sub(r"[-'/.]", " ", expandido)
        return re.sub(r"\s+", " ", limpo).strip()

    @staticmethod
    def normalizar_uf(uf_bruta: str | None) -> str | None:
        """Normaliza a sigla da UF, convertendo nome por extenso via brutils se necessário."""
        if not uf_bruta:
            return None
        texto = uf_bruta.strip()
        if len(texto) == 2:
            return texto.upper()
        sigla = brutils.convert_name_to_uf(texto)
        return sigla.upper() if sigla else texto.upper()


# Instância singleton do catálogo em memória
catalogo_ibge = CatalogoMunicipiosIBGE()
