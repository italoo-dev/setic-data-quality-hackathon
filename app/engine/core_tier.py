"""Etapa do Núcleo Canônico Imutável do Pipeline de Validação (Core Tier Step).

Coordena as estratégias canônicas de validação e normalização permissiva
para CPF, CNPJ, datas, contatos, documentos, CEP e município/UF IBGE.
"""

from __future__ import annotations

from app.domain.interfaces import PipelineStepProtocol
from app.domain.models import ExecutionContext
from app.validators.address import CEPValidator
from app.validators.base import BaseValidator
from app.validators.cnpj import CNPJValidator
from app.validators.contact import EmailValidator, PhoneValidator
from app.validators.cpf import CPFValidator
from app.validators.datetime import DateTimeValidator
from app.validators.document import PISValidator
from app.validators.ibge import IBGEMunicipioValidator


class CoreTierStep(PipelineStepProtocol):
    """Etapa que executa validadores canônicos de núcleo sobre os dados brutos."""

    def __init__(self) -> None:
        self._validators: dict[str, BaseValidator] = {
            "cpf": CPFValidator(),
            "cnpj": CNPJValidator(),
            "telefone": PhoneValidator(),
            "email": EmailValidator(),
            "pis": PISValidator(),
            "cep": CEPValidator(),
            "municipio": IBGEMunicipioValidator(),
            "data_nascimento": DateTimeValidator(),
        }
        self._date_fields = ["data_nascimento", "data", "data_admissao"]

    def register_validator(self, field_name: str, validator: BaseValidator) -> None:
        """Registra uma nova estratégia de validação para um campo específico (OCP)."""
        self._validators[field_name] = validator

    def process(self, context: ExecutionContext) -> ExecutionContext:
        """Processa todos os campos de núcleo presentes na carga de dados brutos."""
        dados = context.dados_brutos

        # 1. Validação de CPF
        if "cpf" in dados and dados["cpf"] is not None:
            val, errs, transfs = self._validators["cpf"].validate_and_normalize(
                "cpf", dados["cpf"], context
            )
            if errs:
                context.erros.extend(errs)
            else:
                context.dados_normalizados["cpf"] = val
                context.transformacoes.extend(transfs)

        # 2. Validação de CNPJ
        if "cnpj" in dados and dados["cnpj"] is not None:
            val, errs, transfs = self._validators["cnpj"].validate_and_normalize(
                "cnpj", dados["cnpj"], context
            )
            if errs:
                context.erros.extend(errs)
            else:
                context.dados_normalizados["cnpj"] = val
                context.transformacoes.extend(transfs)

        # 3. Validação de Datas (data_nascimento, data, data_admissao)
        validador_data = self._validators.get("data_nascimento") or DateTimeValidator()
        for c_data in self._date_fields:
            if c_data in dados and dados[c_data] is not None:
                val, errs, transfs = validador_data.validate_and_normalize(
                    c_data, dados[c_data], context
                )
                if errs:
                    context.erros.extend(errs)
                else:
                    context.dados_normalizados[c_data] = val
                    context.transformacoes.extend(transfs)

        # 4. Validação de Telefone
        if "telefone" in dados and dados["telefone"] is not None:
            val, errs, transfs = self._validators["telefone"].validate_and_normalize(
                "telefone", dados["telefone"], context
            )
            if errs:
                context.erros.extend(errs)
            else:
                context.dados_normalizados["telefone"] = val
                context.transformacoes.extend(transfs)

        # 5. Validação de CEP
        if "cep" in dados and dados["cep"] is not None:
            val, errs, transfs = self._validators["cep"].validate_and_normalize(
                "cep", dados["cep"], context
            )
            if errs:
                context.erros.extend(errs)
            else:
                context.dados_normalizados["cep"] = val
                context.transformacoes.extend(transfs)

        # 6. Validação de E-mail
        if "email" in dados and dados["email"] is not None:
            val, errs, transfs = self._validators["email"].validate_and_normalize(
                "email", dados["email"], context
            )
            if errs:
                context.erros.extend(errs)
            else:
                context.dados_normalizados["email"] = val
                context.transformacoes.extend(transfs)

        # 7. Validação de PIS
        if "pis" in dados and dados["pis"] is not None:
            val, errs, transfs = self._validators["pis"].validate_and_normalize(
                "pis", dados["pis"], context
            )
            if errs:
                context.erros.extend(errs)
            else:
                context.dados_normalizados["pis"] = val
                context.transformacoes.extend(transfs)

        # 8. Validação e Normalização de Município / IBGE
        tem_muni = "municipio" in dados and dados["municipio"] is not None
        tem_ibge = "codigo_ibge" in dados and dados["codigo_ibge"] is not None
        if tem_muni or tem_ibge:
            alvo = dados.get("municipio") or dados.get("codigo_ibge")
            val, errs, transfs = self._validators["municipio"].validate_and_normalize(
                "municipio", alvo, context
            )
            if errs:
                context.erros.extend(errs)
            else:
                context.transformacoes.extend(transfs)

        # 9. Validadores customizados adicionais registrados
        for campo, validador in self._validators.items():
            if (
                campo
                not in [
                    "cpf",
                    "cnpj",
                    "telefone",
                    "email",
                    "pis",
                    "cep",
                    "municipio",
                    "data_nascimento",
                ]
                and campo in dados
                and dados[campo] is not None
            ):
                val, errs, transfs = validador.validate_and_normalize(campo, dados[campo], context)
                if errs:
                    context.erros.extend(errs)
                else:
                    context.dados_normalizados[campo] = val
                    context.transformacoes.extend(transfs)

        return context
