"""Repositório de Persistência e Telemetria de Auditoria (Repository Pattern).

Isola o acesso à tabela registros_auditoria, centralizando operações transacionais,
cálculo de KPIs e recuperação da trilha analítica para a CAGD.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from backend.database import RegistroAuditoria
from backend.domain.interfaces import AuditRepositoryProtocol
from backend.domain.masking import mascarar_dados, mascarar_erros
from backend.schemas import ItemContagem, MetricasOperacionaisCAGD, VolumeSistemaItem


class AuditRepository(AuditRepositoryProtocol):
    """Repositório concreto de auditoria utilizando SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self.db = db

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
        """Persiste um registro de auditoria na base de dados com mascaramento de dados sensíveis."""
        dados_entrada_mascarados = mascarar_dados(dados_entrada)
        dados_normalizados_mascarados = (
            mascarar_dados(dados_normalizados) if dados_normalizados is not None else None
        )
        erros_mascarados = mascarar_erros(erros)

        registro = RegistroAuditoria(
            protocolo=protocolo,
            sistema_origem=sistema_origem,
            sucesso=sucesso,
            status_http=status_http,
            dados_entrada=dados_entrada_mascarados,
            dados_normalizados=dados_normalizados_mascarados,
            erros_detectados=erros_mascarados,
            quantidade_erros=len(erros) if erros else 0,
            tempo_processamento_ms=round(tempo_processamento_ms, 2),
        )
        self.db.add(registro)
        self.db.commit()
        return registro

    def obter_metricas_cagd(self) -> MetricasOperacionaisCAGD:
        """Calcula os indicadores operacionais agregados para o painel de gestão."""
        total = self.db.query(RegistroAuditoria).count()
        total_sucessos = (
            self.db.query(RegistroAuditoria).filter(RegistroAuditoria.sucesso == True).count()  # noqa: E712
        )
        total_bloqueios = (
            self.db.query(RegistroAuditoria).filter(RegistroAuditoria.sucesso == False).count()  # noqa: E712
        )

        taxa_rejeicao = round((total_bloqueios / total * 100), 2) if total > 0 else 0.0

        tempo_medio = (
            self.db.query(func.avg(RegistroAuditoria.tempo_processamento_ms)).scalar() or 0.0
        )
        tempo_medio = round(float(tempo_medio), 2)

        # Agrupamento de volume por sistema de origem
        sistemas_raw = (
            self.db.query(
                RegistroAuditoria.sistema_origem,
                func.count(RegistroAuditoria.id).label("total"),
                func.sum(case((RegistroAuditoria.sucesso == True, 1), else_=0)).label("aprovados"),  # noqa: E712
                func.sum(
                    case((RegistroAuditoria.sucesso == False, 1), else_=0)  # noqa: E712
                ).label("rejeitados"),
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
                    sistema_origem=str(s.sistema_origem),
                    total=tot_s,
                    aprovados=apr_s,
                    rejeitados=rej_s,
                    taxa_rejeicao_percentual=taxa_s,
                )
            )

        # Extração das falhas mais frequentes para rankings
        registros_falhas = (
            self.db.query(RegistroAuditoria.erros_detectados)
            .filter(
                RegistroAuditoria.sucesso == False,  # noqa: E712
                RegistroAuditoria.erros_detectados.isnot(None),
            )
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
                        if isinstance(c, str):
                            contador_campos[c] += 1
                        if isinstance(r, str):
                            contador_regras[r] += 1

        top_campos = [
            ItemContagem(nome=campo, quantidade=qtd)
            for campo, qtd in contador_campos.most_common(10)
        ]
        top_regras = [
            ItemContagem(nome=regra, quantidade=qtd)
            for regra, qtd in contador_regras.most_common(10)
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

    def listar_registros(
        self,
        sistema_origem: str | None = None,
        sucesso: bool | None = None,
        limite: int = 50,
    ) -> list[RegistroAuditoria]:
        """Consulta registros históricos da trilha com filtros opcionais."""
        consulta = self.db.query(RegistroAuditoria)
        if sistema_origem:
            consulta = consulta.filter(RegistroAuditoria.sistema_origem == sistema_origem)
        if sucesso is not None:
            consulta = consulta.filter(RegistroAuditoria.sucesso == sucesso)

        return consulta.order_by(RegistroAuditoria.criado_em.desc()).limit(limite).all()
