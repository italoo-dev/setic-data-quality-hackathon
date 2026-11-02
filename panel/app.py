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
from datetime import datetime
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from sqlalchemy.orm import Session

from app.database import RegistroAuditoria, RegraValidacao, SessionLocal, init_db
from app.engine import MotorValidacao

# Configuração da Página Streamlit
st.set_page_config(
    page_title="CAGD | Plataforma de Qualidade de Dados SETIC",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Constantes e Endereço da API REST
API_URL = os.getenv("API_URL", "http://localhost:8000")

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


def obter_sessao_db() -> Session:
    """Garante a inicialização das tabelas e retorna uma sessão do banco de dados."""
    init_db()
    return SessionLocal()


def consultar_api_saude() -> dict[str, Any] | None:
    """Verifica a conectividade com a API FastAPI."""
    try:
        r = requests.get(f"{API_URL}/api/v1/saude", timeout=1.5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def executar_validacao(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Executa a validação via API REST ou fallback direto para o motor embutido."""
    # 1. Tentar via API HTTP FastAPI
    try:
        r = requests.post(f"{API_URL}/api/v1/validar", json=payload, timeout=5.0)
        return r.status_code, r.json()
    except Exception:
        # 2. Fallback direto para o motor e banco local
        db = obter_sessao_db()
        try:
            motor = MotorValidacao(db)
            res = motor.executar(
                dados_entrada=payload.get("dados", {}),
                sistema_origem=payload.get("sistema_origem", "STREAMLIT_FALLBACK"),
            )
            return res.status_http, res.to_dict()
        finally:
            db.close()


# =====================================================================
# BARRA LATERAL (SIDEBAR)
# =====================================================================

with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/e/ea/Bandeira_de_Rond%C3%B4nia.svg",
        width=80,
    )
    st.title("SETIC / CAGD")
    st.caption("Coordenação de Análise e Gestão de Dados")
    st.markdown("---")

    # Status de Conexão com o Gateway
    info_saude = consultar_api_saude()
    if info_saude and info_saude.get("status") == "operacional":
        st.success(f"🟢 **API Conectada** (v{info_saude.get('versao')})")
        st.caption(f"IBGE: {info_saude.get('municipios_ibge_indexados')} municípios ativos")
    else:
        st.warning("🟡 **API Offline (Modo Direto DB)**")
        st.caption("O painel está operando com conexão direta ao PostgreSQL/SQLite.")

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

    db = obter_sessao_db()
    try:
        # 1. Totalizadores
        total = db.query(RegistroAuditoria).count()
        total_sucessos = (
            db.query(RegistroAuditoria).filter(RegistroAuditoria.sucesso == True).count()  # noqa: E712
        )
        total_bloqueios = (
            db.query(RegistroAuditoria).filter(RegistroAuditoria.sucesso == False).count()  # noqa: E712
        )
        taxa_rejeicao = (total_bloqueios / total * 100) if total > 0 else 0.0

        latencias = [
            r[0]
            for r in db.query(RegistroAuditoria.tempo_processamento_ms).limit(500).all()
            if r[0] is not None
        ]
        latencia_media = (sum(latencias) / len(latencias)) if latencias else 0.0

        # Cards KPI no topo
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total de Requisições", f"{total:,}".replace(",", "."))
        with c2:
            st.metric("Cargas Normalizadas", f"{total_sucessos:,}".replace(",", "."))
        with c3:
            st.metric(
                "Taxa de Bloqueio Estrito",
                f"{taxa_rejeicao:.1f}%",
                delta=f"-{total_bloqueios} rejeições" if total_bloqueios > 0 else "0",
                delta_color="inverse",
            )
        with c4:
            st.metric("Latência Média", f"{latencia_media:.2f} ms")

        st.markdown("---")

        # 2. Gráficos de Análise
        col_esq, col_dir = st.columns(2)

        with col_esq:
            st.subheader("Volume por Sistema de Origem")
            sistemas_dados = (
                db.query(
                    RegistroAuditoria.sistema_origem,
                    RegistroAuditoria.sucesso,
                ).all()
            )

            if sistemas_dados:
                df_sis = pd.DataFrame(sistemas_dados, columns=["sistema_origem", "sucesso"])
                df_sis["status"] = df_sis["sucesso"].apply(
                    lambda x: "Aprovado (200)" if x else "Rejeitado (422)"
                )
                df_agrupado = (
                    df_sis.groupby(["sistema_origem", "status"])
                    .size()
                    .reset_index(name="quantidade")
                )

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
                fig_sis.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=20))
                st.plotly_chart(fig_sis, use_container_width=True)
            else:
                st.info("Nenhuma transação registrada até o momento.")

        with col_dir:
            st.subheader("Campos com Maior Índice de Defeito")
            falhas = (
                db.query(RegistroAuditoria.erros_detectados)
                .filter(RegistroAuditoria.sucesso == False)  # noqa: E712
                .all()
            )

            contagem_campos: dict[str, int] = {}
            for item in falhas:
                if isinstance(item[0], list):
                    for erro in item[0]:
                        if isinstance(erro, dict):
                            campo = erro.get("campo", "desconhecido")
                            contagem_campos[campo] = contagem_campos.get(campo, 0) + 1

            if contagem_campos:
                df_campos = pd.DataFrame(
                    list(contagem_campos.items()), columns=["Campo", "Ocorrências"]
                ).sort_values(by="Ocorrências", ascending=True)

                fig_campos = px.bar(
                    df_campos,
                    x="Ocorrências",
                    y="Campo",
                    orientation="h",
                    color="Ocorrências",
                    color_continuous_scale="Reds",
                )
                fig_campos.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=20))
                st.plotly_chart(fig_campos, use_container_width=True)
            else:
                st.success("Nenhuma falha de validação registrada.")

        # 3. Tabela de Regras Mais Transgredidas
        st.subheader("Detalhamento de Regras Mais Violadas")
        contagem_regras: dict[str, int] = {}
        for item in falhas:
            if isinstance(item[0], list):
                for erro in item[0]:
                    if isinstance(erro, dict):
                        regra = erro.get("regra_violada", "OUTRA")
                        contagem_regras[regra] = contagem_regras.get(regra, 0) + 1

        if contagem_regras:
            df_regras = pd.DataFrame(
                list(contagem_regras.items()), columns=["Código da Regra", "Total de Bloqueios"]
            ).sort_values(by="Total de Bloqueios", ascending=False)
            st.dataframe(df_regras, use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhum bloqueio registrado.")

    finally:
        db.close()


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

    db = obter_sessao_db()
    try:
        todas_regras = db.query(RegraValidacao).order_by(RegraValidacao.id.asc()).all()

        tab_lista, tab_cadastro = st.tabs(["📋 Regras Ativas no Sistema", "➕ Cadastrar Nova Regra"])

        with tab_lista:
            st.subheader("Catálogo de Regras do Motor")

            tabela_dados = []
            for r in todas_regras:
                tipo = "🔒 NÚCLEO (IMUTÁVEL)" if r.eh_imutavel else "⚡ DINÂMICA (CAGD)"
                status_txt = "🟢 Ativa" if r.ativo else "⚪ Inativa"
                tabela_dados.append({
                    "ID": r.id,
                    "Campo": r.campo,
                    "Nome da Regra": r.nome_regra,
                    "Classificação": tipo,
                    "Padrão Regex": r.padrao_regex or "(Algorítmico / Fuzzy)",
                    "Obrigatório": "Sim" if r.obrigatorio else "Não",
                    "Status": status_txt,
                    "Imutável": r.eh_imutavel,
                })

            df_tabela = pd.DataFrame(tabela_dados)
            st.dataframe(
                df_tabela.drop(columns=["Imutável"]),
                use_container_width=True,
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
                        format_func=lambda x: f"[{x.id}] {x.campo} - {x.nome_regra} ({'Ativa' if x.ativo else 'Inativa'})",
                    )
                with col_act1:
                    st.write("")
                    st.write("")
                    btn_label = "Desativar" if regra_escolhida.ativo else "Ativar"
                    if st.button(f"🔄 {btn_label}", use_container_width=True):
                        regra_escolhida.ativo = not regra_escolhida.ativo
                        db.commit()
                        st.success(f"Regra {regra_escolhida.id} atualizada com sucesso!")
                        st.rerun()
                with col_act2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Excluir", use_container_width=True, type="secondary"):
                        db.delete(regra_escolhida)
                        db.commit()
                        st.warning(f"Regra {regra_escolhida.id} excluída!")
                        st.rerun()
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

                # Testador ao vivo do regex dentro do formulário
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
                    if not novo_campo or not novo_nome or not novo_regex or not nova_mensagem:
                        st.error("Por favor, preencha todos os campos obrigatórios (*).")
                    else:
                        regra = RegraValidacao(
                            campo=novo_campo.strip().lower(),
                            nome_regra=novo_nome.strip(),
                            descricao=nova_descricao.strip() if nova_descricao else None,
                            padrao_regex=novo_regex.strip(),
                            mensagem_erro=nova_mensagem.strip(),
                            formato_esperado=novo_formato.strip(),
                            obrigatorio=nova_obrigatoria,
                            ativo=True,
                            eh_imutavel=False,
                        )
                        db.add(regra)
                        db.commit()
                        st.success(f"Regra para o campo '{novo_campo}' criada com sucesso!")
                        st.rerun()

    finally:
        db.close()


# =====================================================================
# TELA 3: SANDBOX DE VALIDAÇÃO EM TEMPO REAL
# =====================================================================

elif menu_selecionado == "🧪 Sandbox de Validação em Tempo Real":
    st.title("🧪 Sandbox de Validação e Normalização em Tempo Real")
    st.markdown(
        "Ambiente de experimentação interativo para testar cargas JSON contra o motor de qualidade."
    )

    # Cenários pré-configurados
    cenarios = {
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
        sistema_origem_input = st.text_input(
            "Sistema de Origem:",
            value=cenarios[escolha_cenario]["sistema_origem"],
        )

    json_inicial = json.dumps(cenarios[escolha_cenario]["dados"], indent=2, ensure_ascii=False)
    payload_texto = st.text_area(
        "Payload de Dados (JSON de Entrada):",
        value=json_inicial,
        height=220,
    )

    if st.button("🚀 Executar Validação e Normalização", type="primary", use_container_width=True):
        try:
            dados_dict = json.loads(payload_texto)
        except json.JSONDecodeError as err:
            st.error(f"Erro de sintaxe JSON: {err}")
            dados_dict = None

        if dados_dict is not None:
            payload_envio = {
                "sistema_origem": sistema_origem_input.strip() or "SANDBOX_STREAMLIT",
                "dados": dados_dict,
            }

            status_code, resultado = executar_validacao(payload_envio)

            st.markdown("---")
            if status_code == 200:
                st.success("✅ **HTTP 200 OK - Carga Homologada e Normalizada com Sucesso!**")
                st.caption(
                    f"Protocolo de Auditoria: `{resultado.get('protocolo')}` | "
                    f"Latência: {resultado.get('tempo_processamento_ms', 0):.2f} ms"
                )

                # Relação de transformações aplicadas
                transformacoes = resultado.get("transformacoes", [])
                if transformacoes:
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
                    st.json(resultado.get("dados_normalizados", {}))

            elif status_code == 422:
                st.error("🛑 **HTTP 422 Unprocessable Entity - Persistência Bloqueada!**")
                st.caption(
                    f"Protocolo de Auditoria: `{resultado.get('protocolo')}` | "
                    f"Latência: {resultado.get('tempo_processamento_ms', 0):.2f} ms"
                )

                st.markdown(f"**Motivo:** {resultado.get('mensagem')}")

                erros = resultado.get("erros", [])
                if erros:
                    st.markdown("**🔍 Diagnósticos Analíticos de Inconsistência:**")
                    df_erros = pd.DataFrame(erros)
                    st.dataframe(
                        df_erros[
                            ["campo", "regra_violada", "valor_rejeitado", "formato_esperado", "mensagem"]
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

                st.subheader("Resposta Completa da API (422)")
                st.json(resultado)


# =====================================================================
# TELA 4: TRILHA DE AUDITORIA E TELEMETRIA
# =====================================================================

elif menu_selecionado == "📜 Trilha de Auditoria e Telemetria":
    st.title("📜 Trilha de Auditoria e Telemetria")
    st.markdown(
        "Rastreabilidade completa de todas as requisições submetidas à plataforma para fins de conformidade e governança."
    )

    db = obter_sessao_db()
    try:
        col_filtro1, col_filtro2, col_filtro3 = st.columns(3)
        with col_filtro1:
            filtro_sistema = st.text_input("Filtrar por Sistema de Origem:")
        with col_filtro2:
            filtro_status = st.selectbox("Filtrar por Status:", ["Todos", "Aprovados (200)", "Bloqueados (422)"])
        with col_filtro3:
            limite = st.slider("Quantidade de Registros:", min_value=10, max_value=200, value=50)

        consulta = db.query(RegistroAuditoria)
        if filtro_sistema:
            consulta = consulta.filter(RegistroAuditoria.sistema_origem.ilike(f"%{filtro_sistema}%"))
        if filtro_status == "Aprovados (200)":
            consulta = consulta.filter(RegistroAuditoria.sucesso == True)  # noqa: E712
        elif filtro_status == "Bloqueados (422)":
            consulta = consulta.filter(RegistroAuditoria.sucesso == False)  # noqa: E712

        registros = consulta.order_by(RegistroAuditoria.criado_em.desc()).limit(limite).all()

        if registros:
            lista_tabela = []
            for r in registros:
                lista_tabela.append({
                    "Protocolo": r.protocolo,
                    "Sistema de Origem": r.sistema_origem,
                    "Status": "✅ 200 OK" if r.sucesso else "🛑 422 Rejeitado",
                    "Falhas": r.quantidade_erros,
                    "Latência (ms)": f"{r.tempo_processamento_ms:.2f}",
                    "Data/Hora (UTC)": r.criado_em.strftime("%d/%m/%Y %H:%M:%S") if r.criado_em else "-",
                })

            df_auditoria = pd.DataFrame(lista_tabela)
            st.dataframe(df_auditoria, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("Inspecionar Registro Detalhado")
            protocolos = [r.protocolo for r in registros]
            proto_sel = st.selectbox("Selecione o Protocolo:", protocolos)

            registro_sel = next((r for r in registros if r.protocolo == proto_sel), None)
            if registro_sel:
                col_in, col_out = st.columns(2)
                with col_in:
                    st.write("**Payload de Entrada Recebido:**")
                    st.json(registro_sel.dados_entrada)
                with col_out:
                    if registro_sel.sucesso:
                        st.write("**Dados Normalizados Persistidos:**")
                        st.json(registro_sel.dados_normalizados)
                    else:
                        st.write("**Erros Diagnósticos que Causaram o Bloqueio:**")
                        st.json(registro_sel.erros_detectados)
        else:
            st.info("Nenhum registro de auditoria encontrado para os filtros selecionados.")

    finally:
        db.close()
