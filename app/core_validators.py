"""Módulo de Validadores de Núcleo (Fachada de Retrocompatibilidade).

Reexporta todos os modelos de validação atômica, utilitários e funções
canônicas a partir do pacote modular app.validators e app.domain.
"""

from app.domain.models import ResultadoValidacao
from app.validators import (
    CatalogoMunicipiosIBGE,
    catalogo_ibge,
    formatar_nome_municipio,
    validar_e_normalizar_cep,
    validar_e_normalizar_cnpj,
    validar_e_normalizar_cpf,
    validar_e_normalizar_data,
    validar_e_normalizar_email,
    validar_e_normalizar_municipio,
    validar_e_normalizar_pis,
    validar_e_normalizar_telefone,
)

__all__ = [
    "CatalogoMunicipiosIBGE",
    "ResultadoValidacao",
    "catalogo_ibge",
    "formatar_nome_municipio",
    "validar_e_normalizar_cep",
    "validar_e_normalizar_cnpj",
    "validar_e_normalizar_cpf",
    "validar_e_normalizar_data",
    "validar_e_normalizar_email",
    "validar_e_normalizar_municipio",
    "validar_e_normalizar_pis",
    "validar_e_normalizar_telefone",
]
