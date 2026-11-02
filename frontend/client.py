"""Cliente HTTP tipado para a API REST da Plataforma de Qualidade de Dados (SETIC/CAGD)."""

from __future__ import annotations

import httpx

from backend.schemas import (
    ConjuntoRegrasExportacao,
    MetricasOperacionaisCAGD,
    RegraExportadaItem,
    RegraValidacaoAtualizacao,
    RegraValidacaoCriacao,
    RegraValidacaoResposta,
    ResultadoImportacaoRegras,
)


class ApiError(Exception):
    """Exceção levantada quando a API retorna um erro HTTP com detalhe."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class SeticApiClient:
    """Cliente HTTP com pool de conexões e tipagem estrita com Pydantic."""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        """Encerra a sessão HTTP e libera o pool de conexões."""
        self._client.close()

    def __enter__(self) -> SeticApiClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def consultar_saude(self) -> dict[str, object] | None:
        """Verifica a conectividade e integridade do gateway."""
        try:
            r = self._client.get("/api/v1/saude", timeout=2.0)
            if r.status_code == 200:
                res = r.json()
                return res if isinstance(res, dict) else None
        except httpx.RequestError:
            pass
        return None

    def obter_metricas(self) -> MetricasOperacionaisCAGD | None:
        """Recupera os indicadores e métricas operacionais consolidadas."""
        try:
            r = self._client.get("/api/v1/metricas")
            if r.status_code == 200:
                return MetricasOperacionaisCAGD.model_validate(r.json())
        except (httpx.RequestError, Exception):
            pass
        return None

    def listar_regras(
        self, campo: str | None = None, apenas_ativas: bool = False
    ) -> list[RegraValidacaoResposta] | None:
        """Lista todas as regras cadastradas (núcleo e dinâmicas)."""
        params: dict[str, str | bool] = {"apenas_ativas": apenas_ativas}
        if campo:
            params["campo"] = campo
        try:
            r = self._client.get("/api/v1/regras", params=params)
            if r.status_code == 200:
                itens = r.json()
                if isinstance(itens, list):
                    return [RegraValidacaoResposta.model_validate(it) for it in itens]
        except (httpx.RequestError, Exception):
            pass
        return None

    def criar_regra(self, regra: RegraValidacaoCriacao) -> RegraValidacaoResposta:
        """Cadastra uma nova regra dinâmica na plataforma."""
        r = self._client.post("/api/v1/regras", json=regra.model_dump())
        if r.status_code in (200, 201):
            return RegraValidacaoResposta.model_validate(r.json())
        detalhe = self._extrair_detalhe(r)
        raise ApiError(r.status_code, detalhe)

    def atualizar_regra(
        self, regra_id: int, atualizacao: RegraValidacaoAtualizacao
    ) -> RegraValidacaoResposta:
        """Atualiza uma regra dinâmica existente."""
        r = self._client.put(
            f"/api/v1/regras/{regra_id}",
            json=atualizacao.model_dump(exclude_unset=True),
        )
        if r.status_code == 200:
            return RegraValidacaoResposta.model_validate(r.json())
        detalhe = self._extrair_detalhe(r)
        raise ApiError(r.status_code, detalhe)

    def alternar_status_regra(self, regra_id: int) -> RegraValidacaoResposta:
        """Ativa ou desativa uma regra dinâmica."""
        r = self._client.patch(f"/api/v1/regras/{regra_id}/toggle")
        if r.status_code == 200:
            return RegraValidacaoResposta.model_validate(r.json())
        detalhe = self._extrair_detalhe(r)
        raise ApiError(r.status_code, detalhe)

    def excluir_regra(self, regra_id: int) -> None:
        """Exclui uma regra dinâmica."""
        r = self._client.delete(f"/api/v1/regras/{regra_id}")
        if r.status_code not in (200, 204):
            detalhe = self._extrair_detalhe(r)
            raise ApiError(r.status_code, detalhe)

    def exportar_regras(self) -> ConjuntoRegrasExportacao | None:
        """Exporta o conjunto de regras dinâmicas em formato estruturado."""
        try:
            r = self._client.get("/api/v1/regras/exportar", params={"apenas_dinamicas": "true"})
            if r.status_code == 200:
                return ConjuntoRegrasExportacao.model_validate(r.json())
        except (httpx.RequestError, Exception):
            pass
        return None

    def importar_regras(
        self, regras: list[RegraExportadaItem] | list[dict[str, object]], sobrescrever: bool
    ) -> ResultadoImportacaoRegras:
        """Importa um conjunto de regras dinâmicas em lote."""
        payload: dict[str, object] = {
            "regras": [r.model_dump() if isinstance(r, RegraExportadaItem) else r for r in regras],
            "sobrescrever": sobrescrever,
        }
        r = self._client.post("/api/v1/regras/importar", json=payload)
        if r.status_code == 200:
            return ResultadoImportacaoRegras.model_validate(r.json())
        detalhe = self._extrair_detalhe(r)
        raise ApiError(r.status_code, detalhe)

    def validar(
        self, dados: dict[str, object], sistema_origem: str
    ) -> tuple[int, dict[str, object]]:
        """Executa a validação de um payload na API REST."""
        payload: dict[str, object] = {
            "sistema_origem": sistema_origem,
            "dados": dados,
        }
        try:
            r = self._client.post("/api/v1/validar", json=payload)
            try:
                res_json = r.json()
                corpo: dict[str, object] = res_json if isinstance(res_json, dict) else {}
            except Exception:
                corpo = {"mensagem": r.text}
            return r.status_code, corpo
        except httpx.RequestError as exc:
            return 503, {
                "status_http": 503,
                "mensagem": f"Não foi possível conectar à API da SETIC ({self.base_url}): {exc}",
                "erros": [],
            }

    def consultar_auditoria(
        self,
        sistema_origem: str | None = None,
        sucesso: bool | None = None,
        limite: int = 50,
    ) -> list[dict[str, object]] | None:
        """Consulta os registros da trilha de auditoria."""
        params: dict[str, str | int | bool] = {"limite": limite}
        if sistema_origem:
            params["sistema_origem"] = sistema_origem
        if sucesso is not None:
            params["sucesso"] = sucesso
        try:
            r = self._client.get("/api/v1/auditoria", params=params)
            if r.status_code == 200:
                itens = r.json()
                if isinstance(itens, list):
                    return [it for it in itens if isinstance(it, dict)]
        except (httpx.RequestError, Exception):
            pass
        return None

    @staticmethod
    def _extrair_detalhe(response: httpx.Response) -> str:
        """Extrai mensagem de erro detalhada da resposta HTTP."""
        try:
            conteudo = response.json()
            if isinstance(conteudo, dict) and "detail" in conteudo:
                return str(conteudo["detail"])
        except Exception:
            pass
        return response.text or f"Erro HTTP {response.status_code}"
