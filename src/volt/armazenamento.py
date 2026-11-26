"""Onde o pipeline guarda e lê seus arquivos.

As etapas só conhecem "chaves" (ex.: carga_horaria/data=2026-11-24/carga.parquet)
e pedem ao armazenamento para ler ou gravar. Assim a mesma etapa roda com uma
pasta local ou, mais tarde, com um bucket do S3.
"""

import os
from datetime import date
from pathlib import Path
from typing import Protocol

import pandas as pd


def chave_carga(dia: date) -> str:
    return f"carga_horaria/data={dia}/carga.parquet"


def chave_previsao(data_alvo: date) -> str:
    return f"previsoes/data_alvo={data_alvo}/previsao.parquet"


class Armazenamento(Protocol):
    """O que toda forma de guardar arquivos precisa saber fazer."""

    def existe(self, chave: str) -> bool: ...

    def ler_parquet(self, chave: str) -> pd.DataFrame: ...

    def gravar_parquet(self, df: pd.DataFrame, chave: str) -> str: ...


class ArmazenamentoLocal:
    """Guarda os arquivos numa pasta do disco."""

    def __init__(self, base: Path):
        self.base = base

    def existe(self, chave: str) -> bool:
        return (self.base / chave).exists()

    def ler_parquet(self, chave: str) -> pd.DataFrame:
        # partitioning=None: sem isso, o pyarrow 24 cria uma coluna a partir da pasta data=...
        return pd.read_parquet(self.base / chave, partitioning=None)

    def gravar_parquet(self, df: pd.DataFrame, chave: str) -> str:
        """Grava num .tmp e renomeia: ou existe o arquivo completo, ou nenhum."""
        caminho = self.base / chave
        caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = caminho.with_suffix(".tmp")
        try:
            df.to_parquet(temporario, index=False)
            os.replace(temporario, caminho)
        finally:
            temporario.unlink(missing_ok=True)  # se falhou no meio, não deixa lixo
        return str(caminho)


def abrir_armazenamento(destino: str | None = None) -> Armazenamento:
    """Usa o destino dado, senão a variável VOLT_DADOS, senão a pasta "data"."""
    destino = destino or os.environ.get("VOLT_DADOS", "data")
    return ArmazenamentoLocal(Path(destino))
