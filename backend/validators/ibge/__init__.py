"""Módulo IBGE: Catálogo em memória e validação geográfica."""

from backend.validators.ibge.catalog import (
    CatalogoMunicipiosIBGE,
    catalogo_ibge,
    formatar_nome_municipio,
)
from backend.validators.ibge.validator import IBGEMunicipioValidator, validar_e_normalizar_municipio

__all__ = [
    "CatalogoMunicipiosIBGE",
    "IBGEMunicipioValidator",
    "catalogo_ibge",
    "formatar_nome_municipio",
    "validar_e_normalizar_municipio",
]
