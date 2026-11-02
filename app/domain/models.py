"""Modelos de Domínio e Value Objects (DDD).

Contém estruturas imutáveis e objetos de transferência internos
para o pipeline de validação, diagnósticos analíticos e telemetria.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ErroDiagnosticoItem:
    """Item estruturado de diagnóstico de erro retornado em falhas de validação (HTTP 422)."""

    campo: str
    regra_violada: str
    valor_rejeitado: Any
    formato_esperado: str
    mensagem: str

    def to_dict(self) -> dict[str, Any]:
        """Converte o erro para dicionário serializável."""
        return asdict(self)


@dataclass
class ResultadoValidacao:
    """Resultado detalhado da validação atômica de um campo."""

    valido: bool
    valor_normalizado: Any = None
    mensagem_transformacao: str | None = None
    campo: str = ""
    regra_violada: str = ""
    valor_rejeitado: Any = None
    formato_esperado: str = ""
    mensagem_erro: str = ""


@dataclass
class ExecutionContext:
    """Contexto de execução que trafega entre as etapas do pipeline de validação."""

    sistema_origem: str
    protocolo: str
    dados_brutos: dict[str, Any]
    dados_normalizados: dict[str, Any] = field(default_factory=dict)
    erros: list[ErroDiagnosticoItem] = field(default_factory=list)
    transformacoes: list[str] = field(default_factory=list)
    inicio_tempo: float = field(default_factory=time.perf_counter)
    tempo_processamento_ms: float = 0.0

    def adicionar_erro(self, erro: ErroDiagnosticoItem) -> None:
        """Registra uma falha diagnóstica no contexto."""
        self.erros.append(erro)

    def adicionar_transformacao(self, mensagem: str) -> None:
        """Registra uma mensagem descritiva de normalização aplicada."""
        self.transformacoes.append(mensagem)

    @property
    def sucesso(self) -> bool:
        """Indica se nenhuma falha de validação foi registrada."""
        return len(self.erros) == 0


@dataclass
class ResultadoMotor:
    """Resultado consolidado da execução do pipeline do motor de validação."""

    sucesso: bool
    protocolo: str
    status_http: int
    sistema_origem: str
    dados_normalizados: dict[str, Any] | None
    erros: list[ErroDiagnosticoItem]
    transformacoes: list[str]
    tempo_processamento_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Converte o resultado consolidado para dicionário serializável."""
        return {
            "sucesso": self.sucesso,
            "protocolo": self.protocolo,
            "status_http": self.status_http,
            "sistema_origem": self.sistema_origem,
            "dados_normalizados": self.dados_normalizados,
            "erros": [e.to_dict() for e in self.erros],
            "transformacoes": self.transformacoes,
            "tempo_processamento_ms": self.tempo_processamento_ms,
        }
