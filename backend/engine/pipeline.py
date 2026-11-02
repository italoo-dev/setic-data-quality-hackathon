"""Orquestrador do Pipeline de Validação e Normalização (Pipeline Pattern).

Coordena sequencialmente:
1. CoreTierStep: Regras de núcleo imutáveis e padronização canônica.
2. DynamicTierStep: Regras dinâmicas cadastradas no PostgreSQL pela CAGD.
3. Telemetria: Registro transacional de auditoria para cálculo de KPIs e métricas.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping

from backend.domain.interfaces import (
    AuditRepositoryProtocol,
    RuleRepositoryProtocol,
)
from backend.domain.models import ExecutionContext, ResultadoMotor
from backend.engine.core_tier import CoreTierStep
from backend.engine.dynamic_tier import DynamicTierStep


class ValidationPipeline:
    """Pipeline orquestrador de etapas de validação e normalização."""

    def __init__(
        self,
        rule_repo: RuleRepositoryProtocol,
        audit_repo: AuditRepositoryProtocol,
    ) -> None:
        self.rule_repo = rule_repo
        self.audit_repo = audit_repo
        self.core_step = CoreTierStep()
        self.dynamic_step = DynamicTierStep(rule_repo)

    def execute(
        self,
        dados_entrada: Mapping[str, object],
        sistema_origem: str,
    ) -> ResultadoMotor:
        """Executa sequencialmente todas as etapas do pipeline e persiste a auditoria."""
        inicio = time.perf_counter()
        protocolo = str(uuid.uuid4())
        dados_dict = dict(dados_entrada)

        context = ExecutionContext(
            sistema_origem=sistema_origem,
            protocolo=protocolo,
            dados_brutos=dados_dict,
            dados_normalizados=dict(dados_entrada),
            inicio_tempo=inicio,
        )

        context = self.core_step.process(context)
        context = self.dynamic_step.process(context)

        tempo_processamento_ms = round((time.perf_counter() - inicio) * 1000.0, 2)
        context.tempo_processamento_ms = tempo_processamento_ms

        sucesso = context.sucesso
        status_http = 200 if sucesso else 422
        dados_norm = context.dados_normalizados if sucesso else None
        erros_dict = [e.to_dict() for e in context.erros] if context.erros else None

        # Persistência transacional de auditoria (DIP)
        self.audit_repo.salvar_registro(
            protocolo=protocolo,
            sistema_origem=sistema_origem,
            sucesso=sucesso,
            status_http=status_http,
            dados_entrada=dados_dict,
            dados_normalizados=dados_norm,
            erros=erros_dict,
            tempo_processamento_ms=tempo_processamento_ms,
        )

        return ResultadoMotor(
            sucesso=sucesso,
            protocolo=protocolo,
            status_http=status_http,
            sistema_origem=sistema_origem,
            dados_normalizados=dados_norm,
            erros=context.erros,
            transformacoes=context.transformacoes,
            tempo_processamento_ms=tempo_processamento_ms,
        )
