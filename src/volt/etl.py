"""ETL: baixa a curva de carga horária do ONS, valida um dia e grava em Parquet."""

import argparse
import io
import os
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pandas as pd
import requests

URL_ONS = "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/curva-carga-ho/CURVA_CARGA_{ano}.csv"


class DiaInvalidoError(ValueError):
    """O dia pedido não tem 24 horas completas e válidas."""


def ler_csv_ons(texto: str, subsistema: str = "SE") -> pd.DataFrame:
    """Converte o CSV do ONS numa tabela (timestamp, carga_mw) de um subsistema."""
    bruto = pd.read_csv(io.StringIO(texto), sep=";")
    df = bruto.loc[bruto["id_subsistema"] == subsistema, ["din_instante", "val_cargaenergiahomwmed"]]
    df = df.rename(columns={"din_instante": "timestamp", "val_cargaenergiahomwmed": "carga_mw"})
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    # valor não numérico vira nulo; validar_dia rejeita só o dia dele
    df["carga_mw"] = pd.to_numeric(df["carga_mw"], errors="coerce").astype(float)
    return df.sort_values("timestamp").reset_index(drop=True)


def validar_dia(df: pd.DataFrame, dia: date) -> pd.DataFrame:
    """Devolve só as linhas do dia, ou levanta DiaInvalidoError."""
    do_dia = df[df["timestamp"].dt.date == dia].reset_index(drop=True)

    if do_dia.empty:
        raise DiaInvalidoError(f"{dia}: dia ainda não publicado pelo ONS")

    horas = do_dia["timestamp"].dt.hour
    if len(do_dia) != 24 or sorted(horas) != list(range(24)):
        faltando = sorted(set(range(24)) - set(horas))
        repetidas = sorted(horas[horas.duplicated()].unique().tolist())
        raise DiaInvalidoError(
            f"{dia}: {len(do_dia)} linhas; horas faltando: {faltando}; horas repetidas: {repetidas}"
        )
    if do_dia["carga_mw"].isna().any():
        raise DiaInvalidoError(f"{dia}: há carga nula")
    if (do_dia["carga_mw"] <= 0).any():
        raise DiaInvalidoError(f"{dia}: há carga menor ou igual a zero")
    return do_dia


def baixar_ano(ano: int) -> str:
    """Baixa o CSV do ano inteiro no portal de dados abertos do ONS."""
    resposta = requests.get(URL_ONS.format(ano=ano), timeout=30)
    resposta.raise_for_status()
    return resposta.text


def caminho_carga(base: Path, dia: date) -> Path:
    return base / "carga_horaria" / f"data={dia}" / "carga.parquet"


def rodar_etl(dia: date, base: Path, fetch: Callable[[int], str] = baixar_ano) -> Path:
    """Busca, valida e grava um dia. Rodar de novo sobrescreve (idempotente)."""
    do_dia = validar_dia(ler_csv_ons(fetch(dia.year)), dia)

    caminho = caminho_carga(base, dia)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    do_dia.to_parquet(temporario, index=False)
    os.replace(temporario, caminho)  # escrita atômica: nunca fica arquivo pela metade
    return caminho


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ETL de um dia da carga horária do ONS (SE/CO)")
    parser.add_argument("dia", type=date.fromisoformat, help="dia no formato AAAA-MM-DD")
    parser.add_argument("--base", type=Path, default=Path("data"), help="pasta de dados")
    args = parser.parse_args(argv)
    print(rodar_etl(args.dia, args.base))


if __name__ == "__main__":
    main()
