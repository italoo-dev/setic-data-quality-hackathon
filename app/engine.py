"""Motor Híbrido de Qualidade e Normalização de Dados da SETIC (Dual-Tier Engine).

Executa:
1. Camada 1: Validadores de Núcleo Imutáveis (CPF, CNPJ, Data, Telefone, CEP, Município IBGE).
2. Camada 2: Regras Dinâmicas cadastradas no PostgreSQL pela CAGD (Regex e Restrições).
3. Telemetria: Registro transacional de auditoria para cálculo de KPIs e métricas operacionais.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core_validators import (
    validar_e_normalizar_cep,
    validar_e_normalizar_cnpj,
    validar_e_normalizar_cpf,
    validar_e_normalizar_data,
    validar_e_normalizar_municipio,
    validar_e_normalizar_telefone,
)
from app.database import RegistroAuditoria, RegraValidacao

logger = logging.getLogger("setic.engine")


@dataclass
class ErroDiagnosticoItem:
    """Item estruturado de diagnóstico de erro retornado em falhas de validação (HTTP 422)."""

    campo: str
    regra_violada: str
    valor_rejeitado: Any
    formato_esperado: str
    mensagem: str

    def to_dict(self) -> dict[str, Any]:
        """Converte o erro para dicionário serializável."""
        return asdict(self)


@dataclass
class ResultadoMotor:
    """Resultado da execução do pipeline do motor de validação."""

    sucesso: bool
    protocolo: str
    status_http: int
    sistema_origem: str
    dados_normalizados: dict[str, Any] | None
    erros: list[ErroDiagnosticoItem]
    transformacoes: list[str]
    tempo_processamento_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Converte o resultado para dicionário."""
        return {
            "sucesso": self.sucesso,
            "protocolo": self.protocolo,
            "status_http": self.status_http,
            "sistema_origem": self.sistema_origem,
            "dados_normalizados": self.dados_normalizados,
            "erros": [e.to_dict() for e in self.erros],
            "transformacoes": self.transformacoes,
            "tempo_processamento_ms": self.tempo_processamento_ms,
        }


