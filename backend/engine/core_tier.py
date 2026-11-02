"""Etapa do Núcleo Canônico Imutável do Pipeline de Validação (Core Tier Step).

Coordena as estratégias canônicas de validação e normalização permissiva
utilizando a estrutura relacional bidict baseada em MultiDict (C),
eliminando repetição de código e permitindo consultas diretas por entidade (ex: map.municipio.keys()).
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.domain.interfaces import PipelineStepProtocol
from backend.domain.models import ExecutionContext
from backend.engine.bidict import BiDict, FieldGroup
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
        self.cpf_validator = CPFValidator()
        self.cnpj_validator = CNPJValidator()
        self.phone_validator = PhoneValidator()
        self.email_validator = EmailValidator()
        self.pis_validator = PISValidator()
        self.cep_validator = CEPValidator()
        self.datetime_validator = DateTimeValidator()

        # Estrutura relacional bidirecional O(1) com suporte a MultiDict C-accelerated
        self.map = BiDict()

        self._registrar_padroes()

    def _registrar_padroes(self) -> None:
        padroes: list[tuple[str, BaseValidator, tuple[str, ...], tuple[str, ...]]] = [
            (
                "cep",
                self.cep_validator,
                (
                    "codigo_postal",
                    "postal_code",
                    "end_cep",
                    "cep_residencia",
                    "cep_estabelecimento",
                ),
                (),
            ),
            (
                "cpf",
                self.cpf_validator,
                ("num_cpf", "numero_cpf", "documento_cpf", "cpf_cnpj"),
                (),
            ),
            (
                "cnpj",
                self.cnpj_validator,
                ("num_cnpj", "numero_cnpj", "documento_cnpj"),
                (),
            ),
            (
                "telefone",
                self.phone_validator,
                (
                    "telefone_contato",
                    "celular",
                    "fone",
                    "tel",
                    "telefone_fixo",
                    "telefone_celular",
                ),
                (),
            ),
            (
                "email",
                self.email_validator,
                ("correio_eletronico", "e_mail", "email_contato", "email_funcional"),
                (),
            ),
            (
                "pis",
                self.pis_validator,
                ("pis_pasep", "pasep", "nis", "numero_pis"),
                (),
            ),
            (
                "data",
                self.datetime_validator,
                (
                    "data_nascimento",
                    "data_admissao",
                    "data_fundacao",
                    "data_evento",
                    "data_expedicao",
                    "data_registro",
                ),
                (),
            ),
            (
                "municipio",
                self.ibge_validator,
                ("cidade", "nome_municipio"),
                ("codigo_ibge", "cod_ibge"),
            ),
        ]
        for canonical, validator, aliases, aux_fields in padroes:
            self.map.add(
                canonical=canonical,
                validator=validator,
                aliases=aliases,
                aux_fields=aux_fields,
            )

    def register_validator(
        self,
        field_name: str,
        validator: BaseValidator,
        aliases: Iterable[str] | None = None,
    ) -> None:
        """Registra uma nova estratégia de validação para um campo e aliases opcionais (OCP)."""
        self.map.add(canonical=field_name, validator=validator, aliases=aliases or ())

    def add_alias(self, alias: str, target: str) -> None:
        """Adiciona um novo alias de campo legado apontando para um campo existente em O(1)."""
        self.map.add_alias(alias=alias, target=target)

    def get_canonical_field(self, field_or_validator: str | BaseValidator) -> str | None:
        """Retorna o campo canônico a partir do campo ou do validador em tempo O(1)."""
        if isinstance(field_or_validator, str):
            group = self.map.get(field_or_validator)
            return group.canonical if group else None
        group = self.map.get_by_validator(field_or_validator)
        return group.canonical if group else None

    def get_aliases(self, field_or_validator: str | BaseValidator) -> list[str]:
        """Retorna todas as chaves e aliases associados em tempo O(1)."""
        if isinstance(field_or_validator, str):
            group = self.map.get(field_or_validator)
            return list(group.keys()) if group else []
        group = self.map.get_by_validator(field_or_validator)
        return list(group.keys()) if group else []

    def process(self, context: ExecutionContext) -> ExecutionContext:
        """Processa todos os campos de núcleo presentes na carga de dados brutos."""
        dados = context.dados_brutos

        # 1. Agrupa os campos presentes na entrada por grupo canônico em O(1)
        grupos_presentes: dict[FieldGroup, list[str]] = {}
        for campo in dados:
            if dados[campo] is not None and campo in self.map:
                grupo = self.map[campo]
                grupos_presentes.setdefault(grupo, []).append(campo)

        # 2. Município / IBGE: resolução composta reutilizando o próprio grupo da entidade
        muni_grupo = self.map.municipio
        if muni_grupo in grupos_presentes:
            chaves_ibge = grupos_presentes.pop(muni_grupo)
            alvo_chave = muni_grupo.first_present(dados) or chaves_ibge[0]
            alvo_valor = dados[alvo_chave]

            val, errs, transfs = muni_grupo.validator.validate_and_normalize(
                alvo_chave, alvo_valor, context
            )
            if errs:
                context.erros.extend(errs)
            else:
                context.transformacoes.extend(transfs)
                if isinstance(val, dict):
                    nome_muni = str(val.get("municipio", ""))
                    for k in chaves_ibge:
                        if k not in muni_grupo.aux_fields:
                            context.dados_normalizados[k] = nome_muni

        # 3. Processamento de todos os demais grupos canônicos registrados
        for grupo, campos in grupos_presentes.items():
            canonic = grupo.canonical
            for campo in campos:
                val, errs, transfs = grupo.validator.validate_and_normalize(
                    campo, dados[campo], context
                )
                if errs:
                    context.erros.extend(errs)
                else:
                    context.dados_normalizados[campo] = val
                    context.transformacoes.extend(transfs)
                    if canonic not in context.dados_normalizados and (
                        len(campos) == 1 or canonic in dados
                    ):
                        context.dados_normalizados[canonic] = val

        return context
