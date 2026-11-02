"""Roteador da API para Gestão e CRUD de Regras de Validação."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.dependencies import get_rule_repository
from backend.database import RegraValidacao
from backend.repositories.rules import RuleRepository
from backend.schemas import (
    ConjuntoRegrasExportacao,
    RegraExportadaItem,
    RegraValidacaoAtualizacao,
    RegraValidacaoCriacao,
    RegraValidacaoResposta,
    RequisicaoImportacaoRegras,
    ResultadoImportacaoRegras,
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


@router.get(
    "/exportar",
    response_model=ConjuntoRegrasExportacao,
    summary="Exportar Regras Dinâmicas (Backup/Portabilidade)",
)
def exportar_regras_dinamicas(
    apenas_dinamicas: bool = True,
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> ConjuntoRegrasExportacao:
    """Exporta o conjunto de regras dinâmicas em formato JSON estruturado."""
    regras = rule_repo.exportar_regras(apenas_dinamicas=apenas_dinamicas)
    return ConjuntoRegrasExportacao(
        versao="1.0",
        gerado_em=datetime.now(UTC).isoformat(),
        total_regras=len(regras),
        regras=[RegraExportadaItem.model_validate(r) for r in regras],
    )


@router.post(
    "/importar",
    response_model=ResultadoImportacaoRegras,
    summary="Importar Regras Dinâmicas em Lote",
)
def importar_regras_dinamicas(
    payload: RequisicaoImportacaoRegras,
    rule_repo: RuleRepository = Depends(get_rule_repository),
) -> ResultadoImportacaoRegras:
    """Importa em lote regras dinâmicas com suporte a sobrescrita e validação de sintaxe regex."""
    dados_regras = [r.model_dump() for r in payload.regras]
    resultado = rule_repo.importar_regras(
        regras=dados_regras,
        sobrescrever=payload.sobrescrever,
    )
    raw_erros = resultado.get("erros")
    erros = [str(e) for e in raw_erros] if isinstance(raw_erros, list) else []
    raw_msgs = resultado.get("mensagens")
    mensagens = [str(m) for m in raw_msgs] if isinstance(raw_msgs, list) else []

    return ResultadoImportacaoRegras(
        sucesso=bool(resultado.get("sucesso", False)),
        total_processadas=int(str(resultado.get("total_processadas", 0))),
        total_criadas=int(str(resultado.get("total_criadas", 0))),
        total_atualizadas=int(str(resultado.get("total_atualizadas", 0))),
        total_ignoradas=int(str(resultado.get("total_ignoradas", 0))),
        erros=erros,
        mensagens=mensagens,
    )


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
