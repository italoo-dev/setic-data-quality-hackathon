# Plataforma Centralizada de Qualidade, Normalização e Gestão de Dados (SETIC/CAGD)

> **Desafio 1 - SETIC (Secretaria de Estado da Tecnologia da Informação e Comunicação de Rondônia)**  
> Plataforma corporativa de saneamento, higienização, normalização permissiva e bloqueio estrito de dados pré-persistência, desenvolvida para a **CAGD (Coordenação de Análise e Gestão de Dados)**.

---

## 1. Visão Geral e Princípios Arquiteturais

A plataforma atua como uma barreira centralizada (*gatekeeper*) na borda da arquitetura de dados do Governo do Estado de Rondônia. Nenhuma carga de dados é persistida nas bases estaduais sem antes ser submetida e homologada pelo motor de qualidade:

```
[Sistemas Emissores] (RH, Sefin, Detran, Saúde, Portal Cidadão)
       │
       ▼  JSON Payload (sistema_origem, dados)
┌────────────────────────────────────────────────────────┐
│  GATEWAY CENTRALIZADO DE QUALIDADE DE DADOS (FASTAPI)  │
│                                                        │
│  ┌─────────────────────────┐ ┌──────────────────────┐  │
│  │   Core Tier (Imutável)  │ │   CAGD Tier (Dinâmico│  │
│  │  CPF, CNPJ, IBGE, Data  │ │   Regex & Restrições │  │
│  └───────────┬─────────────┘ └──────────┬───────────┘  │
│              └──────────────┬───────────┘              │
│                             │                          │
│        ┌────────────────────┴────────────────────┐     │
│        ▼                                         ▼     │
│  [200 OK - Normalizado]                 [422 - Bloqueado]│
│  Canônico (ISO-8601, IBGE 7d)           Diagnóstico Analítico
│  Persistência Homologada                Persistência Interrompida
│  Auditoria Gravada                      Auditoria Gravada│
└─────────────────────────────┬──────────────────────────┘
                              ▼
            ┌──────────────────────────────────┐
            │   PostgreSQL 16 (Auditoria/Regras)│
            │   Streamlit (Painel Executivo CAGD)│
            └──────────────────────────────────┘
```

### 1.1. Normalização Permissiva (*Permissive Normalization*)
Quando a informação enviada pelo sistema cliente é **conceitualmente idônea e válida**, mas apresenta formatos heterogêneos, truncados, informais ou regionais, a plataforma executa a transformação para o padrão canônico institucional:
- **Datas em Português** (`"15 de março de 1985"` ou `"15/03/85"`) $\rightarrow$ Padrão ISO-8601 (`"1985-03-15"`).
- **Municípios Informais ou Abreviados** (`"p. velho"`, `"jiparana"`, `"sao paulo"`) $\rightarrow$ Nome oficial IBGE (`"Porto Velho"`), Código IBGE oficial de 7 dígitos (`"1100205"`) e sigla da UF (`"RO"`).
- **Resolução Bidirecional IBGE** $\rightarrow$ Código `1100122` é resolvido para `"Ji-Paraná/RO"`, e vice-versa.
- **Identificadores Nacionais (CPF, CNPJ, CEP, Telefone)** $\rightarrow$ Dígitos limpos higienizados e máscaras oficiais.

### 1.2. Bloqueio Estrito (*Strict Blocking*)
Quando o dado possui **defeito estrutural, matemático, semântico ou calendário impossível**, o gateway rejeita a transação com **`HTTP 422 Unprocessable Entity`**, impede a persistência e gera um relatório diagnóstico com `campo`, `regra_violada`, `valor_rejeitado`, `formato_esperado` e `mensagem`. Toda tentativa rejeitada gera telemetria de auditoria para fins de governança.

---

## 2. Revisão Arquitetural das Tecnologias

