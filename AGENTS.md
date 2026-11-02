# Diretrizes de Governança e Fluxo de Trabalho de Agentes de IA (AGENTS.md)

Este documento estabelece as regras de governança, arquitetura e desenvolvimento para agentes de inteligência artificial (e desenvolvedores humanos) que atuam no repositório **Plataforma Centralizada de Qualidade, Normalização e Gestão de Dados da SETIC** (Secretaria de Estado da Tecnologia da Informação e Comunicação de Rondônia - Desafio 1 / CAGD).

---

## 1. Contexto e Missão do Sistema

A plataforma atua como uma barreira centralizada (*gatekeeper*) que intercepta dados antes de sua persistência em bases de dados estaduais.
A sua responsabilidade primordial divide-se em dois princípios inegociáveis:

1. **Normalização Permissiva (*Permissive Normalization*)**:
   - Dados que apresentem coerência conceitual, mas formatação arbitrária, informal ou truncada, devem ser higienizados e convertidos para padrões canônicos padronizados.
   - *Exemplos*:
     - Datas em português por extenso (`"15 de março de 1985"` ou `"15/03/85"`) $\rightarrow$ Padrão ISO-8601 (`"1985-03-15"`).
     - Municípios informais ou abreviados (`"p. velho"`, `"jiparana"`, `"sao paulo"`) $\rightarrow$ Nome oficial IBGE (`"Porto Velho"`, `"Ji-Paraná"`, `"São Paulo"`), acompanhado do respectivo código IBGE de 7 dígitos (`"1100205"`) e sigla da UF (`"RO"`).
     - Documentos sem máscara ou com pontuação variada (`"12345678901"` ou `"123.456.789-01"`) $\rightarrow$ Dígitos canônicos higienizados.
     - Telefones e CEPs com ou sem delimitadores $\rightarrow$ Padrão canônico nacional.

2. **Bloqueio Estrito (*Strict Blocking*)**:
   - Dados que contenham falhas estruturais, matemáticas ou semânticas insuperáveis devem ser **estritamente bloqueados**, impedindo a persistência.
   - A resposta da API deve retornar obrigatoriamente **`HTTP 422 Unprocessable Entity`** com diagnóstico analítico por campo (`campo`, `regra_violada`, `valor_rejeitado`, `formato_esperado`, `mensagem`).
   - Toda tentativa de submissão (rejeitada ou aprovada) deve ser persistida para fins de telemetria e auditoria operacional da CAGD.
   - *Exemplos de Bloqueio*:
     - Falha de dígito verificador em CPF ou CNPJ.
     - Datas impossíveis no calendário (ex: `31/02/1990`, `29/02/2023`, `31/04/2021`).
     - Municípios ou UFs inexistentes na base nacional do IBGE.
     - Violação de regras dinâmicas ativas (ex: padrão de matrícula funcional).

---

## 2. Padrões de Commit Atômico (Conventional Commits)

Os agentes de desenvolvimento devem aderir ao princípio de **Commits Atômicos e Isolados**. Jamais crie commits monolíticos (*git dumps*) que combinem camadas distintas da aplicação.

Cada commit deve representar uma única camada arquitetural ou unidade lógica independente:

| Tipo | Escopo | Descrição do Commit |
| :--- | :--- | :--- |
| `docs` | `(agents)` | Atualizações em regras de governança, diretrizes e contratos de IA. |
| `feat` | `(packaging)` | Configuração de empacotamento declarativo (`pyproject.toml`). |
| `feat` | `(nix)` | Ambiente reprodutível, derivações e shell de desenvolvimento (`flake.nix`). |
| `feat` | `(infra)` | Configuração de containers Docker/Podman para o banco de dados (`docker-compose.yml`). |
| `feat` | `(database)` | Camada de persistência, modelos SQLAlchemy e sessões. |
| `feat` | `(validators)` | Validador canônico imutável de CPF, CNPJ, IBGE e datas. |
| `feat` | `(engine)` | Motor híbrido de regras de validação (regras núcleo + regras dinâmicas). |
| `feat` | `(schemas)` | Modelos Pydantic V2 para entrada, saída normalizada e diagnósticos. |
| `feat` | `(api)` | Rotas REST FastAPI, middlewares e telemetria. |
| `feat` | `(dashboard)` | Painel gerencial Streamlit da CAGD (métricas, regras e sandbox). |
| `docs` | `(readme)` | Documentação de arquitetura, guias de execução e chamadas de teste. |
| `test` | `(core)` | Suíte de testes automatizados unitários e de integração. |

---

## 3. Fonte Única da Verdade para Dependências (`Single Source of Truth`)

1. **O arquivo `pyproject.toml` é a única fonte da verdade** para metadados, dependências em tempo de execução, bibliotecas de desenvolvimento e configurações de linters/LSPs.
2. **Nunca declare listas estáticas de pacotes Python no `flake.nix`**.
3. O `flake.nix` deve obrigatoriamente consumir e analisar o `pyproject.toml` de forma dinâmica (através de `pyproject.nix`, `uv2nix` ou `builtins.fromTOML`), garantindo sincronia total e ausência de duplicação.
4. LSPs suportados (Pyright, Ruff) devem operar a partir dos padrões definidos no `pyproject.toml`.

---

## 4. Salvaguardas Arquiteturais Inegociáveis

1. **Uso de Bibliotecas Nacionais Homologadas**:
   - É expressamente proibido reescrever algoritmos de CPF/CNPJ com expressões regulares artesanais quando dispomos de `brutils`.
   - O catálogo oficial de todos os 5.570 municípios brasileiros deve ser resolvido diretamente através dos dados do pacote `brutils` (`brutils/data/cities_code.json`). Requisições externas à rede durante a validação são expressamente proibidas; o motor opera 100% offline, com máxima autonomia e determinismo.
   - Validações telefônicas e verificação de DDDs devem utilizar `phonenumbers` (Google libphonenumber), eliminando mapeamentos manuais de operadoras ou DDDs.
   - Variações ortográficas informais e aproximações devem ser resolvidas com `RapidFuzz` e `Unidecode`.
2. **Imutabilidade do Núcleo de Regras**:
   - As regras núcleo (CPF, CNPJ, Data de Nascimento, Telefone, Município/UF IBGE) são estruturais e devem permanecer marcadas como imutáveis (`eh_imutavel = True`).
   - A interface gerencial (Streamlit) e as rotas de API devem bloquear qualquer tentativa de edição ou exclusão dessas regras fundamentais.
3. **Persistência Confiável e Telemetria**:
   - Dados corrompidos **jamais** devem ser persistidos nas tabelas de dados validados.
   - Cada chamada à rota `/api/v1/validar` deve gerar um `RegistroAuditoria` registrando protocolo, payload de entrada, sucesso/falha, latência em milissegundos e diagnósticos de erro.
4. **Localização e Idioma**:
   - Toda a documentação da API (OpenAPI), mensagens diagnósticas de erro, esquemas Pydantic, comentários centrais e interface de usuário devem estar em **Português do Brasil formal (pt-BR)**.

---

## 5. Ciclo de Verificação Pré-Commit (Verification Loop)

Antes de gerar qualquer commit no repositório, o agente deve validar o código executando a suíte de checagens dentro do ambiente Nix:

```bash
# 1. Análise estática e linting
ruff check .

# 2. Verificação de formatação
ruff format --check .

# 3. Análise estática de tipos
pyright

# 4. Execução dos testes automatizados
pytest
```

Qualquer erro de tipo, sintaxe ou quebra de contrato identificada no ciclo de verificação deve ser sanada antes da criação do commit.
