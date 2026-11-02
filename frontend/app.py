"""Painel Administrativo da CAGD - Coordenação de Análise e Gestão de Dados (SETIC/RO).

Dashboard executivo e operacional construído em Streamlit, oferecendo:
1. Métricas operacionais em tempo real (taxas de rejeição, volume por sistema, top campos/regras).
2. Gestão de regras de validação (regras núcleo imutáveis vs regras dinâmicas da CAGD).
3. Sandbox interativo de teste de payloads em tempo real com cenários de demonstração.
4. Consulta analítica à trilha de auditoria e telemetria.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Previne que o diretório 'frontend' cause sombreamento no sys.path do Streamlit
_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
_FRONTEND_DIR = str(Path(__file__).resolve().parent)
_LOGO_PATH = Path(_FRONTEND_DIR) / "assets" / "logo.svg"
while _FRONTEND_DIR in sys.path:
    sys.path.remove(_FRONTEND_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from backend.schemas import (  # noqa: E402
    RegraValidacaoAtualizacao,
    RegraValidacaoCriacao,
)
from frontend.client import ApiError, SeticApiClient  # noqa: E402

# Configuração da Página Streamlit
st.set_page_config(
    page_title="CAGD | Plataforma de Qualidade de Dados SETIC",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Constantes e Endereço da API REST
API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")


@st.cache_resource
def obter_cliente_api() -> SeticApiClient:
    """Retorna a instância singleton do cliente REST para comunicação com o backend."""
    return SeticApiClient(base_url=API_URL)


cliente_api = obter_cliente_api()

# Estilos CSS Personalizados
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #f8fafc;
        border-radius: 8px;
        padding: 16px;
        border-left: 5px solid #0284c7;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .status-badge-ok {
        background-color: #dcfce7;
        color: #15803d;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .status-badge-err {
        background-color: #fee2e2;
        color: #b91c1c;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .rule-pill-core {
        background-color: #e0e7ff;
        color: #3730a3;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85em;
    }
    .rule-pill-dynamic {
        background-color: #fef3c7;
        color: #92400e;
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =====================================================================
# BARRA LATERAL (SIDEBAR)
# =====================================================================

with st.sidebar:
    if _LOGO_PATH.exists():
        st.image(str(_LOGO_PATH), width="stretch")
    st.title("SETIC / CAGD")
    st.caption("Coordenação de Análise e Gestão de Dados")
    st.markdown("---")

    # Status de Conexão com o Gateway REST
    info_saude = cliente_api.consultar_saude()
    if info_saude and info_saude.get("status") == "operacional":
        st.success(f"🟢 **API Conectada** (v{info_saude.get('versao')})")
        st.caption(f"IBGE: {info_saude.get('municipios_ibge_indexados')} municípios ativos")
    else:
        st.error("🔴 **API Desconectada**")
        st.caption(f"Não foi possível conectar a {API_URL}. Inicie a API FastAPI.")

    st.markdown("---")
    menu_selecionado = st.radio(
        "Navegação Principal",
        [
            "📊 Painel de Métricas (CAGD)",
            "⚙️ Gestão de Regras (Dual-Tier)",
            "🧪 Sandbox de Validação em Tempo Real",
            "📜 Trilha de Auditoria e Telemetria",
        ],
    )
    st.markdown("---")
    st.subheader("📚 Contrato OpenAPI")
    st.link_button(
        "📖 Documentação Swagger UI",
        f"{API_URL}/docs",
        width="stretch",
        help="Acesse a documentação interativa Swagger gerada automaticamente a partir dos esquemas OpenAPI",
    )
    st.link_button(
        "📋 Especificação ReDoc",
        f"{API_URL}/redoc",
        width="stretch",
        help="Visualização técnica da documentação OpenAPI com ReDoc",
    )
    st.markdown("---")
    st.info(
        "**Desafio 1 - SETIC**\n\n"
        "Gatekeeper centralizado de qualidade, normalização permissiva e bloqueio estrito."
    )


# =====================================================================
# TELA 1: PAINEL DE MÉTRICAS OPERACIONAIS (CAGD)
# =====================================================================

if menu_selecionado == "📊 Painel de Métricas (CAGD)":
    st.title("📊 Painel de Métricas Operacionais - CAGD")
    st.markdown(
        "Visão analítica das transações de dados interceptadas, taxas de rejeição e gargalos por sistema emissor."
    )

    metricas = cliente_api.obter_metricas()
    if metricas is None:
        st.error(
            f"⚠️ Não foi possível obter as métricas operacionais. "
            f"Certifique-se de que a API da SETIC esteja ativa em `{API_URL}`."
        )
    else:
        # Cards KPI no topo
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total de Requisições", f"{metricas.total_requisicoes:,}".replace(",", "."))
        with c2:
            st.metric("Cargas Normalizadas", f"{metricas.total_sucessos:,}".replace(",", "."))
        with c3:
            st.metric(
                "Taxa de Bloqueio Estrito",
                f"{metricas.taxa_rejeicao_percentual:.1f}%",
                delta=f"-{metricas.total_bloqueios} rejeições"
                if metricas.total_bloqueios > 0
                else "0",
                delta_color="inverse",
            )
        with c4:
            st.metric("Latência Média", f"{metricas.tempo_medio_processamento_ms:.2f} ms")

        st.markdown("---")

        # Gráficos de Análise
        col_esq, col_dir = st.columns(2)

        with col_esq:
            st.subheader("Volume por Sistema de Origem")
            if metricas.volume_por_sistema:
                linhas_grafico: list[dict[str, object]] = []
                for s in metricas.volume_por_sistema:
                    linhas_grafico.append(
                        {
                            "sistema_origem": s.sistema_origem,
                            "status": "Aprovado (200)",
                            "quantidade": s.aprovados,
                        }
                    )
                    linhas_grafico.append(
                        {
                            "sistema_origem": s.sistema_origem,
                            "status": "Rejeitado (422)",
                            "quantidade": s.rejeitados,
                        }
                    )

                df_agrupado = pd.DataFrame(linhas_grafico)
                fig_sis = px.bar(
                    df_agrupado,
                    x="sistema_origem",
                    y="quantidade",
                    color="status",
                    barmode="group",
                    color_discrete_map={
                        "Aprovado (200)": "#10b981",
                        "Rejeitado (422)": "#ef4444",
                    },
                    labels={"sistema_origem": "Sistema Cliente", "quantidade": "Requisições"},
                )
                fig_sis.update_layout(height=350, margin={"l": 20, "r": 20, "t": 30, "b": 20})
                st.plotly_chart(fig_sis, width="stretch")
            else:
                st.info("Nenhuma transação registrada até o momento.")

        with col_dir:
            st.subheader("Campos com Maior Índice de Defeito")
            if metricas.top_campos_rejeitados:
                df_campos = pd.DataFrame(
                    [
                        {
                            "Campo": it.nome,
                            "Ocorrências": it.quantidade,
                        }
                        for it in metricas.top_campos_rejeitados
                    ]
                ).sort_values(by="Ocorrências", ascending=True)

                fig_campos = px.bar(
                    df_campos,
                    x="Ocorrências",
                    y="Campo",
                    orientation="h",
                    color="Ocorrências",
                    color_continuous_scale="Reds",
                )
                fig_campos.update_layout(height=350, margin={"l": 20, "r": 20, "t": 30, "b": 20})
                st.plotly_chart(fig_campos, width="stretch")
            else:
                st.success("Nenhuma falha de validação registrada.")

        # Tabela de Regras Mais Transgredidas
        st.subheader("Detalhamento de Regras Mais Violadas")
        if metricas.top_regras_violadas:
            df_regras = pd.DataFrame(
                [
                    {
                        "Código da Regra": it.nome,
                        "Total de Bloqueios": it.quantidade,
                    }
                    for it in metricas.top_regras_violadas
                ]
            ).sort_values(by="Total de Bloqueios", ascending=False)
            st.dataframe(df_regras, width="stretch", hide_index=True)
        else:
            st.caption("Nenhum bloqueio registrado.")


# =====================================================================
# TELA 2: GESTÃO DE REGRAS (DUAL-TIER ENGINE)
# =====================================================================

elif menu_selecionado == "⚙️ Gestão de Regras (Dual-Tier)":
    st.title("⚙️ Gestão de Regras de Validação (Dual-Tier Engine)")
    st.markdown(
        """
        O motor opera em arquitetura de dois níveis (*Dual-Tier*):
        1. **Regras Núcleo (Core Tier)**: Algoritmos matemáticos e tabelas oficiais protegidas por lei
           (CPF, CNPJ, IBGE, Data). **São imutáveis e não podem ser desativadas ou apagadas.**
        2. **Regras Dinâmicas (CAGD Tier)**: Expressões regulares e restrições cadastráveis
           pela equipe de gestão para novos campos funcionais.
        """
    )

    todas_regras = cliente_api.listar_regras()

    if todas_regras is None:
        st.error(
            f"⚠️ Não foi possível carregar as regras de validação a partir da API REST (`{API_URL}`)."
        )
    else:
        tab_lista, tab_cadastro, tab_edicao, tab_import_export = st.tabs(
            [
                "📋 Regras Ativas no Sistema",
                "➕ Cadastrar Nova Regra",
                "✏️ Editar Regra Existente",
                "💾 Exportar / Importar Regras",
            ]
        )

        with tab_lista:
            st.subheader("Catálogo de Regras do Motor")

            tabela_dados = [
                {
                    "ID": r.id,
                    "Campo": r.campo,
                    "Nome da Regra": r.nome_regra,
                    "Classificação": "🔒 NÚCLEO (IMUTÁVEL)"
                    if r.eh_imutavel
                    else "⚡ DINÂMICA (CAGD)",
                    "Padrão Regex": r.padrao_regex or "(Algorítmico / Fuzzy)",
                    "Obrigatório": "Sim" if r.obrigatorio else "Não",
                    "Status": "🟢 Ativa" if r.ativo else "⚪ Inativa",
                    "Imutável": r.eh_imutavel,
                }
                for r in todas_regras
            ]

            df_tabela = pd.DataFrame(tabela_dados)
            st.dataframe(
                df_tabela.drop(columns=["Imutável"]),
                width="stretch",
                hide_index=True,
            )

            st.markdown("---")
            st.subheader("Ações sobre Regras Dinâmicas")
            regras_dinamicas = [r for r in todas_regras if not r.eh_imutavel]

            if regras_dinamicas:
                col_sel, col_act1, col_act2 = st.columns([3, 1, 1])
                with col_sel:
                    regra_escolhida = st.selectbox(
                        "Selecione uma regra dinâmica para gerenciar:",
                        regras_dinamicas,
                        format_func=lambda x: (
                            f"[{x.id}] {x.campo} - {x.nome_regra} ({'Ativa' if x.ativo else 'Inativa'})"
                        ),
                    )
                with col_act1:
                    st.write("")
                    st.write("")
                    btn_label = "Desativar" if regra_escolhida.ativo else "Ativar"
                    if st.button(f"🔄 {btn_label}", width="stretch"):
                        try:
                            cliente_api.alternar_status_regra(regra_escolhida.id)
                            st.success(f"Regra [{regra_escolhida.id}] alternada com sucesso!")
                            st.rerun()
                        except ApiError as err:
                            st.error(err.detail)
                with col_act2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Excluir", width="stretch", type="secondary"):
                        try:
                            cliente_api.excluir_regra(regra_escolhida.id)
                            st.warning(f"Regra [{regra_escolhida.id}] excluída com sucesso!")
                            st.rerun()
                        except ApiError as err:
                            st.error(err.detail)
            else:
                st.info("Nenhuma regra dinâmica customizada cadastrada.")

        with tab_cadastro:
            st.subheader("Formulário de Cadastro de Regra Dinâmica")
            st.caption("Cadastre regras corporativas baseadas em Expressões Regulares (Regex).")

            with st.form("form_nova_regra"):
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    novo_campo = st.text_input(
                        "Nome do Campo*",
                        placeholder="ex: matricula_funcional, codigo_contrato, processo_sei",
                    )
                    novo_nome = st.text_input(
                        "Nome da Regra*",
                        placeholder="ex: Padrão Oficial de Matrícula SEGEP",
                    )
                    novo_formato = st.text_input(
                        "Formato Esperado*",
                        placeholder="ex: RO-123456 ou SEI-9999/2026",
                    )
                with col_f2:
                    novo_regex = st.text_input(
                        "Padrão Regex*",
                        value=r"^RO-\d{6}$",
                        help="Expressão regular para validar o formato do campo.",
                    )
                    nova_mensagem = st.text_area(
                        "Mensagem de Erro Diagnóstica*",
                        value="O valor informado não atende ao padrão corporativo oficial.",
                        help="Mensagem amigável retornada em português quando houver bloqueio 422.",
                    )
                    nova_obrigatoria = st.checkbox("Campo Estritamente Obrigatório?")

                nova_descricao = st.text_area(
                    "Descrição Operacional da Regra",
                    placeholder="Explicação sobre a fundamentação e uso da regra pela administração estadual.",
                )

                st.markdown("**🧪 Testador Imediato do Regex**")
                texto_teste = st.text_input(
                    "Valor de Teste para o Regex",
                    value="RO-123456",
                    key="teste_regex_input",
                )
                if novo_regex:
                    try:
                        match = bool(re.search(novo_regex, texto_teste))
                        if match:
                            st.caption("✅ Padrão Regex Confere com o valor de teste!")
                        else:
                            st.caption("❌ Padrão Regex NÃO confere com o valor de teste.")
                    except re.error as e:
                        st.caption(f"⚠️ Erro de sintaxe no Regex: {e}")

                btn_salvar = st.form_submit_button("💾 Salvar Regra Dinâmica", type="primary")

                if btn_salvar:
                    if (
                        not novo_campo
                        or not novo_nome
                        or not novo_regex
                        or not nova_mensagem
                        or not novo_formato
                    ):
                        st.error("Por favor, preencha todos os campos obrigatórios (*).")
                    else:
                        try:
                            payload_regra = RegraValidacaoCriacao(
                                campo=novo_campo.strip().lower(),
                                nome_regra=novo_nome.strip(),
                                descricao=nova_descricao.strip() if nova_descricao else None,
                                padrao_regex=novo_regex.strip(),
                                mensagem_erro=nova_mensagem.strip(),
                                formato_esperado=novo_formato.strip(),
                                obrigatorio=nova_obrigatoria,
                                ativo=True,
                            )
                            cliente_api.criar_regra(payload_regra)
                            st.success(f"Regra para o campo '{novo_campo}' criada com sucesso!")
                            st.rerun()
                        except ApiError as err:
                            st.error(err.detail)
                        except Exception as ex:
                            st.error(f"Erro na criação da regra: {ex}")

        with tab_edicao:
            st.subheader("✏️ Edição de Regra Dinâmica")
            st.caption(
                "Modifique parâmetros, expressões regulares ou mensagens de regras existentes."
            )

            regras_dinamicas_edicao = [r for r in todas_regras if not r.eh_imutavel]
            if not regras_dinamicas_edicao:
                st.info("Nenhuma regra dinâmica customizada cadastrada para edição.")
            else:
                regra_para_editar = st.selectbox(
                    "Selecione a regra para editar:",
                    regras_dinamicas_edicao,
                    key="select_regra_edicao",
                    format_func=lambda x: (
                        f"[{x.id}] {x.campo} - {x.nome_regra} ({'Ativa' if x.ativo else 'Inativa'})"
                    ),
                )

                with st.form("form_editar_regra"):
                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        edit_campo = st.text_input("Nome do Campo*", value=regra_para_editar.campo)
                        edit_nome = st.text_input(
                            "Nome da Regra*", value=regra_para_editar.nome_regra
                        )
                        edit_formato = st.text_input(
                            "Formato Esperado*",
                            value=regra_para_editar.formato_esperado,
                        )
                    with col_e2:
                        edit_regex = st.text_input(
                            "Padrão Regex*",
                            value=regra_para_editar.padrao_regex or "",
                            help="Expressão regular para validar o formato do campo.",
                        )
                        edit_mensagem = st.text_area(
                            "Mensagem de Erro Diagnóstica*",
                            value=regra_para_editar.mensagem_erro,
                            help="Mensagem amigável retornada quando houver bloqueio 422.",
                        )
                        col_chk1, col_chk2 = st.columns(2)
                        with col_chk1:
                            edit_obrigatorio = st.checkbox(
                                "Obrigatório?",
                                value=regra_para_editar.obrigatorio,
                            )
                        with col_chk2:
                            edit_ativo = st.checkbox("Ativo?", value=regra_para_editar.ativo)

                    edit_descricao = st.text_area(
                        "Descrição Operacional da Regra",
                        value=regra_para_editar.descricao or "",
                    )

                    st.markdown("**🧪 Testador Imediato do Regex**")
                    texto_teste_edit = st.text_input(
                        "Valor de Teste para o Regex",
                        value=edit_formato,
                        key="teste_regex_edit_input",
                    )
                    if edit_regex:
                        try:
                            match_edit = bool(re.search(edit_regex, texto_teste_edit))
                            if match_edit:
                                st.caption("✅ Padrão Regex Confere com o valor de teste!")
                            else:
                                st.caption("❌ Padrão Regex NÃO confere com o valor de teste.")
                        except re.error as e:
                            st.caption(f"⚠️ Erro de sintaxe no Regex: {e}")

                    btn_salvar_edicao = st.form_submit_button(
                        "💾 Salvar Alterações", type="primary"
                    )

                    if btn_salvar_edicao:
                        if (
                            not edit_campo
                            or not edit_nome
                            or not edit_regex
                            or not edit_mensagem
                            or not edit_formato
                        ):
                            st.error("Por favor, preencha todos os campos obrigatórios (*).")
                        else:
                            try:
                                re.compile(edit_regex.strip())
                                payload_atualizacao = RegraValidacaoAtualizacao(
                                    campo=edit_campo.strip().lower(),
                                    nome_regra=edit_nome.strip(),
                                    formato_esperado=edit_formato.strip(),
                                    padrao_regex=edit_regex.strip(),
                                    mensagem_erro=edit_mensagem.strip(),
                                    obrigatorio=edit_obrigatorio,
                                    ativo=edit_ativo,
                                    descricao=edit_descricao.strip() if edit_descricao else None,
                                )
                                cliente_api.atualizar_regra(
                                    regra_para_editar.id, payload_atualizacao
                                )
                                st.success(
                                    f"Regra [{regra_para_editar.id}] atualizada com sucesso!"
                                )
                                st.rerun()
                            except re.error as err:
                                st.error(f"Padrão Regex inválido: {err}")
                            except ApiError as err:
                                st.error(err.detail)

        with tab_import_export:
            st.subheader("💾 Exportação e Importação de Regras Dinâmicas")
            st.caption(
                "Permite efetuar backup, versionamento declarativo e sincronização de regras entre ambientes (Desenvolvimento, Homologação e Produção)."
            )

            col_exp, col_imp = st.columns(2)

            with col_exp:
                st.markdown("### 📤 Exportar Conjunto de Regras")
                regras_dinamicas_exp = [r for r in todas_regras if not r.eh_imutavel]
                st.write(
                    f"Total de regras dinâmicas prontas para exportação: **{len(regras_dinamicas_exp)}**"
                )

                dados_exportacao = cliente_api.exportar_regras()
                if dados_exportacao:
                    json_export_str = dados_exportacao.model_dump_json(indent=2)
                    st.download_button(
                        label="📥 Baixar Regras em JSON",
                        data=json_export_str,
                        file_name="regras_dinamicas_cagd.json",
                        mime="application/json",
                        width="stretch",
                    )
                    with st.expander("Pré-visualizar JSON de Exportação"):
                        st.json(dados_exportacao.model_dump())
                else:
                    st.warning("Não foi possível gerar os dados de exportação a partir da API.")

            with col_imp:
                st.markdown("### 📥 Importar Conjunto de Regras")
                arquivo_upload = st.file_uploader(
                    "Carregar arquivo JSON de regras:",
                    type=["json"],
                    key="uploader_regras_json",
                )
                sobrescrever_existentes = st.checkbox(
                    "Sobrescrever regras existentes com mesmo campo e nome?",
                    value=False,
                    help="Se marcado, regras já existentes terão seus atributos (regex, mensagens) atualizados. Se desmarcado, serão mantidas intactas.",
                )

                if arquivo_upload is not None:
                    try:
                        conteudo_json = json.loads(arquivo_upload.getvalue().decode("utf-8"))
                        regras_para_importar: list[dict[str, object]] = []
                        if isinstance(conteudo_json, dict) and "regras" in conteudo_json:
                            raw_regras = conteudo_json.get("regras")
                            if isinstance(raw_regras, list):
                                for item_regra in raw_regras:
                                    if isinstance(item_regra, dict):
                                        regras_para_importar.append(item_regra)
                        elif isinstance(conteudo_json, list):
                            for item_regra in conteudo_json:
                                if isinstance(item_regra, dict):
                                    regras_para_importar.append(item_regra)

                        st.info(
                            f"Arquivo carregado com sucesso contendo **{len(regras_para_importar)}** regras potenciais."
                        )

                        if st.button(
                            "🚀 Processar e Importar Regras",
                            type="primary",
                            width="stretch",
                        ):
                            try:
                                resultado_imp = cliente_api.importar_regras(
                                    regras=regras_para_importar,
                                    sobrescrever=sobrescrever_existentes,
                                )

                                col_m1, col_m2, col_m3 = st.columns(3)
                                col_m1.metric("Criadas", resultado_imp.total_criadas)
                                col_m2.metric("Atualizadas", resultado_imp.total_atualizadas)
                                col_m3.metric("Ignoradas", resultado_imp.total_ignoradas)

                                if resultado_imp.mensagens:
                                    with st.expander("Ver Relatório Detalhado", expanded=True):
                                        for m in resultado_imp.mensagens:
                                            st.write(f"- {m}")

                                if resultado_imp.erros:
                                    for err in resultado_imp.erros:
                                        st.error(f"Erro: {err}")

                                st.success("Importação concluída!")
                                st.rerun()
                            except ApiError as err:
                                st.error(err.detail)

                    except Exception as ex:
                        st.error(f"Falha ao processar arquivo JSON: {ex}")


# =====================================================================
# TELA 3: SANDBOX DE VALIDAÇÃO EM TEMPO REAL
# =====================================================================

elif menu_selecionado == "🧪 Sandbox de Validação em Tempo Real":
    st.title("🧪 Sandbox de Validação e Normalização em Tempo Real")
    st.markdown(
        "Ambiente de experimentação interativo para testar cargas JSON contra o motor de qualidade."
    )
    st.info(
        f"📖 **Contrato Oficial OpenAPI**: Os esquemas e códigos de resposta respeitam as definições da API REST. "
        f"Consulte a [Documentação Swagger Interativa]({API_URL}/docs) ou a especificação [ReDoc]({API_URL}/redoc) para integração direta de sistemas clientes."
    )

    # Cenários pré-configurados
    cenarios: dict[str, dict[str, object]] = {
        "Cenário 1: Normalização Permissiva (Porto Velho 'p. velho', Data Texto, CPF)": {
            "sistema_origem": "SISTEMA_RH_ESTADUAL",
            "dados": {
                "cpf": "117.941.016-59",
                "data_nascimento": "15 de março de 1985",
                "municipio": "p. velho",
                "uf": "RO",
                "telefone": "69992345678",
                "matricula_funcional": "RO-123456",
            },
        },
        "Cenário 2: Município Fora de Rondônia (São Paulo/SP)": {
            "sistema_origem": "SEFIN_CADASTRO_NACIONAL",
            "dados": {
                "cpf": "11794101659",
                "data_nascimento": "20 de julho de 1992",
                "municipio": "sao paulo",
                "uf": "SP",
                "telefone": "(11) 98765-4321",
            },
        },
        "Cenário 3: Bloqueio Estrito (CPF Inválido + 31/02/1990 + Município Desconhecido)": {
            "sistema_origem": "PORTAL_TRANSPARENCIA",
            "dados": {
                "cpf": "123.456.789-00",
                "data_nascimento": "31/02/1990",
                "municipio": "Atlantida",
                "uf": "RO",
            },
        },
        "Cenário 4: Violação de Regra Dinâmica (Matrícula Funcional Fora do Padrão)": {
            "sistema_origem": "SISTEMA_RH_ESTADUAL",
            "dados": {
                "cpf": "117.941.016-59",
                "data_nascimento": "1990-05-10",
                "municipio": "Ji-Paraná",
                "uf": "RO",
                "matricula_funcional": "MAT-009988",
            },
        },
    }

    col_cenario, col_origem = st.columns([2, 1])
    with col_cenario:
        escolha_cenario = st.selectbox("Carregar Cenário de Exemplo:", list(cenarios.keys()))
    with col_origem:
        cenario_selecionado = cenarios[escolha_cenario]
        sistema_origem_default = str(cenario_selecionado.get("sistema_origem", ""))
        sistema_origem_input = st.text_input(
            "Sistema de Origem:",
            value=sistema_origem_default,
        )

    json_inicial = json.dumps(cenario_selecionado.get("dados", {}), indent=2, ensure_ascii=False)
    payload_texto = st.text_area(
        "Payload de Dados (JSON de Entrada):",
        value=json_inicial,
        height=220,
    )

    if st.button("🚀 Executar Validação e Normalização", type="primary", width="stretch"):
        try:
            dados_dict = json.loads(payload_texto)
        except json.JSONDecodeError as err:
            st.error(f"Erro de sintaxe JSON: {err}")
            dados_dict = None

        if dados_dict is not None and isinstance(dados_dict, dict):
            origem = (sistema_origem_input or "").strip() or "SANDBOX_STREAMLIT"
            status_code, resultado = cliente_api.validar(
                dados=dados_dict,
                sistema_origem=origem,
            )

            st.markdown("---")
            if status_code == 200:
                st.success("✅ **HTTP 200 OK - Carga Homologada e Normalizada com Sucesso!**")
                st.caption(
                    f"Protocolo de Auditoria: `{resultado.get('protocolo')}` | "
                    f"Latência: {float(str(resultado.get('tempo_processamento_ms', 0.0))):.2f} ms"
                )

                # Relação de transformações aplicadas
                transformacoes = resultado.get("transformacoes", [])
                if isinstance(transformacoes, list) and transformacoes:
                    st.markdown("**🔄 Normalizações Permissivas Aplicadas:**")
                    for t in transformacoes:
                        st.info(f"• {t}")

                # Comparação Lado a Lado
                col_antes, col_depois = st.columns(2)
                with col_antes:
                    st.subheader("Dados Brutos Recebidos")
                    st.json(dados_dict)
                with col_depois:
                    st.subheader("Dados Canônicos Normalizados")
                    raw_norm = resultado.get("dados_normalizados")
                    st.json(raw_norm if isinstance(raw_norm, dict) else {})

            elif status_code == 422:
                st.error("🛑 **HTTP 422 Unprocessable Entity - Persistência Bloqueada!**")
                st.caption(
                    f"Protocolo de Auditoria: `{resultado.get('protocolo')}` | "
                    f"Latência: {float(str(resultado.get('tempo_processamento_ms', 0.0))):.2f} ms"
                )

                st.markdown(f"**Motivo:** {resultado.get('mensagem')}")

                raw_erros = resultado.get("erros", [])
                erros = (
                    [e for e in raw_erros if isinstance(e, dict)]
                    if isinstance(raw_erros, list)
                    else []
                )
                if erros:
                    st.markdown("**🔍 Diagnósticos Analíticos de Inconsistência:**")
                    df_erros = pd.DataFrame(erros)
                    colunas_exibicao = [
                        c
                        for c in [
                            "campo",
                            "regra_violada",
                            "valor_rejeitado",
                            "formato_esperado",
                            "mensagem",
                        ]
                        if c in df_erros.columns
                    ]
                    st.dataframe(
                        df_erros[colunas_exibicao],
                        width="stretch",
                        hide_index=True,
                    )

                st.subheader("Resposta Completa da API (422)")
                st.json(resultado)
            else:
                st.error(
                    f"Erro na comunicação com a API (Status {status_code}): {resultado.get('mensagem')}"
                )


# =====================================================================
# TELA 4: TRILHA DE AUDITORIA E TELEMETRIA
# =====================================================================

elif menu_selecionado == "📜 Trilha de Auditoria e Telemetria":
    st.title("📜 Trilha de Auditoria e Telemetria")
    st.markdown(
        "Rastreabilidade completa de todas as requisições submetidas à plataforma para fins de conformidade e governança."
    )

    col_filtro1, col_filtro2, col_filtro3 = st.columns(3)
    with col_filtro1:
        filtro_sistema = st.text_input("Filtrar por Sistema de Origem:")
    with col_filtro2:
        filtro_status = st.selectbox(
            "Filtrar por Status:", ["Todos", "Aprovados (200)", "Bloqueados (422)"]
        )
    with col_filtro3:
        limite = st.slider("Quantidade de Registros:", min_value=10, max_value=200, value=50)

    sucesso_param: bool | None = None
    if filtro_status == "Aprovados (200)":
        sucesso_param = True
    elif filtro_status == "Bloqueados (422)":
        sucesso_param = False

    sistema_param = filtro_sistema.strip() if filtro_sistema.strip() else None

    registros = cliente_api.consultar_auditoria(
        sistema_origem=sistema_param,
        sucesso=sucesso_param,
        limite=limite,
    )

    if registros is None:
        st.error(
            f"⚠️ Não foi possível carregar os registros de auditoria a partir da API REST (`{API_URL}`)."
        )
    elif registros:
        lista_tabela = []
        for r in registros:
            criado_em_str = str(r.get("criado_em") or "-")
            tempo_ms = float(str(r.get("tempo_processamento_ms", 0.0)))
            lista_tabela.append(
                {
                    "Protocolo": r.get("protocolo"),
                    "Sistema de Origem": r.get("sistema_origem"),
                    "Status": "✅ 200 OK" if r.get("sucesso") else "🛑 422 Rejeitado",
                    "Falhas": r.get("quantidade_erros", 0),
                    "Latência (ms)": f"{tempo_ms:.2f}",
                    "Data/Hora": criado_em_str,
                }
            )

        df_auditoria = pd.DataFrame(lista_tabela)
        st.dataframe(df_auditoria, width="stretch", hide_index=True)

        st.markdown("---")
        st.subheader("Inspecionar Registro Detalhado")
        protocolos = [str(r.get("protocolo")) for r in registros if r.get("protocolo")]
        proto_sel = st.selectbox("Selecione o Protocolo:", protocolos)

        registro_sel = next((r for r in registros if r.get("protocolo") == proto_sel), None)
        if registro_sel:
            col_in, col_out = st.columns(2)
            with col_in:
                st.write("**Payload de Entrada Recebido:**")
                st.json(registro_sel.get("dados_entrada") or {})
            with col_out:
                if registro_sel.get("sucesso"):
                    st.write("**Dados Normalizados Persistidos:**")
                    st.json(registro_sel.get("dados_normalizados") or {})
                else:
                    st.write("**Erros Diagnósticos que Causaram o Bloqueio:**")
                    st.json(registro_sel.get("erros_detectados") or {})
    else:
        st.info("Nenhum registro de auditoria encontrado para os filtros selecionados.")
