"""Aplicação Principal FastAPI - Plataforma de Qualidade e Gestão de Dados SETIC/CAGD.

Fornece a API REST assíncrona de alta performance para:
1. Interceptação e saneamento prévio de cargas de dados (/api/v1/validar).
2. Fornecimento de telemetria e métricas operacionais consolidadas (/api/v1/metricas).
3. Gerenciamento e CRUD de regras de validação dinâmicas (/api/v1/regras).
4. Consulta à trilha de auditoria para fins de governança (/api/v1/auditoria).
"""

from __future__ import annotations

import logging
from collections import Counter
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core_validators import catalogo_ibge
from app.database import RegistroAuditoria, RegraValidacao, get_db, init_db
from app.engine import MotorValidacao
from app.schemas import (
    ErroDiagnosticoDetalhe,
    ItemContagem,
    MetricasOperacionaisCAGD,
    RegraValidacaoAtualizacao,
    RegraValidacaoCriacao,
    RegraValidacaoResposta,
    RequisicaoValidacao,
    RespostaBloqueioValidacao,
    RespostaNormalizada,
    VolumeSistemaItem,
)

logger = logging.getLogger("setic.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida da aplicação FastAPI: inicializa tabelas e pré-aquece catálogos."""
    logger.info("Iniciando a Plataforma de Qualidade de Dados SETIC/CAGD...")
    init_db()
    # Garante que o catálogo nacional IBGE esteja aquecido na memória
    _ = len(catalogo_ibge.por_codigo)
    yield
    logger.info("Encerrando a Plataforma SETIC/CAGD.")


app = FastAPI(
    title="Plataforma Centralizada de Qualidade, Normalização e Gestão de Dados - SETIC/RO",
    description="""
## Arquitetura de Gatekeeper Centralizado de Qualidade de Dados (CAGD)

Esta plataforma atua como uma barreira preventiva (*gatekeeper*) que intercepta cargas de dados
antes de sua persistência em bancos de dados estaduais de Rondônia:

1. **Normalização Permissiva (*Permissive Normalization*)**:
   - Dados conceitualmente válidos com formatação informal ou truncada são higienizados e convertidos para padrões canônicos
     (ex: `"15 de março de 1985"` $\\rightarrow$ `"1985-03-15"`, `"p. velho"` $\\rightarrow$ `"Porto Velho"` com código IBGE `1100205`).
2. **Bloqueio Estrito (*Strict Blocking*)**:
   - Cargas com defeitos estruturais, matemáticos ou temporais são rejeitadas com **HTTP 422 Unprocessable Entity**,
     fornecendo diagnóstico analítico de cada campo violado e registrando auditoria de telemetria.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configuração de CORS para permitir acesso do painel Streamlit e clientes corporativos
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================================================
# ROTA DE HEALTHCHECK
# =====================================================================


@app.get(
    "/api/v1/saude",
    summary="Verificação de Saúde Operacional",
    tags=["Operação e Diagnóstico"],
)
def checar_saude(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Retorna o estado operacional dos serviços, banco de dados e catálogo IBGE."""
    total_regras = 0
    try:
        total_regras = db.query(RegraValidacao).count()
        status_db = "conectado"
    except Exception as e:
        status_db = f"erro: {e}"

    return {
        "status": "operacional",
        "servico": "setic-qualidade-dados",
        "versao": "1.0.0",
        "banco_de_dados": status_db,
        "total_regras_carregadas": total_regras if status_db == "conectado" else 0,
        "municipios_ibge_indexados": len(catalogo_ibge.por_codigo),
    }


# =====================================================================
# ROTA PRINCIPAL DE VALIDAÇÃO E NORMALIZAÇÃO DE DADOS
# =====================================================================


@app.post(
    "/api/v1/validar",
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
    tags=["Qualidade e Normalização"],
)
def validar_e_normalizar(
    requisicao: RequisicaoValidacao,
    db: Session = Depends(get_db),
) -> Any:
    """Interpreta e processa os dados brutos recebidos.

    - Se a carga for válida: aplica normalizações permissivas e retorna **200 OK**.
    - Se houver falhas conceituais ou estruturais: bloqueia a persistência com **422 Unprocessable Entity**.
    - Em ambos os casos, registra a transação de auditoria para apuração da CAGD.
    """
    motor = MotorValidacao(db)
    resultado = motor.executar(
        dados_entrada=requisicao.dados,
        sistema_origem=requisicao.sistema_origem,
    )

    if not resultado.sucesso:
        # Bloqueio Estrito: HTTP 422 com diagnósticos detalhados
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

    # Normalização Permissiva: HTTP 200 OK com payload canônico
    return RespostaNormalizada(
        sucesso=True,
        protocolo=resultado.protocolo,
        status_http=200,
        sistema_origem=resultado.sistema_origem,
        dados_normalizados=resultado.dados_normalizados or {},
        transformacoes=resultado.transformacoes,
        tempo_processamento_ms=resultado.tempo_processamento_ms,
    )


# =====================================================================
# ROTA DE MÉTRICAS OPERACIONAIS PARA A CAGD
# =====================================================================


@app.get(
    "/api/v1/metricas",
    response_model=MetricasOperacionaisCAGD,
    summary="Métricas Operacionais Consolidadas para a CAGD",
    tags=["Gestão e Telemetria"],
)
def obter_metricas_cagd(db: Session = Depends(get_db)) -> MetricasOperacionaisCAGD:
    """Calcula estatísticas agregadas de qualidade, rejeição e latência para a gestão."""
    total = db.query(RegistroAuditoria).count()
    total_sucessos = (
        db.query(RegistroAuditoria).filter(RegistroAuditoria.sucesso == True).count()  # noqa: E712
    )
    total_bloqueios = (
        db.query(RegistroAuditoria).filter(RegistroAuditoria.sucesso == False).count()  # noqa: E712
    )

    taxa_rejeicao = round((total_bloqueios / total * 100), 2) if total > 0 else 0.0

    tempo_medio = db.query(func.avg(RegistroAuditoria.tempo_processamento_ms)).scalar() or 0.0
    tempo_medio = round(float(tempo_medio), 2)

    # Agrupamento de volume por sistema de origem
    sistemas_raw = (
        db.query(
            RegistroAuditoria.sistema_origem,
            func.count(RegistroAuditoria.id).label("total"),
            func.sum(case((RegistroAuditoria.sucesso == True, 1), else_=0)).label("aprovados"),  # noqa: E712
            func.sum(case((RegistroAuditoria.sucesso == False, 1), else_=0)).label("rejeitados"),  # noqa: E712
        )
        .group_by(RegistroAuditoria.sistema_origem)
        .all()
    )

    volume_sistemas: list[VolumeSistemaItem] = []
    for s in sistemas_raw:
        tot_s = int(s.total)
        apr_s = int(s.aprovados or 0)
        rej_s = int(s.rejeitados or 0)
        taxa_s = round((rej_s / tot_s * 100), 2) if tot_s > 0 else 0.0
        volume_sistemas.append(
            VolumeSistemaItem(
                sistema_origem=s.sistema_origem,
                total=tot_s,
                aprovados=apr_s,
                rejeitados=rej_s,
                taxa_rejeicao_percentual=taxa_s,
            )
        )

    # Extração de falhas para cálculo de top campos e top regras rejeitadas
    registros_falhas = (
        db.query(RegistroAuditoria.erros_detectados)
        .filter(RegistroAuditoria.sucesso == False, RegistroAuditoria.erros_detectados.isnot(None))  # noqa: E712
        .limit(1000)
        .all()
    )

    contador_campos: Counter[str] = Counter()
    contador_regras: Counter[str] = Counter()

    for reg in registros_falhas:
        erros_lista = reg[0]
        if isinstance(erros_lista, list):
            for e in erros_lista:
                if isinstance(e, dict):
                    c = e.get("campo")
                    r = e.get("regra_violada")
                    if c:
                        contador_campos[c] += 1
                    if r:
                        contador_regras[r] += 1

    top_campos = [
        ItemContagem(nome=campo, quantidade=qtd) for campo, qtd in contador_campos.most_common(10)
    ]
    top_regras = [
        ItemContagem(nome=regra, quantidade=qtd) for regra, qtd in contador_regras.most_common(10)
    ]

    return MetricasOperacionaisCAGD(
        total_requisicoes=total,
        total_sucessos=total_sucessos,
        total_bloqueios=total_bloqueios,
        taxa_rejeicao_percentual=taxa_rejeicao,
        tempo_medio_processamento_ms=tempo_medio,
        volume_por_sistema=volume_sistemas,
        top_campos_rejeitados=top_campos,
        top_regras_violadas=top_regras,
    )


# =====================================================================
# ROTAS DE CRUD DE REGRAS DE VALIDAÇÃO (DUAL-TIER ENGINE)
# =====================================================================


@app.get(
    "/api/v1/regras",
    response_model=list[RegraValidacaoResposta],
    summary="Listar Todas as Regras de Validação",
    tags=["Gestão de Regras"],
)
def listar_regras(
    campo: str | None = None,
    apenas_ativas: bool = False,
    db: Session = Depends(get_db),
) -> list[RegraValidacao]:
    """Retorna todas as regras cadastradas (núcleo imutável e dinâmicas da CAGD)."""
    consulta = db.query(RegraValidacao)
    if campo:
        consulta = consulta.filter(RegraValidacao.campo == campo)
    if apenas_ativas:
        consulta = consulta.filter(RegraValidacao.ativo == True)  # noqa: E712

    return consulta.order_by(RegraValidacao.eh_imutavel.desc(), RegraValidacao.id.asc()).all()


@app.post(
    "/api/v1/regras",
    response_model=RegraValidacaoResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar Nova Regra Dinâmica",
    tags=["Gestão de Regras"],
)
def criar_regra_dinamica(
    dados_regra: RegraValidacaoCriacao,
    db: Session = Depends(get_db),
) -> RegraValidacao:
    """Registra uma nova regra dinâmica configurada pela CAGD."""
    nova_regra = RegraValidacao(
        campo=dados_regra.campo.strip().lower(),
        nome_regra=dados_regra.nome_regra.strip(),
        descricao=dados_regra.descricao,
        padrao_regex=dados_regra.padrao_regex,
        mensagem_erro=dados_regra.mensagem_erro,
        formato_esperado=dados_regra.formato_esperado,
        obrigatorio=dados_regra.obrigatorio,
        ativo=dados_regra.ativo,
        eh_imutavel=False,  # Novas regras são sempre dinâmicas e gerenciáveis
    )
    db.add(nova_regra)
    db.commit()
    db.refresh(nova_regra)
    return nova_regra


@app.put(
    "/api/v1/regras/{regra_id}",
    response_model=RegraValidacaoResposta,
    summary="Atualizar Regra Dinâmica Existente",
    tags=["Gestão de Regras"],
)
def atualizar_regra_dinamica(
    regra_id: int,
    atualizacao: RegraValidacaoAtualizacao,
    db: Session = Depends(get_db),
) -> RegraValidacao:
    """Atualiza atributos de uma regra dinâmica. Bloqueia alteração de regras imutáveis."""
    regra = db.query(RegraValidacao).filter(RegraValidacao.id == regra_id).first()
    if not regra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra com ID {regra_id} não encontrada.",
        )

    if regra.eh_imutavel:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operação Proibida: Esta é uma regra fundamental de núcleo imutável da plataforma e não pode ser modificada.",
        )

    dados_dict = atualizacao.model_dump(exclude_unset=True)
    for chave, valor in dados_dict.items():
        setattr(regra, chave, valor)

    db.commit()
    db.refresh(regra)
    return regra


