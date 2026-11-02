"""Etapa do Núcleo Canônico Imutável do Pipeline de Validação (Core Tier Step).

Coordena as estratégias canônicas de validação e normalização permissiva
utilizando mapeamento indexado O(1) e a biblioteca de alta performance 'multidict'
(extensão em C) para gestão e recuperação de aliases de campos legados.
"""

from __future__ import annotations

from collections.abc import Iterable

from multidict import MultiDict

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
        self.ibge_validator = IBGEMunicipioValidator()
        self._validators: dict[str, BaseValidator] = {}
        self._canonical: dict[str, str] = {}
        self._canonical_by_validator: dict[BaseValidator, str] = {}
        self._aliases_by_canonical: MultiDict[str] = MultiDict()

        self._registrar_padroes()

    def _registrar_padroes(self) -> None:
        regras: tuple[tuple[BaseValidator, str, tuple[str, ...]], ...] = (
            (
                CEPValidator(),
                "cep",
                (
                    "codigo_postal",
                    "postal_code",
                    "end_cep",
                    "cep_residencia",
                    "cep_estabelecimento",
                ),
            ),
            (
                CPFValidator(),
                "cpf",
                ("num_cpf", "numero_cpf", "documento_cpf", "cpf_cnpj"),
            ),
            (
                CNPJValidator(),
                "cnpj",
                ("num_cnpj", "numero_cnpj", "documento_cnpj"),
            ),
            (
                PhoneValidator(),
                "telefone",
                ("telefone_contato", "celular", "fone", "tel", "telefone_fixo", "telefone_celular"),
            ),
            (
                EmailValidator(),
                "email",
                ("correio_eletronico", "e_mail", "email_contato", "email_funcional"),
            ),
            (
                PISValidator(),
                "pis",
                ("pis_pasep", "pasep", "nis", "numero_pis"),
            ),
            (
                DateTimeValidator(),
                "data",
                (
                    "data_nascimento",
                    "data_admissao",
                    "data_fundacao",
                    "data_evento",
                    "data_expedicao",
                    "data_registro",
                ),
            ),
            (
                self.ibge_validator,
                "municipio",
                ("cidade", "nome_municipio", "codigo_ibge", "cod_ibge"),
            ),
        )
        for validador, canonic, aliases in regras:
            self.register(canonic, validador, aliases)

    def register(
        self,
        canonical: str,
        validator: BaseValidator,
        aliases: Iterable[str] = (),
    ) -> None:
        """Mapeia um campo canônico e seus aliases legados para um único validador em O(1)."""
        self._validators[canonical] = validator
        self._canonical[canonical] = canonical
        self._canonical_by_validator[validator] = canonical

        for alias in aliases:
            self._validators[alias] = validator
            self._canonical[alias] = canonical
            self._aliases_by_canonical.add(canonical, alias)

    def register_validator(
        self,
        field_name: str,
        validator: BaseValidator,
        aliases: Iterable[str] | None = None,
    ) -> None:
        """Registra uma nova estratégia de validação para um campo e aliases opcionais (OCP)."""
        self.register(field_name, validator, aliases or ())

    def add_alias(self, alias: str, target: str) -> None:
        """Adiciona um novo alias de campo legado apontando para um campo canônico existente em O(1)."""
        if target not in self._validators:
            raise KeyError(f"Campo '{target}' não está registrado no Core Tier.")
        validator = self._validators[target]
        canonic = self._canonical[target]
        self._validators[alias] = validator
        self._canonical[alias] = canonic
        self._aliases_by_canonical.add(canonic, alias)

    @property
    def validators(self) -> dict[str, BaseValidator]:
        """Acesso direto ao dicionário de validadores por campo/alias."""
        return self._validators

    @property
    def aliases_by_canonical(self) -> MultiDict[str]:
        """Acesso à estrutura MultiDict C-accelerated de aliases por campo canônico."""
        return self._aliases_by_canonical

    def get_canonical_field(self, field_or_validator: str | BaseValidator) -> str | None:
        """Retorna o campo canônico em tempo O(1) a partir do campo ou do validador."""
        if isinstance(field_or_validator, str):
            return self._canonical.get(field_or_validator)
        return self._canonical_by_validator.get(field_or_validator)

    def get_aliases(self, field_or_validator: str | BaseValidator) -> list[str]:
        """Retorna todas as chaves e aliases associados em tempo O(1)."""
        canonic = self.get_canonical_field(field_or_validator)
        if not canonic:
            return []
        aliases = list(self._aliases_by_canonical.getall(canonic, ()))
        if canonic not in aliases:
            aliases.insert(0, canonic)
        return aliases

    def process(self, context: ExecutionContext) -> ExecutionContext:
        """Processa todos os campos de núcleo presentes na carga de dados brutos."""
        dados = context.dados_brutos

        # 1. Agrupa os campos presentes na entrada pelo seu validador correspondente em O(1)
        por_validador: dict[BaseValidator, list[str]] = {}
        for campo in dados:
            if dados[campo] is not None and campo in self._validators:
                validador = self._validators[campo]
                por_validador.setdefault(validador, []).append(campo)

        # 2. Processamento de Município / IBGE (resolução composta de município, UF e código IBGE)
        if self.ibge_validator in por_validador:
            chaves_ibge = por_validador.pop(self.ibge_validator)
            alvo_chave = next(
                (
                    k
                    for k in ("municipio", "cidade", "nome_municipio", "codigo_ibge")
                    if k in chaves_ibge
                ),
                chaves_ibge[0],
            )
            alvo_valor = dados[alvo_chave]
            val, errs, transfs = self.ibge_validator.validate_and_normalize(
                alvo_chave, alvo_valor, context
            )
            if errs:
                context.erros.extend(errs)
            else:
                context.transformacoes.extend(transfs)
                if isinstance(val, dict):
                    nome_muni = str(val.get("municipio", ""))
                    for k in chaves_ibge:
                        if k not in ("codigo_ibge", "cod_ibge"):
                            context.dados_normalizados[k] = nome_muni

        # 3. Processamento de todos os demais validadores registrados
        for validador, campos in por_validador.items():
            canonical_key = self._canonical_by_validator.get(validador)
            for campo in campos:
                val, errs, transfs = validador.validate_and_normalize(campo, dados[campo], context)
                if errs:
                    context.erros.extend(errs)
                else:
                    context.dados_normalizados[campo] = val
                    context.transformacoes.extend(transfs)
                    if (
                        canonical_key
                        and canonical_key not in context.dados_normalizados
                        and (len(campos) == 1 or canonical_key in dados)
                    ):
                        context.dados_normalizados[canonical_key] = val

        return context
