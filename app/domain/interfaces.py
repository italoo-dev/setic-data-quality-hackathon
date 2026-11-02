"""Protocolos e Interfaces de Domínio (Interface Segregation & Dependency Inversion).

Estabelece contratos estritos que desacoplam os validadores, repositórios de
persistência e etapas orquestradas do pipeline de execução.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.models import ErroDiagnosticoItem, ExecutionContext


class BaseValidatorProtocol(Protocol):
    """Contrato que todo validador concreto de campo deve implementar (Strategy Pattern)."""

    def validate_and_normalize(
        self,
        field_name: str,
        value: Any,
        context: ExecutionContext,
    ) -> tuple[Any, list[ErroDiagnosticoItem], list[str]]:
        """Executa a validação e normalização do campo.

        Retorna:
            tuple[Any, list[ErroDiagnosticoItem], list[str]]:
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
        dados_entrada: dict[str, Any],
        dados_normalizados: dict[str, Any] | None,
        erros: list[dict[str, Any]] | None,
        tempo_processamento_ms: float,
    ) -> Any:
        """Persiste atomicamente uma transação auditável."""
        ...

    def obter_metricas_cagd(self) -> dict[str, Any]:
        """Calcula os indicadores operacionais agregados para a CAGD."""
        ...

    def listar_registros(
        self,
        sistema_origem: str | None = None,
        sucesso: bool | None = None,
        limite: int = 50,
    ) -> list[Any]:
        """Recupera registros históricos ordenados decrescentemente."""
        ...


class RuleRepositoryProtocol(Protocol):
    """Contrato de persistência e gestão de regras dinâmicas de validação."""

    def listar_ativas_dinamicas(self) -> list[Any]:
        """Recupera regras ativas não imutáveis para execução no pipeline dinâmico."""
        ...

    def listar_todas(self) -> list[Any]:
        """Recupera todas as regras cadastradas (núcleo e dinâmicas)."""
        ...

    def obter_por_id(self, regra_id: int) -> Any | None:
        """Recupera uma regra específica pelo seu identificador primário."""
        ...

    def criar(self, dados: dict[str, Any]) -> Any:
        """Cadastra uma nova regra dinâmica."""
        ...

    def atualizar(self, regra: Any, dados: dict[str, Any]) -> Any:
        """Atualiza atributos de uma regra existente."""
        ...

    def excluir(self, regra: Any) -> None:
        """Remove uma regra dinâmica."""
        ...

    def alternar_status(self, regra: Any) -> Any:
        """Alterna a flag ativo (True/False) de uma regra."""
        ...
