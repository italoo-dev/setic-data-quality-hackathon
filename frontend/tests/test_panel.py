"""Testes Automatizados da Camada de Interface / Painel Streamlit (Frontend)."""

from __future__ import annotations

from frontend.app import _LOGO_PATH, consultar_api_saude, executar_validacao


def test_logo_asset_exists_and_valid():
    """Verifica se o logotipo SVG do Tux/NixOS existe e contém a estrutura esperada."""
    assert _LOGO_PATH.exists()
    assert _LOGO_PATH.is_file()
    conteudo = _LOGO_PATH.read_text(encoding="utf-8")
    assert "<svg" in conteudo
    assert "nix-lambda" in conteudo
    assert "tux-beak" in conteudo


def test_consultar_api_saude_sem_servidor():
    """Verifica que a consulta de saúde lida graciosamente com ausência de API remota."""
    # Como a API externa pode estar offline no ambiente de teste unitário,
    # deve retornar None ou dicionário de status sem lançar exceção não tratada.
    res = consultar_api_saude()
    assert res is None or isinstance(res, dict)


def test_executar_validacao_fallback_motor_local():
    """Verifica a execução de validação via fallback direto do motor quando sem HTTP."""
    payload: dict[str, object] = {
        "sistema_origem": "TESTE_FRONTEND",
        "dados": {
            "cpf": "117.941.016-59",
            "data_nascimento": "15/03/1985",
            "municipio": "Porto Velho",
            "uf": "RO",
        },
    }
    status_code, resultado = executar_validacao(payload)
    assert status_code in (200, 422)
    assert isinstance(resultado, dict)
    assert "protocolo" in resultado
