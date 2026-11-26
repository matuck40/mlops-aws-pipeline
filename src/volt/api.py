"""API: só lê previsões já gravadas pelo pipeline; nunca roda o modelo."""

from collections.abc import Callable
from datetime import date, timedelta

from fastapi import FastAPI, HTTPException

from volt.armazenamento import Armazenamento, abrir_armazenamento, chave_previsao
from volt.tempo import hoje_brasilia


def criar_app(dados: Armazenamento, hoje: Callable[[], date] = hoje_brasilia) -> FastAPI:
    app = FastAPI(title="Volt — previsão de carga horária (SE/CO)")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/previsao")
    def previsao(data: str | None = None) -> dict:
        # data como texto: a API responde 400 (e não o 422 automático do FastAPI)
        if data is None:
            data_alvo = hoje() + timedelta(days=1)
        else:
            try:
                data_alvo = date.fromisoformat(data)
            except ValueError:
                raise HTTPException(400, f"data inválida: {data!r}; use AAAA-MM-DD") from None

        chave = chave_previsao(data_alvo)
        if not dados.existe(chave):
            raise HTTPException(404, f"previsão de {data_alvo} ainda não gerada")

        df = dados.ler_parquet(chave)
        return {
            "data": data_alvo.isoformat(),
            "versao_modelo": str(df["versao_modelo"].iloc[0]),
            "previsoes": [
                {"hora": ts.strftime("%H:%M"), "previsto_mw": float(mw)}
                for ts, mw in zip(df["timestamp"], df["previsto_mw"])
            ],
        }

    return app


def criar_app_padrao() -> FastAPI:
    """App com o armazenamento definido por VOLT_DADOS, para uso local.

    Rodar com: uvicorn volt.api:criar_app_padrao --factory
    """
    return criar_app(abrir_armazenamento())