| Tecnologia | Função no Sistema | Detalhes e Justificativa de Engenharia |
| :--- | :--- | :--- |
| **Python 3.12+ & FastAPI** | Gateway REST Assíncrono | Processamento de alta vazão com documentação OpenAPI interativa em Português do Brasil formal (pt-BR). |
| **Pydantic V2** | Validação & Parsing Core | Validação ultrarrápida compilada em Rust com coerção estrita e esquemas tipados. |
| **pyproject.toml** | *Single Source of Truth* | Especificação declarativa única (PEP 621) para dependências de runtime, dev tools, linters e LSPs. |
| **Nix Flake (`pyproject.nix`)** | Ambiente Puro & Reprodutível | Shell declarativo simplificado que analisa diretamente o `pyproject.toml`, provisionando Python 3.12, utilitários nativos e hooks de automação. |
| **PostgreSQL 16 (Docker / Podman)** | Persistência Relacional em Container | Executado isoladamente via container (`docker-compose.yml`), persistindo regras dinâmicas (`RegraValidacao`) e telemetria (`RegistroAuditoria`). |
| **Streamlit** | Painel Executivo da CAGD | Dashboard operacional em tempo real: cards KPI, gráficos de falha, gestão de regras e sandbox interativo de testes. |
| **`brutils` & `validate-docbr`** | Identificadores Nacionais & IBGE | Validação matemática estrita de CPF/CNPJ (módulo 11) e resolução local de todos os 5.570 municípios brasileiros via `brutils/data/cities_code.json`, sem chamadas externas. |
| **`phonenumbers` (libphonenumber)** | Padrão Telefônico Nacional & DDD | Validação e formatação oficial segundo especificações da Anatel e Google libphonenumber, eliminando listas manuais de DDDs. |
| **`dateparser`** | Normalização Fuzzy de Datas | Reconhecimento inteligente de datas arbitrárias escritas em português do Brasil e bloqueio de datas impossíveis. |
| **`RapidFuzz` & `Unidecode`** | Resolução Fonética e de Distância | Algoritmos C++ de distância de Levenshtein (*WRatio*) para aproximação de municípios informais contra o catálogo nacional de 5.570+ cidades. |

---

## 3. Instalação e Execução com Nix Flake e Containers

O projeto adota ambiente puramente reprodutível. O Nix provê o runtime Python, ferramentas C/C++ e LSPs a partir do `pyproject.toml`, enquanto o PostgreSQL 16 é executado em container isolado via **Docker ou Podman**, simplificando o flake ao máximo.

### 3.1. Entrar no Ambiente de Desenvolvimento
No diretório raiz do projeto, execute:

```bash
nix develop
```

O hook minimalista do Nix irá:
1. Configurar a variável de ambiente `DATABASE_URL` para o PostgreSQL na porta `5432`.
2. Criar e sincronizar o ambiente virtual `.venv` diretamente a partir do `pyproject.toml` usando `uv`.

### 3.2. Inicialização do Banco de Dados em Container

Suba o PostgreSQL 16 via Docker Compose ou Podman:

```bash
docker compose up -d
# ou com podman:
podman compose up -d
```

---

## 4. Instruções para Inicialização dos Serviços

Dentro do shell `nix develop`:

