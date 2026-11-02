"""Repositório de Regras de Validação (Repository Pattern).

Isola as operações de persistência e consulta da tabela regras_validacao,
garantindo controle sobre regras imutáveis de núcleo e regras dinâmicas da CAGD.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.database import RegraValidacao


class RuleRepository:
    """Repositório concreto de regras de validação utilizando SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def listar_ativas_dinamicas(self) -> list[RegraValidacao]:
        """Recupera regras dinâmicas ativas (excluindo regras imutáveis de núcleo)."""
        return (
            self.db.query(RegraValidacao)
            .filter(
                RegraValidacao.ativo == True,  # noqa: E712
                RegraValidacao.eh_imutavel == False,  # noqa: E712
            )
            .all()
        )

    def listar_todas(
        self,
        campo: str | None = None,
        apenas_ativas: bool = False,
    ) -> list[RegraValidacao]:
        """Recupera todas as regras cadastradas com filtros opcionais."""
        consulta = self.db.query(RegraValidacao)
        if campo:
            consulta = consulta.filter(RegraValidacao.campo == campo)
        if apenas_ativas:
            consulta = consulta.filter(RegraValidacao.ativo == True)  # noqa: E712

        return consulta.order_by(
            RegraValidacao.eh_imutavel.desc(),
            RegraValidacao.id.asc(),
        ).all()

    def obter_por_id(self, regra_id: int) -> RegraValidacao | None:
        """Busca uma regra pelo identificador único."""
        return self.db.query(RegraValidacao).filter(RegraValidacao.id == regra_id).first()

    def criar(self, dados: dict[str, object]) -> RegraValidacao:
        """Cria e persiste uma nova regra dinâmica."""
        regra = RegraValidacao(
            campo=str(dados["campo"]).strip().lower(),
            nome_regra=str(dados["nome_regra"]).strip(),
            descricao=str(dados["descricao"]) if dados.get("descricao") is not None else None,
            padrao_regex=str(dados["padrao_regex"])
            if dados.get("padrao_regex") is not None
            else None,
            mensagem_erro=str(dados["mensagem_erro"]).strip(),
            formato_esperado=str(dados["formato_esperado"]).strip(),
            obrigatorio=bool(dados.get("obrigatorio", False)),
            ativo=bool(dados.get("ativo", True)),
            eh_imutavel=False,
        )
        self.db.add(regra)
        self.db.commit()
        self.db.refresh(regra)
        return regra

    def atualizar(self, regra: RegraValidacao, dados: dict[str, object]) -> RegraValidacao:
        """Atualiza campos permitidos de uma regra existente."""
        for chave, valor in dados.items():
            if hasattr(regra, chave) and valor is not None:
                setattr(regra, chave, valor)

        self.db.commit()
        self.db.refresh(regra)
        return regra

    def excluir(self, regra: RegraValidacao) -> None:
        """Remove a regra do banco de dados."""
        self.db.delete(regra)
        self.db.commit()

    def alternar_status(self, regra: RegraValidacao) -> RegraValidacao:
        """Inverte o status ativo/inativo da regra."""
        regra.ativo = not regra.ativo
        self.db.commit()
        self.db.refresh(regra)
        return regra
