"""Testes unitários para o módulo de mascaramento de dados sensíveis (LGPD).

Garante que nenhuma informação pessoal identificável (CPF, CNPJ, telefone,
e-mail e PIS) seja persistida ou exibida sem máscara de privacidade.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, RegistroAuditoria
from backend.domain.masking import (
    CAMPOS_SENSIVEIS,
    mascarar_cnpj,
    mascarar_cpf,
    mascarar_dados,
    mascarar_email,
    mascarar_erros,
    mascarar_pis,
    mascarar_telefone,
    mascarar_valor,
)
from backend.engine.core_tier import CoreTierStep
from backend.repositories.audit import AuditRepository


@pytest.fixture
def db_session_masking():
    """Cria uma sessão isolada SQLite em memória para testes de persistência mascarada."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_campos_sensiveis_bidict():
    """Valida se CAMPOS_SENSIVEIS provém dinamicamente do BiDict do Core Tier."""
    step = CoreTierStep()
    assert CAMPOS_SENSIVEIS == step.map.campos_sensiveis
    assert "cpf" in CAMPOS_SENSIVEIS
    assert "num_cpf" in CAMPOS_SENSIVEIS
    assert "cnpj" in CAMPOS_SENSIVEIS
    assert "celular" in CAMPOS_SENSIVEIS
    assert "telefone_contato" in CAMPOS_SENSIVEIS
    assert "correio_eletronico" in CAMPOS_SENSIVEIS
    assert "pis" in CAMPOS_SENSIVEIS
    assert "nis" in CAMPOS_SENSIVEIS
    assert "municipio" not in CAMPOS_SENSIVEIS
    assert "codigo_ibge" not in CAMPOS_SENSIVEIS
    assert "cep" not in CAMPOS_SENSIVEIS


def test_mascarar_cpf():
    """Valida mascaramento de CPF preservando formatação quando presente."""
    assert mascarar_cpf("117.941.016-59") == "117.***.***-59"
    assert mascarar_cpf("11794101659") == "117******59"
    assert mascarar_cpf("123") == "***"
    assert mascarar_cpf("12345") == "12***45"


def test_mascarar_cnpj():
    """Valida mascaramento de CNPJ preservando formatação quando presente."""
    assert mascarar_cnpj("12.345.678/0001-95") == "12.***.***/0001-95"
    assert mascarar_cnpj("12345678000195") == "12******000195"
    assert mascarar_cnpj("1234") == "***"


def test_mascarar_pis():
    """Valida mascaramento de PIS/PASEP preservando formatação quando presente."""
    assert mascarar_pis("123.45678.90-1") == "123.*****.90-1"
    assert mascarar_pis("12345678901") == "123*****901"
    assert mascarar_pis("12") == "***"


def test_mascarar_telefone():
    """Valida mascaramento de telefones fixos e celulares mantendo formato de entrada (com ou sem parênteses)."""
    assert mascarar_telefone("(69) 99234-5678") == "(69) 9****-5678"
    assert mascarar_telefone("69992345678") == "699****5678"
    assert mascarar_telefone("+55 (69) 99234-5678") == "(69) 9****-5678"
    assert mascarar_telefone("(69) 3216-5000") == "(69) ****-5000"
    assert mascarar_telefone("6932165000") == "69****5000"
    assert mascarar_telefone("99234-5678") == "9****-5678"
    assert mascarar_telefone("3216-5000") == "****-5000"
    assert mascarar_telefone("123") == "***"


def test_mascarar_email():
    """Valida mascaramento de correio eletrônico."""
    assert mascarar_email("cidadao@rondonia.gov.br") == "c***o@rondonia.gov.br"
    assert mascarar_email("ab@rondonia.gov.br") == "a***@rondonia.gov.br"
    assert mascarar_email("a@rondonia.gov.br") == "a***@rondonia.gov.br"
    assert mascarar_email("invalido") == "i***o"
    assert mascarar_email("abc") == "***"


def test_mascarar_valor_por_campo():
    """Valida despacho polimórfico de mascaramento por nome do campo ou alias."""
    assert mascarar_valor("cpf", "11794101659") == "117******59"
    assert mascarar_valor("num_cpf", "117.941.016-59") == "117.***.***-59"
    assert mascarar_valor("celular", "(69) 99234-5678") == "(69) 9****-5678"
    assert mascarar_valor("celular", "69992345678") == "699****5678"
    assert mascarar_valor("correio_eletronico", "user@gov.br") == "u***r@gov.br"
    assert mascarar_valor("municipio", "Porto Velho") == "Porto Velho"
    assert mascarar_valor("uf", "RO") == "RO"
    assert mascarar_valor("data", "1985-03-15") == "1985-03-15"
    assert mascarar_valor("cpf", None) is None


def test_mascarar_dados_dicionario_completo():
    """Valida mascaramento de dicionários mantendo campos não sensíveis intactos."""
    dados = {
        "cpf": "117.941.016-59",
        "num_cpf": "11794101659",
        "telefone": "(69) 99234-5678",
        "email": "contato@setic.ro.gov.br",
        "pis": "12345678901",
        "municipio": "Porto Velho",
        "uf": "RO",
        "codigo_ibge": "1100205",
        "data": "1985-03-15",
    }
    mascarados = mascarar_dados(dados)

    # Campos sensíveis mascarados conforme formatação fornecida
    assert mascarados["cpf"] == "117.***.***-59"
    assert mascarados["num_cpf"] == "117******59"
    assert mascarados["telefone"] == "(69) 9****-5678"
    assert mascarados["email"] == "c***o@setic.ro.gov.br"
    assert mascarados["pis"] == "123*****901"

    # Campos públicos / geográficos / cadastrais preservados
    assert mascarados["municipio"] == "Porto Velho"
    assert mascarados["uf"] == "RO"
    assert mascarados["codigo_ibge"] == "1100205"
    assert mascarados["data"] == "1985-03-15"

    # Dicionário vazio e None
    assert mascarar_dados({}) == {}
    assert mascarar_dados(None) == {}


