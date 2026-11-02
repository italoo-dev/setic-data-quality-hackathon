"""Etapa do Núcleo Canônico Imutável do Pipeline de Validação (Core Tier Step).

Coordena as estratégias canônicas de validação e normalização permissiva
para CPF, CNPJ, datas, contatos, documentos, CEP e município/UF IBGE.
"""

from __future__ import annotations

from backend.domain.interfaces import PipelineStepProtocol
from backend.domain.models import ExecutionContext
from backend.validators.address import CEPValidator
from backend.validators.base import BaseValidator
from backend.validators.cnpj import CNPJValidator
from backend.validators.contact import EmailValidator, PhoneValidator
from backend.validators.cpf import CPFValidator
from backend.validators.datetime import DateTimeValidator
from backend.validators.document import PISValidator
from backend.validators.ibge import IBGEMunicipioValidator


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

        # 1. Validação genérica para campos mapeados diretamente
        campos_diretos = [c for c in self._validators if c not in ("data_nascimento", "municipio")]
        for campo in campos_diretos:
            if campo in dados and dados[campo] is not None:
                val, errs, transfs = self._validators[campo].validate_and_normalize(
                    campo, dados[campo], context
                )
                if errs:
                    context.erros.extend(errs)
                else:
                    context.dados_normalizados[campo] = val
                    context.transformacoes.extend(transfs)

        # 2. Validação de Datas (data_nascimento, data, data_admissao)
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

        # 3. Validação e Normalização de Município / IBGE
        tem_muni = "municipio" in dados and dados["municipio"] is not None
        tem_ibge = "codigo_ibge" in dados and dados["codigo_ibge"] is not None
        if (tem_muni or tem_ibge) and "municipio" in self._validators:
            alvo = dados.get("municipio") or dados.get("codigo_ibge")
            val, errs, transfs = self._validators["municipio"].validate_and_normalize(
                "municipio", alvo, context
            )
            if errs:
                context.erros.extend(errs)
            else:
                context.transformacoes.extend(transfs)

        return context
