"""API: só lê previsões já gravadas pelo pipeline; nunca roda o modelo."""

import os
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException

from volt.previsao import caminho_previsao


def criar_app(base: Path, hoje: Callable[[], date] = date.today) -> FastAPI:
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

        caminho = caminho_previsao(base, data_alvo)
        if not caminho.exists():
            raise HTTPException(404, f"previsão de {data_alvo} ainda não gerada")

        # partitioning=None: não criar coluna a partir da pasta data_alvo=...
        df = pd.read_parquet(caminho, partitioning=None)
        return {
            "data": data_alvo.isoformat(),
            "versao_modelo": str(df["versao_modelo"].iloc[0]),
            "previsoes": [
                {"hora": ts.strftime("%H:%M"), "previsto_mw": float(mw)}
                for ts, mw in zip(df["timestamp"], df["previsto_mw"])
            ],
        }

    return app


app = criar_app(Path(os.environ.get("VOLT_DATA_DIR", "data")))
