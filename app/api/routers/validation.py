"""Roteador da API para Validação e Normalização de Cargas de Dados."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.dependencies import get_validation_pipeline
from app.engine.pipeline import ValidationPipeline
from app.schemas import (
    ErroDiagnosticoDetalhe,
    RequisicaoValidacao,
    RespostaBloqueioValidacao,
    RespostaNormalizada,
)

router = APIRouter(prefix="/api/v1", tags=["Qualidade e Normalização"])


@router.post(
    "/validar",
    response_model=RespostaNormalizada,
    responses={
        200: {
            "model": RespostaNormalizada,
            "description": "Carga aprovada. Retorna dados higienizados e normalizados prontos para persistência.",
        },
        422: {
            "model": RespostaBloqueioValidacao,
            "description": "Carga rejeitada. Defeito estrutural detectado. Persistência bloqueada com relatório de auditoria.",
        },
    },
    summary="Validar e Normalizar Carga de Dados",
)
def validar_e_normalizar(
    requisicao: RequisicaoValidacao,
    pipeline: ValidationPipeline = Depends(get_validation_pipeline),
) -> Any:
    """Interpreta e processa os dados brutos recebidos.

    - Se a carga for válida: aplica normalizações permissivas e retorna **200 OK**.
    - Se houver falhas conceituais ou estruturais: bloqueia a persistência com **422 Unprocessable Entity**.
    - Em ambos os casos, registra a transação de auditoria para apuração da CAGD.
    """
    resultado = pipeline.execute(
        dados_entrada=requisicao.dados,
        sistema_origem=requisicao.sistema_origem,
    )

    if not resultado.sucesso:
        conteudo_bloqueio = RespostaBloqueioValidacao(
            sucesso=False,
            protocolo=resultado.protocolo,
            status_http=422,
            sistema_origem=resultado.sistema_origem,
            mensagem="Falha na validação dos dados de entrada. Persistência bloqueada.",
            erros=[
                ErroDiagnosticoDetalhe(
                    campo=e.campo,
                    regra_violada=e.regra_violada,
                    valor_rejeitado=e.valor_rejeitado,
                    formato_esperado=e.formato_esperado,
                    mensagem=e.mensagem,
                )
                for e in resultado.erros
            ],
            tempo_processamento_ms=resultado.tempo_processamento_ms,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=conteudo_bloqueio.model_dump(),
        )

    return RespostaNormalizada(
        sucesso=True,
        protocolo=resultado.protocolo,
        status_http=200,
        sistema_origem=resultado.sistema_origem,
        dados_normalizados=resultado.dados_normalizados or {},
        transformacoes=resultado.transformacoes,
        tempo_processamento_ms=resultado.tempo_processamento_ms,
    )
