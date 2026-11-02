"""Módulo de Validadores Canônicos de Núcleo (Strategy Pattern).

Disponibiliza estratégias desacopladas para cada domínio de identificador,
contato, endereço, temporal e geográfico nacional.
"""

from app.validators.address import CEPValidator, validar_e_normalizar_cep
from app.validators.base import BaseValidator
from app.validators.cnpj import CNPJValidator, validar_e_normalizar_cnpj
from app.validators.contact import (
    EmailValidator,
    PhoneValidator,
    validar_e_normalizar_email,
    validar_e_normalizar_telefone,
)
from app.validators.cpf import CPFValidator, validar_e_normalizar_cpf
from app.validators.datetime import DateTimeValidator, validar_e_normalizar_data
from app.validators.document import PISValidator, validar_e_normalizar_pis
from app.validators.ibge import (
    CatalogoMunicipiosIBGE,
    IBGEMunicipioValidator,
    catalogo_ibge,
    formatar_nome_municipio,
    validar_e_normalizar_municipio,
)

__all__ = [
    "BaseValidator",
    "CEPValidator",
    "CNPJValidator",
    "CPFValidator",
    "CatalogoMunicipiosIBGE",
    "DateTimeValidator",
    "EmailValidator",
    "IBGEMunicipioValidator",
    "PISValidator",
    "PhoneValidator",
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