class MotorValidacao:
    """Motor de execução de qualidade e normalização de dados."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def executar(
        self,
        dados_entrada: dict[str, Any],
        sistema_origem: str,
    ) -> ResultadoMotor:
        """Executa o pipeline completo de validação, normalização e auditoria."""
        inicio = time.perf_counter()
        protocolo = str(uuid.uuid4())

        dados_normalizados: dict[str, Any] = dict(dados_entrada)
        erros: list[ErroDiagnosticoItem] = []
        transformacoes: list[str] = []

        # =================================================================
        # FASE 1: VALIDADORES DE NÚCLEO IMUTÁVEIS (CORE TIER)
        # =================================================================

        # 1.1 Validação e Normalização de CPF
        if "cpf" in dados_entrada and dados_entrada["cpf"] is not None:
            res_cpf = validar_e_normalizar_cpf(dados_entrada["cpf"])
            if res_cpf.valido:
                dados_normalizados["cpf"] = res_cpf.valor_normalizado
                if res_cpf.mensagem_transformacao:
                    transformacoes.append(res_cpf.mensagem_transformacao)
            else:
                erros.append(
                    ErroDiagnosticoItem(
                        campo="cpf",
                        regra_violada=res_cpf.regra_violada,
                        valor_rejeitado=res_cpf.valor_rejeitado,
                        formato_esperado=res_cpf.formato_esperado,
                        mensagem=res_cpf.mensagem_erro,
                    )
                )

        # 1.2 Validação e Normalização de CNPJ
        if "cnpj" in dados_entrada and dados_entrada["cnpj"] is not None:
            res_cnpj = validar_e_normalizar_cnpj(dados_entrada["cnpj"])
            if res_cnpj.valido:
                dados_normalizados["cnpj"] = res_cnpj.valor_normalizado
                if res_cnpj.mensagem_transformacao:
                    transformacoes.append(res_cnpj.mensagem_transformacao)
            else:
                erros.append(
                    ErroDiagnosticoItem(
                        campo="cnpj",
                        regra_violada=res_cnpj.regra_violada,
                        valor_rejeitado=res_cnpj.valor_rejeitado,
                        formato_esperado=res_cnpj.formato_esperado,
                        mensagem=res_cnpj.mensagem_erro,
                    )
                )

        # 1.3 Validação e Normalização de Data de Nascimento (ou campos com sufixo data/data_nascimento)
        for campo_data in ["data_nascimento", "data", "data_admissao"]:
            if campo_data in dados_entrada and dados_entrada[campo_data] is not None:
                res_data = validar_e_normalizar_data(dados_entrada[campo_data], campo=campo_data)
                if res_data.valido:
                    dados_normalizados[campo_data] = res_data.valor_normalizado
                    if res_data.mensagem_transformacao:
                        transformacoes.append(res_data.mensagem_transformacao)
                else:
                    erros.append(
                        ErroDiagnosticoItem(
                            campo=campo_data,
                            regra_violada=res_data.regra_violada,
                            valor_rejeitado=res_data.valor_rejeitado,
                            formato_esperado=res_data.formato_esperado,
                            mensagem=res_data.mensagem_erro,
                        )
                    )

        # 1.4 Validação e Normalização de Telefone
        if "telefone" in dados_entrada and dados_entrada["telefone"] is not None:
            res_tel = validar_e_normalizar_telefone(dados_entrada["telefone"])
            if res_tel.valido:
                dados_normalizados["telefone"] = res_tel.valor_normalizado
                if res_tel.mensagem_transformacao:
                    transformacoes.append(res_tel.mensagem_transformacao)
            else:
                erros.append(
                    ErroDiagnosticoItem(
                        campo="telefone",
                        regra_violada=res_tel.regra_violada,
                        valor_rejeitado=res_tel.valor_rejeitado,
                        formato_esperado=res_tel.formato_esperado,
                        mensagem=res_tel.mensagem_erro,
                    )
                )

        # 1.5 Validação e Normalização de CEP
        if "cep" in dados_entrada and dados_entrada["cep"] is not None:
            res_cep = validar_e_normalizar_cep(dados_entrada["cep"])
            if res_cep.valido:
                dados_normalizados["cep"] = res_cep.valor_normalizado
                if res_cep.mensagem_transformacao:
                    transformacoes.append(res_cep.mensagem_transformacao)
            else:
                erros.append(
                    ErroDiagnosticoItem(
                        campo="cep",
                        regra_violada=res_cep.regra_violada,
                        valor_rejeitado=res_cep.valor_rejeitado,
                        formato_esperado=res_cep.formato_esperado,
                        mensagem=res_cep.mensagem_erro,
                    )
                )

        # 1.6 Resolução Bidirecional e Aproximação Fuzzy de Município IBGE
        tem_municipio = "municipio" in dados_entrada and dados_entrada["municipio"] is not None
        tem_codigo_ibge = (
            "codigo_ibge" in dados_entrada and dados_entrada["codigo_ibge"] is not None
        )

        if tem_municipio or tem_codigo_ibge:
            alvo_busca = dados_entrada.get("municipio") or dados_entrada.get("codigo_ibge")
            uf_informada = dados_entrada.get("uf")

            res_muni = validar_e_normalizar_municipio(alvo_busca, uf_informada)
            if res_muni.valido and isinstance(res_muni.valor_normalizado, dict):
                dados_normalizados["municipio"] = res_muni.valor_normalizado["municipio"]
                dados_normalizados["codigo_ibge"] = res_muni.valor_normalizado["codigo_ibge"]
                dados_normalizados["uf"] = res_muni.valor_normalizado["uf"]
                if res_muni.mensagem_transformacao:
                    transformacoes.append(res_muni.mensagem_transformacao)
            else:
                erros.append(
                    ErroDiagnosticoItem(
                        campo=res_muni.campo or "municipio",
                        regra_violada=res_muni.regra_violada,
                        valor_rejeitado=res_muni.valor_rejeitado,
                        formato_esperado=res_muni.formato_esperado,
                        mensagem=res_muni.mensagem_erro,
                    )
                )

        # =================================================================
        # FASE 2: REGRAS DINÂMICAS DO BANCO DE DADOS (CAGD TIER)
        # =================================================================
        regras_dinamicas = (
            self.db.query(RegraValidacao)
            .filter(RegraValidacao.ativo == True, RegraValidacao.eh_imutavel == False)  # noqa: E712
            .all()
        )

        for regra in regras_dinamicas:
            campo = regra.campo
            valor_campo = dados_entrada.get(campo)

            # Verificação de obrigatoriedade
            if regra.obrigatorio and (valor_campo is None or str(valor_campo).strip() == ""):
                erros.append(
                    ErroDiagnosticoItem(
                        campo=campo,
                        regra_violada="CAMPO_OBRIGATORIO_AUSENTE",
                        valor_rejeitado=None,
                        formato_esperado=regra.formato_esperado,
                        mensagem=f"O campo '{campo}' é obrigatório segundo a regra cadastrada pela CAGD.",
                    )
                )
                continue

            # Se o campo foi fornecido e possui padrão regex configurado
            if valor_campo is not None and str(valor_campo).strip() != "" and regra.padrao_regex:
                valor_str = str(valor_campo).strip()
                try:
                    if not re.search(regra.padrao_regex, valor_str):
                        erros.append(
                            ErroDiagnosticoItem(
                                campo=campo,
                                regra_violada=f"PADRAO_REGEX_VIOLADO_{regra.id}",
                                valor_rejeitado=valor_campo,
                                formato_esperado=regra.formato_esperado,
                                mensagem=regra.mensagem_erro,
                            )
                        )
                    else:
                        # Limpeza leve de espaços desnecessários
                        dados_normalizados[campo] = valor_str
                except re.error as e:
                    logger.error(f"Padrão Regex inválido na regra {regra.id}: {e}")

        # =================================================================
        # FASE 3: DECISÃO FINAL, TELEMETRIA E AUDITORIA
        # =================================================================
        tempo_ms = round((time.perf_counter() - inicio) * 1000, 2)
        sucesso = len(erros) == 0
        status_http = 200 if sucesso else 422

        # Registro de Auditoria / Telemetria da Transação
        try:
            registro = RegistroAuditoria(
                protocolo=protocolo,
                sistema_origem=sistema_origem,
                sucesso=sucesso,
                status_http=status_http,
                dados_entrada=dados_entrada,
                dados_normalizados=dados_normalizados if sucesso else None,
                erros_detectados=[e.to_dict() for e in erros] if erros else None,
                quantidade_erros=len(erros),
                tempo_processamento_ms=tempo_ms,
            )
            self.db.add(registro)
            self.db.commit()
        except Exception as e:
            logger.error(f"Erro ao persistir telemetria de auditoria: {e}")
            self.db.rollback()

        return ResultadoMotor(
            sucesso=sucesso,
            protocolo=protocolo,
            status_http=status_http,
            sistema_origem=sistema_origem,
            dados_normalizados=dados_normalizados if sucesso else None,
            erros=erros,
            transformacoes=transformacoes,
            tempo_processamento_ms=tempo_ms,
        )
