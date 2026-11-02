"""Aplicação Principal FastAPI - Plataforma de Qualidade e Gestão de Dados SETIC/CAGD.

Fornece a API REST assíncrona de alta performance para:
1. Interceptação e saneamento prévio de cargas de dados (/api/v1/validar).
2. Fornecimento de telemetria e métricas operacionais consolidadas (/api/v1/metricas).
3. Gerenciamento e CRUD de regras de validação dinâmicas (/api/v1/regras).
4. Consulta à trilha de auditoria para fins de governança (/api/v1/auditoria).
5. Verificação de saúde operacional (/api/v1/saude).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db
from backend.api.routers import (
    audit_router,
    metrics_router,
    rules_router,
    validation_router,
)
from backend.database import RegraValidacao, init_db
from backend.validators.ibge import catalogo_ibge

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


# Rota de Diagnóstico e Saúde Operacional
@app.get(
    "/api/v1/saude",
    summary="Verificação de Saúde Operacional",
    tags=["Operação e Diagnóstico"],
)
def checar_saude(db: Session = Depends(get_db)) -> dict[str, object]:
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


# Inclusão dos Roteadores Modulares
app.include_router(validation_router)
app.include_router(rules_router)
app.include_router(metrics_router)
app.include_router(audit_router)
