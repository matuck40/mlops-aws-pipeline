"""Previsão em lote: gera as 24 horas do dia alvo e grava em Parquet."""

import argparse
from datetime import date, timedelta

import pandas as pd

from volt.armazenamento import Armazenamento, abrir_armazenamento, chave_carga, chave_previsao

SEMANA = timedelta(days=7)


def naive_sazonal(dados: Armazenamento, data_alvo: date) -> pd.DataFrame:
    """Prevê cada hora do alvo como a carga da mesma hora 7 dias antes."""
    referencia = data_alvo - SEMANA
    chave = chave_carga(referencia)
    if not dados.existe(chave):
        raise FileNotFoundError(
            f"previsão de {data_alvo}: falta a carga de {referencia} (rode o ETL desse dia)"
        )
    carga = dados.ler_parquet(chave)
    return pd.DataFrame(
        {
            "timestamp": carga["timestamp"] + SEMANA,
            "previsto_mw": carga["carga_mw"],
            "versao_modelo": "naive_sazonal",
        }
    )


def rodar_previsao(data_alvo: date, dados: Armazenamento) -> str:
    """Gera e grava a previsão do dia alvo. Rodar de novo sobrescreve."""
    return dados.gravar_parquet(naive_sazonal(dados, data_alvo), chave_previsao(data_alvo))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Previsão das 24 horas de um dia (naive sazonal)")
    parser.add_argument("data_alvo", type=date.fromisoformat, help="dia a prever, AAAA-MM-DD")
    args = parser.parse_args(argv)
    print(rodar_previsao(args.data_alvo, abrir_armazenamento()))


if __name__ == "__main__":
    main()
