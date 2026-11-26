"""Gravação de arquivos compartilhada pelas etapas do pipeline."""

import os
from pathlib import Path

import pandas as pd


def gravar_parquet_atomico(df: pd.DataFrame, caminho: Path) -> Path:
    """Grava num .tmp e renomeia: ou existe o arquivo completo, ou nenhum."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    try:
        df.to_parquet(temporario, index=False)
        os.replace(temporario, caminho)
    finally:
        temporario.unlink(missing_ok=True)  # se falhou no meio, não deixa lixo
    return caminho
