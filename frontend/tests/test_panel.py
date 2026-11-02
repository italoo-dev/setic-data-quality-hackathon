"""Testes Automatizados da Camada de Interface / Painel Streamlit e Cliente REST (Frontend)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from backend.schemas import (
    RegraValidacaoAtualizacao,
    RegraValidacaoCriacao,
)
from frontend.app import _LOGO_PATH, obter_cliente_api
from frontend.client import ApiError, SeticApiClient


def test_logo_asset_exists_and_valid():
    """Verifica se o logotipo SVG do Tux/NixOS existe e contém a estrutura esperada."""
    assert _LOGO_PATH.exists()
    assert _LOGO_PATH.is_file()
    conteudo = _LOGO_PATH.read_text(encoding="utf-8")
    assert "<svg" in conteudo
    assert "nix-lambda" in conteudo
    assert "tux-beak" in conteudo


def test_obter_cliente_api_singleton():
    """Verifica se a função singleton retorna uma instância de SeticApiClient."""
    cliente = obter_cliente_api()
    assert isinstance(cliente, SeticApiClient)


def test_cliente_api_saude_sucesso():
    """Verifica consulta de saúde quando a API responde HTTP 200."""
    resposta_mock = MagicMock(spec=httpx.Response)
    resposta_mock.status_code = 200
    resposta_mock.json.return_value = {
        "status": "operacional",
        "versao": "1.0.0",
        "municipios_ibge_indexados": 5570,
    }

    cliente = SeticApiClient()
    with patch.object(cliente._client, "get", return_value=resposta_mock):
        res = cliente.consultar_saude()
        assert res is not None
        assert res.get("status") == "operacional"
        assert res.get("municipios_ibge_indexados") == 5570


def test_cliente_api_saude_offline():
    """Verifica comportamento gracioso quando a API está offline."""
    cliente = SeticApiClient()
    with patch.object(
        cliente._client,
        "get",
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        res = cliente.consultar_saude()
        assert res is None


def test_cliente_api_obter_metricas_sucesso():
    """Verifica obtenção tipada de métricas operacionais consolidadas."""
    resposta_mock = MagicMock(spec=httpx.Response)
    resposta_mock.status_code = 200
    resposta_mock.json.return_value = {
        "total_requisicoes": 150,
        "total_sucessos": 120,
        "total_bloqueios": 30,
        "taxa_rejeicao_percentual": 20.0,
        "tempo_medio_processamento_ms": 1.45,
        "volume_por_sistema": [
            {
                "sistema_origem": "RH",
                "total": 150,
                "aprovados": 120,
                "rejeitados": 30,
                "taxa_rejeicao_percentual": 20.0,
            }
        ],
        "top_campos_rejeitados": [{"nome": "cpf", "quantidade": 25}],
        "top_regras_violadas": [{"nome": "CORE_CPF_INVALIDO", "quantidade": 25}],
    }

    cliente = SeticApiClient()
    with patch.object(cliente._client, "get", return_value=resposta_mock):
        metricas = cliente.obter_metricas()
        assert metricas is not None
        assert metricas.total_requisicoes == 150
        assert metricas.total_sucessos == 120
        assert metricas.total_bloqueios == 30
        assert metricas.taxa_rejeicao_percentual == 20.0
        assert len(metricas.volume_por_sistema) == 1
        assert metricas.volume_por_sistema[0].sistema_origem == "RH"


def test_cliente_api_obter_metricas_falha():
    """Verifica retorno None em caso de falha de conexão na busca de métricas."""
    cliente = SeticApiClient()
    with patch.object(cliente._client, "get", side_effect=httpx.RequestError("Timeout")):
        assert cliente.obter_metricas() is None


def test_cliente_api_listar_regras_sucesso():
    """Verifica listagem tipada de regras de validação."""
    resposta_mock = MagicMock(spec=httpx.Response)
    resposta_mock.status_code = 200
    resposta_mock.json.return_value = [
        {
            "id": 1,
            "campo": "cpf",
            "nome_regra": "CPF Válido",
            "descricao": "Validação de CPF",
            "padrao_regex": None,
            "mensagem_erro": "CPF inválido",
            "formato_esperado": "11 dígitos",
            "obrigatorio": True,
            "ativo": True,
            "eh_imutavel": True,
            "criado_em": "2026-11-02T12:00:00Z",
            "atualizado_em": "2026-11-02T12:00:00Z",
        }
    ]

    cliente = SeticApiClient()
    with patch.object(cliente._client, "get", return_value=resposta_mock):
        regras = cliente.listar_regras()
        assert regras is not None
        assert len(regras) == 1
        assert regras[0].campo == "cpf"
        assert regras[0].eh_imutavel is True


def test_cliente_api_criar_regra_sucesso_e_erro():
    """Verifica criação de regra dinâmica com sucesso e erro tipado."""
    nova_regra = RegraValidacaoCriacao(
        campo="matricula",
        nome_regra="Padrão Matrícula",
        formato_esperado="RO-123456",
        padrao_regex=r"^RO-\d{6}$",
        mensagem_erro="Formato inválido",
    )

    mock_ok = MagicMock(spec=httpx.Response)
    mock_ok.status_code = 201
    mock_ok.json.return_value = {
        "id": 10,
        "campo": "matricula",
        "nome_regra": "Padrão Matrícula",
        "descricao": None,
        "padrao_regex": r"^RO-\d{6}$",
        "mensagem_erro": "Formato inválido",
        "formato_esperado": "RO-123456",
        "obrigatorio": False,
        "ativo": True,
        "eh_imutavel": False,
        "criado_em": "2026-11-02T12:00:00Z",
        "atualizado_em": "2026-11-02T12:00:00Z",
    }

    cliente = SeticApiClient()
    with patch.object(cliente._client, "post", return_value=mock_ok):
        criada = cliente.criar_regra(nova_regra)
        assert criada.id == 10
        assert criada.campo == "matricula"

    mock_err = MagicMock(spec=httpx.Response)
    mock_err.status_code = 422
    mock_err.json.return_value = {"detail": "Regex inválido"}
    mock_err.text = '{"detail": "Regex inválido"}'

    with patch.object(cliente._client, "post", return_value=mock_err):
        with pytest.raises(ApiError) as exc_info:
            cliente.criar_regra(nova_regra)
        assert exc_info.value.status_code == 422
        assert "Regex inválido" in exc_info.value.detail


def test_cliente_api_atualizar_regra_sucesso():
    """Verifica atualização de regra dinâmica via cliente REST."""
    atualizacao = RegraValidacaoAtualizacao(nome_regra="Nome Atualizado")
    mock_ok = MagicMock(spec=httpx.Response)
    mock_ok.status_code = 200
    mock_ok.json.return_value = {
        "id": 10,
        "campo": "matricula",
        "nome_regra": "Nome Atualizado",
        "descricao": None,
        "padrao_regex": r"^RO-\d{6}$",
        "mensagem_erro": "Formato inválido",
        "formato_esperado": "RO-123456",
        "obrigatorio": False,
        "ativo": True,
        "eh_imutavel": False,
        "criado_em": "2026-11-02T12:00:00Z",
        "atualizado_em": "2026-11-02T12:00:00Z",
    }

    cliente = SeticApiClient()
    with patch.object(cliente._client, "put", return_value=mock_ok):
        res = cliente.atualizar_regra(10, atualizacao)
        assert res.nome_regra == "Nome Atualizado"


def test_cliente_api_alternar_status_regra():
    """Verifica alternância de status ativo/inativo."""
    mock_ok = MagicMock(spec=httpx.Response)
    mock_ok.status_code = 200
    mock_ok.json.return_value = {
        "id": 10,
        "campo": "matricula",
        "nome_regra": "Padrão",
        "descricao": None,
        "padrao_regex": None,
        "mensagem_erro": "Erro",
        "formato_esperado": "RO-123",
        "obrigatorio": False,
        "ativo": False,
        "eh_imutavel": False,
        "criado_em": "2026-11-02T12:00:00Z",
        "atualizado_em": "2026-11-02T12:00:00Z",
    }

    cliente = SeticApiClient()
    with patch.object(cliente._client, "patch", return_value=mock_ok):
        res = cliente.alternar_status_regra(10)
        assert res.ativo is False


def test_cliente_api_excluir_regra():
    """Verifica exclusão de regra dinâmica."""
    mock_ok = MagicMock(spec=httpx.Response)
    mock_ok.status_code = 204

    cliente = SeticApiClient()
    with patch.object(cliente._client, "delete", return_value=mock_ok):
        # Não deve lançar exceção
        cliente.excluir_regra(10)

    mock_err = MagicMock(spec=httpx.Response)
    mock_err.status_code = 403
    mock_err.json.return_value = {"detail": "Regra imutável"}
    mock_err.text = '{"detail": "Regra imutável"}'

    with patch.object(cliente._client, "delete", return_value=mock_err):
        with pytest.raises(ApiError) as exc_info:
            cliente.excluir_regra(1)
        assert exc_info.value.status_code == 403


def test_cliente_api_exportar_e_importar_regras():
    """Verifica fluxo de exportação e importação de regras dinâmicas."""
    mock_exp = MagicMock(spec=httpx.Response)
    mock_exp.status_code = 200
    mock_exp.json.return_value = {
        "versao": "1.0",
        "gerado_em": "2026-11-02T12:00:00Z",
        "total_regras": 1,
        "regras": [
            {
                "campo": "codigo",
                "nome_regra": "Código",
                "descricao": None,
                "padrao_regex": r"^\d+$",
                "mensagem_erro": "Apenas dígitos",
                "formato_esperado": "123",
                "obrigatorio": True,
                "ativo": True,
            }
        ],
    }

    cliente = SeticApiClient()
    with patch.object(cliente._client, "get", return_value=mock_exp):
        exportadas = cliente.exportar_regras()
        assert exportadas is not None
        assert exportadas.total_regras == 1

    mock_imp = MagicMock(spec=httpx.Response)
    mock_imp.status_code = 200
    mock_imp.json.return_value = {
        "sucesso": True,
        "total_processadas": 1,
        "total_criadas": 1,
        "total_atualizadas": 0,
        "total_ignoradas": 0,
        "erros": [],
        "mensagens": ["Regra criada"],
    }

    with patch.object(cliente._client, "post", return_value=mock_imp):
        assert exportadas is not None
        res_imp = cliente.importar_regras(exportadas.regras, sobrescrever=True)
        assert res_imp.sucesso is True
        assert res_imp.total_criadas == 1


def test_cliente_api_validar_200_422_503():
    """Verifica execução de validação via API REST nos diferentes códigos de resposta."""
    cliente = SeticApiClient()

    # 1. Sucesso 200
    mock_200 = MagicMock(spec=httpx.Response)
    mock_200.status_code = 200
    mock_200.json.return_value = {
        "protocolo": "PROT-100",
        "status_http": 200,
        "dados_normalizados": {"cpf": "11794101659"},
        "transformacoes": ["Sanitização de CPF"],
        "tempo_processamento_ms": 1.1,
    }

    with patch.object(cliente._client, "post", return_value=mock_200):
        code, res = cliente.validar({"cpf": "117.941.016-59"}, "TESTE")
        assert code == 200
        assert res.get("protocolo") == "PROT-100"

    # 2. Rejeição 422
    mock_422 = MagicMock(spec=httpx.Response)
    mock_422.status_code = 422
    mock_422.json.return_value = {
        "protocolo": "PROT-200",
        "status_http": 422,
        "mensagem": "Falha de validação",
        "erros": [{"campo": "cpf", "regra_violada": "CORE_CPF_INVALIDO"}],
        "tempo_processamento_ms": 0.9,
    }

    with patch.object(cliente._client, "post", return_value=mock_422):
        code, res = cliente.validar({"cpf": "000.000.000-00"}, "TESTE")
        assert code == 422
        assert res.get("protocolo") == "PROT-200"

    # 3. Falha de conexão 503
    with patch.object(
        cliente._client, "post", side_effect=httpx.ConnectError("Connection refused")
    ):
        code, res = cliente.validar({"cpf": "11794101659"}, "TESTE")
        assert code == 503
        assert "Não foi possível conectar" in str(res.get("mensagem"))


def test_cliente_api_consultar_auditoria():
    """Verifica consulta de registros de auditoria via cliente REST."""
    mock_res = MagicMock(spec=httpx.Response)
    mock_res.status_code = 200
    mock_res.json.return_value = [
        {
            "id": 1,
            "protocolo": "PROT-AUDIT-1",
            "sistema_origem": "TESTE",
            "sucesso": True,
            "tempo_processamento_ms": 1.2,
            "criado_em": "2026-11-02T12:00:00Z",
        }
    ]

    cliente = SeticApiClient()
    with patch.object(cliente._client, "get", return_value=mock_res):
        registros = cliente.consultar_auditoria(sistema_origem="TESTE", limite=10)
        assert registros is not None
        assert len(registros) == 1
        assert registros[0]["protocolo"] == "PROT-AUDIT-1"


def test_cliente_api_context_manager():
    """Verifica fechamento de sessão via context manager."""
    with SeticApiClient() as c:
        assert isinstance(c, SeticApiClient)