### 4.1. Iniciar a API REST FastAPI
```bash
uvicorn app.main:app --reload --port 8000
```
- **Documentação Swagger (OpenAPI em pt-BR)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Documentação ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 4.2. Iniciar o Painel Streamlit da CAGD
```bash
streamlit run panel/app.py
```
- **Interface Web da CAGD**: [http://localhost:8501](http://localhost:8501)

### 4.3. Execução dos Testes Automatizados e Linters
```bash
# Suíte de testes unitários e de integração
pytest

# Análise estática, formatação e verificação de tipos
ruff check .
ruff format --check .
pyright
```

---

## 5. Exemplos Práticos de Teste com `curl`

### 5.1. Carga Válida 1: Município de Rondônia informal ("p. velho"), Data por Extenso e CPF sem Máscara
```bash
curl -X POST "http://localhost:8000/api/v1/validar" \
  -H "Content-Type: application/json" \
  -d '{
    "sistema_origem": "SISTEMA_RH_ESTADUAL",
    "dados": {
      "cpf": "117.941.016-59",
      "data_nascimento": "15 de março de 1985",
      "municipio": "p. velho",
      "uf": "RO",
      "telefone": "(69) 99234-5678",
      "matricula_funcional": "RO-123456"
    }
  }'
```
**Resposta Esperada (`HTTP 200 OK`)**:
```json
{
  "sucesso": true,
  "protocolo": "8b92bdfc-c5fd-4dfa-ba62-a5676db7a3dc",
  "status_http": 200,
  "sistema_origem": "SISTEMA_RH_ESTADUAL",
  "dados_normalizados": {
    "cpf": "11794101659",
    "data_nascimento": "1985-03-15",
    "municipio": "Porto Velho",
    "codigo_ibge": "1100205",
    "uf": "RO",
    "telefone": "69992345678",
    "matricula_funcional": "RO-123456"
  },
  "transformacoes": [
    "CPF normalizado para '11794101659' (Formatado: 117.941.016-59).",
    "Data '15 de março de 1985' normalizada para o formato ISO-8601 '1985-03-15'.",
    "Telefone normalizado para '69992345678' (Formatado: (69) 99234-5678).",
    "Município informal 'p. velho' aproximado para 'Porto Velho' (Score: 79.2%, IBGE: 1100205)."
  ],
  "tempo_processamento_ms": 1.25
}
```

---

### 5.2. Carga Válida 2: Município Fora de Rondônia (São Paulo/SP)
Demonstra que a plataforma carrega os 5.570+ municípios brasileiros e valida qualquer localidade nacional:
```bash
curl -X POST "http://localhost:8000/api/v1/validar" \
  -H "Content-Type: application/json" \
  -d '{
    "sistema_origem": "SEFIN_CADASTRO_NACIONAL",
    "dados": {
      "cpf": "11794101659",
      "data_nascimento": "20 de julho de 1995",
      "municipio": "sao paulo",
      "uf": "SP",
      "telefone": "(11) 98765-4321"
    }
  }'
```
**Resposta Esperada (`HTTP 200 OK`)**:
```json
{
  "sucesso": true,
  "status_http": 200,
  "dados_normalizados": {
    "cpf": "11794101659",
    "data_nascimento": "1995-07-20",
    "municipio": "São Paulo",
    "codigo_ibge": "3550308",
    "uf": "SP",
    "telefone": "11987654321"
  }
}
```

---

### 5.3. Carga Válida 3: Resolução Reversa de Código IBGE para Nome Oficial
```bash
curl -X POST "http://localhost:8000/api/v1/validar" \
  -H "Content-Type: application/json" \
  -d '{
    "sistema_origem": "SEDUC_MATRICULAS",
    "dados": {
      "codigo_ibge": "1100122",
      "cpf": "11794101659"
    }
  }'
```
**Resposta Esperada (`HTTP 200 OK`)**:
```json
{
  "sucesso": true,
  "dados_normalizados": {
    "codigo_ibge": "1100122",
    "municipio": "Ji-Paraná",
    "uf": "RO",
    "cpf": "11794101659"
  }
}
```

---

### 5.4. Bloqueio Estrito 1: Falha no Dígito Verificador de CPF
```bash
curl -X POST "http://localhost:8000/api/v1/validar" \
  -H "Content-Type: application/json" \
  -d '{
    "sistema_origem": "PORTAL_TRANSPARENCIA",
    "dados": {
      "cpf": "123.456.789-00",
      "municipio": "Porto Velho",
      "uf": "RO"
    }
  }'
```
**Resposta Esperada (`HTTP 422 Unprocessable Entity`)**:
```json
{
  "sucesso": false,
  "protocolo": "95a73e1c-c760-4c12-b2da-3ea761cb7891",
  "status_http": 422,
  "sistema_origem": "PORTAL_TRANSPARENCIA",
  "mensagem": "Falha na validação dos dados de entrada. Persistência bloqueada.",
  "erros": [
    {
      "campo": "cpf",
      "regra_violada": "DIGITO_VERIFICADOR_INVALIDO",
      "valor_rejeitado": "123.456.789-00",
      "formato_esperado": "CPF com dígitos verificadores válidos (Algoritmo Módulo 11 da Receita Federal)",
      "mensagem": "Os dígitos verificadores do CPF não conferem com o algoritmo matemático oficial."
    }
  ]
}
```

---

### 5.5. Bloqueio Estrito 2: Data Impossível no Calendário ("31/02/1990")
```bash
curl -X POST "http://localhost:8000/api/v1/validar" \
  -H "Content-Type: application/json" \
  -d '{
    "sistema_origem": "SISTEMA_SAUDE_SUS",
    "dados": {
      "cpf": "11794101659",
      "data_nascimento": "31/02/1990"
    }
  }'
```
**Resposta Esperada (`HTTP 422 Unprocessable Entity`)**:
```json
{
  "sucesso": false,
  "status_http": 422,
  "erros": [
    {
      "campo": "data_nascimento",
      "regra_violada": "DATA_IMPOSSIVEL_CALENDARIO",
      "valor_rejeitado": "31/02/1990",
      "formato_esperado": "Data existente no calendário gregoriano",
      "mensagem": "A data '31/02/1990' é impossível no calendário gregoriano: day is out of range for month."
    }
  ]
}
```

---

### 5.6. Bloqueio Estrito 3: Município Inexistente na Base Nacional IBGE
```bash
curl -X POST "http://localhost:8000/api/v1/validar" \
  -H "Content-Type: application/json" \
  -d '{
    "sistema_origem": "CADASTRO_EXTERNO",
    "dados": {
      "cpf": "11794101659",
      "municipio": "Atlantida",
      "uf": "RO"
    }
  }'
```
**Resposta Esperada (`HTTP 422 Unprocessable Entity`)**:
```json
{
  "sucesso": false,
  "status_http": 422,
  "erros": [
    {
      "campo": "municipio",
      "regra_violada": "MUNICIPIO_IBGE_NAO_ENCONTRADO",
      "valor_rejeitado": "Atlantida",
      "formato_esperado": "Nome oficial ou grafia aproximável de município registrado no IBGE",
      "mensagem": "O município 'Atlantida' não foi localizado na base oficial do IBGE para a UF especificada (RO)."
    }
  ]
}
```

---

### 5.7. Bloqueio Estrito 4: Violação de Regra Dinâmica (Matrícula Funcional Fora do Padrão)
```bash
curl -X POST "http://localhost:8000/api/v1/validar" \
  -H "Content-Type: application/json" \
  -d '{
    "sistema_origem": "SISTEMA_RH_ESTADUAL",
    "dados": {
      "cpf": "11794101659",
      "matricula_funcional": "MAT-009988"
    }
  }'
```
**Resposta Esperada (`HTTP 422 Unprocessable Entity`)**:
```json
{
  "sucesso": false,
  "status_http": 422,
  "erros": [
    {
      "campo": "matricula_funcional",
      "regra_violada": "PADRAO_REGEX_VIOLADO_6",
      "valor_rejeitado": "MAT-009988",
      "formato_esperado": "RO-123456",
      "mensagem": "A matrícula funcional deve seguir rigorosamente o padrão RO- seguido de 6 dígitos numéricos."
    }
  ]
}
```

---

### 5.8. Consulta de Métricas Agregadas da CAGD
```bash
curl -X GET "http://localhost:8000/api/v1/metricas"
```
**Resposta Esperada (`HTTP 200 OK`)**:
```json
{
  "total_requisicoes": 142,
  "total_sucessos": 118,
  "total_bloqueios": 24,
  "taxa_rejeicao_percentual": 16.9,
  "tempo_medio_processamento_ms": 2.14,
  "volume_por_sistema": [
    {
      "sistema_origem": "SISTEMA_RH_ESTADUAL",
      "total": 80,
      "aprovados": 72,
      "rejeitados": 8,
      "taxa_rejeicao_percentual": 10.0
    }
  ],
  "top_campos_rejeitados": [
    { "nome": "cpf", "quantidade": 14 },
    { "nome": "data_nascimento", "quantidade": 6 },
    { "nome": "matricula_funcional", "quantidade": 4 }
  ],
  "top_regras_violadas": [
    { "nome": "DIGITO_VERIFICADOR_INVALIDO", "quantidade": 14 },
    { "nome": "DATA_IMPOSSIVEL_CALENDARIO", "quantidade": 6 }
  ]
}
```

---

## 6. Governança do Repositório e Regras de Agentes (`AGENTS.md`)

Este repositório possui regras rigorosas de governança descritas em `AGENTS.md`:
- **Commits Atômicos**: Commits isolados por camada arquitetural com Conventional Commits (`feat(engine):`, `feat(api):`, etc.).
- **Fonte Única da Verdade**: Todas as dependências declaradas no `pyproject.toml`; nunca liste pacotes fixos no `flake.nix`.
- **Salvaguardas de Domínio**: Validação matemática obrigatória; proibição de persistência de dados defeituosos; núcleo de regras estritamente imutável.
- **Ciclo de Verificação**: Execução mandatória de `ruff check .`, `ruff format --check .`, `pyright` e `pytest` antes de cada commit.
