"""Etapa de Regras Dinâmicas do Banco de Dados (Dynamic Tier Step).

Executa as validações cadastradas e mantidas dinamicamente pela CAGD no PostgreSQL
(regras de formato regex, obrigatoriedade e regras corporativas estaduais).
"""

from __future__ import annotations

import logging
import re

from app.domain.interfaces import RuleRepositoryProtocol
from app.domain.models import ErroDiagnosticoItem, ExecutionContext

logger = logging.getLogger("setic.engine.dynamic")


class DynamicTierStep:
    """Etapa que aplica as regras ativas dinâmicas providas pelo RuleRepository."""

    def __init__(self, rule_repo: RuleRepositoryProtocol) -> None:
        self.rule_repo = rule_repo

    def process(self, context: ExecutionContext) -> ExecutionContext:
        """Aplica as regras dinâmicas sobre o contexto da requisição."""
        regras_dinamicas = self.rule_repo.listar_ativas_dinamicas()
        dados = context.dados_brutos

        for regra in regras_dinamicas:
            campo = regra.campo
            valor_campo = dados.get(campo)

            # Verificação de obrigatoriedade
            if regra.obrigatorio and (valor_campo is None or str(valor_campo).strip() == ""):
                context.adicionar_erro(
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
                        context.adicionar_erro(
                            ErroDiagnosticoItem(
                                campo=campo,
                                regra_violada=f"PADRAO_REGEX_VIOLADO_{regra.id}",
                                valor_rejeitado=valor_campo,
                                formato_esperado=regra.formato_esperado,
                                mensagem=regra.mensagem_erro,
                            )
                        )
                    else:
                        context.dados_normalizados[campo] = valor_str
                except re.error as err:
                    logger.error(
                        f"Regex inválido na regra dinâmica #{regra.id} ('{regra.padrao_regex}'): {err}"
                    )

        return context
