"""Repositório de Regras de Validação (Repository Pattern).

Isola as operações de persistência e consulta da tabela regras_validacao,
garantindo controle sobre regras imutáveis de núcleo e regras dinâmicas da CAGD.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.database import RegraValidacao
from app.domain.interfaces import RuleRepositoryProtocol


class RuleRepository(RuleRepositoryProtocol):
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

    def exportar_regras(self, apenas_dinamicas: bool = True) -> list[dict[str, object]]:
        """Recupera regras para fins de exportação e backup declarativo."""
        consulta = self.db.query(RegraValidacao)
        if apenas_dinamicas:
            consulta = consulta.filter(RegraValidacao.eh_imutavel == False)  # noqa: E712
        regras = consulta.order_by(RegraValidacao.campo.asc(), RegraValidacao.id.asc()).all()
        return [
            {
                "campo": r.campo,
                "nome_regra": r.nome_regra,
                "descricao": r.descricao,
                "padrao_regex": r.padrao_regex,
                "mensagem_erro": r.mensagem_erro,
                "formato_esperado": r.formato_esperado,
                "obrigatorio": r.obrigatorio,
                "ativo": r.ativo,
            }
            for r in regras
        ]

    def importar_regras(
        self,
        regras: list[dict[str, object]],
        sobrescrever: bool = False,
    ) -> dict[str, object]:
        """Importa em lote regras dinâmicas, com suporte a validação de regex e sobrescrita."""
        import re

        total_criadas = 0
        total_atualizadas = 0
        total_ignoradas = 0
        erros: list[str] = []
        mensagens: list[str] = []

        for idx, item in enumerate(regras, start=1):
            campo_raw = item.get("campo")
            nome_raw = item.get("nome_regra")
            if not campo_raw or not nome_raw:
                erros.append(f"Item #{idx}: 'campo' e 'nome_regra' são obrigatórios.")
                continue

            campo = str(campo_raw).strip().lower()
            nome_regra = str(nome_raw).strip()
            padrao_regex = str(item["padrao_regex"]).strip() if item.get("padrao_regex") else None

            # Validação sintática do regex antes de persistir
            if padrao_regex:
                try:
                    re.compile(padrao_regex)
                except re.error as e:
                    erros.append(f"Item #{idx} ({campo} / {nome_regra}): regex inválido ({e}).")
                    continue

            # Buscar se já existe regra com mesmo campo e nome
            existente = (
                self.db.query(RegraValidacao)
                .filter(
                    RegraValidacao.campo == campo,
                    RegraValidacao.nome_regra == nome_regra,
                )
                .first()
            )

            if existente:
                if existente.eh_imutavel:
                    erros.append(
                        f"Item #{idx} ({campo}): não é permitido sobrescrever regra núcleo imutável."
                    )
                    continue

                if sobrescrever:
                    existente.descricao = (
                        str(item["descricao"]) if item.get("descricao") is not None else None
                    )
                    existente.padrao_regex = padrao_regex
                    existente.mensagem_erro = str(
                        item.get("mensagem_erro", existente.mensagem_erro)
                    )
                    existente.formato_esperado = str(
                        item.get("formato_esperado", existente.formato_esperado)
                    )
                    existente.obrigatorio = bool(item.get("obrigatorio", existente.obrigatorio))
                    existente.ativo = bool(item.get("ativo", existente.ativo))
                    total_atualizadas += 1
                    mensagens.append(
                        f"Regra '{nome_regra}' para o campo '{campo}' atualizada com sucesso."
                    )
                else:
                    total_ignoradas += 1
                    mensagens.append(
                        f"Regra '{nome_regra}' para o campo '{campo}' já existe (ignorada)."
                    )
            else:
                nova_regra = RegraValidacao(
                    campo=campo,
                    nome_regra=nome_regra,
                    descricao=(
                        str(item["descricao"]) if item.get("descricao") is not None else None
                    ),
                    padrao_regex=padrao_regex,
                    mensagem_erro=str(item.get("mensagem_erro", "Formato inválido")),
                    formato_esperado=str(item.get("formato_esperado", "Padrão especificado")),
                    obrigatorio=bool(item.get("obrigatorio", False)),
                    ativo=bool(item.get("ativo", True)),
                    eh_imutavel=False,
                )
                self.db.add(nova_regra)
                total_criadas += 1
                mensagens.append(f"Regra '{nome_regra}' para o campo '{campo}' criada com sucesso.")

        if total_criadas > 0 or total_atualizadas > 0:
            self.db.commit()

        return {
            "sucesso": len(erros) == 0,
            "total_processadas": len(regras),
            "total_criadas": total_criadas,
            "total_atualizadas": total_atualizadas,
            "total_ignoradas": total_ignoradas,
            "erros": erros,
            "mensagens": mensagens,
        }
