"""Testes unitários para o CoreTierStep com MultiDict de alta performance.

Garante o funcionamento de consultas em tempo O(1), suporte a aliases de sistemas legados
e integridade de normalização e diagnósticos de erro.
"""

from __future__ import annotations

import brutils
import pytest
from multidict import MultiDict

from backend.domain.models import ErroDiagnosticoItem, ExecutionContext
from backend.engine.core_tier import CoreTierStep
from backend.validators.address import CEPValidator
from backend.validators.base import BaseValidator
from backend.validators.cpf import CPFValidator


def test_core_tier_multidict_lookup():
    """Valida o mapeamento N:1 de chaves e o uso de MultiDict C-accelerated no CoreTierStep."""
    step = CoreTierStep()

    # 1. Estrutura de aliases em C (MultiDict)
    assert isinstance(step.aliases_by_canonical, MultiDict)
    aliases_cep = step.get_aliases("cep")
    assert "cep" in aliases_cep
    assert "codigo_postal" in aliases_cep
    assert "postal_code" in aliases_cep

    # 2. Resolução direta O(1) de múltiplos aliases para a mesma instância de validador
    assert isinstance(step.validators["cep"], CEPValidator)
    assert step.validators["codigo_postal"] is step.validators["cep"]
    assert step.validators["postal_code"] is step.validators["cep"]
    assert isinstance(step.validators["cpf"], CPFValidator)
    assert step.validators["num_cpf"] is step.validators["cpf"]

    # 3. Resolução O(1) do campo canônico (tanto por string quanto por instância do validador)
    assert step.get_canonical_field(step.validators["cep"]) == "cep"
    assert step.get_canonical_field(step.validators["cpf"]) == "cpf"
    assert step.get_canonical_field("codigo_postal") == "cep"
    assert step.get_canonical_field("num_cpf") == "cpf"
    assert step.get_canonical_field("inexistente") is None


def test_core_tier_legacy_cep_aliases_and_canonical_propagation():
    """Verifica se campos de CEP legados (codigo_postal, end_cep) são processados e normalizados."""
    step = CoreTierStep()

    # Cenário 1: Legacy 'codigo_postal' válido
    ctx1 = ExecutionContext(
        sistema_origem="LEGADO_SISTEMA_A",
        protocolo="prot-cep-1",
        dados_brutos={"codigo_postal": "76801-000"},
    )
    res1 = step.process(ctx1)
    assert res1.sucesso is True
    # Mantém o campo do legado E propaga para a chave canônica 'cep'
    assert res1.dados_normalizados["codigo_postal"] == "76801000"
    assert res1.dados_normalizados["cep"] == "76801000"

    # Cenário 2: Legacy 'end_cep' válido
    ctx2 = ExecutionContext(
        sistema_origem="LEGADO_SISTEMA_B",
        protocolo="prot-cep-2",
        dados_brutos={"end_cep": "76.801-000"},
    )
    res2 = step.process(ctx2)
    assert res2.sucesso is True
    assert res2.dados_normalizados["end_cep"] == "76801000"
    assert res2.dados_normalizados["cep"] == "76801000"

    # Cenário 3: Legacy 'postal_code' inválido -> diagnóstico deve reportar o nome do campo legado
    ctx3 = ExecutionContext(
        sistema_origem="LEGADO_SISTEMA_C",
        protocolo="prot-cep-3",
        dados_brutos={"postal_code": "1234"},
    )
    res3 = step.process(ctx3)
    assert res3.sucesso is False
    assert len(res3.erros) == 1
    assert res3.erros[0].campo == "postal_code"
    assert res3.erros[0].regra_violada == "FORMATO_CEP_INVALIDO"


