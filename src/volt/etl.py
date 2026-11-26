"""ETL: baixa a curva de carga horária do ONS, valida um dia e grava em Parquet."""

import argparse
import io
from collections.abc import Callable
from datetime import date

import pandas as pd
import requests

from volt.armazenamento import Armazenamento, abrir_armazenamento, chave_carga

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


def buscar_ano(ano: int, fetch: Callable[[int], str]) -> str:
    """Baixa o ano; um 404 (ano ainda não publicado) vira DiaInvalidoError."""
    try:
        return fetch(ano)
    except requests.HTTPError as erro:
        if erro.response is not None and erro.response.status_code == 404:
            raise DiaInvalidoError(f"ano {ano} ainda não publicado pelo ONS") from erro
        raise


def rodar_etl(dia: date, dados: Armazenamento, fetch: Callable[[int], str] = baixar_ano) -> str:
    """Busca, valida e grava um dia. Rodar de novo sobrescreve (idempotente)."""
    try:
        texto = buscar_ano(dia.year, fetch)
    except DiaInvalidoError as erro:
        raise DiaInvalidoError(f"{dia}: {erro}") from erro.__cause__
    do_dia = validar_dia(ler_csv_ons(texto), dia)

    return dados.gravar_parquet(do_dia, chave_carga(dia))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ETL de um dia da carga horária do ONS (SE/CO)")
    parser.add_argument("dia", type=date.fromisoformat, help="dia no formato AAAA-MM-DD")
    args = parser.parse_args(argv)
    print(rodar_etl(args.dia, abrir_armazenamento()))


if __name__ == "__main__":
    main()