def test_mascarar_erros_diagnosticos():
    """Valida mascaramento do valor rejeitado em diagnósticos de erro de campos sensíveis."""
    erros: list[dict[str, object]] = [
        {
            "campo": "cpf",
            "regra_violada": "DIGITO_VERIFICADOR_INVALIDO",
            "valor_rejeitado": "11794101600",
            "formato_esperado": "CPF válido",
            "mensagem": "Falha de validação",
        },
        {
            "campo": "municipio",
            "regra_violada": "MUNICIPIO_INEXISTENTE",
            "valor_rejeitado": "Atlantida",
            "formato_esperado": "Município existente",
            "mensagem": "Não encontrado",
        },
    ]
    erros_masc = mascarar_erros(erros)
    assert erros_masc is not None
    assert erros_masc[0]["valor_rejeitado"] == "117******00"
    assert erros_masc[1]["valor_rejeitado"] == "Atlantida"
    assert mascarar_erros(None) is None


def test_audit_repository_nao_persiste_dados_sensiveis(db_session_masking):
    """Garante que a persistência no banco de dados armazena dados de auditoria estritamente mascarados."""
    repo = AuditRepository(db_session_masking)

    dados_entrada: dict[str, object] = {
        "cpf": "117.941.016-59",
        "telefone": "(69) 99234-5678",
        "email": "cidadao@rondonia.gov.br",
        "municipio": "p. velho",
        "uf": "RO",
    }
    dados_norm: dict[str, object] = {
        "cpf": "11794101659",
        "telefone": "+5569992345678",
        "email": "cidadao@rondonia.gov.br",
        "municipio": "Porto Velho",
        "uf": "RO",
    }

    registro = repo.salvar_registro(
        protocolo="prot-mask-test-01",
        sistema_origem="SISTEMA_TESTE",
        sucesso=True,
        status_http=200,
        dados_entrada=dados_entrada,
        dados_normalizados=dados_norm,
        erros=None,
        tempo_processamento_ms=12.5,
    )
    assert registro.protocolo == "prot-mask-test-01"

    # Recupera diretamente da tabela do banco de dados
    db_reg = (
        db_session_masking.query(RegistroAuditoria)
        .filter(RegistroAuditoria.protocolo == "prot-mask-test-01")
        .first()
    )
    assert db_reg is not None

    # O banco de dados NÃO pode conter o CPF ou telefone em texto puro
    assert "117.941.016-59" not in str(db_reg.dados_entrada)
    assert "11794101659" not in str(db_reg.dados_normalizados)
    assert "99234-5678" not in str(db_reg.dados_entrada)
    assert "cidadao@rondonia.gov.br" not in str(db_reg.dados_entrada)

    # Mas contém a versão mascarada com segurança (dados_entrada preserva formato; dados_normalizados reflete formato canônico numérico)
    assert db_reg.dados_entrada["cpf"] == "117.***.***-59"
    assert db_reg.dados_normalizados["cpf"] == "117******59"
    assert db_reg.dados_entrada["telefone"] == "(69) 9****-5678"
    assert db_reg.dados_normalizados["telefone"] == "699****5678"
    assert db_reg.dados_entrada["municipio"] == "p. velho"
    assert db_reg.dados_normalizados["municipio"] == "Porto Velho"


def test_pipeline_mantem_resposta_normalizada_e_mascara_somente_log(db_session_masking):
    """Garante que a resposta da API mantém o dado canônico normalizado, e apenas a camada de log/persistência é mascarada."""
    from backend.engine.pipeline import ValidationPipeline
    from backend.repositories.rules import RuleRepository

    rule_repo = RuleRepository(db_session_masking)
    audit_repo = AuditRepository(db_session_masking)
    pipeline = ValidationPipeline(rule_repo=rule_repo, audit_repo=audit_repo)

    payload: dict[str, object] = {
        "cpf": "117.941.016-59",
        "telefone": "(69) 99234-5678",
        "email": "cidadao@rondonia.gov.br",
        "municipio": "p. velho",
        "uf": "RO",
    }

    resultado = pipeline.execute(dados_entrada=payload, sistema_origem="SISTEMA_ORIGEM_TESTE")

    # 1. A RESPOSTA DA API REFLETE OS DADOS NORMALIZADOS REAIS (NÃO MASCARADOS)
    assert resultado.sucesso is True
    assert resultado.dados_normalizados is not None
    assert resultado.dados_normalizados["cpf"] == "11794101659"
    assert resultado.dados_normalizados["telefone"] == "69992345678"
    assert resultado.dados_normalizados["email"] == "cidadao@rondonia.gov.br"
    assert resultado.dados_normalizados["municipio"] == "Porto Velho"

    # 2. A CAMADA DE LOG / PERSISTÊNCIA NO BANCO ARMAZENA ESTES MESMOS DADOS MASCARADOS
    db_reg = (
        db_session_masking.query(RegistroAuditoria)
        .filter(RegistroAuditoria.protocolo == resultado.protocolo)
        .first()
    )
    assert db_reg is not None
    assert db_reg.dados_entrada["cpf"] == "117.***.***-59"
    assert db_reg.dados_normalizados["cpf"] == "117******59"
    assert db_reg.dados_entrada["telefone"] == "(69) 9****-5678"
    assert db_reg.dados_normalizados["telefone"] == "699****5678"
    assert db_reg.dados_entrada["email"] == "c***o@rondonia.gov.br"
    assert db_reg.dados_normalizados["email"] == "c***o@rondonia.gov.br"