def test_core_tier_legacy_cpf_phone_email_and_date_aliases():
    """Verifica processamento de múltiplos campos legados no mesmo payload."""
    step = CoreTierStep()
    pis_valido = brutils.generate_pis()

    ctx = ExecutionContext(
        sistema_origem="LEGADO_ADMINISTRATIVO",
        protocolo="prot-legado-completo",
        dados_brutos={
            "num_cpf": "117.941.016-59",
            "celular": "(69) 99234-5678",
            "correio_eletronico": "cidadao@rondonia.gov.br",
            "data_admissao": "10 de maio de 2020",
            "cidade": "p. velho",
            "uf": "RO",
            "codigo_postal": "76801-000",
            "pis_pasep": pis_valido,
        },
    )

    res = step.process(ctx)
    assert res.sucesso is True

    # Campos legados presentes normalizados
    assert res.dados_normalizados["num_cpf"] == "11794101659"
    assert res.dados_normalizados["celular"] == "69992345678"
    assert res.dados_normalizados["correio_eletronico"] == "cidadao@rondonia.gov.br"
    assert res.dados_normalizados["data_admissao"] == "2020-05-10"
    assert res.dados_normalizados["cidade"] == "Porto Velho"
    assert res.dados_normalizados["codigo_postal"] == "76801000"
    assert res.dados_normalizados["pis_pasep"] == pis_valido

    # Chaves canônicas propagadas
    assert res.dados_normalizados["cpf"] == "11794101659"
    assert res.dados_normalizados["telefone"] == "69992345678"
    assert res.dados_normalizados["email"] == "cidadao@rondonia.gov.br"
    assert res.dados_normalizados["municipio"] == "Porto Velho"
    assert res.dados_normalizados["codigo_ibge"] == "1100205"
    assert res.dados_normalizados["cep"] == "76801000"
    assert res.dados_normalizados["pis"] == pis_valido


def test_core_tier_dynamic_alias_registration():
    """Verifica cadastro dinâmico de novos aliases via add_alias e register_validator."""
    step = CoreTierStep()

    # Adiciona novo alias legado para o CEP canônico existente
    step.add_alias("cep_entrega", "cep")
    assert step.validators["cep_entrega"] is step.validators["cep"]

    ctx_alias = ExecutionContext(
        sistema_origem="TESTE_ALIAS",
        protocolo="prot-alias",
        dados_brutos={"cep_entrega": "76801-000"},
    )
    res_alias = step.process(ctx_alias)
    assert res_alias.sucesso is True
    assert res_alias.dados_normalizados["cep_entrega"] == "76801000"
    assert res_alias.dados_normalizados["cep"] == "76801000"

    # Erro ao associar alias a campo inexistente
    with pytest.raises(KeyError):
        step.add_alias("invalido", "campo_que_nao_existe")

    # Registro de novo validador customizado com lista de chaves N:1 (OCP)
    class CustomSectorValidator(BaseValidator):
        def validate_and_normalize(
            self,
            field_name: str,
            value: object,
            context: ExecutionContext,
        ) -> tuple[object, list[ErroDiagnosticoItem], list[str]]:
            if value == "SEC-GOV":
                return "SETIC-RO", [], ["Setor mapeado para SETIC."]
            return (
                value,
                [
                    self.build_diagnostic_error(
                        campo=field_name,
                        regra_violada="SETOR_INVALIDO",
                        valor_rejeitado=value,
                        formato_esperado="SEC-GOV",
                        mensagem="Setor inválido.",
                    )
                ],
                [],
            )

    sector_validator = CustomSectorValidator()
    step.register_validator(
        "setor",
        sector_validator,
        aliases=["lotacao", "unidade_administrativa"],
    )

    # Validação reversa
    assert step.get_canonical_field(sector_validator) == "setor"
    assert set(step.get_aliases(sector_validator)) == {
        "setor",
        "lotacao",
        "unidade_administrativa",
    }

    # Validação via alias 'unidade_administrativa'
    ctx_setor = ExecutionContext(
        sistema_origem="TESTE_SETOR",
        protocolo="prot-setor",
        dados_brutos={"unidade_administrativa": "SEC-GOV"},
    )
    res_setor = step.process(ctx_setor)
    assert res_setor.sucesso is True
    assert res_setor.dados_normalizados["unidade_administrativa"] == "SETIC-RO"
    assert res_setor.dados_normalizados["setor"] == "SETIC-RO"
