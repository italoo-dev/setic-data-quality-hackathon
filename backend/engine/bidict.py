"""Estrutura de dados relacional bidirecional O(1) baseada na biblioteca multidict.

Permite agrupar campos canônicos, validadores e aliases legados com acesso O(1),
expondo propriedades diretas por entidade (ex: map.municipio.keys()) e eliminando
duplicações de chaves e verificações algorítmicas repetidas.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from multidict import MultiDict

from backend.validators.base import BaseValidator


@dataclass(frozen=True, slots=True)
class FieldGroup:
    """Grupo canônico de validação com aliases e metadados indexados."""

    canonical: str
    validator: BaseValidator
    aliases: tuple[str, ...] = ()
    aux_fields: tuple[str, ...] = ()
    sensivel: bool = False

    @property
    def all_aliases(self) -> tuple[str, ...]:
        """Retorna todos os aliases (aliases + aux_fields)."""
        return (*self.aliases, *self.aux_fields)

    @property
    def all_keys(self) -> tuple[str, ...]:
        """Retorna todas as chaves (canônica + aliases + aux_fields) do grupo."""
        return (self.canonical, *self.aliases, *self.aux_fields)

    def keys(self) -> tuple[str, ...]:
        """Retorna a tupla completa de chaves do grupo."""
        return self.all_keys

    def first_present(self, dados: Mapping[str, object]) -> str | None:
        """Retorna a primeira chave deste grupo presente nos dados brutos informados."""
        for k in self.all_keys:
            if k in dados and dados[k] is not None:
                return k
        return None

    def get_present_keys(self, dados: Mapping[str, object]) -> list[str]:
        """Retorna todas as chaves deste grupo presentes nos dados brutos informados."""
        return [k for k in self.all_keys if k in dados and dados[k] is not None]


class BiDict:
    """Mapeamento bidirecional O(1) integrando a biblioteca MultiDict em C."""

    def __init__(self) -> None:
        self._multidict: MultiDict[str] = MultiDict()
        self._key_to_group: dict[str, FieldGroup] = {}
        self._validator_to_group: dict[BaseValidator, FieldGroup] = {}
        self._canonical_to_group: dict[str, FieldGroup] = {}

    def add(
        self,
        canonical: str,
        validator: BaseValidator,
        aliases: Iterable[str] = (),
        aux_fields: Iterable[str] = (),
        sensivel: bool = False,
    ) -> FieldGroup:
        """Registra um grupo canônico com aliases e mapeamento bidirecional O(1)."""
        alias_tuple = tuple(aliases)
        aux_tuple = tuple(aux_fields)
        group = FieldGroup(
            canonical=canonical,
            validator=validator,
            aliases=alias_tuple,
            aux_fields=aux_tuple,
            sensivel=sensivel,
        )

        self._canonical_to_group[canonical] = group
        self._validator_to_group[validator] = group

        for k in group.all_keys:
            self._key_to_group[k] = group

        for alias in (*alias_tuple, *aux_tuple):
            self._multidict.add(canonical, alias)

        return group

    def add_alias(self, alias: str, target: str) -> None:
        """Adiciona dinamicamente um novo alias a um grupo canônico existente."""
        if target not in self._key_to_group:
            raise KeyError(f"Campo '{target}' não está registrado no Core Tier.")
        old_group = self._key_to_group[target]
        canonic = old_group.canonical
        new_aliases = (*old_group.aliases, alias)
        new_group = FieldGroup(
            canonical=canonic,
            validator=old_group.validator,
            aliases=new_aliases,
            aux_fields=old_group.aux_fields,
            sensivel=old_group.sensivel,
        )

        self._canonical_to_group[canonic] = new_group
        self._validator_to_group[old_group.validator] = new_group
        for k in new_group.all_keys:
            self._key_to_group[k] = new_group
        self._multidict.add(canonic, alias)

    def get(self, key: str) -> FieldGroup | None:
        """Retorna o FieldGroup associado à chave ou None em O(1)."""
        return self._key_to_group.get(key)

    def get_by_validator(self, validator: BaseValidator) -> FieldGroup | None:
        """Retorna o FieldGroup associado ao validador em O(1)."""
        return self._validator_to_group.get(validator)

    def __getitem__(self, key: str) -> FieldGroup:
        return self._key_to_group[key]

    def __contains__(self, key: object) -> bool:
        return key in self._key_to_group

    def __getattr__(self, name: str) -> FieldGroup:
        if name in self._canonical_to_group:
            return self._canonical_to_group[name]
        raise AttributeError(f"'{type(self).__name__}' não possui o grupo canônico '{name}'.")

    @property
    def multidict(self) -> MultiDict[str]:
        """Acesso à estrutura MultiDict C-accelerated subjacente."""
        return self._multidict

    @property
    def key_to_group(self) -> dict[str, FieldGroup]:
        """Acesso ao mapeamento chave -> grupo."""
        return self._key_to_group

    @property
    def campos_sensiveis(self) -> frozenset[str]:
        """Retorna o conjunto imutável de todas as chaves e aliases de grupos marcados como sensíveis."""
        return frozenset(
            k
            for grupo in self._canonical_to_group.values()
            if grupo.sensivel
            for k in grupo.all_keys
        )

    # Propriedades tipadas para acesso direto (ex: map.municipio.keys())
    @property
    def municipio(self) -> FieldGroup:
        return self._canonical_to_group["municipio"]

    @property
    def cep(self) -> FieldGroup:
        return self._canonical_to_group["cep"]

    @property
    def cpf(self) -> FieldGroup:
        return self._canonical_to_group["cpf"]

    @property
    def cnpj(self) -> FieldGroup:
        return self._canonical_to_group["cnpj"]

    @property
    def telefone(self) -> FieldGroup:
        return self._canonical_to_group["telefone"]

    @property
    def email(self) -> FieldGroup:
        return self._canonical_to_group["email"]

    @property
    def pis(self) -> FieldGroup:
        return self._canonical_to_group["pis"]

    @property
    def data(self) -> FieldGroup:
        return self._canonical_to_group["data"]
