"""Testes de Arquitetura Limpa, Pipeline e Strategy Pattern."""

from __future__ import annotations

import pytest

from backend.database import SessionLocal, init_db
from backend.domain.interfaces import (
    AuditRepositoryProtocol,
    BaseValidatorProtocol,
    PipelineStepProtocol,
    RuleRepositoryProtocol,
)
from backend.domain.models import ErroDiagnosticoItem, ExecutionContext
from backend.engine.core_tier import CoreTierStep
from backend.engine.dynamic_tier import DynamicTierStep
from backend.engine.pipeline import ValidationPipeline
from backend.repositories.audit import AuditRepository
from backend.repositories.rules import RuleRepository
from backend.validators.base import BaseValidator


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


def test_rule_repository_export_import(db):
    """Verifica isolamento e manipulação de conjuntos de regras via RuleRepository."""
    import uuid

    from backend.database import RegraValidacao

    rule_repo = RuleRepository(db)

    # Exportar regras dinâmicas
    regras_exportadas = rule_repo.exportar_regras(apenas_dinamicas=True)
    assert isinstance(regras_exportadas, list)

    campo_teste = f"contrato_ti_{uuid.uuid4().hex[:6]}"

    # Importar uma regra de teste
    regras_novas: list[dict[str, object]] = [
        {
            "campo": campo_teste,
            "nome_regra": "Padrão de Contrato de TI",
            "descricao": "Regra para testes automatizados",
            "padrao_regex": r"^TI-\d{4}$",
            "mensagem_erro": "Número de contrato inválido",
            "formato_esperado": "TI-1234",
            "obrigatorio": False,
            "ativo": True,
        }
    ]

    try:
        res_imp = rule_repo.importar_regras(regras_novas, sobrescrever=False)
        assert res_imp["sucesso"] is True
        assert res_imp["total_criadas"] == 1

        # Atualizar com sobrescrita
        regras_novas[0]["mensagem_erro"] = "Contrato deve ser TI-XXXX"
        res_imp2 = rule_repo.importar_regras(regras_novas, sobrescrever=True)
        assert res_imp2["sucesso"] is True
        assert res_imp2["total_atualizadas"] == 1
    finally:
        db.query(RegraValidacao).filter(RegraValidacao.campo == campo_teste).delete()
        db.commit()


def test_protocols_explicit_inheritance_contract(db):
    """Garante conformidade nominal e estrutural com herança explícita de Protocolos."""
    # 1. BaseValidator herda e cumpre BaseValidatorProtocol
    assert issubclass(BaseValidator, BaseValidatorProtocol)

    # 2. RuleRepository herda e cumpre RuleRepositoryProtocol
    rule_repo = RuleRepository(db)
    assert issubclass(RuleRepository, RuleRepositoryProtocol)
    assert isinstance(rule_repo, RuleRepositoryProtocol)

    # 3. AuditRepository herda e cumpre AuditRepositoryProtocol
    audit_repo = AuditRepository(db)
    assert issubclass(AuditRepository, AuditRepositoryProtocol)
    assert isinstance(audit_repo, AuditRepositoryProtocol)

    # 4. CoreTierStep e DynamicTierStep herdam e cumprem PipelineStepProtocol
    core_step = CoreTierStep()
    dynamic_step = DynamicTierStep(rule_repo)
    assert issubclass(CoreTierStep, PipelineStepProtocol)
    assert issubclass(DynamicTierStep, PipelineStepProtocol)
    assert isinstance(core_step, PipelineStepProtocol)
    assert isinstance(dynamic_step, PipelineStepProtocol)
