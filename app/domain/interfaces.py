"""Protocolos e Interfaces de Domínio (Interface Segregation & Dependency Inversion).

Estabelece contratos estritos que desacoplam os validadores, repositórios de
persistência e etapas orquestradas do pipeline de execução.
"""

from __future__ import annotations

from typing import Protocol

from app.database import RegistroAuditoria, RegraValidacao
from app.domain.models import ErroDiagnosticoItem, ExecutionContext
from app.schemas import MetricasOperacionaisCAGD


class BaseValidatorProtocol(Protocol):
    """Contrato que todo validador concreto de campo deve implementar (Strategy Pattern)."""

    def validate_and_normalize(
        self,
        field_name: str,
        value: object,
        context: ExecutionContext,
    ) -> tuple[object, list[ErroDiagnosticoItem], list[str]]:
        """Executa a validação e normalização do campo.

        Retorna:
            tuple[object, list[ErroDiagnosticoItem], list[str]]:
                - valor normalizado (ou o original caso haja falha)
                - lista de erros diagnósticos detectados
                - lista de mensagens descritivas das transformações realizadas
        """
        ...


class PipelineStepProtocol(Protocol):
    """Contrato de uma etapa executável dentro do ValidationPipeline."""

    def process(self, context: ExecutionContext) -> ExecutionContext:
        """Executa a etapa de processamento sobre o contexto de validação."""
        ...


class AuditRepositoryProtocol(Protocol):
    """Contrato de persistência e telemetria operacional de auditoria."""

    def salvar_registro(
        self,
        protocolo: str,
        sistema_origem: str,
        sucesso: bool,
        status_http: int,
        dados_entrada: dict[str, object],
        dados_normalizados: dict[str, object] | None,
        erros: list[dict[str, object]] | None,
        tempo_processamento_ms: float,
    ) -> RegistroAuditoria:
        """Persiste atomicamente uma transação auditável."""
        ...

    def obter_metricas_cagd(self) -> MetricasOperacionaisCAGD:
        """Calcula os indicadores operacionais agregados para a CAGD."""
        ...

    def listar_registros(
        self,
        sistema_origem: str | None = None,
        sucesso: bool | None = None,
        limite: int = 50,
    ) -> list[RegistroAuditoria]:
        """Recupera registros históricos ordenados decrescentemente."""
        ...


class RuleRepositoryProtocol(Protocol):
    """Contrato de persistência e gestão de regras dinâmicas de validação."""

    def listar_ativas_dinamicas(self) -> list[RegraValidacao]:
        """Recupera regras ativas não imutáveis para execução no pipeline dinâmico."""
        ...

    def listar_todas(
        self,
        campo: str | None = None,
        apenas_ativas: bool = False,
    ) -> list[RegraValidacao]:
        """Recupera todas as regras cadastradas (núcleo e dinâmicas)."""
        ...

    def obter_por_id(self, regra_id: int) -> RegraValidacao | None:
        """Recupera uma regra específica pelo seu identificador primário."""
        ...

    def criar(self, dados: dict[str, object]) -> RegraValidacao:
        """Cadastra uma nova regra dinâmica."""
        ...

    def atualizar(self, regra: RegraValidacao, dados: dict[str, object]) -> RegraValidacao:
        """Atualiza atributos de uma regra existente."""
        ...

    def excluir(self, regra: RegraValidacao) -> None:
        """Remove uma regra dinâmica."""
        ...

    def alternar_status(self, regra: RegraValidacao) -> RegraValidacao:
        """Alterna a flag ativo (True/False) de uma regra."""
        ...
