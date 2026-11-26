"""ETL: lê a curva de carga horária do ONS e valida um dia."""

import io
from datetime import date

import pandas as pd


class DiaInvalidoError(ValueError):
    """O dia pedido não tem 24 horas completas e válidas."""


def ler_csv_ons(texto: str, subsistema: str = "SE") -> pd.DataFrame:
    """Converte o CSV do ONS numa tabela (timestamp, carga_mw) de um subsistema."""
    bruto = pd.read_csv(io.StringIO(texto), sep=";")
    df = bruto.loc[bruto["id_subsistema"] == subsistema, ["din_instante", "val_cargaenergiahomwmed"]]
    df = df.rename(columns={"din_instante": "timestamp", "val_cargaenergiahomwmed": "carga_mw"})
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["carga_mw"] = df["carga_mw"].astype(float)
    return df.sort_values("timestamp").reset_index(drop=True)


def validar_dia(df: pd.DataFrame, dia: date) -> pd.DataFrame:
    """Devolve só as linhas do dia, ou levanta DiaInvalidoError."""
    do_dia = df[df["timestamp"].dt.date == dia].reset_index(drop=True)

    horas = do_dia["timestamp"].dt.hour
    if len(do_dia) != 24 or sorted(horas) != list(range(24)):
        raise DiaInvalidoError(f"{dia}: esperava as 24 horas, encontrei {len(do_dia)} linhas")
    if do_dia["carga_mw"].isna().any():
        raise DiaInvalidoError(f"{dia}: há carga nula")
    if (do_dia["carga_mw"] <= 0).any():
        raise DiaInvalidoError(f"{dia}: há carga menor ou igual a zero")
    return do_dia
