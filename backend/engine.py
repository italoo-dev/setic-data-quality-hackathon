"""Motor de Validação (Fachada de Retrocompatibilidade).

Reexporta a classe orquestradora MotorValidacao, o ValidationPipeline
e as estruturas de resultado a partir de backend.engine e backend.domain.
"""

from backend.domain.models import ErroDiagnosticoItem, ExecutionContext, ResultadoMotor
from backend.engine.core_tier import CoreTierStep
from backend.engine.dynamic_tier import DynamicTierStep
from backend.engine.pipeline import MotorValidacao, ValidationPipeline

__all__ = [
    "CoreTierStep",
    "DynamicTierStep",
    "ErroDiagnosticoItem",
    "ExecutionContext",
    "MotorValidacao",
    "ResultadoMotor",
    "ValidationPipeline",
]
