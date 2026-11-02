"""Módulo de persistência e modelos relacionais SQLAlchemy para a plataforma SETIC.

Gerencia conexões com o PostgreSQL, controle transacional e esquemas para:
1. Regras dinâmicas de validação (RegraValidacao).
2. Telemetria e logs de auditoria operacional (RegistroAuditoria).
"""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

# Resolução da URL de Conexão com suporte a fallback de contingência
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres@localhost:5433/setic_qualidade",
)

# Configuração do Engine SQLAlchemy
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=15,
        max_overflow=25,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Classe base para os modelos declarativos da aplicação."""

    pass


class RegraValidacao(Base):
    """Tabela de regras de validação da plataforma.

    Suporta o modelo Dual-Tier:
    - Regras de Núcleo (eh_imutavel = True): CPF, CNPJ, IBGE, Data de Nascimento.
      Não podem ser excluídas nem alteradas em padrões algorítmicos.
    - Regras Dinâmicas (eh_imutavel = False): Regex e restrições configuradas pela CAGD.
    """

    __tablename__ = "regras_validacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campo: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    nome_regra: Mapped[str] = mapped_column(String(128), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    padrao_regex: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mensagem_erro: Mapped[str] = mapped_column(Text, nullable=False)
    formato_esperado: Mapped[str] = mapped_column(String(256), nullable=False)
    obrigatorio: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    eh_imutavel: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def to_dict(self) -> dict[str, Any]:
        """Serializa o modelo para dicionário."""
        return {
            "id": self.id,
            "campo": self.campo,
            "nome_regra": self.nome_regra,
            "descricao": self.descricao,
            "padrao_regex": self.padrao_regex,
            "mensagem_erro": self.mensagem_erro,
            "formato_esperado": self.formato_esperado,
            "obrigatorio": self.obrigatorio,
            "ativo": self.ativo,
            "eh_imutavel": self.eh_imutavel,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
            "atualizado_em": self.atualizado_em.isoformat() if self.atualizado_em else None,
        }


class RegistroAuditoria(Base):
    """Tabela de telemetria e trilha de auditoria para o CAGD.

    Registra cada transação submetida ao endpoint /api/v1/validar,
    permitindo apuração de taxas de rejeição, gargalos de qualidade
    e desempenho por sistema cliente.
    """

    __tablename__ = "registros_auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    protocolo: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    sistema_origem: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sucesso: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    status_http: Mapped[int] = mapped_column(Integer, nullable=False)
    dados_entrada: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    dados_normalizados: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    erros_detectados: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    quantidade_erros: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tempo_processamento_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    def to_dict(self) -> dict[str, Any]:
        """Serializa o registro de auditoria para dicionário."""
        return {
            "id": self.id,
            "protocolo": self.protocolo,
            "sistema_origem": self.sistema_origem,
            "sucesso": self.sucesso,
            "status_http": self.status_http,
            "dados_entrada": self.dados_entrada,
            "dados_normalizados": self.dados_normalizados,
            "erros_detectados": self.erros_detectados,
            "quantidade_erros": self.quantidade_erros,
            "tempo_processamento_ms": self.tempo_processamento_ms,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }


# Índices compostos para consultas analíticas frequentes
Index("ix_auditoria_sistema_sucesso", RegistroAuditoria.sistema_origem, RegistroAuditoria.sucesso)
Index("ix_auditoria_criado_sucesso", RegistroAuditoria.criado_em, RegistroAuditoria.sucesso)


def get_db() -> Generator[Any, None, None]:
    """Dependency injection generator para sessões do banco de dados no FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def popular_regras_iniciais(db: Any) -> None:
    """Popula regras imutáveis de núcleo e regras dinâmicas de demonstração."""
    regras_iniciais = [
        # Regras de Núcleo (Imutáveis)
        {
            "campo": "cpf",
            "nome_regra": "Algoritmo Canônico de CPF (Receita Federal)",
            "descricao": "Validação de formato e dígitos verificadores do CPF via algoritmo módulo 11 (brutils/validate-docbr).",
            "padrao_regex": r"^\d{11}$|^\d{3}\.\d{3}\.\d{3}-\d{2}$",
            "mensagem_erro": "O CPF informado possui dígitos verificadores inválidos ou estrutura matemática inconsistente.",
            "formato_esperado": "11 dígitos numéricos com dígitos verificadores válidos",
            "obrigatorio": False,
            "ativo": True,
            "eh_imutavel": True,
        },
        {
            "campo": "cnpj",
            "nome_regra": "Algoritmo Canônico de CNPJ (Receita Federal)",
            "descricao": "Validação estrita de dígitos verificadores e formato de CNPJ (brutils/validate-docbr).",
            "padrao_regex": r"^\d{14}$|^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$",
            "mensagem_erro": "O CNPJ informado possui dígitos verificadores matematicamente inconsistentes.",
            "formato_esperado": "14 dígitos numéricos com dígitos verificadores válidos",
            "obrigatorio": False,
            "ativo": True,
            "eh_imutavel": True,
        },
        {
            "campo": "data_nascimento",
            "nome_regra": "Validação Temporal e Calendárica de Nascimento",
            "descricao": "Normalização fuzzy via dateparser e bloqueio estrito de datas impossíveis no calendário gregoriano.",
            "padrao_regex": None,
            "mensagem_erro": "Data inexistente no calendário (ex: 31 de fevereiro) ou situada no futuro.",
            "formato_esperado": "Data gregoriana válida (ISO-8601 AAAA-MM-DD ou formato textual em português)",
            "obrigatorio": False,
            "ativo": True,
            "eh_imutavel": True,
        },
        {
            "campo": "telefone",
            "nome_regra": "Padrão Telefônico Nacional (Anatel)",
            "descricao": "Validação de DDD e quantitativo de dígitos para números fixos (10) e móveis (11 com nono dígito).",
            "padrao_regex": r"^(?:\+?55)?(?:\s?\(?[1-9]{2}\)?\s?)(?:9[0-9]{8}|[2-8][0-9]{7})$",
            "mensagem_erro": "Número de telefone ou DDD inválido segundo os padrões regulatórios da Anatel.",
            "formato_esperado": "(DDD) 9XXXX-XXXX para celular ou (DDD) XXXX-XXXX para fixo",
            "obrigatorio": False,
            "ativo": True,
            "eh_imutavel": True,
        },
        {
            "campo": "municipio",
            "nome_regra": "Resolução Bidirecional e Aproximação IBGE",
            "descricao": "Resolução fonética/distância de Levenshtein contra os 5.570+ municípios brasileiros do IBGE.",
            "padrao_regex": None,
            "mensagem_erro": "Município não identificado na base nacional de localidades do IBGE.",
            "formato_esperado": "Nome de município brasileiro reconhecido ou código oficial de 7 dígitos",
            "obrigatorio": False,
            "ativo": True,
            "eh_imutavel": True,
        },
        # Regras Dinâmicas (Customizáveis pela CAGD)
        {
            "campo": "matricula_funcional",
            "nome_regra": "Padrão de Matrícula de Servidor Estadual de Rondônia",
            "descricao": "Formato corporativo oficial de matrícula de servidores do Governo de Rondônia.",
            "padrao_regex": r"^RO-\d{6}$",
            "mensagem_erro": "A matrícula funcional deve seguir rigorosamente o padrão RO- seguido de 6 dígitos numéricos.",
            "formato_esperado": "RO-123456",
            "obrigatorio": False,
            "ativo": True,
            "eh_imutavel": False,
        },
        {
            "campo": "codigo_contrato",
            "nome_regra": "Padrão de Identificação de Contrato Administrativo",
            "descricao": "Estrutura padrão de número de contrato no âmbito do Poder Executivo Estadual.",
            "padrao_regex": r"^CT-\d{4}/\d{4}$",
            "mensagem_erro": "O código de contrato deve conter o prefixo CT- seguido do sequencial e do ano com 4 dígitos.",
            "formato_esperado": "CT-0042/2026",
            "obrigatorio": False,
            "ativo": True,
            "eh_imutavel": False,
        },
        {
            "campo": "email_institucional",
            "nome_regra": "Domínio de Correio Eletrônico Governamental de Rondônia",
            "descricao": "Restringe e valida endereços de correio eletrônico oficiais com domínio @*.ro.gov.br.",
            "padrao_regex": r"^[a-zA-Z0-9._%+-]+@([a-zA-Z0-9-]+\.)*ro\.gov\.br$",
            "mensagem_erro": "O e-mail deve pertencer a um domínio governamental oficial de Rondônia (*.ro.gov.br).",
            "formato_esperado": "servidor@setic.ro.gov.br",
            "obrigatorio": False,
            "ativo": True,
            "eh_imutavel": False,
        },
    ]

    for item in regras_iniciais:
        existente = (
            db.query(RegraValidacao)
            .filter(
                RegraValidacao.campo == item["campo"],
                RegraValidacao.nome_regra == item["nome_regra"],
            )
            .first()
        )
        if not existente:
            regra = RegraValidacao(**item)
            db.add(regra)
    db.commit()


def init_db() -> None:
    """Inicializa as tabelas do banco de dados e semeia regras padrão."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        popular_regras_iniciais(db)
    finally:
        db.close()
