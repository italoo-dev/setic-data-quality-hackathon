"""Motor de Validação (Fachada de Retrocompatibilidade).

Reexporta a classe orquestradora MotorValidacao, o ValidationPipeline
e as estruturas de resultado a partir de app.engine e app.domain.
"""

from app.domain.models import ErroDiagnosticoItem, ExecutionContext, ResultadoMotor
from app.engine.core_tier import CoreTierStep
from app.engine.dynamic_tier import DynamicTierStep
from app.engine.pipeline import MotorValidacao, ValidationPipeline

__all__ = [
    "CoreTierStep",
    "DynamicTierStep",
    "ErroDiagnosticoItem",
    "ExecutionContext",
    "MotorValidacao",
    "ResultadoMotor",
    "ValidationPipeline",
]
