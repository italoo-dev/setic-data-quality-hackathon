"""Roteador da API para Gestão e CRUD de Regras de Validação."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_rule_repository
from app.database import RegraValidacao
from app.repositories.rules import RuleRepository
from app.schemas import (
    RegraValidacaoAtualizacao,
    RegraValidacaoCriacao,
    RegraValidacaoResposta,
)

router = APIRouter(prefix="/api/v1/regras", tags=["Gestão de Regras"])


@router.get(
    "",
    response_model=list[RegraValidacaoResposta],
    summary="Listar Todas as Regras de Validação",
)
def listar_regras(
    campo: str | None = None,
    apenas_ativas: bool = False,
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> list[RegraValidacao]:
    """Retorna todas as regras cadastradas (núcleo imutável e dinâmicas da CAGD)."""
    return rule_repo.listar_todas(campo=campo, apenas_ativas=apenas_ativas)


@router.post(
    "",
    response_model=RegraValidacaoResposta,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar Nova Regra Dinâmica",
)
def criar_regra_dinamica(
    dados_regra: RegraValidacaoCriacao,
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> RegraValidacao:
    """Registra uma nova regra dinâmica configurada pela CAGD."""
    return rule_repo.criar(dados_regra.model_dump())


@router.put(
    "/{regra_id}",
    response_model=RegraValidacaoResposta,
    summary="Atualizar Regra Dinâmica Existente",
)
def atualizar_regra_dinamica(
    regra_id: int,
    atualizacao: RegraValidacaoAtualizacao,
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> RegraValidacao:
    """Atualiza atributos de uma regra dinâmica. Bloqueia alteração de regras imutáveis."""
    regra = rule_repo.obter_por_id(regra_id)
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
    return rule_repo.atualizar(regra, dados_dict)


@router.delete(
    "/{regra_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir Regra Dinâmica",
)
def excluir_regra_dinamica(
    regra_id: int,
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> None:
    """Exclui uma regra dinâmica cadastrada. Regras imutáveis não podem ser removidas."""
    regra = rule_repo.obter_por_id(regra_id)
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

    rule_repo.excluir(regra)


@router.patch(
    "/{regra_id}/toggle",
    response_model=RegraValidacaoResposta,
    summary="Alternar Status Ativo/Inativo de Regra Dinâmica",
)
def alternar_status_regra(
    regra_id: int,
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> RegraValidacao:
    """Ativa ou desativa temporariamente uma regra dinâmica."""
    regra = rule_repo.obter_por_id(regra_id)
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

    return rule_repo.alternar_status(regra)
