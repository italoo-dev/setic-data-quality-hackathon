"""Modelos de dados declarativos e esquemas Pydantic V2 em Português do Brasil.

Define as estruturas de:
1. Requisição de validação/normalização.
2. Resposta de aprovação com dados normalizados (200 OK).
3. Resposta de diagnóstico e bloqueio estrito (422 Unprocessable Entity).
4. Métricas operacionais agregadas para a CAGD.
5. Modelos de CRUD para regras dinâmicas de qualidade de dados.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RequisicaoValidacao(BaseModel):
    """Esquema de entrada para validação e normalização de dados."""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "sistema_origem": "SISTEMA_RH_ESTADUAL",
                "dados": {
                    "cpf": "117.941.016-59",
                    "data_nascimento": "15 de março de 1985",
                    "municipio": "p. velho",
                    "uf": "RO",
                    "telefone": "(69) 99234-5678",
                    "matricula_funcional": "RO-123456",
                },
            }
        },
    )

    sistema_origem: str = Field(
        ...,
        min_length=2,
        max_length=64,
        description="Identificador corporativo do sistema emissor da requisição",
        examples=["SISTEMA_RH_ESTADUAL", "PORTAL_CIDADAO_RO", "SEFIN_CADASTRO"],
    )
    dados: dict[str, object] = Field(
        ...,
        description="Dicionário chave-valor com os dados brutos a serem analisados, normalizados ou bloqueados",
    )


class ErroDiagnosticoDetalhe(BaseModel):
    """Diagnóstico individual de inconsistência em um campo específico."""

    campo: str = Field(
        ...,
        description="Nome do campo em que foi detectada a desconformidade",
        examples=["cpf", "data_nascimento", "municipio"],
    )
    regra_violada: str = Field(
        ...,
        description="Código identificador da regra ou validação transgredida",
        examples=[
            "DIGITO_VERIFICADOR_INVALIDO",
            "DATA_IMPOSSIVEL_CALENDARIO",
            "MUNICIPIO_IBGE_NAO_ENCONTRADO",
        ],
    )
    valor_rejeitado: object = Field(
        ...,
        description="Valor original submetido que foi rejeitado pelo motor de qualidade",
    )
    formato_esperado: str = Field(
        ...,
        description="Descrição canônica do formato, padrão ou restrição esperada para o campo",
    )
    mensagem: str = Field(
        ...,
        description="Explicação diagnóstica amigável em língua portuguesa do motivo da rejeição",
    )


class RespostaNormalizada(BaseModel):
    """Contrato de resposta quando a carga de dados atende às regras e é normalizada (HTTP 200)."""

    sucesso: bool = Field(
        default=True,
        description="Indicador de sucesso da operação de validação e normalização",
    )
    protocolo: str = Field(
        ...,
        description="Identificador universal único (UUID) para rastreabilidade e auditoria da transação",
    )
    status_http: int = Field(
        default=200,
        description="Código de status HTTP correspondente ao resultado",
    )
    sistema_origem: str = Field(
        ...,
        description="Sistema de origem informado na requisição",
    )
    dados_normalizados: dict[str, object] = Field(
        ...,
        description="Carga de dados higienizada, canônica e pronta para persistência segura",
    )
    transformacoes: list[str] = Field(
        default_factory=list,
        description="Relação de conversões e higienizações aplicadas sobre os dados de entrada",
    )
    tempo_processamento_ms: float = Field(
        ...,
        description="Latência total da verificação e normalização em milissegundos",
    )


class RespostaBloqueioValidacao(BaseModel):
    """Contrato de resposta quando a carga de dados apresenta defeitos estruturais (HTTP 422)."""

    sucesso: bool = Field(
        default=False,
        description="Indicador booleano que expressa a rejeição dos dados",
    )
    protocolo: str = Field(
        ...,
        description="Identificador universal único (UUID) da transação rejeitada para auditoria",
    )
    status_http: int = Field(
        default=422,
        description="Código HTTP 422 Unprocessable Entity",
    )
    sistema_origem: str = Field(
        ...,
        description="Sistema de origem que realizou a submissão rejeitada",
    )
    mensagem: str = Field(
        default="Falha na validação dos dados de entrada. Persistência bloqueada.",
        description="Mensagem geral informando o bloqueio da persistência",
    )
    erros: list[ErroDiagnosticoDetalhe] = Field(
        ...,
        description="Lista analítica de cada erro e defeito detectado por campo",
    )
    tempo_processamento_ms: float = Field(
        ...,
        description="Latência total despendida na análise em milissegundos",
    )


class VolumeSistemaItem(BaseModel):
    """Estatística agregada de volume por sistema de origem."""

    sistema_origem: str
    total: int
    aprovados: int
    rejeitados: int
    taxa_rejeicao_percentual: float


class ItemContagem(BaseModel):
    """Contagem de ocorrências de uma categoria."""

    nome: str
    quantidade: int


class MetricasOperacionaisCAGD(BaseModel):
    """Visão analítica operacional e consolidada para o painel de gestão da CAGD."""

    total_requisicoes: int = Field(..., description="Total acumulado de requisições de validação")
    total_sucessos: int = Field(..., description="Total de cargas aprovadas e normalizadas")
    total_bloqueios: int = Field(..., description="Total de cargas rejeitadas e bloqueadas")
    taxa_rejeicao_percentual: float = Field(..., description="Percentual de rejeição global")
    tempo_medio_processamento_ms: float = Field(..., description="Latência média de processamento")
    volume_por_sistema: list[VolumeSistemaItem] = Field(
        ..., description="Volume segregado por sistema emissor"
    )
    top_campos_rejeitados: list[ItemContagem] = Field(
        ..., description="Campos que mais concentram falhas"
    )
    top_regras_violadas: list[ItemContagem] = Field(
        ..., description="Regras que mais resultaram em bloqueio"
    )


class RegraValidacaoCriacao(BaseModel):
    """Esquema para cadastro de uma nova regra dinâmica de validação."""

    campo: str = Field(..., min_length=2, max_length=64, description="Nome do campo a ser validado")
    nome_regra: str = Field(..., min_length=3, max_length=128, description="Título da regra")
    descricao: str | None = Field(None, description="Detalhamento operacional da regra")
    padrao_regex: str | None = Field(
        None, max_length=512, description="Expressão regular para conferência"
    )
    mensagem_erro: str = Field(
        ..., min_length=5, description="Mensagem diagnóstica exibida em caso de falha"
    )
    formato_esperado: str = Field(..., min_length=3, max_length=256, description="Formato exigido")
    obrigatorio: bool = Field(
        default=False, description="Define se a presença do campo é estritamente obrigatória"
    )
    ativo: bool = Field(default=True, description="Define se a regra está ativada no pipeline")


class RegraValidacaoAtualizacao(BaseModel):
    """Esquema para atualização de uma regra dinâmica existente."""

    nome_regra: str | None = Field(None, min_length=3, max_length=128)
    descricao: str | None = None
    padrao_regex: str | None = Field(None, max_length=512)
    mensagem_erro: str | None = Field(None, min_length=5)
    formato_esperado: str | None = Field(None, min_length=3, max_length=256)
    obrigatorio: bool | None = None
    ativo: bool | None = None


class RegraValidacaoResposta(BaseModel):
    """Representação serializada de uma regra cadastrada na plataforma."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    campo: str
    nome_regra: str
    descricao: str | None
    padrao_regex: str | None
    mensagem_erro: str
    formato_esperado: str
    obrigatorio: bool
    ativo: bool
    eh_imutavel: bool
    criado_em: datetime | None
    atualizado_em: datetime | None
