"""Testes de Arquitetura Limpa, Pipeline e Strategy Pattern."""

from __future__ import annotations

import pytest

from app.database import SessionLocal, init_db
from app.domain.models import ErroDiagnosticoItem, ExecutionContext
from app.engine.core_tier import CoreTierStep
from app.engine.pipeline import ValidationPipeline
from app.repositories.audit import AuditRepository
from app.repositories.rules import RuleRepository
from app.validators.base import BaseValidator


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Garante tabelas inicializadas para os testes de arquitetura."""
    init_db()


@pytest.fixture
def db():
    """Sessão isolada de teste."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_strategy_pattern_registration_ocp():
    """Verifica se novas estratégias de validação podem ser registradas no CoreTierStep (OCP)."""

    class CustomDocValidator(BaseValidator):
        def validate_and_normalize(
            self,
            field_name: str,
            value: object,
            context: ExecutionContext,
        ) -> tuple[object, list[ErroDiagnosticoItem], list[str]]:
            if value == "CUSTOM-OK":
                return "NORMALIZED-CUSTOM", [], ["Custom doc normalizado."]
            return (
                value,
                [
                    self.build_diagnostic_error(
                        campo=field_name,
                        regra_violada="CUSTOM_DOC_INVALIDO",
                        valor_rejeitado=value,
                        formato_esperado="CUSTOM-OK",
                        mensagem="Formato customizado rejeitado.",
                    )
                ],
                [],
            )

    core_step = CoreTierStep()
    core_step.register_validator("documento_customizado", CustomDocValidator())

    # Cenário Válido
    ctx_valido = ExecutionContext(
        sistema_origem="TESTE_OCP",
        protocolo="uuid-teste-1",
        dados_brutos={"documento_customizado": "CUSTOM-OK"},
    )
    res_valido = core_step.process(ctx_valido)
    assert res_valido.sucesso is True
    assert res_valido.dados_normalizados["documento_customizado"] == "NORMALIZED-CUSTOM"

    # Cenário Inválido
    ctx_invalido = ExecutionContext(
        sistema_origem="TESTE_OCP",
        protocolo="uuid-teste-2",
        dados_brutos={"documento_customizado": "VALOR-ERRADO"},
    )
    res_invalido = core_step.process(ctx_invalido)
    assert res_invalido.sucesso is False
    assert res_invalido.erros[0].regra_violada == "CUSTOM_DOC_INVALIDO"


def test_repository_pattern_rule_isolation(db):
    """Verifica isolamento e métodos do RuleRepository."""
    repo = RuleRepository(db)
    regras = repo.listar_todas()
    assert len(regras) >= 3

    regras_dinamicas = repo.listar_ativas_dinamicas()
    # Todas devem ter eh_imutavel == False
    for r in regras_dinamicas:
        assert r.eh_imutavel is False


def test_repository_pattern_audit_metrics(db):
    """Verifica o cálculo de métricas operacionais no AuditRepository."""
    audit_repo = AuditRepository(db)
    metricas = audit_repo.obter_metricas_cagd()
    assert metricas.total_requisicoes >= 0
    assert metricas.taxa_rejeicao_percentual >= 0
    assert isinstance(metricas.volume_por_sistema, list)


def test_pipeline_pattern_end_to_end_orchestration(db):
    """Verifica a execução orquestrada do ValidationPipeline conectando Core e Dynamic tiers."""
    rule_repo = RuleRepository(db)
    audit_repo = AuditRepository(db)
    pipeline = ValidationPipeline(rule_repo=rule_repo, audit_repo=audit_repo)

    payload = {
        "cpf": "117.941.016-59",
        "data_nascimento": "10 de outubro de 1995",
        "municipio": "porto velho",
        "uf": "RO",
        "matricula_funcional": "RO-654321",
    }

    resultado = pipeline.execute(dados_entrada=payload, sistema_origem="SISTEMA_RH")
    assert resultado.sucesso is True
    assert resultado.dados_normalizados is not None
    assert resultado.dados_normalizados["cpf"] == "11794101659"
    assert resultado.dados_normalizados["data_nascimento"] == "1995-10-10"
    assert resultado.dados_normalizados["codigo_ibge"] == "1100205"
    assert resultado.tempo_processamento_ms > 0
