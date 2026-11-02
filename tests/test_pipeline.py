"""Suíte de Testes Automatizados - Motor de Qualidade e API SETIC/CAGD."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core_validators import (
    validar_e_normalizar_cnpj,
    validar_e_normalizar_cpf,
    validar_e_normalizar_data,
    validar_e_normalizar_municipio,
    validar_e_normalizar_telefone,
)
from app.database import SessionLocal, init_db
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Inicializa tabelas do banco de dados para os testes."""
    init_db()


@pytest.fixture
def db_session():
    """Gera uma sessão isolada para o teste."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    """Cliente de teste FastAPI."""
    return TestClient(app)


# =====================================================================
# TESTES DE VALIDADORES DE NÚCLEO (CORE VALIDATORS)
# =====================================================================


def test_cpf_valido_normalizacao():
    """Verifica se um CPF válido com máscara e espaços é normalizado para 11 dígitos limpos."""
    res = validar_e_normalizar_cpf("  117.941.016-59  ")
    assert res.valido is True
    assert res.valor_normalizado == "11794101659"


def test_cpf_invalido_checksum_bloqueio():
    """Verifica se um CPF com dígitos verificadores incorretos é estritamente bloqueado."""
    res = validar_e_normalizar_cpf("123.456.789-00")
    assert res.valido is False
    assert res.regra_violada == "DIGITO_VERIFICADOR_INVALIDO"


def test_cpf_digitos_repetidos_bloqueio():
    """Verifica se CPF com dígitos idênticos é rejeitado."""
    res = validar_e_normalizar_cpf("111.111.111-11")
    assert res.valido is False
    assert res.regra_violada == "CPF_SEQUENCIA_INVALIDA"


def test_cnpj_valido_normalizacao():
    """Verifica se CNPJ válido é normalizado para 14 dígitos limpos."""
    from validate_docbr import CNPJ

    cnpj_gerador = CNPJ()
    cnpj_valido_com_mascara = cnpj_gerador.generate(mask=True)
    res = validar_e_normalizar_cnpj(cnpj_valido_com_mascara)
    assert res.valido is True
    assert len(res.valor_normalizado) == 14


def test_data_portugues_normalizacao_iso():
    """Verifica se data escrita por extenso em português é convertida para ISO-8601 (AAAA-MM-DD)."""
    res = validar_e_normalizar_data("15 de março de 1985")
    assert res.valido is True
    assert res.valor_normalizado == "1985-03-15"


def test_data_impossivel_calendario_bloqueio():
    """Verifica se datas impossíveis no calendário (ex: 31 de fevereiro) são estritamente bloqueadas."""
    res = validar_e_normalizar_data("31/02/1990")
    assert res.valido is False
    assert res.regra_violada == "DATA_IMPOSSIVEL_CALENDARIO"

    res_bissexto = validar_e_normalizar_data("29/02/2023")  # 2023 não é bissexto
    assert res_bissexto.valido is False
    assert res_bissexto.regra_violada == "DATA_IMPOSSIVEL_CALENDARIO"


def test_telefone_valido_normalizacao():
    """Verifica se telefone com DDD 69 é aceito e normalizado."""
    res = validar_e_normalizar_telefone("(69) 99234-5678")
    assert res.valido is True
    assert res.valor_normalizado == "69992345678"


def test_telefone_ddd_inexistente_bloqueio():
    """Verifica se DDD não regulamentado pela Anatel causa bloqueio."""
    res = validar_e_normalizar_telefone("(20) 99234-5678")
    assert res.valido is False
    assert res.regra_violada == "DDD_INEXISTENTE_NO_BRASIL"


def test_municipio_fuzzy_rondonia():
    """Verifica se 'p. velho' é aproximado para 'Porto Velho' com código IBGE 1100205."""
    res = validar_e_normalizar_municipio("p. velho", "RO")
    assert res.valido is True
    assert res.valor_normalizado["municipio"] == "Porto Velho"
    assert res.valor_normalizado["codigo_ibge"] == "1100205"
    assert res.valor_normalizado["uf"] == "RO"


def test_municipio_nacional_fora_ro():
    """Verifica a resolução de cidades de outros estados (São Paulo/SP)."""
    res = validar_e_normalizar_municipio("sao paulo", "SP")
    assert res.valido is True
    assert res.valor_normalizado["municipio"] == "São Paulo"
    assert res.valor_normalizado["codigo_ibge"] == "3550308"


def test_municipio_bidirecional_codigo_ibge():
    """Verifica a resolução reversa do código IBGE de 7 dígitos para o nome oficial."""
    res = validar_e_normalizar_municipio("1100122")
    assert res.valido is True
    assert res.valor_normalizado["municipio"] == "Ji-Paraná"
    assert res.valor_normalizado["uf"] == "RO"


def test_municipio_inexistente_bloqueio():
    """Verifica se município inventado é rejeitado com 422."""
    res = validar_e_normalizar_municipio("Atlantida", "RO")
    assert res.valido is False
    assert res.regra_violada == "MUNICIPIO_IBGE_NAO_ENCONTRADO"


# =====================================================================
# TESTES DE INTEGRAÇÃO END-TO-END COM FASTAPI
# =====================================================================


def test_api_validar_payload_valido(client):
    """Verifica resposta 200 OK da API com dados normalizados e protocolo."""
    payload = {
        "sistema_origem": "TESTE_INTEGRACAO",
        "dados": {
            "cpf": "117.941.016-59",
            "data_nascimento": "15 de março de 1985",
            "municipio": "p. velho",
            "uf": "RO",
            "matricula_funcional": "RO-123456",
        },
    }
    resp = client.post("/api/v1/validar", json=payload)
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["sucesso"] is True
    assert dados["dados_normalizados"]["cpf"] == "11794101659"
    assert dados["dados_normalizados"]["data_nascimento"] == "1985-03-15"
    assert dados["dados_normalizados"]["municipio"] == "Porto Velho"
    assert dados["dados_normalizados"]["codigo_ibge"] == "1100205"
    assert "protocolo" in dados


def test_api_validar_payload_corrompido_bloqueio(client):
    """Verifica resposta 422 Unprocessable Entity com diagnóstico detalhado."""
    payload = {
        "sistema_origem": "TESTE_INTEGRACAO",
        "dados": {
            "cpf": "123.456.789-00",
            "data_nascimento": "31/02/1990",
            "municipio": "Wakanda",
            "matricula_funcional": "MAT-INVALIDA",
        },
    }
    resp = client.post("/api/v1/validar", json=payload)
    assert resp.status_code == 422
    dados = resp.json()
    assert dados["sucesso"] is False
    assert len(dados["erros"]) >= 4

    campos_com_erro = {e["campo"] for e in dados["erros"]}
    assert "cpf" in campos_com_erro
    assert "data_nascimento" in campos_com_erro
    assert "municipio" in campos_com_erro
    assert "matricula_funcional" in campos_com_erro


def test_api_metricas_cagd(client):
    """Verifica o endpoint de métricas operacionais para a CAGD."""
    resp = client.get("/api/v1/metricas")
    assert resp.status_code == 200
    metricas = resp.json()
    assert "total_requisicoes" in metricas
    assert "taxa_rejeicao_percentual" in metricas
    assert "volume_por_sistema" in metricas
    assert "top_campos_rejeitados" in metricas


def test_api_bloqueio_alteracao_regra_imutavel(client):
    """Verifica que regras de núcleo protegidas não podem ser excluídas nem alteradas."""
    # Obter regra com eh_imutavel = True
    regras = client.get("/api/v1/regras").json()
    regra_core = next(r for r in regras if r["eh_imutavel"])

    # Tentativa de exclusão deve retornar 403 Forbidden
    resp_delete = client.delete(f"/api/v1/regras/{regra_core['id']}")
    assert resp_delete.status_code == 403

    # Tentativa de toggle deve retornar 403 Forbidden
    resp_toggle = client.patch(f"/api/v1/regras/{regra_core['id']}/toggle")
    assert resp_toggle.status_code == 403