@app.delete(
    "/api/v1/regras/{regra_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir Regra Dinâmica",
    tags=["Gestão de Regras"],
)
def excluir_regra_dinamica(
    regra_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Exclui uma regra dinâmica cadastrada. Regras imutáveis não podem ser removidas."""
    regra = db.query(RegraValidacao).filter(RegraValidacao.id == regra_id).first()
    if not regra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra com ID {regra_id} não encontrada.",
        )

    if regra.eh_imutavel:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operação Proibida: Regras fundamentais de núcleo são protegidas e não podem ser excluídas.",
        )

    db.delete(regra)
    db.commit()


@app.patch(
    "/api/v1/regras/{regra_id}/toggle",
    response_model=RegraValidacaoResposta,
    summary="Alternar Status Ativo/Inativo de Regra Dinâmica",
    tags=["Gestão de Regras"],
)
def alternar_status_regra(
    regra_id: int,
    db: Session = Depends(get_db),
) -> RegraValidacao:
    """Ativa ou desativa temporariamente uma regra dinâmica."""
    regra = db.query(RegraValidacao).filter(RegraValidacao.id == regra_id).first()
    if not regra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra com ID {regra_id} não encontrada.",
        )

    if regra.eh_imutavel:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operação Proibida: Regras fundamentais de núcleo não podem ser desativadas.",
        )

    regra.ativo = not regra.ativo
    db.commit()
    db.refresh(regra)
    return regra


# =====================================================================
# ROTA DE CONSULTA DA TRILHA DE AUDITORIA
# =====================================================================


@app.get(
    "/api/v1/auditoria",
    summary="Consultar Trilha de Auditoria e Telemetria",
    tags=["Gestão e Telemetria"],
)
def consultar_auditoria(
    sistema_origem: str | None = None,
    sucesso: bool | None = None,
    limite: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Consulta os registros mais recentes da trilha de auditoria operacional."""
    consulta = db.query(RegistroAuditoria)
    if sistema_origem:
        consulta = consulta.filter(RegistroAuditoria.sistema_origem == sistema_origem)
    if sucesso is not None:
        consulta = consulta.filter(RegistroAuditoria.sucesso == sucesso)

    registros = consulta.order_by(RegistroAuditoria.criado_em.desc()).limit(limite).all()
    return [r.to_dict() for r in registros]
