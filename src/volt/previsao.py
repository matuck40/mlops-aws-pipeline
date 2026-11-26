"""Previsão em lote: gera as 24 horas do dia alvo e grava em Parquet."""

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from volt.arquivos import gravar_parquet_atomico
from volt.etl import caminho_carga

SEMANA = timedelta(days=7)


def naive_sazonal(base: Path, data_alvo: date) -> pd.DataFrame:
    """Prevê cada hora do alvo como a carga da mesma hora 7 dias antes."""
    referencia = data_alvo - SEMANA
    caminho = caminho_carga(base, referencia)
    if not caminho.exists():
        raise FileNotFoundError(
            f"previsão de {data_alvo}: falta a carga de {referencia} (rode o ETL desse dia)"
        )
    # partitioning=None: sem isso, o pyarrow 24 cria uma coluna "data" a partir da pasta data=...
    carga = pd.read_parquet(caminho, partitioning=None)
    return pd.DataFrame(
        {
            "timestamp": carga["timestamp"] + SEMANA,
            "previsto_mw": carga["carga_mw"],
            "versao_modelo": "naive_sazonal",
        }
    )


def caminho_previsao(base: Path, data_alvo: date) -> Path:
    return base / "previsoes" / f"data_alvo={data_alvo}" / "previsao.parquet"


def rodar_previsao(data_alvo: date, base: Path) -> Path:
    """Gera e grava a previsão do dia alvo. Rodar de novo sobrescreve."""
    return gravar_parquet_atomico(naive_sazonal(base, data_alvo), caminho_previsao(base, data_alvo))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Previsão das 24 horas de um dia (naive sazonal)")
    parser.add_argument("data_alvo", type=date.fromisoformat, help="dia a prever, AAAA-MM-DD")
    parser.add_argument("--base", type=Path, default=Path("data"), help="pasta de dados")
    args = parser.parse_args(argv)
    print(rodar_previsao(args.data_alvo, args.base))


if __name__ == "__main__":
    main()
