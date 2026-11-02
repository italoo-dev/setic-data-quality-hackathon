"""Suíte de Testes Automatizados - Motor de Qualidade e API SETIC/CAGD."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.database import SessionLocal, init_db
from backend.main import app
from backend.validators import (
    validar_e_normalizar_cep,
    validar_e_normalizar_cnpj,
    validar_e_normalizar_cpf,
    validar_e_normalizar_data,
    validar_e_normalizar_email,
    validar_e_normalizar_municipio,
    validar_e_normalizar_pis,
    validar_e_normalizar_telefone,
)


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
    import brutils

    cnpj_limpo = brutils.generate_cnpj()
    cnpj_valido_com_mascara = brutils.format_cnpj(cnpj_limpo)
    res = validar_e_normalizar_cnpj(cnpj_valido_com_mascara)
    assert res.valido is True
    assert isinstance(res.valor_normalizado, str)
    assert len(res.valor_normalizado) == 14


def test_data_portugues_normalizacao_iso():
    """Verifica se data escrita por extenso em português é convertida para ISO-8601 (AAAA-MM-DD)."""
    res = validar_e_normalizar_data("15 de março de 1985")
    assert res.valido is True
    assert res.valor_normalizado == "1985-03-15"
    assert res.campo == "data"


def test_data_impossivel_calendario_bloqueio():
    """Verifica se datas impossíveis no calendário (ex: 31 de fevereiro) são estritamente bloqueadas."""
    res = validar_e_normalizar_data("31/02/1990")
    assert res.valido is False
    assert res.regra_violada == "DATA_IMPOSSIVEL_CALENDARIO"
    assert res.campo == "data"

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
    assert res.regra_violada == "TELEFONE_INVALIDO_ANATEL"


def test_municipio_fuzzy_rondonia():
    """Verifica se 'p. velho' é aproximado para 'Porto Velho' com código IBGE 1100205."""
    res = validar_e_normalizar_municipio("p. velho", "RO")
    assert res.valido is True
    assert isinstance(res.valor_normalizado, dict)
    assert res.valor_normalizado["municipio"] == "Porto Velho"
    assert res.valor_normalizado["codigo_ibge"] == "1100205"
    assert res.valor_normalizado["uf"] == "RO"


def test_municipio_nacional_fora_ro():
    """Verifica a resolução de cidades de outros estados (São Paulo/SP)."""
    res = validar_e_normalizar_municipio("sao paulo", "SP")
    assert res.valido is True
    assert isinstance(res.valor_normalizado, dict)
    assert res.valor_normalizado["municipio"] in ("São Paulo", "Sao Paulo")
    assert res.valor_normalizado["codigo_ibge"] == "3550308"


def test_municipio_bidirecional_codigo_ibge():
    """Verifica a resolução reversa do código IBGE de 7 dígitos para o nome oficial."""
    res = validar_e_normalizar_municipio("1100122")
    assert res.valido is True
    assert isinstance(res.valor_normalizado, dict)
    assert res.valor_normalizado["municipio"] in ("Ji-Paraná", "Ji-Parana")
    assert res.valor_normalizado["uf"] == "RO"


def test_municipio_inexistente_bloqueio():
    """Verifica se município inventado é rejeitado com 422."""
    res = validar_e_normalizar_municipio("Atlantida", "RO")
    assert res.valido is False
    assert res.regra_violada == "MUNICIPIO_IBGE_NAO_ENCONTRADO"


def test_municipio_com_uf_nome_extenso():
    """Verifica se nome do estado por extenso (ex: 'Rondônia') é convertido para a sigla oficial via brutils."""
    res = validar_e_normalizar_municipio("Porto Velho", "Rondônia")
    assert res.valido is True
    assert isinstance(res.valor_normalizado, dict)
    assert res.valor_normalizado["municipio"] == "Porto Velho"
    assert res.valor_normalizado["uf"] == "RO"
    assert res.valor_normalizado["codigo_ibge"] == "1100205"


def test_cep_valido_normalizacao():
    """Verifica se CEP com ou sem hífen é normalizado para 8 dígitos via brutils."""
    res_com_hifen = validar_e_normalizar_cep("76801-000")
    assert res_com_hifen.valido is True
    assert res_com_hifen.valor_normalizado == "76801000"

    res_sem_hifen = validar_e_normalizar_cep("76801000")
    assert res_sem_hifen.valido is True
    assert res_sem_hifen.valor_normalizado == "76801000"


def test_cep_invalido_bloqueio():
    """Verifica se CEP com formato inadequado é rejeitado via brutils."""
    res = validar_e_normalizar_cep("12345")
    assert res.valido is False
    assert res.regra_violada == "FORMATO_CEP_INVALIDO"


def test_email_valido_normalizacao():
    """Verifica se e-mail com letras maiúsculas é normalizado para minúsculas via brutils."""
    res = validar_e_normalizar_email("Contato@SETIC.RO.GOV.BR")
    assert res.valido is True
    assert res.valor_normalizado == "contato@setic.ro.gov.br"


def test_email_invalido_bloqueio():
    """Verifica se e-mail malformado é rejeitado via brutils."""
    res = validar_e_normalizar_email("usuario_invalido_sem_arroba.com")
    assert res.valido is False
    assert res.regra_violada == "FORMATO_EMAIL_INVALIDO"


def test_pis_valido_normalizacao():
    """Verifica se PIS válido é normalizado para 11 dígitos limpos via brutils."""
    import brutils

    pis_gerado = brutils.generate_pis()
    res = validar_e_normalizar_pis(pis_gerado)
    assert res.valido is True
    assert isinstance(res.valor_normalizado, str)
    assert len(res.valor_normalizado) == 11


def test_pis_invalido_bloqueio():
    """Verifica se PIS com dígitos inválidos é rejeitado via brutils."""
    res = validar_e_normalizar_pis("111.11111.11-1")
    assert res.valido is False
    assert res.regra_violada == "PIS_INVALIDO"


# =====================================================================
# TESTES DE INTEGRAÇÃO END-TO-END COM FASTAPI
# =====================================================================


def test_api_validar_payload_valido(client):
    """Verifica resposta 200 OK da API com dados normalizados e protocolo."""
    payload = {
        "sistema_origem": "TESTE_INTEGRACAO",
        "dados": {
            "cpf": "117.941.016-59",
            "data": "15 de março de 1985",
            "data_nascimento": "15 de março de 1985",
            "municipio": "p. velho",
            "uf": "RO",
            "cep": "76.801-000",
            "email": "JOAO.SILVA@RO.GOV.BR",
            "matricula_funcional": "RO-123456",
        },
    }
    resp = client.post("/api/v1/validar", json=payload)
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["sucesso"] is True
    assert dados["dados_normalizados"]["cpf"] == "11794101659"
    assert dados["dados_normalizados"]["data"] == "1985-03-15"
    assert dados["dados_normalizados"]["data_nascimento"] == "1985-03-15"
    assert dados["dados_normalizados"]["municipio"] == "Porto Velho"
    assert dados["dados_normalizados"]["codigo_ibge"] == "1100205"
    assert dados["dados_normalizados"]["cep"] == "76801000"
    assert dados["dados_normalizados"]["email"] == "joao.silva@ro.gov.br"
    assert "protocolo" in dados


def test_api_validar_payload_corrompido_bloqueio(client):
    """Verifica resposta 422 Unprocessable Entity com diagnóstico detalhado."""
    payload = {
        "sistema_origem": "TESTE_INTEGRACAO",
        "dados": {
            "cpf": "123.456.789-00",
            "data_nascimento": "31/02/1990",
            "municipio": "Wakanda",
            "cep": "123",
            "email": "invalido",
            "matricula_funcional": "MAT-INVALIDA",
        },
    }
    resp = client.post("/api/v1/validar", json=payload)
    assert resp.status_code == 422
    dados = resp.json()
    assert dados["sucesso"] is False
    assert len(dados["erros"]) >= 6

    campos_com_erro = {e["campo"] for e in dados["erros"]}
    assert "cpf" in campos_com_erro
    assert "data_nascimento" in campos_com_erro
    assert "municipio" in campos_com_erro
    assert "cep" in campos_com_erro
    assert "email" in campos_com_erro
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


def test_api_editar_regra_dinamica(client):
    """Verifica a edição (PUT) de uma regra dinâmica existente."""
    # Criar regra temporária para teste
    payload_criacao = {
        "campo": "codigo_projeto_teste",
        "nome_regra": "Padrão de Projeto Original",
        "descricao": "Descrição teste",
        "padrao_regex": r"^PRJ-\d{4}$",
        "mensagem_erro": "Código de projeto inválido.",
        "formato_esperado": "PRJ-9999",
        "obrigatorio": False,
        "ativo": True,
    }
    resp_post = client.post("/api/v1/regras", json=payload_criacao)
    assert resp_post.status_code == 201
    regra_criada = resp_post.json()
    regra_id = regra_criada["id"]

    # Atualizar atributos da regra
    payload_edicao = {
        "nome_regra": "Padrão de Projeto Atualizado",
        "padrao_regex": r"^PRJ-\d{5}$",
        "mensagem_erro": "Código de projeto deve ter 5 dígitos.",
        "formato_esperado": "PRJ-99999",
        "obrigatorio": True,
    }
    resp_put = client.put(f"/api/v1/regras/{regra_id}", json=payload_edicao)
    assert resp_put.status_code == 200
    regra_atualizada = resp_put.json()
    assert regra_atualizada["nome_regra"] == "Padrão de Projeto Atualizado"
    assert regra_atualizada["padrao_regex"] == r"^PRJ-\d{5}$"
    assert regra_atualizada["formato_esperado"] == "PRJ-99999"
    assert regra_atualizada["obrigatorio"] is True

    # Limpeza
    client.delete(f"/api/v1/regras/{regra_id}")


def test_api_exportar_e_importar_regras(client):
    """Verifica os fluxos de exportação e importação em lote de regras dinâmicas."""
    import uuid

    # 1. Exportação
    resp_exp = client.get("/api/v1/regras/exportar")
    assert resp_exp.status_code == 200
    dados_exp = resp_exp.json()
    assert dados_exp["versao"] == "1.0"
    assert "regras" in dados_exp
    assert isinstance(dados_exp["regras"], list)

    campo_teste = f"numero_processo_cagd_{uuid.uuid4().hex[:6]}"

    # 2. Importação com nova regra
    regra_importacao = {
        "campo": campo_teste,
        "nome_regra": "Padrão de Processo CAGD",
        "descricao": "Regra importada via automação",
        "padrao_regex": r"^CAGD-\d{4}/\d{4}$",
        "mensagem_erro": "Processo fora do padrão CAGD.",
        "formato_esperado": "CAGD-1234/2026",
        "obrigatorio": False,
        "ativo": True,
    }
    payload_imp = {
        "sobrescrever": False,
        "regras": [regra_importacao],
    }

    try:
        resp_imp = client.post("/api/v1/regras/importar", json=payload_imp)
        assert resp_imp.status_code == 200
        res_imp = resp_imp.json()
        assert res_imp["sucesso"] is True
        assert res_imp["total_processadas"] == 1
        assert res_imp["total_criadas"] == 1

        # 3. Importação duplicada sem sobrescrita (deve ignorar)
        resp_imp2 = client.post("/api/v1/regras/importar", json=payload_imp)
        assert resp_imp2.status_code == 200
        res_imp2 = resp_imp2.json()
        assert res_imp2["total_ignoradas"] == 1

        # 4. Importação duplicada com sobrescrita ativada (deve atualizar)
        regra_importacao["mensagem_erro"] = "Mensagem atualizada via sobrescrita."
        payload_imp_sobrescrita = {
            "sobrescrever": True,
            "regras": [regra_importacao],
        }
        resp_imp3 = client.post("/api/v1/regras/importar", json=payload_imp_sobrescrita)
        assert resp_imp3.status_code == 200
        res_imp3 = resp_imp3.json()
        assert res_imp3["total_atualizadas"] == 1
    finally:
        regras_api = client.get(f"/api/v1/regras?campo={campo_teste}").json()
        for r in regras_api:
            client.delete(f"/api/v1/regras/{r['id']}")
